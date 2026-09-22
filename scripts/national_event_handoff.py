"""Offline Chat -> Work intake. Prints proposals/receipts; never writes runtime data.

Input is data, never code or instructions. Successful intake is NOT verification,
publication approval, a scheduled Chat run, or a running Work Cloud trigger.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .audit_national_event_coverage import PREFECTURES, _csv_bytes, _normal, audit
from .signals.sources.base import JST
from .signals.entity_aliases import _build_lookup_maps, normalize_venue_with_lookup
from .ticketjam_review_state import (
    _validate_confirmed,
    apply_reviews,
    fingerprint,
    is_pure_suppression,
    is_datetime_correction,
    promote_confirmed,
    validate_config_replacement,
)

STREAMS = {"venue_official", "announcement", "ticketjam"}
OFFICIAL = {"venue_official", "artist_official", "promoter_official", "ticket_official"}
SOURCE_CLASSES = OFFICIAL | {"news", "official_social", "social", "secondary_market"}
FIELDS = {
    "schema_version",
    "stream",
    "scope_revision",
    "base_commit",
    "venue_id",
    "event_key",
    "candidate_fingerprint",
    "change_type",
    "current_values",
    "proposed_values",
    "source_class",
    "discovery_url",
    "evidence_url",
    "evidence_summary",
    "published_at_utc",
    "observed_at_utc",
    "retrieval_method",
    "evidence_status",
    "unresolved_fields",
    "next_check_date",
}
VALUE_FIELDS = {
    "event_date",
    "event_end_date",
    "event_start_time",
    "venue_name",
    "artist_name",
    "title",
    "event_status",
}
MAX_INPUT_BYTES = 256 * 1024


def validate_submission_paths(files: list[dict]) -> None:
    """Use GitHub's changed-file metadata, never filenames claimed by a proposal."""
    if not files:
        raise ValueError("empty submission")
    for entry in files:
        path = entry.get("path", "")
        if (
            not re.fullmatch(r"docs/ai/event-proposals/[a-zA-Z0-9_-]+\.json", path)
            or entry.get("mode") != "100644"
            or entry.get("status") not in {"added", "modified"}
        ):
            raise ValueError(
                "proposal PR must contain only regular proposal JSON files"
            )


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def published_snapshot(payload: dict, *, base_commit: str) -> dict:
    """Wrap Work's trusted LP input, not an attachment asserted by a submitter."""
    return {
        "base_commit": base_commit,
        "lp_fingerprint": digest(payload),
        "payload": deepcopy(payload),
    }


def _published_rows(published: dict | None, base_commit: str) -> list[dict]:
    if published is None:
        raise ValueError("current published snapshot required for import preview")
    payload = published.get("payload", {})
    if (
        published.get("base_commit") != base_commit
        or published.get("lp_fingerprint") != digest(payload)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("events"), list)
    ):
        raise ValueError("stale published snapshot")
    rows = payload["events"]
    if any(not isinstance(r, dict) or not r.get("event_key") for r in rows):
        raise ValueError("invalid published event")
    if len({r["event_key"] for r in rows}) != len(rows):
        raise ValueError("duplicate published event keys")
    return rows


def _event_values(row: dict) -> dict:
    return {
        **{k: row.get(k) for k in VALUE_FIELDS},
        "event_end_date": row.get("event_end_date") or row.get("event_date"),
        "event_status": row.get("event_status", "scheduled"),
    }


def _utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("UTC timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("UTC timestamp required")
    return parsed


def _url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("public HTTPS URL required")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("public HTTPS URL required")
    return url.hostname.lower()


def load_json(path: Path):
    # Check before reading; duplicate keys must not override earlier evidence.
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("proposal input exceeds 256 KiB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def scope_bundle(
    registry: list[dict],
    config: dict,
    tickets: list[dict],
    aliases: list[dict],
    *,
    candidates: list[dict] | None = None,
    state: dict | None = None,
) -> dict:
    """Derive ALL registered venues; enabled/capacity never reduce discovery scope."""
    report = audit(registry, config, tickets)
    alias_map = {
        r["venue_id"]: json.loads(r.get("aliases_json") or "[]")
        for r in aliases
        if r.get("is_enabled", "1") == "1"
    }
    names: dict[str, set[str]] = {}
    for row in registry:
        for name in [row["venue_name"], *alias_map.get(row["venue_id"], [])]:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("invalid venue alias")
            names.setdefault(_normal(name), set()).add(row["venue_id"])
    alias_conflicts = [
        {"alias": key, "venue_ids": sorted(ids)}
        for key, ids in names.items()
        if len(ids) > 1
    ]
    saved_urls: dict[str, set[str]] = {}
    for event in config.get("confirmed_events", []):
        ids = names.get(_normal(event.get("venue_name") or ""), set())
        if (
            len(ids) == 1
            and event.get("source_class") in OFFICIAL
            and event.get("evidence_url")
        ):
            saved_urls.setdefault(next(iter(ids)), set()).add(event["evidence_url"])
    state = state or {"runs": {}, "last_success": {}, "proposals": {}}
    # Queue is a review input, not another runtime venue master.
    candidates = candidates or []
    revision = digest(
        {
            "registry": registry,
            "aliases": aliases,
            "watches": config["watch_venues"],
            "tickets": tickets,
            "candidates": candidates,
        }
    )
    scopes = []
    for i, pref in enumerate(PREFECTURES, 1):
        code = f"{i:02d}"
        venues = []
        for row in registry:
            if row["pref_code"] != code:
                continue
            venues.append(
                {
                    "venue_id": row["venue_id"],
                    "venue_name": row["venue_name"],
                    "aliases": alias_map.get(row["venue_id"], []),
                    "official_url": row["official_url"],
                    "schedule_url": row.get("source_url"),
                    "official_fetch_enabled": row["is_enabled"] == "1",
                    "scope_review": "pending",
                    "fetch_status": "unvisited",
                    "saved_official_urls": sorted(
                        saved_urls.get(row["venue_id"], set())
                    ),
                    "last_success_by_stream": {
                        stream: state["last_success"].get(
                            f"{stream}|venue:{row['venue_id']}"
                        )
                        for stream in sorted(STREAMS)
                    },
                }
            )
        scopes.append(
            {
                "pref_code": code,
                "pref_name": pref,
                "review_status": "pending",
                "venues": venues,
                "candidates": [r for r in candidates if r["pref_code"] == code],
                "pending_proposals": [
                    {"proposal_id": key, "status": record["status"]}
                    for key, record in state["proposals"].items()
                    if record["status"] == "needs_work_verification"
                    and any(
                        e["venue_id"] in {v["venue_id"] for v in venues}
                        for e in record["evidence"]
                    )
                ],
            }
        )
    return {
        "schema_version": 1,
        "scope_revision": revision,
        "national_census_complete": False,
        "streams": sorted(STREAMS),
        "identity_blockers": report["identity_conflicts"] + alias_conflicts,
        "orphan_ids": report["orphan_web_watch_ids"] + report["orphan_ticketjam_ids"],
        "scopes": scopes,
    }


def write_scope_views(bundle: dict, output_dir: Path) -> dict:
    """Export small derived snapshots for Chat's GitHub reader, not a master."""
    output_dir.mkdir(parents=True, exist_ok=True)
    index = {k: v for k, v in bundle.items() if k != "scopes"}
    index.update(snapshot_only=True, shards=[])
    for start in range(0, len(bundle["scopes"]), 6):
        scopes = bundle["scopes"][start : start + 6]
        filename = f"{scopes[0]['pref_code']}-{scopes[-1]['pref_code']}.json"
        payload = {
            "scope_revision": bundle["scope_revision"],
            "snapshot_only": True,
            "scopes": scopes,
        }
        raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
        (output_dir / filename).write_bytes(raw)
        index["shards"].append(
            dict(
                path=filename,
                pref_codes=[r["pref_code"] for r in scopes],
                sha256=hashlib.sha256(raw).hexdigest(),
                bytes=len(raw),
            )
        )
    (output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    )
    return index


def validate_proposal(
    proposal: dict,
    registry: list[dict],
    *,
    base_commit: str,
    scope_revision: str,
    queue: dict | None = None,
    published: dict | None = None,
) -> dict:
    if not isinstance(proposal, dict) or set(proposal) != FIELDS:
        raise ValueError("proposal requires exact data-only fields")
    if proposal["schema_version"] != 1 or proposal["stream"] not in STREAMS:
        raise ValueError("unknown schema or stream")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", base_commit)
        or proposal["base_commit"] != base_commit
    ):
        raise ValueError("base changed: refresh inputs and revalidate")
    if proposal["scope_revision"] != scope_revision:
        raise ValueError("stale scope")
    venues = {r["venue_id"]: r for r in registry}
    venue_id = proposal["venue_id"]
    if venue_id not in venues:
        raise ValueError("unknown venue: resolve registry identity before intake")
    if proposal["change_type"] not in {
        "new",
        "additional",
        "correction",
        "cancelled",
        "postponed",
    }:
        raise ValueError("unknown change type")
    if proposal["source_class"] not in SOURCE_CLASSES:
        raise ValueError("unknown source class")
    if proposal["evidence_status"] not in {
        "official_body",
        "lead_only",
        "fetch_failed",
    }:
        raise ValueError("unknown evidence status")
    if proposal["retrieval_method"] not in {
        "requests_bs4",
        "crawl4ai",
        "browser",
        "web_search",
        "web_open",
    }:
        raise ValueError("unknown retrieval method")
    _url(proposal["discovery_url"])
    if proposal["evidence_url"] is not None:
        _url(proposal["evidence_url"])
    if (
        not isinstance(proposal["evidence_summary"], str)
        or not 1 <= len(proposal["evidence_summary"]) <= 1000
    ):
        raise ValueError("short evidence summary required")
    observed = _utc(proposal["observed_at_utc"])
    if (
        proposal["published_at_utc"] is not None
        and _utc(proposal["published_at_utc"]) > observed
    ):
        raise ValueError("publication cannot follow observation")
    if (
        date.fromisoformat(proposal["next_check_date"])
        < observed.astimezone(JST).date()
    ):
        raise ValueError("next check precedes observation")
    unresolved = proposal["unresolved_fields"]
    if not isinstance(unresolved, list) or any(
        not isinstance(x, str) for x in unresolved
    ):
        raise ValueError("unresolved_fields must be strings")
    for values in (proposal["current_values"], proposal["proposed_values"]):
        if not isinstance(values, dict) or not set(values) <= VALUE_FIELDS:
            raise ValueError("unsupported event fields")
        for key, value in values.items():
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("event values must be nonempty strings or null")
            if key in {"event_date", "event_end_date"} and value is not None:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError("event date must be YYYY-MM-DD")
                date.fromisoformat(value)
            if key == "event_start_time" and value is not None:
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                    raise ValueError("START must be HH:MM or null")
    values = proposal["proposed_values"]
    if values.get("venue_name") != venues[venue_id]["venue_name"]:
        raise ValueError("venue ID and name disagree")
    if not values.get("artist_name") or not values.get("title"):
        raise ValueError("artist or representative event name and title required")
    if values.get("event_status", "scheduled") not in {
        "scheduled",
        "cancelled",
        "postponed",
    }:
        raise ValueError("unsupported event status")
    if (
        proposal["change_type"] in {"cancelled", "postponed"}
        and values.get("event_status") != proposal["change_type"]
    ):
        raise ValueError("change type and event status disagree")
    if values.get("event_end_date") and (
        not values.get("event_date") or values["event_end_date"] < values["event_date"]
    ):
        raise ValueError("invalid date interval")
    key, fp = proposal["event_key"], proposal["candidate_fingerprint"]
    origin_kind = "new_event"
    published_input_fingerprint = None
    if key is not None or fp is not None:
        candidates = (queue or {}).get("candidates", []) + (queue or {}).get(
            "official_rechecks", []
        )
        matches = [r for r in candidates if r["event_key"] == key]
        published_matches = []
        if published is not None and proposal["stream"] != "ticketjam":
            rows = _published_rows(published, base_commit)
            published_matches = [r for r in rows if r["event_key"] == key]
        if len(matches) + len(published_matches) != 1:
            raise ValueError("unknown or stale existing candidate")
        if published_matches:
            snapshot = published_matches[0]
            if digest(snapshot) != fp:
                raise ValueError("stale published event fingerprint")
            if _event_values(snapshot) != _event_values(proposal["current_values"]):
                raise ValueError("published event and current values disagree")
            origin_kind = "published_event"
            published_input_fingerprint = published["lp_fingerprint"]
        else:
            snapshot = matches[0]
            if fingerprint(snapshot) != fp:
                raise ValueError("unknown or stale existing candidate")
            origin_kind = "ticketjam_candidate"
            for field in (
                "event_date",
                "event_end_date",
                "event_start_time",
                "venue_name",
                "artist_name",
                "title",
                "event_status",
            ):
                if _event_values(snapshot).get(field) != _event_values(
                    proposal["current_values"] or values
                ).get(field):
                    raise ValueError("existing candidate and proposal disagree")
        if snapshot.get("venue_name") != venues[venue_id]["venue_name"]:
            # Venue moves require a separate identity/migration review.
            raise ValueError("existing venue and registry disagree")
    elif proposal["stream"] == "ticketjam":
        raise ValueError(
            "Ticketjam proposals require a real candidate key and fingerprint"
        )
    identity = {
        "venue_id": venue_id,
        "change_type": proposal["change_type"],
        "current_values": proposal["current_values"],
        "proposed_values": values,
    }
    return {
        "proposal_id": digest(identity),
        "proposal_hash": digest(proposal),
        "status": "needs_work_verification",
        "can_publish": False,
        "missing_event_date": not bool(values.get("event_date")),
        "origin_kind": origin_kind,
        "published_input_fingerprint": published_input_fingerprint,
    }


def stage_official_event(
    proposal: dict,
    decision: dict,
    registry: list[dict],
    *,
    base_commit: str,
    scope_revision: str,
    queue: dict | None = None,
    review_state: dict | None = None,
    config: dict | None = None,
    published: dict | None = None,
    prepare_import: bool = False,
    venue_aliases: list[dict] | None = None,
    source_snapshot: dict | None = None,
) -> dict:
    """Separate Work decision -> existing official-event shape, still no config/DB write."""
    receipt = validate_proposal(
        proposal,
        registry,
        base_commit=base_commit,
        scope_revision=scope_revision,
        queue=queue,
        published=published,
    )
    if set(decision) - {"replaces_config_fingerprint"} != {
        "proposal_hash",
        "base_commit",
        "status",
        "reason",
        "checked_at_utc",
        "next_check_date",
        "official_event",
    }:
        raise ValueError("unexpected Work decision fields")
    if (
        decision["proposal_hash"] != receipt["proposal_hash"]
        or decision["base_commit"] != base_commit
    ):
        raise ValueError("Work verification is stale")
    if decision["status"] != "confirmed" or not decision["reason"]:
        raise ValueError("Work has not confirmed this proposal")
    if _utc(decision["checked_at_utc"]) < _utc(proposal["observed_at_utc"]):
        raise ValueError("verification precedes proposal")
    event = decision["official_event"]
    event_fields = {
        "event_id",
        "title",
        "artist_name",
        "venue_name",
        "pref_name",
        "event_start_date",
        "event_end_date",
        "event_start_time",
        "event_end_time",
        "source_class",
        "evidence_url",
        "url",
        "evidence_snippet",
        "content_extractor",
        "event_status",
        "event_category",
        "enabled",
    }
    if not isinstance(event, dict) or not set(event) <= event_fields:
        raise ValueError("unsupported official event fields")
    if (
        date.fromisoformat(decision["next_check_date"])
        < _utc(decision["checked_at_utc"]).astimezone(JST).date()
    ):
        raise ValueError("next check precedes Work verification")
    host = _url(event.get("evidence_url"))
    # A Chat assertion of official_body does not authorize SNS/news/secondary URLs.
    for domain in (
        "x.com",
        "twitter.com",
        "facebook.com",
        "instagram.com",
        "ticketjam.jp",
        "wikipedia.org",
    ):
        if host == domain or host.endswith("." + domain):
            raise ValueError("standalone social/secondary evidence cannot be promoted")
    values = proposal["proposed_values"]
    if not values.get("event_date"):
        raise ValueError("unannounced date remains a research proposal")
    _validate_confirmed(values, event)
    if event.get("event_start_time") != values.get("event_start_time"):
        raise ValueError("Work start time disagrees: revise the proposal first")
    if (event.get("event_end_date") or event["event_start_date"]) != (
        values.get("event_end_date") or values["event_date"]
    ):
        raise ValueError("Work end date disagrees")
    for field in ("title", "artist_name"):
        if event[field] != values[field]:
            raise ValueError("Work evidence and proposed event disagree")
    if event.get("event_status", "scheduled") != values.get(
        "event_status", "scheduled"
    ):
        raise ValueError("Work event status disagrees")
    pref = next(
        r["pref_name"] for r in registry if r["venue_id"] == proposal["venue_id"]
    )
    if event.get("pref_name") != pref:
        raise ValueError("Work evidence prefecture disagrees")
    candidate_review_state = None
    source_review_state = review_state
    if receipt["origin_kind"] == "ticketjam_candidate":
        # Reuse the existing decision validator without fabricating Ticketjam identities.
        candidates = queue["candidates"] + queue.get("official_rechecks", [])
        d = {
            k: decision[k]
            for k in (
                "status",
                "reason",
                "checked_at_utc",
                "next_check_date",
                "official_event",
            )
        }
        d.update(
            event_key=proposal["event_key"],
            candidate_fingerprint=proposal["candidate_fingerprint"],
        )
        candidate = next(
            c for c in candidates if c["event_key"] == proposal["event_key"]
        )
        official_values = {
            field: _event_values(values).get(field)
            for field in (
                "event_date",
                "event_end_date",
                "event_start_time",
                "venue_name",
                "artist_name",
                "event_status",
            )
            if _event_values(candidate).get(field) != _event_values(values).get(field)
            and _event_values(values).get(field)
        }
        if official_values:
            if proposal["change_type"] not in {"correction", "cancelled", "postponed"}:
                raise ValueError(
                    "candidate disagreement requires an explicit correction"
                )
            # The original candidate is still wrong. Do not mark its old time/date
            # confirmed, invent a candidate, or discard the previous history.
            d.pop("official_event")
            d.update(
                status="conflict",
                official_values=official_values,
                evidence_url=event["evidence_url"],
            )
            if is_pure_suppression(candidate, event):
                d["official_suppression"] = deepcopy(event)
            elif is_datetime_correction(candidate, event):
                d["official_correction"] = deepcopy(event)
        candidate_review_state = apply_reviews(review_state or {}, candidates, [d])
        previous = (review_state or {}).get("events", {}).get(proposal["event_key"], {})
        if previous.get("history") and previous["history"][-1] == d:
            # Replaying the identical plan against its original trusted snapshots.
            source_review_state = deepcopy(review_state)
            history = source_review_state["events"][proposal["event_key"]]["history"]
            history.pop()
            if not history:
                del source_review_state["events"][proposal["event_key"]]
    correction = None
    if (
        prepare_import
        and source_snapshot is not None
        and proposal["change_type"] == "correction"
        and is_datetime_correction(proposal["current_values"], event)
    ):
        from .event_corrections import prepare_correction

        _published_rows(published, base_commit)
        correction = prepare_correction(
            proposal,
            event,
            receipt,
            source_snapshot,
            published,
            source_review_state,
            base_commit,
        )
    config_review_status = "not_checked"
    if config is not None:
        matching = [
            row
            for row in config.get("confirmed_events", [])
            if row["event_id"] == event["event_id"]
        ]
        if len(matching) > 1:
            raise ValueError("duplicate existing official event IDs")
        if matching:
            planned = _import_event(
                event, proposal, receipt, decision["checked_at_utc"]
            )
            if correction:
                planned["date_time_correction"] = correction
            validate_config_replacement(
                matching[0],
                planned,
                origin_key=proposal["event_key"],
                replaces_fingerprint=decision.get("replaces_config_fingerprint"),
            )
            config_review_status = "replacement_checked"
        elif decision.get("replaces_config_fingerprint"):
            raise ValueError("replacement target no longer exists")
        else:
            config_review_status = "new_event_id_checked"
    result = {
        **receipt,
        "status": "verified_draft",
        "verified_at_utc": decision["checked_at_utc"],
        "official_event": deepcopy(event),
        "origin": {
            "kind": receipt["origin_kind"],
            "event_key": proposal["event_key"],
            "candidate_fingerprint": proposal["candidate_fingerprint"],
            "published_input_fingerprint": receipt["published_input_fingerprint"],
        },
        "candidate_review_state": candidate_review_state,
        "config_review_status": config_review_status,
        "publication_status": "approval_pending",
        "can_publish": False,
        "date_time_correction": correction,
    }
    if prepare_import:
        result["import_preview"] = _prepare_import_preview(
            result,
            proposal,
            config,
            published,
            registry,
            venue_aliases,
            base_commit=base_commit,
        )
    return result


def _import_event(event: dict, proposal: dict, receipt: dict, verified_at: str) -> dict:
    planned = dict(event, verified_at_utc=verified_at)
    if receipt["origin_kind"] == "published_event":
        planned.update(
            published_event_key=proposal["event_key"],
            published_input_fingerprint=receipt["published_input_fingerprint"],
        )
    else:
        planned["discovery_event_key"] = proposal["event_key"]
    return planned


def _prepare_import_preview(
    receipt: dict,
    proposal: dict,
    config: dict | None,
    published: dict | None,
    registry: list[dict],
    venue_aliases: list[dict] | None,
    *,
    base_commit: str,
) -> dict:
    """Only called after validation; produce a copy, never a runtime write."""
    rows = _published_rows(published, base_commit)
    if config is None:
        raise ValueError("current config required for import preview")
    if venue_aliases is None:
        raise ValueError("current venue aliases required for import preview")
    aliases_by_id = {
        r["venue_id"]: tuple(json.loads(r.get("aliases_json") or "[]"))
        for r in venue_aliases
        if r.get("is_enabled", "1") == "1"
    }
    keep, compact = _build_lookup_maps(
        [(r["venue_name"], aliases_by_id.get(r["venue_id"], ())) for r in registry]
    )
    events = config.get("confirmed_events", [])
    if len({r["event_id"] for r in events}) != len(events):
        raise ValueError("duplicate existing official event IDs")
    result = {
        "base_commit": base_commit,
        "scope_revision": proposal["scope_revision"],
        "input_config_fingerprint": digest(config),
        "input_published_fingerprint": published["lp_fingerprint"],
        "input_aliases_fingerprint": digest(venue_aliases),
        "status": "blocked",
        "action": None,
        "config": None,
    }
    suppression = (
        receipt["origin_kind"] in {"ticketjam_candidate", "published_event"}
        and proposal["change_type"] in {"cancelled", "postponed"}
        and is_pure_suppression(proposal["current_values"], receipt["official_event"])
    )
    # Pure status notices use the existing authoritative suppression policy.
    # Date/time corrections require Work's reviewed old-source retirement proof.
    correction = receipt.get("date_time_correction")
    if (
        not suppression
        and not correction
        and (
            proposal["change_type"] not in {"new", "additional"}
            or receipt["origin_kind"] == "published_event"
            or receipt["official_event"].get("event_status", "scheduled") != "scheduled"
        )
    ):
        return dict(result, reason="source_correction_requires_migration")
    if receipt["origin_kind"] == "new_event" and proposal["current_values"]:
        return dict(result, reason="existing_event_origin_required")
    event = _import_event(
        receipt["official_event"], proposal, receipt, receipt["verified_at_utc"]
    )
    if correction:
        event["date_time_correction"] = correction
    existing = next((r for r in events if r["event_id"] == event["event_id"]), None)
    if existing is not None:
        # The earlier shared replacement guard already checked this row.
        if {k: v for k, v in existing.items() if k != "verified_at_utc"} != {
            k: v for k, v in event.items() if k != "verified_at_utc"
        }:
            return dict(result, reason="source_correction_requires_migration")
        return dict(
            result,
            status="ready_for_review",
            action="unchanged",
            config=deepcopy(config),
        )
    if suppression:
        planned = deepcopy(config)
        planned.setdefault("confirmed_events", []).append(event)
        return dict(
            result,
            status="ready_for_review",
            action="add_suppression",
            config=planned,
        )
    start = event["event_start_date"]
    end = event.get("event_end_date") or start
    for row in [*events, *rows]:
        if correction:
            if row.get("event_key") == correction["published_event_key"]:
                continue
            if row.get("event_id"):
                from .signals.sources.base import compute_signal_uid

                uid = compute_signal_uid(
                    "venue_web_discovery",
                    row.get("url") or row.get("evidence_url"),
                    extra_key=row["event_id"],
                )
                if any(
                    r["source_id"] == "venue_web_discovery" and r["record_id"] == uid
                    for r in correction["retired_records"]
                ):
                    continue
        row_venue, _ = normalize_venue_with_lookup(row.get("venue_name"), keep, compact)
        row_start = row.get("event_date") or row.get("event_start_date")
        row_end = row.get("event_end_date") or row_start
        if (
            _normal(row_venue) == _normal(event["venue_name"])
            and row_start
            and row_end
            and row_start <= end
            and start <= row_end
            and (
                not row.get("event_start_time")
                or not event.get("event_start_time")
                or row["event_start_time"] == event["event_start_time"]
            )
        ):
            return dict(result, reason="possible_existing_performance")
    if correction:
        planned = deepcopy(config)
        planned.setdefault("confirmed_events", []).append(event)
        return dict(
            result, status="ready_for_review", action="add_correction", config=planned
        )
    if receipt["origin_kind"] == "ticketjam_candidate":
        key = proposal["event_key"]
        record = receipt["candidate_review_state"]["events"][key]
        if record["history"][-1]["status"] != "confirmed":
            return dict(result, reason="source_correction_requires_migration")
        # Do not promote unrelated historical decisions as a side effect.
        planned = promote_confirmed(config, {"events": {key: record}})
    else:
        planned = deepcopy(config)
        planned.setdefault("confirmed_events", []).append(event)
    return dict(result, status="ready_for_review", action="add", config=planned)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry", type=Path, default=Path("data/venue_registry.csv")
    )
    parser.add_argument("--aliases", type=Path, default=Path("data/venue_aliases.csv"))
    parser.add_argument(
        "--config", type=Path, default=Path("data/venue_web_discovery_config.json")
    )
    parser.add_argument(
        "--ticketjam", type=Path, default=Path("data/ticketjam_venue_pages.csv")
    )
    parser.add_argument("--census-candidates", type=Path)
    parser.add_argument("--pref-code", choices=[f"{i:02d}" for i in range(1, 48)])
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--decision", type=Path)
    parser.add_argument(
        "--prepare-import",
        action="store_true",
        help="Print a review-only config copy; requires decision and trusted current LP",
    )
    parser.add_argument("--queue", type=Path)
    parser.add_argument(
        "--published-lp",
        type=Path,
        help="Read-only LP from Work's trusted current base; never a proposal attachment",
    )
    parser.add_argument(
        "--review-state", type=Path, help="Read-only prior Ticketjam review history"
    )
    parser.add_argument("--state", type=Path, help="Read-only Work ledger snapshot")
    parser.add_argument(
        "--scope-output-dir", type=Path, help="Export derived Chat views outside data/"
    )
    parser.add_argument("--base-commit")
    parser.add_argument(
        "--events-db",
        type=Path,
        help="Work's trusted read-only DB for date/time correction previews",
    )
    parser.add_argument(
        "--event-signals-db",
        type=Path,
        help="Work's trusted read-only signal DB for date/time correction previews",
    )
    args = parser.parse_args(argv)
    if args.decision and not args.proposal:
        parser.error("decision requires proposal")
    if args.prepare_import and (not args.decision or not args.published_lp):
        parser.error("import preview requires decision and published LP")
    if bool(args.events_db) != bool(args.event_signals_db) or (
        args.events_db and not args.prepare_import
    ):
        parser.error("both trusted DB paths and import preview are required")
    if args.scope_output_dir and (args.proposal or args.pref_code):
        parser.error(
            "scope export cannot be combined with intake or a single prefecture"
        )
    if args.scope_output_dir and (
        Path("data").resolve() == args.scope_output_dir.resolve()
        or Path("data").resolve() in args.scope_output_dir.resolve().parents
    ):
        parser.error("scope views must not overwrite runtime data")
    registry = _csv_bytes(
        args.registry.read_bytes(), {"venue_id", "venue_name", "pref_code", "pref_name"}
    )
    config = json.loads(args.config.read_text())
    tickets = _csv_bytes(
        args.ticketjam.read_bytes(), {"venue_id", "venue_name", "is_enabled"}
    )
    aliases = _csv_bytes(args.aliases.read_bytes(), {"venue_id", "aliases_json"})
    candidates = (
        json.loads(args.census_candidates.read_text())["candidates"]
        if args.census_candidates
        else []
    )
    bundle = scope_bundle(
        registry,
        config,
        tickets,
        aliases,
        candidates=candidates,
        state=json.loads(args.state.read_text()) if args.state else None,
    )
    if args.proposal:
        if not args.base_commit or bundle["identity_blockers"] or bundle["orphan_ids"]:
            parser.error("current base and unambiguous registry are required")
        context = dict(
            base_commit=args.base_commit,
            scope_revision=bundle["scope_revision"],
            queue=json.loads(args.queue.read_text()) if args.queue else None,
            published=published_snapshot(
                json.loads(args.published_lp.read_text()), base_commit=args.base_commit
            )
            if args.published_lp
            else None,
        )
        proposal = load_json(args.proposal)
        source_snapshot = None
        if args.events_db:
            from .build_lp_events import load_lp_records

            payload = context["published"]["payload"]
            records = load_lp_records(
                events_db_path=args.events_db,
                event_signals_db_path=args.event_signals_db,
                as_of_date=date.fromisoformat(payload["as_of_date"]),
                include_past=payload.get("history_window_days", 90) is None,
                past_days=payload.get("history_window_days", 90) or 0,
            )
            source_snapshot = dict(
                base_commit=args.base_commit,
                records=records,
                records_fingerprint=digest(records),
            )
        bundle = (
            stage_official_event(
                proposal,
                load_json(args.decision),
                registry,
                review_state=json.loads(args.review_state.read_text())
                if args.review_state
                else None,
                config=config,
                prepare_import=args.prepare_import,
                source_snapshot=source_snapshot,
                venue_aliases=aliases,
                **context,
            )
            if args.decision
            else validate_proposal(proposal, registry, **context)
        )
    elif args.pref_code:
        bundle["scopes"] = [
            r for r in bundle["scopes"] if r["pref_code"] == args.pref_code
        ]
    elif args.scope_output_dir:
        bundle = write_scope_views(bundle, args.scope_output_dir)
    print(json.dumps(bundle, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
