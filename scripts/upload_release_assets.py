"""Replace GitHub Release assets without trusting the tag-scoped asset listing.

`gh release upload --clobber` finds existing assets through
`GET /repos/{repo}/releases/tags/{tag}`. After another publish replaces the
assets, that endpoint (and the release list) can keep returning deleted asset
ids for several minutes, so the clobber DELETE fails with 404. This script uses
the tag only to resolve the stable release id, then lists, deletes, uploads,
and verifies assets through the id-scoped endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Protocol, Sequence

API_BASE = "https://api.github.com"
UPLOADS_BASE = "https://uploads.github.com"
DEFAULT_BACKOFF_SECONDS = (20, 40)
RETRYABLE_STATUSES = frozenset({422, 500, 502, 503, 504})


class ReleaseApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class ReleaseClient(Protocol):
    def list_assets(self, release_id: int) -> list[dict]: ...

    def delete_asset(self, asset_id: int) -> None: ...

    def upload_asset(self, release_id: int, path: Path) -> dict: ...


class GitHubReleaseClient:
    def __init__(self, repository: str, token: str) -> None:
        self.repository = repository
        self.token = token

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> object:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise ReleaseApiError(exc.code, exc.read().decode("utf-8", "replace")[:500]) from exc
        except urllib.error.URLError as exc:
            # Treat transport failures like a gateway error so they are retried.
            raise ReleaseApiError(502, str(exc.reason)) from exc
        return json.loads(payload) if payload else None

    def release_id(self, tag: str) -> int:
        # The release id is stable across asset replacement, so the tag endpoint
        # is safe here even while its asset list is stale.
        quoted_tag = urllib.parse.quote(tag, safe="")
        release = self._request("GET", f"{API_BASE}/repos/{self.repository}/releases/tags/{quoted_tag}")
        return int(release["id"])  # type: ignore[index]

    def list_assets(self, release_id: int) -> list[dict]:
        assets: list[dict] = []
        page = 1
        while True:
            batch = self._request(
                "GET",
                f"{API_BASE}/repos/{self.repository}/releases/{release_id}/assets?per_page=100&page={page}",
            )
            assets.extend(batch)  # type: ignore[arg-type]
            if len(batch) < 100:  # type: ignore[arg-type]
                return assets
            page += 1

    def delete_asset(self, asset_id: int) -> None:
        self._request("DELETE", f"{API_BASE}/repos/{self.repository}/releases/assets/{asset_id}")

    def upload_asset(self, release_id: int, path: Path) -> dict:
        name = urllib.parse.quote(path.name, safe="")
        return self._request(  # type: ignore[return-value]
            "POST",
            f"{UPLOADS_BASE}/repos/{self.repository}/releases/{release_id}/assets?name={name}",
            body=path.read_bytes(),
            content_type="application/octet-stream",
        )


def _sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _replace_asset(client: ReleaseClient, release_id: int, path: Path) -> None:
    for asset in client.list_assets(release_id):
        if asset.get("name") != path.name:
            continue
        try:
            client.delete_asset(int(asset["id"]))
        except ReleaseApiError as exc:
            # Already gone (for example removed by an earlier publish) is the desired state.
            if exc.status != 404:
                raise
    client.upload_asset(release_id, path)


def _verify_assets(client: ReleaseClient, release_id: int, paths: Sequence[Path]) -> None:
    assets = client.list_assets(release_id)
    problems: list[str] = []
    for path in paths:
        matches = [asset for asset in assets if asset.get("name") == path.name]
        if len(matches) != 1:
            problems.append(f"{path.name}: expected 1 asset, found {len(matches)}")
            continue
        asset = matches[0]
        if asset.get("state") != "uploaded":
            problems.append(f"{path.name}: state={asset.get('state')}")
        if asset.get("size") != path.stat().st_size:
            problems.append(f"{path.name}: size={asset.get('size')} local={path.stat().st_size}")
        digest = asset.get("digest")
        if digest and digest != _sha256_digest(path):
            problems.append(f"{path.name}: digest={digest} local={_sha256_digest(path)}")
    if problems:
        raise RuntimeError("release asset verification failed: " + "; ".join(problems))


def publish_assets(
    client: ReleaseClient,
    release_id: int,
    paths: Sequence[Path],
    *,
    backoff_seconds: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Replace each asset in order, retrying transient conflicts, then verify all."""
    for path in paths:
        for attempt in range(len(backoff_seconds) + 1):
            try:
                _replace_asset(client, release_id, path)
                break
            except ReleaseApiError as exc:
                if exc.status not in RETRYABLE_STATUSES or attempt == len(backoff_seconds):
                    raise
                delay = backoff_seconds[attempt]
                print(f"retrying {path.name} in {delay}s after {exc}")
                sleep(delay)
        print(f"uploaded {path.name}")
    _verify_assets(client, release_id, paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace GitHub Release assets via the release id.")
    parser.add_argument("--tag", required=True, help="Existing release tag.")
    parser.add_argument("paths", nargs="+", type=Path, help="Files to upload, in upload order.")
    args = parser.parse_args()

    repository = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = str(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not repository or not token:
        parser.error("GITHUB_REPOSITORY and GH_TOKEN (or GITHUB_TOKEN) are required")
    missing = [str(path) for path in args.paths if not path.is_file()]
    if missing:
        parser.error(f"missing file(s): {', '.join(missing)}")

    client = GitHubReleaseClient(repository, token)
    release_id = client.release_id(args.tag)
    print(f"release {args.tag} id={release_id}")
    publish_assets(client, release_id, args.paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
