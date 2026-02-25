from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RELEASE_TAG = "external-events-latest"
DEFAULT_ASSET_FILENAMES = ("events.sqlite", "event_signals.sqlite")


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _build_manifest(data_dir: Path, release_tag: str) -> dict[str, object]:
    assets: dict[str, dict[str, object]] = {}
    missing: list[str] = []

    for filename in DEFAULT_ASSET_FILENAMES:
        path = data_dir / filename
        if not path.exists():
            missing.append(filename)
            continue
        if not path.is_file():
            missing.append(filename)
            continue
        stat = path.stat()
        assets[filename] = {
            "size_bytes": int(stat.st_size),
            "sha256": _compute_sha256(path),
        }

    if missing:
        raise FileNotFoundError(f"missing required asset(s): {', '.join(missing)}")

    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    repository = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    commit_sha = str(os.environ.get("GITHUB_SHA") or "").strip()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "dataset": "external_events",
        "release_tag": release_tag,
        "generated_at_utc": generated_at_utc,
        "assets": assets,
    }
    if repository:
        manifest["source_repository"] = repository
    if commit_sha:
        manifest["source_commit_sha"] = commit_sha
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build data/manifest.json for external event assets.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Directory containing sqlite assets.")
    parser.add_argument("--output", type=Path, default=Path("data/manifest.json"), help="Output manifest path.")
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG, help="Release tag name used for the assets.")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    output_path = args.output.resolve()
    manifest = _build_manifest(data_dir=data_dir, release_tag=str(args.release_tag).strip() or DEFAULT_RELEASE_TAG)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"manifest written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
