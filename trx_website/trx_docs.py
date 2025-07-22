import re
import shutil
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Match, Optional

from git import Repo

from trx_website.settings import (
    GITHUB_ORGANIZATION,
    TRX_DOCS_DIR,
    TRX_GITHUB_REPOSITORY,
)

IGNORED_FILES: list[str] = [
    "tr1/CHANGELOG.md",
    "tr1/IMPROVEMENTS.md",
    "tr1/README.md",
    "tr2/CHANGELOG.md",
    "tr2/IMPROVEMENTS.md",
    "tr2/README.md",
    "SECRETS.md",
    "CONTRIBUTING.md",
]


@dataclass
class Branch:
    name: str
    commit_sha: str


@dataclass
class TRXDoc:
    branch: str
    path: Path
    content: str
    title: str
    parent: Optional["TRXDoc"] = None
    children: list["TRXDoc"] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """
        Return the URL slug for this document, treating README.md as the directory index.
        Includes branch as the first path segment.
        """
        parts = list(self.rel_path.parent.parts)
        if self.path.stem != "README":
            parts.append(self.path.stem)

        parts = [
            (
                match.group(1)
                if (match := re.match(r"\d+-(.*)", part))
                else part
            )
            for part in parts
        ]

        return "/".join(parts).lower()

    def has_child(self, doc: "TRXDoc") -> bool:
        if not self.children:
            return False
        return self.path == doc.path or any(
            child.path == doc.path or child.has_child(doc)
            for child in self.children
        )

    @property
    def rel_slug(self) -> str:
        """Return the slug relative to the branch (dropping the branch prefix)."""
        parts = self.slug.split("/", 1)
        return parts[1] if len(parts) > 1 else ""

    @property
    def rel_path(self) -> Path:
        return self.path.relative_to(TRX_DOCS_DIR)

    @classmethod
    def from_file(cls, md_file: Path, branch: str) -> "TRXDoc":
        text = md_file.read_text(encoding="utf-8")
        metadata, content = cls._parse_frontmatter(text)
        title = metadata.get("title", md_file.stem)
        return cls(
            branch=branch,
            path=md_file,
            content=content,
            title=title,
        )

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                raw_meta = parts[1]
                rest = parts[2]
                metadata: dict[str, Any] = {}
                for line in raw_meta.splitlines():
                    if not line.strip() or ":" not in line:
                        continue
                    key, val = line.split(":", 1)
                    value = val.strip().strip('"').strip("'")
                    metadata[key.strip()] = value
                return metadata, rest.lstrip("\n")
        return {}, text


@contextmanager
def clone_repo(repo_url: str, branch_name: str) -> Iterator[tuple[Path, Repo]]:
    with tempfile.TemporaryDirectory() as tmpdirname:
        cloned_repo_dir = Path(tmpdirname)
        repo = Repo.clone_from(
            repo_url, cloned_repo_dir, branch=branch_name, depth=1
        )
        yield cloned_repo_dir, repo


def copy_md_files(source_dir: Path, target_dir: Path) -> None:
    if not source_dir.exists():
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    for md_file in source_dir.rglob("*.md"):
        # Calculate the relative path to maintain directory structure
        relative_path = md_file.relative_to(source_dir)
        target_file = target_dir / relative_path

        # Skip ignored files
        if str(relative_path) in IGNORED_FILES:
            continue

        # Ensure the target subdirectory exists
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy(md_file, target_file)


def postprocess(doc: TRXDoc, all_docs: list[TRXDoc]) -> None:
    docs_lookup = {doc.path.resolve(): doc for doc in all_docs}

    def process_common_link(match: Match[str]) -> tuple[str, str]:
        text = match.group("text")
        link = match.group("link")
        file_path = (doc.path.parent / link).resolve()
        if linked_doc := docs_lookup.get(file_path):
            link = f"/trx/docs/{linked_doc.slug}"
        elif not link.startswith("https://"):
            print("Warning: unknown link", link, match.group("hash"))
        if link_hash := match.group("hash"):
            link += f'#{link_hash.lstrip("#")}'
        return text, link

    def process_md_link(match: Match[str]) -> str:
        text, link = process_common_link(match)
        return f"[{text}]({link})"

    def process_html_link(match: Match[str]) -> str:
        text, link = process_common_link(match)
        return f'<a href="{link}">{text}</a>'

    doc.content = re.sub(
        r"\[(?P<text>[^\]]*)\]\((?P<link>[^)]*?)(?P<hash>#[^\]]*)?\)",
        process_md_link,
        doc.content,
    )
    doc.content = re.sub(
        r"<a href=[\"'](?P<link>[^\"'#]*?)(?P<hash>#[^\"']*)?[\"']>(?P<text>[^<>]*)<\/a>",
        process_html_link,
        doc.content,
        flags=re.M | re.DOTALL,
    )


def get_trx_doc_branches() -> dict[str, Branch]:
    return {
        dir.name: Branch(
            name=dir.name, commit_sha=(dir / "head.txt").read_text()
        )
        for dir in sorted([p for p in TRX_DOCS_DIR.iterdir() if p.is_dir()])
    }


def get_trx_docs(branch: str) -> dict[str, TRXDoc]:
    """
    Scan the local TRX docs directory for a given branch and build
    a tree of TRXDoc objects, sorted by their path.
    Directories are represented by README.md files.
    """
    branch_dir = TRX_DOCS_DIR / branch
    if not branch_dir.exists():
        return {}

    # collect all docs keyed by their slug path segments tuple
    docs_by_key: dict[str, TRXDoc] = {}
    for md_file in sorted(branch_dir.rglob("*.md")):
        rel = md_file.relative_to(branch_dir)
        if str(rel) in IGNORED_FILES:
            continue
        doc = TRXDoc.from_file(md_file, branch=branch)
        docs_by_key[doc.rel_slug] = doc

    all_docs = list(docs_by_key.values())
    for doc in all_docs:
        postprocess(doc, all_docs)

    return docs_by_key


def make_docs_nav(docs_by_key: dict[str, TRXDoc]) -> list[TRXDoc]:
    # build parent-child relationships
    children_map: dict[str, list[TRXDoc]] = defaultdict(list)
    for key, doc in docs_by_key.items():
        parent_key = "/".join(key.split("/")[:-1])
        children_map[parent_key].append(doc)

    # attach sorted children to each doc
    for key, doc in docs_by_key.items():
        children = children_map.get(key, [])
        doc.children = sorted(children, key=lambda d: d.path)
        for child in children:
            child.parent = doc

    roots = children_map.get("", [])

    # return the root-level docs
    return sorted(roots, key=lambda d: d.path)


def sync_trx_docs() -> None:
    repo_url = (
        f"https://github.com/{GITHUB_ORGANIZATION}/{TRX_GITHUB_REPOSITORY}.git"
    )
    branches = ["develop", "stable"]
    base_target_dir = TRX_DOCS_DIR

    if base_target_dir.exists():
        shutil.rmtree(base_target_dir)
    for branch_name in branches:
        target_dir = base_target_dir / branch_name
        with clone_repo(repo_url, branch_name) as (repo_dir, repo):
            docs_dir = repo_dir / "docs"
            copy_md_files(docs_dir, target_dir)
            (target_dir / "head.txt").write_text(repo.head.commit.hexsha)


if __name__ == "__main__":
    sync_trx_docs()
