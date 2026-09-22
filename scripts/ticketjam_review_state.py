"""Persist Codex-reviewed evidence; never infer confirmation from a search hit."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from .build_lp_events import write_lp_events
from .signals.text_quality import text_quality_issue
from .signals.sources.base import JST, compute_signal_uid, trim_snippet
from .signals.sources.venue_web_discovery import CONTENT_EXTRACTORS

STATUSES = {
    "confirmed",
    "insufficient",
    "conflict",
    "fetch_failed",
    "duplicate",
    "ancillary",
}
IDENTITY_FIELDS = (
    "event_date",
    "event_start_time",
    "venue_name",
    "artist_name",
    "title",
)


def fingerprint(candidate: dict) -> str:
    value = {key: candidate.get(key) for key in IDENTITY_FIELDS}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def due_review(candidate: dict, state: dict, today: str) -> bool:
    record = state.get("events", {}).get(candidate["event_key"])
    if not record or record["candidate_fingerprint"] != fingerprint(candidate):
        return True
    return date.fromisoformat(
        record["history"][-1]["next_check_date"]
    ) <= date.fromisoformat(today)


def _validate_confirmed(candidate: dict, event: dict) -> None:
    for key in (
        "event_id",
        "title",
        "artist_name",
        "venue_name",
        "event_start_date",
        "evidence_url",
        "url",
        "evidence_snippet",
        "content_extractor",
    ):
        if not event.get(key) or text_quality_issue(event[key]):
            raise ValueError(f"missing or invalid official evidence: {key}")
    if event.get("source_class") not in {
        "venue_official",
        "artist_official",
        "promoter_official",
        "ticket_official",
    }:
        raise ValueError("unsupported official source class")
    if event["content_extractor"] not in CONTENT_EXTRACTORS:
        raise ValueError("unsupported content extractor")
    for key in ("url", "evidence_url"):
        url = urlparse(event[key])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("official evidence must use a public HTTPS URL")
        if url.hostname == "ticketjam.jp" or url.hostname.endswith(".ticketjam.jp"):
            raise ValueError("secondary market is not official evidence")
    for source, target in [
        ("event_date", "event_start_date"),
        ("venue_name", "venue_name"),
    ]:
        if candidate[source] != event[target]:
            raise ValueError(f"official evidence conflicts with candidate: {source}")
    if candidate.get("event_start_time") and candidate["event_start_time"] != event.get(
        "event_start_time"
    ):
        raise ValueError("official start time conflicts with candidate")
    start = date.fromisoformat(event["event_start_date"])
    end = date.fromisoformat(event.get("event_end_date") or event["event_start_date"])
    if end < start:
        raise ValueError("official end date precedes start")
    if event.get("event_start_time"):
        time.fromisoformat(event["event_start_time"])


def is_pure_suppression(candidate: dict, event: dict) -> bool:
    """A status notice may suppress the old performance, never move or rename it."""
    return (
        candidate.get("event_status", "scheduled") == "scheduled"
        and event.get("event_status") in {"cancelled", "postponed"}
        and candidate.get("event_date") == event.get("event_start_date")
        and (candidate.get("event_end_date") or candidate.get("event_date"))
        == (event.get("event_end_date") or event.get("event_start_date"))
        and all(
            candidate.get(k) == event.get(k)
            for k in ("event_start_time", "venue_name", "artist_name", "title")
        )
    )


def _validate_suppression(candidate: dict, review: dict) -> None:
    event = review.get("official_suppression")
    if (
        not isinstance(event, dict)
        or review.get("status") != "conflict"
        or not is_pure_suppression(candidate, event)
        or review.get("official_values") != {"event_status": event.get("event_status")}
    ):
        raise ValueError("suppression requires a pure status conflict")
    _validate_confirmed(candidate, event)


def matches_official_suppression(row: dict, record: dict) -> bool:
    """Only the exact latest verified status row can pass an origin conflict hold."""
    history = record.get("history", [])
    if not history or "official_suppression" not in history[-1]:
        return False
    review = history[-1]
    candidate = record.get("candidate_snapshot", {})
    if record.get("candidate_fingerprint") != fingerprint(candidate) or review.get(
        "candidate_fingerprint"
    ) != fingerprint(candidate):
        return False
    try:
        _validate_suppression(candidate, review)
    except (ValueError, KeyError, TypeError):
        return False
    event = review["official_suppression"]
    expected = {
        "source_id": "venue_web_discovery",
        "record_id": compute_signal_uid(
            "venue_web_discovery", event["url"], extra_key=event["event_id"]
        ),
        "discovery_event_key": review["event_key"],
        "event_date": event["event_start_date"],
        "event_end_date": event.get("event_end_date") or event["event_start_date"],
        "event_start_time": event.get("event_start_time"),
        "event_status": event["event_status"],
        "title": event["title"],
        "url": event["url"],
        "source_class": event["source_class"],
        "evidence_url": event["evidence_url"],
        "evidence_snippet": trim_snippet(event["evidence_snippet"]),
        "content_extractor": event["content_extractor"],
    }
    return all(row.get(k) == v for k, v in expected.items()) and all(
        (row.get("raw_" + k) or row.get(k)) == event[k]
        for k in ("venue_name", "artist_name")
    )


def apply_reviews(state: dict, candidates: list[dict], decisions: list[dict]) -> dict:
    result = deepcopy(state) if state else {"schema_version": 1, "events": {}}
    if result.get("schema_version") != 1:
        raise ValueError("unsupported review state schema")
    lookup = {row["event_key"]: row for row in candidates}
    if len(lookup) != len(candidates):
        raise ValueError("duplicate candidate keys")
    for decision in decisions:
        key = decision["event_key"]
        if (
            key not in lookup
            or decision["status"] not in STATUSES
            or not decision.get("reason")
        ):
            raise ValueError("unknown candidate, status or missing reason")
        if decision.get("candidate_fingerprint") != fingerprint(lookup[key]):
            raise ValueError("review candidate fingerprint is missing or stale")
        if decision["status"] == "conflict":
            values = decision.get("official_values", {})
            permitted = {
                "event_date",
                "event_start_time",
                "venue_name",
                "artist_name",
                "event_status",
            }
            if (
                isinstance(values, dict)
                and "event_status" in values
                and values["event_status"]
                not in {
                    "scheduled",
                    "cancelled",
                    "postponed",
                }
            ):
                raise ValueError("unsupported official event status")
            if (
                not isinstance(values, dict)
                or not values
                or not set(values) <= permitted
                or not any(
                    bool(value)
                    and (
                        lookup[key].get(
                            field, "scheduled" if field == "event_status" else None
                        )
                        not in value
                        if isinstance(value, list)
                        else value
                        != lookup[key].get(
                            field, "scheduled" if field == "event_status" else None
                        )
                    )
                    for field, value in values.items()
                )
            ):
                raise ValueError("conflict requires a structured disagreement")
        if "official_suppression" in decision:
            _validate_suppression(lookup[key], decision)
        checked = datetime.fromisoformat(
            decision["checked_at_utc"].replace("Z", "+00:00")
        )
        if (
            checked.tzinfo is None
            or checked.utcoffset() != timezone.utc.utcoffset(checked)
            or date.fromisoformat(decision["next_check_date"])
            < checked.astimezone(JST).date()
        ):
            raise ValueError("invalid review timing")
        if decision["status"] == "confirmed":
            _validate_confirmed(lookup[key], decision.get("official_event", {}))
        record = result["events"].setdefault(key, {"history": []})
        if decision in record["history"]:
            continue
        if record["history"] and checked <= datetime.fromisoformat(
            record["history"][-1]["checked_at_utc"].replace("Z", "+00:00")
        ):
            raise ValueError("review history must advance chronologically")
        record["candidate_snapshot"] = deepcopy(lookup[key])
        record["candidate_fingerprint"] = fingerprint(lookup[key])
        record["history"].append(deepcopy(decision))
    return result


def config_fingerprint(event: dict) -> str:
    return hashlib.sha256(
        json.dumps(event, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def validate_config_replacement(
    existing: dict,
    event: dict,
    *,
    origin_key: str | None,
    replaces_fingerprint: str | None,
) -> None:
    """Shared guard for applying or staging a replacement of an official row."""
    if {k: v for k, v in existing.items() if k != "verified_at_utc"} == {
        k: v for k, v in event.items() if k != "verified_at_utc"
    }:
        return
    if (
        not origin_key
        or existing.get("discovery_event_key") != origin_key
        or replaces_fingerprint != config_fingerprint(existing)
    ):
        raise ValueError(f"conflicting existing official event: {event['event_id']}")


def promote_confirmed(config: dict, state: dict) -> dict:
    result = deepcopy(config)
    events = result.setdefault("confirmed_events", [])
    by_id = {event["event_id"]: event for event in events}
    for key, record in sorted(state.get("events", {}).items()):
        review = record["history"][-1]
        if review["status"] != "confirmed":
            continue
        event = deepcopy(review["official_event"])
        event.update(verified_at_utc=review["checked_at_utc"], discovery_event_key=key)
        existing = by_id.get(event["event_id"])
        if existing is not None:
            if {k: v for k, v in existing.items() if k != "verified_at_utc"} != {
                k: v for k, v in event.items() if k != "verified_at_utc"
            }:
                validate_config_replacement(
                    existing,
                    event,
                    origin_key=key,
                    replaces_fingerprint=review.get("replaces_config_fingerprint"),
                )
                existing.clear()
                existing.update(event)
            existing["verified_at_utc"] = event["verified_at_utc"]
            continue
        events.append(event)
        by_id[event["event_id"]] = event
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-output", type=Path)
    args = parser.parse_args()
    if bool(args.config) != bool(args.config_output):
        parser.error("--config and --config-output must be supplied together")
    outputs = [args.state] + ([args.config_output] if args.config_output else [])
    inputs = [args.queue, args.decisions]
    if len({p.resolve() for p in outputs}) != len(outputs) or any(
        p.resolve() in {x.resolve() for x in inputs} for p in outputs
    ):
        parser.error(
            "outputs must be distinct and must not overwrite queue or decisions"
        )
    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    queue = json.loads(args.queue.read_text())
    decisions = json.loads(args.decisions.read_text())
    updated = apply_reviews(
        state, queue["candidates"] + queue.get("official_rechecks", []), decisions
    )
    config = (
        promote_confirmed(json.loads(args.config.read_text()), updated)
        if args.config
        else None
    )
    if config is not None:
        write_lp_events(config, args.config_output)
    write_lp_events(updated, args.state)
    print(
        f"Recorded {len(decisions)} reviews; total {len(updated['events'])} candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
