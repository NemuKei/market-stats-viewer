import hashlib
from pathlib import Path

import pytest

from scripts.upload_release_assets import ReleaseApiError, publish_assets


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FakeReleaseClient:
    """In-memory release that only exposes the id-scoped asset endpoints."""

    def __init__(self, assets: list[dict] | None = None) -> None:
        self.assets = list(assets or [])
        self.next_id = 1000
        self.calls: list[tuple] = []
        self.upload_failures: list[ReleaseApiError] = []
        self.ghost_assets: list[dict] = []

    def list_assets(self, release_id: int) -> list[dict]:
        self.calls.append(("list", release_id))
        listed = [dict(asset) for asset in self.ghost_assets + self.assets]
        self.ghost_assets = []
        return listed

    def delete_asset(self, asset_id: int) -> None:
        self.calls.append(("delete", asset_id))
        if not any(asset["id"] == asset_id for asset in self.assets):
            raise ReleaseApiError(404, "Not Found")
        self.assets = [asset for asset in self.assets if asset["id"] != asset_id]

    def upload_asset(self, release_id: int, path: Path) -> dict:
        self.calls.append(("upload", path.name))
        if self.upload_failures:
            raise self.upload_failures.pop(0)
        data = path.read_bytes()
        self.next_id += 1
        asset = {
            "id": self.next_id,
            "name": path.name,
            "size": len(data),
            "state": "uploaded",
            "digest": _digest(data),
        }
        self.assets.append(asset)
        return dict(asset)


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_replaces_existing_asset_found_via_release_id(tmp_path: Path) -> None:
    path = _write(tmp_path, "lp_events.json", b"new")
    client = FakeReleaseClient(
        [{"id": 1, "name": "lp_events.json", "size": 3, "state": "uploaded", "digest": _digest(b"old")}]
    )

    publish_assets(client, 42, [path], sleep=lambda _: None)

    assert ("delete", 1) in client.calls
    assert [asset["name"] for asset in client.assets] == ["lp_events.json"]
    assert client.assets[0]["digest"] == _digest(b"new")


def test_delete_not_found_is_treated_as_already_removed(tmp_path: Path) -> None:
    path = _write(tmp_path, "events.sqlite", b"db")
    client = FakeReleaseClient()
    # A concurrent publisher already removed id 7, but the listing still shows it.
    client.ghost_assets.append(
        {"id": 7, "name": "events.sqlite", "size": 2, "state": "uploaded", "digest": _digest(b"xx")}
    )
    sleeps: list[float] = []

    publish_assets(client, 42, [path], sleep=sleeps.append)

    assert ("delete", 7) in client.calls
    assert sleeps == []
    assert [asset["name"] for asset in client.assets] == ["events.sqlite"]


def test_retries_upload_conflict_with_backoff(tmp_path: Path) -> None:
    path = _write(tmp_path, "manifest.json", b"{}")
    client = FakeReleaseClient()
    client.upload_failures.extend(
        [ReleaseApiError(422, "already_exists"), ReleaseApiError(502, "Bad Gateway")]
    )
    sleeps: list[float] = []

    publish_assets(client, 42, [path], sleep=sleeps.append)

    assert sleeps == [20, 40]
    assert [call[0] for call in client.calls].count("upload") == 3
    assert [asset["name"] for asset in client.assets] == ["manifest.json"]


def test_gives_up_after_bounded_attempts(tmp_path: Path) -> None:
    path = _write(tmp_path, "manifest.json", b"{}")
    client = FakeReleaseClient()
    client.upload_failures.extend([ReleaseApiError(503, "Unavailable")] * 3)
    sleeps: list[float] = []

    with pytest.raises(ReleaseApiError):
        publish_assets(client, 42, [path], sleep=sleeps.append)

    assert sleeps == [20, 40]


def test_non_retryable_error_fails_immediately(tmp_path: Path) -> None:
    path = _write(tmp_path, "manifest.json", b"{}")
    client = FakeReleaseClient()
    client.upload_failures.append(ReleaseApiError(403, "Forbidden"))
    sleeps: list[float] = []

    with pytest.raises(ReleaseApiError):
        publish_assets(client, 42, [path], sleep=sleeps.append)

    assert sleeps == []


def test_final_verification_rejects_digest_mismatch(tmp_path: Path) -> None:
    path = _write(tmp_path, "lp_events.json", b"new")
    client = FakeReleaseClient()
    original_upload = client.upload_asset

    def corrupting_upload(release_id: int, upload_path: Path) -> dict:
        asset = original_upload(release_id, upload_path)
        client.assets[-1]["digest"] = _digest(b"other")
        return asset

    client.upload_asset = corrupting_upload  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="lp_events.json"):
        publish_assets(client, 42, [path], sleep=lambda _: None)


def test_final_verification_rejects_duplicate_names(tmp_path: Path) -> None:
    path = _write(tmp_path, "lp_events.json", b"new")
    client = FakeReleaseClient()
    original_upload = client.upload_asset

    def duplicating_upload(release_id: int, upload_path: Path) -> dict:
        asset = original_upload(release_id, upload_path)
        client.assets.append(dict(asset, id=asset["id"] + 500))
        return asset

    client.upload_asset = duplicating_upload  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="lp_events.json"):
        publish_assets(client, 42, [path], sleep=lambda _: None)


def test_uploads_in_given_order_so_manifest_goes_last(tmp_path: Path) -> None:
    paths = [
        _write(tmp_path, name, name.encode())
        for name in ("events.sqlite", "event_signals.sqlite", "lp_events.json", "manifest.json")
    ]
    client = FakeReleaseClient()

    publish_assets(client, 42, paths, sleep=lambda _: None)

    uploads = [call[1] for call in client.calls if call[0] == "upload"]
    assert uploads == [path.name for path in paths]
