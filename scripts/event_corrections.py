"""Reviewed date/time replacement plans; original DB rows remain untouched."""

from copy import deepcopy
from datetime import date
import hashlib
import json
import re

from .ticketjam_review_state import (
    is_datetime_correction,
    matches_official_correction,
    matches_official_event,
    _validate_confirmed,
)

# Ignore fetch timestamps, but stop if the source's meaning or evidence changed.
RECORD_FIELDS = (
    "source_id",
    "record_id",
    "event_date",
    "event_end_date",
    "event_start_time",
    "event_end_time",
    "event_status",
    "venue_name",
    "artist_name",
    "title",
    "url",
    "source_class",
    "evidence_url",
    "evidence_snippet",
    "pref_name",
    "raw_venue_name",
    "raw_artist_name",
    "event_category",
    "capacity",
    "content_extractor",
    "discovery_event_key",
    "date_time_correction",
)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def record_fingerprint(row):
    return digest({k: row.get(k) for k in RECORD_FIELDS})


def identity(row):
    return row["source_id"], row["record_id"]


def event_values(row):
    return {
        k: row.get(k)
        for k in (
            "event_date",
            "event_start_time",
            "venue_name",
            "artist_name",
            "title",
        )
    } | {
        "event_end_date": row.get("event_end_date") or row["event_date"],
        "event_status": row.get("event_status", "scheduled"),
    }


def prepare_correction(
    proposal, event, receipt, snapshot, published, review_state, base
):
    """Bind a proposal to Work's exact LP and source rows, never to attached claims."""
    from .ticketjam_discovery import build_discovery_bundle, BASELINE_SOURCES
    from .build_lp_events import build_strict_event_groups, merge_supplemental_groups

    if snapshot.get("base_commit") != base or snapshot.get(
        "records_fingerprint"
    ) != digest(snapshot.get("records")):
        raise ValueError("stale correction source snapshot")
    records = snapshot["records"]
    lookup = {identity(r): r for r in records}
    if len(lookup) != len(records):
        raise ValueError("duplicate correction source identities")
    payload = published["payload"]
    actual = build_discovery_bundle(
        records,
        as_of_date=date.fromisoformat(payload["as_of_date"]),
        review_state=review_state,
        include_past=payload.get("history_window_days", 90) is None,
        past_days=payload.get("history_window_days", 90) or 0,
    )[0]
    if actual["events"] != payload["events"]:
        raise ValueError("correction source snapshot does not reproduce current LP")
    targets = [
        r
        for r in payload["events"]
        if event_values(r) == event_values(proposal["current_values"])
    ]
    if len(targets) != 1:
        raise ValueError("correction requires one published old performance")
    target = targets[0]
    if (
        event.get("event_end_time") != target.get("event_end_time")
        or event.get("enabled") is False
    ):
        raise ValueError("correction must preserve end time and remain enabled")
    refs = {
        identity(r)
        for r in target["supporting_sources"]
        if r["source_id"] in BASELINE_SOURCES
    }
    if not refs or not refs <= lookup.keys():
        raise ValueError("missing correction source rows")
    selected = [lookup[k] for k in sorted(refs)]
    if any(r.get("date_time_correction") for r in selected):
        raise ValueError("chained correction requires a new migration review")
    groups, _ = merge_supplemental_groups(
        build_strict_event_groups(
            [r for r in records if r["source_id"] in BASELINE_SOURCES]
        )[0]
    )
    # Unknown-time rows can belong to several performances. Never retire those blindly.
    if any(
        sum(any(identity(m) == ref for m in g["members"]) for g in groups) != 1
        for ref in refs
    ):
        raise ValueError("correction source is shared across performances")
    origin = dict(
        kind=receipt["origin_kind"],
        event_key=proposal["event_key"],
        candidate_fingerprint=proposal["candidate_fingerprint"],
    )
    return dict(
        schema_version=1,
        base_commit=base,
        proposal_hash=digest(proposal),
        input_published_fingerprint=published["lp_fingerprint"],
        input_records_fingerprint=snapshot["records_fingerprint"],
        published_event_key=target["event_key"],
        published_event_fingerprint=digest(target),
        current_values=event_values(target),
        official_event=deepcopy(event),
        origin=origin,
        retired_records=[
            dict(
                source_id=r["source_id"],
                record_id=r["record_id"],
                fingerprint=record_fingerprint(r),
            )
            for r in selected
        ],
    )


def apply_corrections(records, state):
    """Retire exact old rows in memory only; a changed input stops LP generation."""
    notices = [r for r in records if r.get("date_time_correction")]
    if not notices:
        return records
    lookup = {identity(r): r for r in records}
    if len(lookup) != len(records):
        raise ValueError("duplicate correction source identities")
    retired = set()
    for row in notices:
        proof = row["date_time_correction"]
        if (
            not isinstance(proof, dict)
            or proof.get("schema_version") != 1
            or not {"current_values", "official_event", "origin", "retired_records"}
            <= proof.keys()
        ):
            raise ValueError("invalid date/time correction proof")
        old, event, origin = (
            proof["current_values"],
            proof["official_event"],
            proof["origin"],
        )
        if not is_datetime_correction(old, event):
            raise ValueError("only date/time correction is supported")
        _validate_confirmed(
            dict(
                old,
                event_date=event["event_start_date"],
                event_start_time=event.get("event_start_time"),
            ),
            event,
        )
        if not re.fullmatch("[0-9a-f]{40}", proof.get("base_commit", "")) or any(
            not re.fullmatch("[0-9a-f]{64}", proof.get(k, ""))
            for k in (
                "proposal_hash",
                "input_published_fingerprint",
                "input_records_fingerprint",
                "published_event_fingerprint",
            )
        ):
            raise ValueError("missing correction provenance")
        key = (
            origin.get("event_key")
            if origin.get("kind") == "ticketjam_candidate"
            else None
        )
        if origin.get("kind") not in {
            "published_event",
            "ticketjam_candidate",
        } or not matches_official_event(row, event, key):
            raise ValueError("correction row disagrees with approved event")
        if any(row.get(k) != event.get(k) for k in ("event_end_time", "pref_name")):
            raise ValueError("correction row changes approved location or end time")
        if key and not matches_official_correction(
            row, state.get("events", {}).get(key, {})
        ):
            raise ValueError("correction no longer matches the latest candidate review")
        refs = proof.get("retired_records")
        if not isinstance(refs, list) or not refs:
            raise ValueError("correction has no retired source rows")
        seen = set()
        for ref in refs:
            ident = identity(ref)
            if ident in seen or ident in retired or ident == identity(row):
                raise ValueError("overlapping correction source rows")
            if ident[0] not in {
                "official_events",
                "venue_web_discovery",
                "starto_concert",
                "kstyle_music",
            }:
                raise ValueError("invalid retired source")
            if not re.fullmatch("[0-9a-f]{64}", ref.get("fingerprint", "")):
                raise ValueError("invalid retired source fingerprint")
            if ident in lookup and lookup[ident].get("date_time_correction"):
                raise ValueError("chained correction requires a new migration review")
            seen.add(ident)
            if (
                ident in lookup
                and record_fingerprint(lookup[ident]) != ref["fingerprint"]
            ):
                raise ValueError(
                    "correction source changed: reverify before publication"
                )
        retired.update(seen)
    remaining = [r for r in records if identity(r) not in retired]
    # A newly discovered old row with a new ID must not resurrect the old performance.
    for notice in notices:
        old = notice["date_time_correction"]["current_values"]
        for row in remaining:
            if row["source_id"] == "ticketjam_events" or row in notices:
                continue
            if all(
                row.get(k) == old.get(k)
                for k in ("event_date", "venue_name", "artist_name")
            ) and (
                not row.get("event_start_time")
                or not old.get("event_start_time")
                or row["event_start_time"] == old["event_start_time"]
            ):
                raise ValueError(
                    "unreviewed old correction source: reverify before publication"
                )
    return remaining
