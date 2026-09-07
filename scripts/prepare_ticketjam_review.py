"""Prepare a bounded, evidence-oriented work list for the Codex event reviewer."""

from __future__ import annotations

import argparse
import csv
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlparse

from .build_lp_events import DATA_DIR, load_lp_records, write_lp_events, today_jst
from .ticketjam_discovery import BASELINE_SOURCES, build_discovery_bundle
from .ticketjam_review_state import apply_reviews, fingerprint


def resolve_covered_candidates(
    publication: dict, queue: dict, state: dict, checked_at: str
) -> tuple[dict, list[str]]:
    targets = {row["event_key"]: row for row in publication["events"]}
    decisions = []
    checked_date = datetime.fromisoformat(checked_at.replace("Z", "+00:00")).date()
    for candidate in queue["candidates"]:
        if candidate["status"] in {"expired", "ancillary_ticket"} or not candidate.get(
            "review_due", True
        ):
            continue
        history = (
            state.get("events", {}).get(candidate["event_key"], {}).get("history", [])
        )
        if any(review["status"] == "confirmed" for review in history):
            continue
        if history and history[-1]["status"] in {"conflict", "ancillary"}:
            continue
        target = targets.get(candidate["event_key"])
        if not target or target["display_source_id"] not in BASELINE_SOURCES:
            continue
        if any(
            candidate.get(k) != target.get(k)
            for k in ("event_date", "event_start_time", "venue_name", "artist_name")
        ):
            continue
        decisions.append(
            {
                "event_key": candidate["event_key"],
                "candidate_fingerprint": fingerprint(candidate),
                "status": "duplicate",
                "reason": "取得済み上位sourceの厳密event_key・開催日・会場・出演者・時刻が一致。新しいWeb確認の主張ではなく既存掲載との照合。",
                "checked_at_utc": checked_at,
                "next_check_date": (checked_date + timedelta(days=3)).isoformat(),
                "duplicate_of_event_key": target["event_key"],
                "duplicate_target_fingerprint": fingerprint(target),
                "evidence_url": target.get("evidence_url") or target.get("url"),
                "verification_method": "existing_authoritative_record",
            }
        )
    if not decisions:
        return deepcopy(state), []
    updated = apply_reviews(state, queue["candidates"], decisions)
    return updated, [row["event_key"] for row in decisions]


def prepare_batch(
    queue: dict, *, max_candidates=60, venue_urls: dict | None = None
) -> dict:
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    due = [
        row
        for row in queue["candidates"] + queue.get("official_rechecks", [])
        if row.get("review_due", True) and row.get("status") != "expired"
    ]
    due.sort(
        key=lambda row: (
            row["event_date"],
            -int(row.get("capacity") or 0),
            row["event_key"],
        )
    )
    selected = due[:max_candidates]
    grouped = {}
    for original in selected:
        row = deepcopy(original)
        row["candidate_fingerprint"] = fingerprint(row)
        urls = row.get("verification_urls") or (
            [row["official_url"]] if row.get("official_url") else []
        )
        if not urls and venue_urls and venue_urls.get(row["venue_name"]):
            urls = [venue_urls[row["venue_name"]]]
        group_key = urls[0] if urls else row["venue_name"]
        group = grouped.setdefault(
            group_key,
            {
                "venue_name": row["venue_name"],
                "reference_urls": [],
                "search_queries": [],
                "candidates": [],
            },
        )
        for key, values in [
            ("reference_urls", urls),
            ("search_queries", row.get("search_queries", [])),
        ]:
            for value in values:
                if value not in group[key]:
                    group[key].append(value)
        group["candidates"].append(row)
    return {
        "schema_version": 1,
        "as_of_date": queue["as_of_date"],
        "due_count": len(due),
        "selected_count": len(selected),
        "remaining_due_count": len(due) - len(selected),
        "groups": list(grouped.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state", type=Path, default=DATA_DIR / "ticketjam_review_state.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-candidates", type=int, default=60)
    parser.add_argument(
        "--resolve-covered",
        action="store_true",
        help="Record strict matches against existing authoritative rows.",
    )
    args = parser.parse_args()
    if args.state.resolve() == args.output.resolve():
        parser.error("output must not overwrite review state")
    state = json.loads(args.state.read_text(encoding="utf-8"))
    today = today_jst()
    records = load_lp_records(as_of_date=today)
    publication, queue = build_discovery_bundle(
        records, as_of_date=today, review_state=state
    )
    resolved = []
    if args.resolve_covered:
        now = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        state, resolved = resolve_covered_candidates(publication, queue, state, now)
        publication, queue = build_discovery_bundle(
            records, as_of_date=today, review_state=state
        )
        if resolved:
            write_lp_events(state, args.state)
    with (DATA_DIR / "venue_registry.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        venue_urls = {
            row["venue_name"]: row.get("source_url") or row.get("official_url")
            for row in csv.DictReader(handle)
        }
    rejected = {"ticketjam.jp", "ticket.co.jp", "ticketcircle.jp"}
    venue_urls = {
        name: url
        for name, url in venue_urls.items()
        if url
        and not any(
            (urlparse(url).hostname or "") == domain
            or (urlparse(url).hostname or "").endswith("." + domain)
            for domain in rejected
        )
    }
    plan = prepare_batch(
        queue, max_candidates=args.max_candidates, venue_urls=venue_urls
    )
    plan["resolved_existing_event_keys"] = resolved
    write_lp_events(plan, args.output)
    print(
        f"review plan: {plan['selected_count']} selected / {plan['due_count']} due; {len(resolved)} existing matches resolved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
