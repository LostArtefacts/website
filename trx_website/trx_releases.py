import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from trx_website.settings import (
    GITHUB_ORGANIZATION,
    GITHUB_TOKEN,
    TRX_GITHUB_REPOSITORY,
    TRX_RELEASE_CACHE_PATH,
)


def extract_youtube_id(content: str) -> str | None:
    if match := re.search(
        r"https?://(?:www\.)?youtube\.com/watch\?v=([-\w]+)(?:&\S*)?", content
    ):
        return match.group(1)
    if match := re.search(r"https?://youtu\.be/([-\w]+)(?:\?\S*)?", content):
        return match.group(1)
    return None


def process_release_body(body: str) -> str:
    out_lines: list[str] = []
    for line in body.splitlines():
        if line.rstrip(":") in "### Changes":
            out_lines.append("")
            continue
        if line.rstrip(":") == "### Video preview":
            continue
        if extract_youtube_id(line):
            continue
        if re.search(r"\*\*(Tag|Commit): ", line):
            continue
        if re.search(r"\) - (\d{4})-(\d{2})-(\d{2})$", line):
            continue
        if " · " in line and "Diff" in line and "History" in line:
            continue
        out_lines.append(line)
    result = "\n".join(out_lines)
    result = re.sub(
        r"#(\d+)",
        rf"[#\1](https://github.com/{GITHUB_ORGANIZATION}/{TRX_GITHUB_REPOSITORY}/issues/\1)",
        result,
    )
    return result


@dataclass
class GitHubReleaseAsset:
    name: str
    download_url: str
    updated_at: datetime

    @property
    def platform_suffix(self) -> str:
        if "Windows" in self.name:
            return ".zip"
        if ".dmg" in self.name:
            return ""
        if "Installer" in self.name:
            return "installer"
        if "Linux" in self.name:
            return ""
        return ""

    @property
    def platform(self) -> str:
        if "Windows" in self.name:
            return "windows"
        if ".dmg" in self.name:
            return "mac"
        if "Installer" in self.name:
            return "windows"
        if "Linux" in self.name:
            return "linux"
        return "unknown"


@dataclass
class GitHubRelease:
    name: str
    tag_name: str
    raw_body: str
    created_at: datetime
    published_at: datetime
    prerelease: bool
    assets: list[GitHubReleaseAsset]

    @property
    def body(self) -> str:
        return process_release_body(self.raw_body)

    @property
    def youtube_id(self) -> str | None:
        return extract_youtube_id(self.raw_body)

    @property
    def video_embed_url(self) -> str | None:
        if self.youtube_id is None:
            return None
        return f"https://www.youtube.com/embed/{self.youtube_id}"

    def get_platform_assets(self, platform: str) -> list[GitHubReleaseAsset]:
        return [asset for asset in self.assets if asset.platform == platform]

    @property
    def platforms(self) -> list[str]:
        return sorted(
            set(asset.platform for asset in self.assets), reverse=True
        )


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Type {type(obj).__name__} not serializable")


def get_trx_releases() -> list[GitHubRelease]:
    if not TRX_RELEASE_CACHE_PATH.exists():
        return []

    items = json.loads(TRX_RELEASE_CACHE_PATH.read_text())
    releases: list[GitHubRelease] = []
    for item in items:
        assets = [
            GitHubReleaseAsset(
                name=item["name"],
                download_url=item["browser_download_url"],
                updated_at=datetime.fromisoformat(item["updated_at"]),
            )
            for item in item["assets"]
        ]
        releases.append(
            GitHubRelease(
                name=item["name"],
                tag_name=item["tag_name"],
                raw_body=item["body"],
                published_at=datetime.fromisoformat(item["published_at"]),
                created_at=datetime.fromisoformat(item["created_at"]),
                prerelease=item["prerelease"],
                assets=sorted(
                    assets, key=lambda asset: asset.platform, reverse=True
                ),
            )
        )

    return sorted(
        releases, key=lambda release: release.published_at, reverse=True
    )


def sync_trx_releases() -> None:
    token = GITHUB_TOKEN
    owner = "LostArtefacts"
    repo = "TRX"

    api_url: str | None = (
        f"https://api.github.com/repos/{owner}/{repo}/releases"
    )

    all_releases = []
    while api_url is not None:
        response = requests.get(
            api_url,
            params={"per_page": 100},
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        print(response.status_code)
        response.raise_for_status()

        if match := re.search(
            "<(.*)>.*next", response.headers.get("link") or ""
        ):
            api_url = match.group(1)
        else:
            api_url = None

        all_releases.extend(response.json())

    TRX_RELEASE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRX_RELEASE_CACHE_PATH.write_text(json.dumps(all_releases, indent=4))

    print("All releases in sync.")


if __name__ == "__main__":
    sync_trx_releases()
