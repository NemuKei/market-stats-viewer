"""Validate a publication package using only Python's standard library."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, time
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlparse

from .build_external_events_manifest import DEFAULT_ASSET_FILENAMES
from .events.types import JAPAN_PREFECTURES

DISPLAY_SOURCES = {
    "official_events",
    "venue_web_discovery",
    "starto_concert",
    "kstyle_music",
}


def validate_payload(payload: dict, *, expected_date: str | None = None) -> dict:
    if (
        payload.get("schema_version") != 1
        or payload.get("ticketjam_policy") != "discovery"
    ):
        raise ValueError("publication must use schema v1 and discovery policy")
    date.fromisoformat(payload["as_of_date"])
    if expected_date and payload["as_of_date"] != expected_date:
        raise ValueError("publication as-of date is stale")
    events = payload["events"]
    keys = set()
    sources = Counter()
    for row in events:
        if row["display_source_id"] not in DISPLAY_SOURCES:
            raise ValueError("unapproved publication source")
        if row["display_source_id"] == "venue_web_discovery" and row.get(
            "display_source_class"
        ) not in {
            "venue_official",
            "artist_official",
            "promoter_official",
            "ticket_official",
        }:
            raise ValueError("unapproved official source class")
        for field in ("event_key", "title", "venue_name", "artist_name"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"missing public event field: {field}")
        if row["event_key"] in keys:
            raise ValueError("duplicate public event key")
        keys.add(row["event_key"])
        if row.get("pref_name") not in JAPAN_PREFECTURES:
            raise ValueError(
                f"missing or invalid domestic prefecture: {row['event_key']}"
            )
        event_date = date.fromisoformat(row["event_date"])
        if (
            row.get("event_end_date")
            and date.fromisoformat(row["event_end_date"]) < event_date
        ):
            raise ValueError("invalid event date interval")
        if row.get("event_start_time"):
            time.fromisoformat(row["event_start_time"])
        url = urlparse(row.get("url") or "")
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            raise ValueError("invalid public event URL")
        if url.hostname == "ticketjam.jp" or url.hostname.endswith(".ticketjam.jp"):
            raise ValueError("secondary URL cannot be the public event link")
        sources[row["display_source_id"]] += 1
    summary = payload["summary"]
    if summary["event_count"] != len(events) or summary[
        "counts_by_display_source"
    ] != dict(sources):
        raise ValueError("publication summary does not match rows")
    return {
        "event_count": len(events),
        "counts_by_display_source": dict(sources),
        "as_of_date": payload["as_of_date"],
    }


def validate_package(
    data_dir: Path,
    *,
    manifest_path: Path | None = None,
    expected_date: str | None = None,
    expected_commit: str | None = None,
) -> dict:
    manifest = json.loads(
        (manifest_path or data_dir / "manifest.json").read_text(encoding="utf-8")
    )
    if expected_commit and manifest.get("source_commit_sha") != expected_commit:
        raise ValueError("manifest source commit does not match checkout")
    for filename in DEFAULT_ASSET_FILENAMES:
        path = data_dir / filename
        meta = manifest["assets"][filename]
        if (
            path.stat().st_size != meta["size_bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]
        ):
            raise ValueError(f"manifest mismatch: {filename}")
        if filename.endswith(".sqlite"):
            connection = sqlite3.connect(
                path.resolve().as_uri() + "?immutable=1", uri=True
            )
            try:
                if connection.execute("pragma integrity_check").fetchone()[0] != "ok":
                    raise ValueError(f"database integrity error: {filename}")
            finally:
                connection.close()
    return validate_payload(
        json.loads((data_dir / "lp_events.json").read_text(encoding="utf-8")),
        expected_date=expected_date,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--expected-as-of-date")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    result = validate_package(
        args.data_dir,
        manifest_path=args.manifest,
        expected_date=args.expected_as_of_date,
        expected_commit=args.expected_commit,
    )
    print(json.dumps({"valid": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
