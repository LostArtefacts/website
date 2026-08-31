import re
import shutil
import tempfile
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Match, Optional

from git import Repo
from git.exc import GitCommandError
from markupsafe import Markup, escape

from trx_website.settings import (
    GITHUB_ORGANIZATION,
    TRX_DOCS_DIR,
    TRX_GITHUB_REPOSITORY,
)
from trx_website.templating import slugify
from trx_website.utils import cache_for

CLONE_ATTEMPTS = 3
CLONE_RETRY_DELAY = 5.0

IGNORED_FILES: list[str] = [
    "tr1/CHANGELOG.md",
    "tr1/IMPROVEMENTS.md",
    "tr1/README.md",
    "tr2/CHANGELOG.md",
    "tr2/IMPROVEMENTS.md",
    "tr2/README.md",
    "tr3/CHANGELOG.md",
    "tr3/IMPROVEMENTS.md",
    "tr3/README.md",
    "CHANGELOG.md",
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
    root_dir: Path
    path: Path
    content: str
    title: str
    has_metadata: bool = False
    hidden: bool = False
    order: Optional[int] = None
    has_trx_root: bool = False
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
        """Return the document slug used by the docs router for this layout."""
        parts = self.slug.split("/")
        if len(parts) <= 1:
            return ""
        rel_parts = parts[1:]
        if rel_parts and rel_parts[0] == "trx":
            rel_parts = rel_parts[1:]
        return "/".join(rel_parts)

    @property
    def rel_path(self) -> Path:
        return self.path.relative_to(TRX_DOCS_DIR)

    @classmethod
    def from_file(
        cls,
        md_file: Path,
        branch: str,
        root_dir: Path,
        has_trx_root: bool,
    ) -> "TRXDoc":
        text = md_file.read_text(encoding="utf-8")
        metadata, content = cls._parse_frontmatter(text)
        title = metadata.get("title", md_file.stem)
        raw_order = metadata.get("order")
        order = int(raw_order) if raw_order is not None else None
        return cls(
            branch=branch,
            root_dir=root_dir,
            path=md_file,
            content=content,
            title=title,
            has_metadata=bool(metadata),
            hidden=str(metadata.get("hidden", "")).lower()
            in ("1", "true", "yes"),
            order=order,
            has_trx_root=has_trx_root,
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
        repo = clone_with_retries(repo_url, branch_name, cloned_repo_dir)
        yield cloned_repo_dir, repo


def clone_with_retries(
    repo_url: str, branch_name: str, target_dir: Path
) -> Repo:
    """
    Clone a branch, retrying a few times with a growing pause.

    GitHub occasionally rejects an anonymous clone of a public repo - it
    answers the fetch with a credentials prompt, which git reports as
    "could not read Username". That clears on its own, so a couple of
    retries turn a failed sync into a slow one.
    """
    for attempt in range(1, CLONE_ATTEMPTS + 1):
        try:
            return Repo.clone_from(
                repo_url, target_dir, branch=branch_name, depth=1
            )
        except GitCommandError:
            if attempt == CLONE_ATTEMPTS:
                raise
            # a fresh clone needs an empty directory
            for child in target_dir.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            time.sleep(CLONE_RETRY_DELAY * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


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


# the shipped scripts, in the order they are listed on the section page.
# anything the repo ships that isn't named here is listed after these, under
# its own directory name, so a new game doesn't silently go missing.
LUA_SCRIPT_GROUPS: dict[str, str] = {
    "games/tr1": "Tomb Raider I",
    "games/tr1-ub": "Tomb Raider I - Unfinished Business",
    "games/tr2": "Tomb Raider II",
    "games/tr2-gm": "Tomb Raider II - The Golden Mask",
    "games/tr3": "Tomb Raider III",
    "games/tr3-la": "Tomb Raider III - The Lost Artifact",
    "games/tr4": "Tomb Raider IV",
    "modules": "Shared modules",
}

LUA_SECTION_INTRO = """\
These are the Lua scripts TRX ships with, reproduced here exactly as they are
installed alongside the games. They are the level scripts that drive the
original games' behavior under TRX, so they double as worked examples of the
API: read one next to the level it belongs to and you can see how the hooks
described in the rest of this section are used in practice.

Each script is shown verbatim. To adapt one, copy it into your own project's
`data/scripts` directory and point your game flow at it.
"""


def _fence(content: str) -> str:
    """A code fence long enough to survive whatever backticks are inside."""
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _lua_script_dirs(ship_dir: Path) -> list[tuple[str, str, Path]]:
    """Every directory of shipped scripts, as (key, label, path)."""
    found: dict[str, Path] = {}
    for scripts_dir in sorted(ship_dir.glob("games/*/scripts")):
        found[f"games/{scripts_dir.parent.name}"] = scripts_dir
    if (modules_dir := ship_dir / "modules").is_dir():
        found["modules"] = modules_dir

    known = [
        (key, label, found[key])
        for key, label in LUA_SCRIPT_GROUPS.items()
        if key in found
    ]
    unknown = [
        (key, key.split("/")[-1], path)
        for key, path in sorted(found.items())
        if key not in LUA_SCRIPT_GROUPS
    ]
    return [
        (key, label, path)
        for key, label, path in known + unknown
        if any(path.glob("*.lua"))
    ]


def write_lua_script_docs(
    repo_dir: Path, ship_dir: Path, target_dir: Path
) -> None:
    """Turn the shipped Lua scripts into a docs section.

    The scripts live outside the docs tree in the TRX repository and are not
    markdown, so they are wrapped into generated pages here: one index listing
    every script, and one hidden page per script holding its source. Going
    through the docs tree rather than a route of its own means the branch
    selector, the sidebar, the search and the syntax highlighting all apply to
    them for free.
    """
    groups = _lua_script_dirs(ship_dir)
    if not groups:
        return

    index = [
        "---",
        "title: Shipped scripts",
        "order: 99",
        "---",
        "",
        "## Shipped scripts",
        "",
        LUA_SECTION_INTRO,
    ]

    for key, label, scripts_dir in groups:
        index += ["", f"### {label}", ""]
        for script in sorted(scripts_dir.glob("*.lua")):
            source = script.relative_to(repo_dir)
            content = script.read_text(encoding="utf-8")
            fence = _fence(content)

            page = target_dir / key / f"{script.stem}.md"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                "\n".join(
                    [
                        "---",
                        f"title: {label} - {script.name}",
                        "hidden: true",
                        "---",
                        "",
                        f"## {script.name}",
                        "",
                        f"Shipped with TRX as `{source}`.",
                        "",
                        fence + "lua",
                        content.rstrip("\n"),
                        fence,
                        "",
                        "[Back to the shipped scripts](../"
                        + ("../" if "/" in key else "")
                        + "README.md)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            index.append(f"- [{script.name}]({key}/{script.stem}.md)")

    index.append("")
    (target_dir / "README.md").write_text("\n".join(index), encoding="utf-8")


def get_docs_source_dirs(docs_dir: Path) -> list[Path]:
    source_dirs = [
        docs_dir / dirname for dirname in ("trx", "tr1", "tr2", "tr3")
    ]
    existing_source_dirs = [
        source_dir for source_dir in source_dirs if source_dir.exists()
    ]
    if existing_source_dirs:
        return existing_source_dirs
    return [docs_dir]


def postprocess(doc: TRXDoc, all_docs: list[TRXDoc]) -> None:
    docs_lookup = {doc.path.resolve(): doc for doc in all_docs}

    def process_common_link(match: Match[str]) -> tuple[str, str]:
        text = match.group("text")
        link = match.group("link")
        file_path = (doc.path.parent / link).resolve()
        if not link:
            # an anchor alone points within the page being processed
            pass
        elif linked_doc := docs_lookup.get(file_path):
            link = f"/trx/docs/{linked_doc.branch}/{linked_doc.rel_slug}"
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
        r"\[(?P<text>[^\]]*)\]\((?P<link>[^)#]*?)(?P<hash>#[^)]*)?\)",
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
    if not TRX_DOCS_DIR.exists():
        # nothing has been synced yet
        return {}
    return {
        d.name: Branch(
            name=d.name,
            commit_sha=(
                head_file.read_text().strip()
                if (head_file := d / "head.txt").exists()
                else "unknown"
            ),
        )
        for d in sorted(p for p in TRX_DOCS_DIR.iterdir() if p.is_dir())
    }


@cache_for(duration=600)
def get_trx_docs(branch: str) -> dict[str, TRXDoc]:
    """
    Scan the local TRX docs directory for a given branch and build
    a tree of TRXDoc objects, sorted by their path.
    Directories are represented by README.md files.

    Cached: reading and cross-linking the tree costs a few hundred
    milliseconds, and every docs page needs the whole thing. The webhook
    clears the cache when it pulls new docs.
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
        doc = TRXDoc.from_file(
            md_file,
            branch=branch,
            root_dir=branch_dir,
            has_trx_root=(branch_dir / "trx").exists(),
        )
        docs_by_key[doc.rel_slug] = doc

    all_docs = list(docs_by_key.values())
    for doc in all_docs:
        postprocess(doc, all_docs)

    return docs_by_key


@dataclass
class SearchHit:
    doc: TRXDoc
    score: int
    anchor: str
    snippet: Markup


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$", re.M)

# a heading with markdown in it renders to something whose slug we can't
# predict from the source text, so those hits link to the top of the page
PLAIN_HEADING_RE = re.compile(r"^[\w .,'()/-]+$")

SNIPPET_RADIUS = 90


def _headings(content: str) -> list[tuple[int, str]]:
    """Every heading in the document, as (offset, text)."""
    return [(m.start(), m.group(2)) for m in HEADING_RE.finditer(content)]


def _plain(text: str) -> str:
    """Strip the markup a reader shouldn't see in a one-line snippet."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[`*_#|]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _snippet(content: str, terms: list[str], at: int) -> Markup:
    start = max(0, at - SNIPPET_RADIUS)
    end = min(len(content), at + SNIPPET_RADIUS)
    text = _plain(content[start:end])

    out = escape(text)
    for term in sorted(set(terms), key=len, reverse=True):
        out = Markup(
            re.sub(
                f"({re.escape(escape(term))})",
                r"<mark>\1</mark>",
                str(out),
                flags=re.I,
            )
        )

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return Markup(prefix) + out + Markup(suffix)


def search_docs(docs_by_key: dict[str, TRXDoc], query: str) -> list[SearchHit]:
    """Rank documents against a free-text query.

    A linear scan over the whole corpus: it is under a megabyte and already in
    memory, so this costs well under a millisecond and needs no index. Bodies
    are searched in full, code blocks included - the names people look up, like
    environment variables and Lua functions, only appear there.
    """
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return []

    hits: list[SearchHit] = []
    for doc in docs_by_key.values():
        title = doc.title.lower()
        body = doc.content.lower()
        if not all(term in title or term in body for term in terms):
            continue

        headings = _headings(doc.content)
        heading_text = " ".join(text.lower() for _, text in headings)
        score = sum(
            title.count(term) * 50
            + heading_text.count(term) * 10
            + body.count(term)
            for term in terms
        )

        # anchor and snippet both hang off the first body match
        at = min(
            (pos for term in terms if (pos := body.find(term)) >= 0),
            default=-1,
        )
        anchor = ""
        if at >= 0:
            preceding = [text for pos, text in headings if pos <= at]
            if preceding and PLAIN_HEADING_RE.match(preceding[-1]):
                anchor = slugify(preceding[-1])

        hits.append(
            SearchHit(
                doc=doc,
                score=score,
                anchor=anchor,
                snippet=(
                    _snippet(doc.content, terms, at)
                    if at >= 0
                    else escape(_plain(doc.content[:SNIPPET_RADIUS]))
                ),
            )
        )

    return sorted(hits, key=lambda hit: (-hit.score, hit.doc.title.lower()))


def nav_doc_for(docs_by_key: dict[str, TRXDoc], doc: TRXDoc) -> TRXDoc:
    """Return the sidebar entry a document is read under.

    Hidden documents - the generated pages for the shipped Lua scripts - have
    no entry of their own, so the sidebar highlights the nearest visible
    ancestor instead of losing its place entirely.
    """
    if not doc.hidden:
        return doc
    key = doc.rel_slug
    while key:
        key = "/".join(key.split("/")[:-1])
        parent = docs_by_key.get(key)
        if parent is not None and not parent.hidden:
            return parent
    return doc


def make_docs_nav(docs_by_key: dict[str, TRXDoc]) -> list[TRXDoc]:
    def sort_key(doc: TRXDoc) -> tuple[int, str, str]:
        order = doc.order if doc.order is not None else 999999
        return order, doc.title.lower(), str(doc.path).lower()

    # build parent-child relationships
    children_map: dict[str, list[TRXDoc]] = defaultdict(list)
    for key, doc in docs_by_key.items():
        parent_key = "/".join(key.split("/")[:-1])
        if parent_key == key:
            continue
        children_map[parent_key].append(doc)

    def in_nav(doc: TRXDoc) -> bool:
        return doc.has_metadata and not doc.hidden

    # attach sorted children to each doc
    for key, doc in docs_by_key.items():
        children = [
            child for child in children_map.get(key, []) if in_nav(child)
        ]
        doc.children = sorted(children, key=sort_key)
        for child in children:
            child.parent = doc

    roots = [doc for doc in children_map.get("", []) if in_nav(doc)]

    # return the root-level docs
    return sorted(roots, key=sort_key)


def sync_trx_docs() -> None:
    """
    Rebuild the local docs tree from the TRX repository.

    The new tree is built off to the side and only swapped in once every
    branch has been fetched, so a failing clone leaves the docs that are
    already being served untouched.
    """
    repo_url = (
        f"https://github.com/{GITHUB_ORGANIZATION}/{TRX_GITHUB_REPOSITORY}.git"
    )
    branches = ["develop", "stable"]
    base_target_dir = TRX_DOCS_DIR.parent / f"{TRX_DOCS_DIR.name}.new"

    if base_target_dir.exists():
        shutil.rmtree(base_target_dir)
    for branch_name in branches:
        target_dir = base_target_dir / branch_name
        with clone_repo(repo_url, branch_name) as (repo_dir, repo):
            docs_dir = repo_dir / "docs"
            for source_dir in get_docs_source_dirs(docs_dir):
                copy_md_files(source_dir, target_dir / source_dir.name)
            # only branches that document Lua have a section to hang the
            # shipped scripts off
            if (target_dir / "trx/lua/README.md").exists():
                write_lua_script_docs(
                    repo_dir,
                    repo_dir / "data/trx/ship",
                    target_dir / "trx/lua/scripts",
                )
            (target_dir / "head.txt").write_text(repo.head.commit.hexsha)

    swap_in_docs(base_target_dir, TRX_DOCS_DIR)


def swap_in_docs(new_dir: Path, target_dir: Path) -> None:
    """
    Put a freshly built docs tree in place of the current one.

    Both directories are siblings, so the renames are atomic and the
    window in which no tree is in place is a single syscall wide.
    """
    old_dir = target_dir.parent / f"{target_dir.name}.old"
    if old_dir.exists():
        shutil.rmtree(old_dir)
    if target_dir.exists():
        target_dir.rename(old_dir)
    new_dir.rename(target_dir)
    if old_dir.exists():
        shutil.rmtree(old_dir)


if __name__ == "__main__":
    sync_trx_docs()
