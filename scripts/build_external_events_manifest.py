from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RELEASE_TAG = "external-events-latest"
DEFAULT_ASSET_FILENAMES = ("events.sqlite", "event_signals.sqlite", "lp_events.json")
ALL_DATES_ASSET_FILENAME = "lp_events_all.json"


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _build_manifest(data_dir: Path, release_tag: str, *, include_public_schedule_days: bool = False,
                    expected_public_sha256: str | None = None, expected_baseline_sha256: str | None = None,
                    expected_approval_sha256: str | None = None) -> dict[str, object]:
    assets: dict[str, dict[str, object]] = {}
    missing: list[str] = []

    filenames = DEFAULT_ASSET_FILENAMES + (
        (ALL_DATES_ASSET_FILENAME,) if (data_dir / ALL_DATES_ASSET_FILENAME).is_file() else ()
    )
    if include_public_schedule_days:
        from .build_public_schedule_days import PUBLIC_ASSET_FILENAME, PUBLIC_BASELINE_FILENAME, validate_public_package
        if any(v is None for v in (expected_public_sha256, expected_baseline_sha256, expected_approval_sha256)):
            raise ValueError("public schedule distribution requires all three reviewed pins")
        validate_public_package(data_dir, expected_public_sha256=expected_public_sha256,
            expected_baseline_sha256=expected_baseline_sha256, expected_approval_sha256=expected_approval_sha256)
        filenames += (PUBLIC_ASSET_FILENAME, PUBLIC_BASELINE_FILENAME)
    for filename in filenames:
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
    parser.add_argument("--include-public-schedule-days", action="store_true")
    parser.add_argument("--expected-public-schedule-sha256")
    parser.add_argument("--expected-public-baseline-sha256")
    parser.add_argument("--expected-approval-set-sha256")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    output_path = args.output.resolve()
    manifest = _build_manifest(data_dir=data_dir, release_tag=str(args.release_tag).strip() or DEFAULT_RELEASE_TAG,
        include_public_schedule_days=args.include_public_schedule_days,
        expected_public_sha256=args.expected_public_schedule_sha256, expected_baseline_sha256=args.expected_public_baseline_sha256,
        expected_approval_sha256=args.expected_approval_set_sha256)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"manifest written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
