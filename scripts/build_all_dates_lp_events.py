"""Add a full retained-date asset while keeping the existing 90-day asset intact."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .build_lp_events import build_lp_events, write_lp_events
from .event_identity_registry import DEFAULT_REGISTRY_PATH
from .validate_external_events import validate_payload

ALL_DATES_ASSET = "lp_events_all.json"
ALL_DATES_SCOPE = "all_verified_retained"


def validate_all_dates_payload(payload: dict, recent: dict | None = None, *,
                               allow_internal_identity_records: bool = False) -> dict:
    result = validate_payload(payload)
    if not isinstance(payload.get("identity_registry"), dict):
        raise ValueError("all-dates asset requires a reviewed fixed-ID revision")
    if (not {"history_scope", "include_past", "history_window_days", "history_start_date"} <= payload.keys()
            or payload.get("history_scope") != ALL_DATES_SCOPE
            or payload.get("include_past") is not True
            or payload.get("history_window_days") is not None
            or payload.get("history_start_date") is not None):
        raise ValueError("all-dates asset must have an explicit unbounded retained-date contract")
    if "location_held_records" in payload or ("identity_held_records" in payload and not allow_internal_identity_records):
        raise ValueError("public all-dates asset must not contain private candidate details")
    rows = payload["events"]
    if not rows:
        raise ValueError("all-dates asset must not be empty")
    if payload.get("retained_from_date") != min(row["event_date"] for row in rows):
        raise ValueError("all-dates retained start does not match rows")
    if payload.get("retained_through_date") != max(row.get("event_end_date") or row["event_date"] for row in rows):
        raise ValueError("all-dates retained end does not match rows")
    if recent is not None:
        validate_payload(recent)
        if (payload.get("as_of_date") != recent.get("as_of_date")
                or payload.get("generated_at_utc") != recent.get("generated_at_utc")
                or payload.get("identity_registry") != recent.get("identity_registry")):
            raise ValueError("all-dates source generation or fixed-ID revision differs from recent asset")
        all_rows = {row["event_key"]: row for row in rows}
        if any(all_rows.get(row["event_key"]) != row for row in recent["events"]):
            raise ValueError("all-dates asset changed or lost a current public event")
        cutoff = recent.get("history_start_date")
        if recent.get("history_window_days") != 90 or not isinstance(cutoff, str):
            raise ValueError("recent asset must have its 90-day history contract")
        date.fromisoformat(cutoff)
        recent_ids = {row["event_key"] for row in recent["events"]}
        if any(row["event_key"] not in recent_ids and (row.get("event_end_date") or row["event_date"]) >= cutoff for row in rows):
            raise ValueError("all-dates asset contains an extra event inside the recent window")
    return result


def build_all_dates_payload(recent: dict, **source_paths) -> dict:
    validate_payload(recent)
    if recent.get("history_window_days") != 90 or not recent.get("generated_at_utc"):
        raise ValueError("recent source must retain its 90-day generation contract")
    payload = build_lp_events(include_past=True,
        as_of_date=date.fromisoformat(recent["as_of_date"]), **source_paths)
    # Re-exporting retained rows must not make old source observations look fresh.
    payload["generated_at_utc"] = recent["generated_at_utc"]
    payload["history_scope"] = ALL_DATES_SCOPE
    if not payload["events"]:
        raise ValueError("all-dates asset has no verified retained events")
    payload["retained_from_date"] = min(row["event_date"] for row in payload["events"])
    payload["retained_through_date"] = max(row.get("event_end_date") or row["event_date"] for row in payload["events"])
    # Candidate details stay private. Counts explain exclusions without publishing records.
    payload.pop("location_held_records", None)
    # write_lp_events requires internal identity candidates for its protected write;
    # it strips them from the published bytes. Public validation never allows them.
    validate_all_dates_payload(payload, recent, allow_internal_identity_records=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--identity-registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.data_dir.resolve()
    recent = json.loads((root / "lp_events.json").read_text(encoding="utf-8"))
    payload = build_all_dates_payload(recent, events_db_path=root / "events.sqlite",
        event_signals_db_path=root / "event_signals.sqlite", identity_registry_path=args.identity_registry)
    output = args.output or root / ALL_DATES_ASSET
    write_lp_events(payload, output, identity_registry_path=args.identity_registry)
    print(f"all-dates verified retained events: {len(payload['events'])}; source generation preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
