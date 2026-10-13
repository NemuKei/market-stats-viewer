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
    if payload.get("schema_version") != 1:
        raise ValueError("publication must use schema v1")
    if "ticketjam_events" in payload.get("source_priority", []):
        raise ValueError("ticketjam must not be a publication source")
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
    if "identity_registry" in payload:
        from .event_identity_registry import validate_observation

        registry = payload["identity_registry"]
        if (not isinstance(registry, dict) or set(registry) != {"schema_version", "revision", "sha256"}
                or type(registry.get("schema_version")) is not int or registry["schema_version"] not in {1, 2}
                or type(registry.get("revision")) is not int or registry["revision"] < 1
                or not isinstance(registry.get("sha256"), str) or len(registry["sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in registry["sha256"])):
            raise ValueError("invalid identity registry metadata")
        held = payload.get("identity_held_records")
        if (type(summary.get("identity_held_record_count")) is not int or summary["identity_held_record_count"] < 0
                or "identity_held_records" in payload and (not isinstance(held, list)
                or summary["identity_held_record_count"] != len(held))):
            raise ValueError("identity held summary mismatch")
        for candidate in held or []:
            if (not isinstance(candidate, dict) or set(candidate) != {"candidate_key", "identity", "source_records", "fingerprint", "reason", "related_event_uids"}
                    or candidate["reason"] not in {"superseded_observation", "changed_or_unbound_observation", "unregistered_candidate", "multiple_candidates_for_fixed_id"}
                    or not isinstance(candidate["related_event_uids"], list)
                    or any(not isinstance(uid, str) or not uid for uid in candidate["related_event_uids"])):
                raise ValueError("invalid identity held candidate")
            validate_observation({key: candidate[key] for key in ["candidate_key", "identity", "source_records", "fingerprint"]})
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
    require_all_dates: bool = False,
    require_public_schedule_days: bool = False,
    expected_public_sha256: str | None = None,
    expected_baseline_sha256: str | None = None,
    expected_approval_sha256: str | None = None,
) -> dict:
    manifest = json.loads(
        (manifest_path or data_dir / "manifest.json").read_text(encoding="utf-8")
    )
    if expected_commit and manifest.get("source_commit_sha") != expected_commit:
        raise ValueError("manifest source commit does not match checkout")
    from .build_external_events_manifest import ALL_DATES_ASSET_FILENAME
    has_all_dates = ALL_DATES_ASSET_FILENAME in manifest.get("assets", {})
    if require_all_dates and not has_all_dates:
        raise ValueError("all-dates asset is missing from manifest")
    filenames = DEFAULT_ASSET_FILENAMES + ((ALL_DATES_ASSET_FILENAME,) if has_all_dates else ())
    from .build_public_schedule_days import PUBLIC_ASSET_FILENAME, PUBLIC_BASELINE_FILENAME, validate_public_package
    public_names = {PUBLIC_ASSET_FILENAME, PUBLIC_BASELINE_FILENAME}
    present = public_names & set(manifest.get("assets", {}))
    if present and present != public_names or require_public_schedule_days and present != public_names:
        raise ValueError("public schedule asset/baseline pair is missing from manifest")
    if require_public_schedule_days and any(v is None for v in (expected_public_sha256, expected_baseline_sha256, expected_approval_sha256)):
        raise ValueError("public schedule validation requires all three reviewed pins")
    if present:
        filenames += (PUBLIC_ASSET_FILENAME, PUBLIC_BASELINE_FILENAME)
    for filename in filenames:
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
    recent = json.loads((data_dir / "lp_events.json").read_text(encoding="utf-8"))
    result = validate_payload(recent, expected_date=expected_date)
    if has_all_dates:
        from .build_all_dates_lp_events import validate_all_dates_payload
        validate_all_dates_payload(json.loads((data_dir / ALL_DATES_ASSET_FILENAME).read_text(encoding="utf-8")), recent)
    if present:
        result.update(validate_public_package(data_dir, expected_public_sha256=expected_public_sha256,
            expected_baseline_sha256=expected_baseline_sha256, expected_approval_sha256=expected_approval_sha256))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--expected-as-of-date")
    parser.add_argument("--expected-commit")
    parser.add_argument("--require-all-dates", action="store_true")
    parser.add_argument("--require-public-schedule-days", action="store_true")
    parser.add_argument("--expected-public-schedule-sha256")
    parser.add_argument("--expected-public-baseline-sha256")
    parser.add_argument("--expected-approval-set-sha256")
    parser.add_argument(
        "--lp-events",
        type=Path,
        help="Validate only this LP events JSON (no manifest); used before data pushes.",
    )
    args = parser.parse_args(argv)
    if args.lp_events:
        result = validate_payload(
            json.loads(args.lp_events.read_text(encoding="utf-8")),
            expected_date=args.expected_as_of_date,
        )
        print(json.dumps({"valid": True, **result}, ensure_ascii=False))
        return 0
    result = validate_package(
        args.data_dir,
        manifest_path=args.manifest,
        expected_date=args.expected_as_of_date,
        expected_commit=args.expected_commit,
        require_all_dates=args.require_all_dates,
        require_public_schedule_days=args.require_public_schedule_days,
        expected_public_sha256=args.expected_public_schedule_sha256,
        expected_baseline_sha256=args.expected_public_baseline_sha256,
        expected_approval_sha256=args.expected_approval_set_sha256,
    )
    print(json.dumps({"valid": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
