"""Prepare secondary-market leads for official verification without promoting them."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re
import unicodedata
from typing import Any

BASELINE_SOURCES = {
    "official_events",
    "venue_web_discovery",
    "starto_concert",
    "kstyle_music",
}
ANCILLARY_PATTERN = re.compile(r"駐車[場券]|駐車券|駐車場|シャトルバス券|グッズ引換券")


def _name(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold())


def _artist_hint(left: str, right: str) -> bool:
    """Reading suffixes suggest review, never authorize a merge."""
    a, b = _name(left), _name(right)
    if not a or not b:
        return False
    return a == b or re.sub(r"\([^()]*\)$", "", a) == re.sub(r"\([^()]*\)$", "", b)


def build_review_queue(
    payload: dict[str, Any], review_state: dict | None = None
) -> dict[str, Any]:
    from .ticketjam_review_state import due_review, fingerprint

    reference_date = payload["as_of_date"]
    state = review_state or {"schema_version": 1, "events": {}}
    if state.get("schema_version") != 1:
        raise ValueError("unsupported review state schema")
    trusted = [
        row for row in payload["events"] if row["display_source_id"] in BASELINE_SOURCES
    ]
    targets = {row["event_key"]: row for row in trusted}
    baseline = {}
    for row in trusted:
        baseline.setdefault((row["event_date"], row["venue_name"]), []).append(row)
    candidates = []
    for row in payload["events"]:
        if row["display_source_id"] != "ticketjam_events":
            continue
        matches = []
        for other in baseline.get((row["event_date"], row["venue_name"]), []):
            time, other_time = (
                row.get("event_start_time"),
                other.get("event_start_time"),
            )
            if time and other_time and time != other_time:
                continue
            if _artist_hint(
                row.get("artist_name") or "", other.get("artist_name") or ""
            ):
                matches.append(other["event_key"])
        text = (row.get("title") or "") + " " + (row.get("artist_name") or "")
        expired = (row.get("event_end_date") or row["event_date"]) < reference_date
        status = (
            "expired"
            if expired
            else "ancillary_ticket"
            if ANCILLARY_PATTERN.search(text)
            else "possible_existing_match"
            if matches
            else "pending_official"
        )
        candidate = {
            key: row.get(key)
            for key in (
                "event_key",
                "event_date",
                "event_end_date",
                "event_start_time",
                "venue_name",
                "artist_name",
                "title",
                "pref_name",
                "capacity",
            )
        }
        query = f"{row.get('artist_name', '')} {row['venue_name']} {row['event_date']}"
        candidate.update(
            status=status,
            official_confirmed=False,
            discovery_url=row.get("evidence_url") or row.get("url"),
            matching_event_keys=sorted(matches),
            search_queries=[query + " 公式", query + " 主催"]
            if status == "pending_official"
            else [],
            verification_urls=[],
        )
        record = state.get("events", {}).get(row["event_key"])
        due = not expired and due_review(candidate, state, reference_date)
        if record:
            previous = record["history"][-1]
            candidate["previous_review"] = {
                key: previous[key]
                for key in ("status", "checked_at_utc", "next_check_date")
            }
            confirmed = next(
                (r for r in reversed(record["history"]) if r["status"] == "confirmed"),
                None,
            )
            if confirmed:
                candidate["verification_urls"].append(
                    confirmed["official_event"]["evidence_url"]
                )
            if (
                previous["status"] == "conflict"
                and previous.get("evidence_url")
                and previous["evidence_url"] not in candidate["verification_urls"]
            ):
                candidate["verification_urls"].append(previous["evidence_url"])
            if previous["status"] == "duplicate":
                target = targets.get(previous.get("duplicate_of_event_key"))
                due = due or (
                    not expired
                    and (
                        not target
                        or fingerprint(target)
                        != previous.get("duplicate_target_fingerprint")
                    )
                )
        for key in matches:
            url = targets[key].get("evidence_url") or targets[key].get("url")
            if url and url not in candidate["verification_urls"]:
                candidate["verification_urls"].append(url)
        candidate["review_due"] = due
        if not due:
            candidate["search_queries"] = []
        candidates.append(candidate)
    candidates.sort(key=lambda row: (row["event_date"], row["event_key"]))
    official_rechecks = []
    queued = {row["event_key"] for row in candidates}
    for key, record in sorted(state.get("events", {}).items()):
        confirmed = next(
            (r for r in reversed(record["history"]) if r["status"] == "confirmed"), None
        )
        if key in queued or not confirmed:
            continue
        row = targets.get(key) or record.get("candidate_snapshot")
        if not row:
            continue
        item = {
            field: row.get(field)
            for field in (
                "event_key",
                "event_date",
                "event_end_date",
                "event_start_time",
                "venue_name",
                "artist_name",
                "title",
                "pref_name",
                "capacity",
            )
        }
        expired = (item.get("event_end_date") or item["event_date"]) < reference_date
        item["review_due"] = not expired and due_review(item, state, reference_date)
        item["status"] = "expired" if expired else "official_recheck"
        item["official_url"] = confirmed["official_event"]["evidence_url"]
        item["verification_urls"] = [item["official_url"]]
        item["previous_review"] = {
            field: record["history"][-1][field]
            for field in ("status", "checked_at_utc", "next_check_date")
        }
        official_rechecks.append(item)
    return {
        "schema_version": 1,
        "as_of_date": reference_date,
        "source_generated_at_utc": payload.get("generated_at_utc"),
        "summary": {
            "candidate_count": len(candidates),
            "counts_by_status": dict(
                sorted(Counter(row["status"] for row in candidates).items())
            ),
            "due_count": sum(r["review_due"] for r in candidates + official_rechecks),
        },
        "candidates": candidates,
        "official_rechecks": official_rechecks,
    }


def apply_discovery_policy(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    result["events"] = [
        row
        for row in result["events"]
        if row["display_source_id"] != "ticketjam_events"
    ]
    result["ticketjam_policy"] = "discovery"
    result["summary"]["ticketjam_withheld_event_count"] = len(payload["events"]) - len(
        result["events"]
    )
    result["summary"]["event_count"] = len(result["events"])
    result["summary"]["counts_by_display_source"] = dict(
        sorted(Counter(row["display_source_id"] for row in result["events"]).items())
    )
    return result


def apply_reviewed_policy(
    payload: dict[str, Any], review_state: dict
) -> dict[str, Any]:
    """Withhold reviewed rows only while their identity and duplicate target agree."""
    from .ticketjam_review_state import fingerprint

    if review_state.get("schema_version") != 1:
        raise ValueError("unsupported review state schema")
    result = deepcopy(payload)
    by_key = {row["event_key"]: row for row in result["events"]}
    withheld = []
    ignored = []
    for row in result["events"]:
        if row["display_source_id"] != "ticketjam_events":
            continue
        record = review_state.get("events", {}).get(row["event_key"])
        if not record:
            continue
        review = record["history"][-1]
        if review["status"] not in {"duplicate", "conflict", "ancillary"}:
            continue
        if record["candidate_fingerprint"] != fingerprint(row):
            ignored.append(
                {"event_key": row["event_key"], "reason": "candidate_changed"}
            )
            continue
        if review["status"] == "duplicate":
            target = by_key.get(review.get("duplicate_of_event_key"))
            if (
                not target
                or target["display_source_id"] not in BASELINE_SOURCES
                or fingerprint(target) != review.get("duplicate_target_fingerprint")
                or any(
                    row.get(k) != target.get(k)
                    for k in ("event_date", "venue_name", "event_start_time")
                )
            ):
                ignored.append(
                    {
                        "event_key": row["event_key"],
                        "reason": "duplicate_target_changed_or_missing",
                    }
                )
                continue
            sources = target.setdefault("supporting_sources", [])
            known = {(r.get("source_id"), r.get("record_id")) for r in sources}
            for evidence in row.get("supporting_sources", []):
                key = (evidence.get("source_id"), evidence.get("record_id"))
                if key not in known:
                    sources.append(deepcopy(evidence))
                    known.add(key)
        withheld.append(
            {
                "event_key": row["event_key"],
                "status": review["status"],
                "reason": review["reason"],
                "checked_at_utc": review.get("checked_at_utc"),
            }
        )
    keys = {r["event_key"] for r in withheld}
    result["events"] = [row for row in result["events"] if row["event_key"] not in keys]
    result["ticketjam_policy"] = "reviewed"
    result["ticketjam_reviewed_withheld"] = sorted(
        withheld, key=lambda r: r["event_key"]
    )
    result["ticketjam_ignored_reviews"] = sorted(ignored, key=lambda r: r["event_key"])
    result["summary"]["ticketjam_reviewed_withheld_event_count"] = len(withheld)
    result["summary"]["event_count"] = len(result["events"])
    result["summary"]["counts_by_display_source"] = dict(
        sorted(Counter(row["display_source_id"] for row in result["events"]).items())
    )
    return result


def build_discovery_bundle(
    records: list[dict[str, Any]],
    *,
    as_of_date=None,
    review_state: dict | None = None,
    include_past=False,
    past_days=90,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep discovery records out of authoritative grouping and displayed values."""
    from .build_lp_events import assemble_lp_payload
    from .ticketjam_review_state import fingerprint

    state = review_state or {"schema_version": 1, "events": {}}
    if state.get("schema_version") != 1:
        raise ValueError("unsupported review state schema")
    from .signals.entity_aliases import load_venue_prefecture_map
    from .events.types import JAPAN_PREFECTURES

    venue_prefectures = load_venue_prefecture_map()
    location_held = []
    ticketjam = [row for row in records if row["source_id"] == "ticketjam_events"]
    trusted = []
    held = []
    for row in records:
        if row["source_id"] not in BASELINE_SOURCES:
            continue
        origin = row.get("discovery_event_key")
        review = state["events"].get(origin, {}).get("history", [])
        if (
            row["source_id"] == "venue_web_discovery"
            and review
            and review[-1]["status"] in {"conflict", "ancillary"}
        ):
            held.append(
                {
                    "record_id": row["record_id"],
                    "discovery_event_key": origin,
                    "reason": review[-1]["status"],
                }
            )
        else:
            from .signals.sources.venue_web_discovery import ACCEPTED_SOURCE_CLASSES

            if row["source_id"] == "venue_web_discovery" and (
                row.get("source_class") not in ACCEPTED_SOURCE_CLASSES
                or not row.get("evidence_url")
                or not row.get("evidence_snippet")
            ):
                raise ValueError(
                    "unverified venue_web_discovery record cannot be published"
                )
            row = dict(row)
            known_pref = venue_prefectures.get(row["venue_name"])
            if known_pref and row.get("pref_name") and row["pref_name"] != known_pref:
                location_held.append(
                    {
                        "source_id": row["source_id"],
                        "record_id": row["record_id"],
                        "reason": "venue_prefecture_conflict",
                    }
                )
                continue
            row["pref_name"] = row.get("pref_name") or known_pref
            if row["pref_name"] not in JAPAN_PREFECTURES:
                location_held.append(
                    {
                        "source_id": row["source_id"],
                        "record_id": row["record_id"],
                        "reason": "unresolved_domestic_location",
                    }
                )
                continue
            trusted.append(row)
    kwargs = dict(as_of_date=as_of_date, include_past=include_past, past_days=past_days)
    published = assemble_lp_payload(trusted, **kwargs)
    leads = assemble_lp_payload(ticketjam, **kwargs)
    queue_input = {**published, "events": published["events"] + leads["events"]}
    queue = build_review_queue(queue_input, state)
    targets = {row["event_key"]: row for row in published["events"]}
    attached = 0
    for candidate in leads["events"]:
        record = state["events"].get(candidate["event_key"])
        if not record or record.get("candidate_fingerprint") != fingerprint(candidate):
            continue
        review = record["history"][-1]
        target_key = (
            review.get("duplicate_of_event_key")
            if review["status"] == "duplicate"
            else candidate["event_key"]
        )
        target = targets.get(target_key)
        if review["status"] not in {"duplicate", "confirmed"} or not target:
            continue
        if any(
            candidate.get(k) != target.get(k)
            for k in ("event_date", "venue_name", "event_start_time")
        ):
            continue
        if review["status"] == "duplicate" and fingerprint(target) != review.get(
            "duplicate_target_fingerprint"
        ):
            continue
        sources = target["supporting_sources"]
        existing = {(r.get("source_id"), r.get("record_id")) for r in sources}
        for source in candidate["supporting_sources"]:
            identity = (source.get("source_id"), source.get("record_id"))
            if identity not in existing:
                sources.append(deepcopy(source))
                existing.add(identity)
                attached += 1
    published["location_held_records"] = location_held
    published["summary"]["location_held_record_count"] = len(location_held)
    published["ticketjam_policy"] = "discovery"
    published["source_priority"] = [
        s for s in published["source_priority"] if s != "ticketjam_events"
    ]
    published["discovery_source_ids"] = ["ticketjam_events"]
    published["ticketjam_promoted_held_records"] = held
    published["summary"]["ticketjam_discovery_record_count"] = len(ticketjam)
    published["summary"]["ticketjam_review_candidate_count"] = len(queue["candidates"])
    published["summary"]["ticketjam_verified_support_count"] = attached
    published["summary"]["ticketjam_promoted_held_record_count"] = len(held)
    return published, queue
