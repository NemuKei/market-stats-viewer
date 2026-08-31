"""Build LP-ready consolidated event data.

The output keeps the display row to the highest-priority source and retains
lower-priority matches as supporting_sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .events.category import (
    EVENT_CATEGORY_BASEBALL,
    EVENT_CATEGORY_CONCERT,
    EVENT_CATEGORY_OTHER,
)
from .signals.entity_aliases import (
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
)
from .signals.text_quality import validate_event_text_fields

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DEFAULT_EVENTS_DB_PATH = DATA_DIR / "events.sqlite"
DEFAULT_EVENT_SIGNALS_DB_PATH = DATA_DIR / "event_signals.sqlite"
DEFAULT_OUTPUT_PATH = DATA_DIR / "lp_events.json"
DEFAULT_HISTORY_WINDOW_DAYS = 90
SUPPLEMENTAL_TITLE_MIN_LENGTH = 8
SUPPLEMENTAL_TITLE_SIMILARITY_THRESHOLD = 0.80

SOURCE_PRIORITY = {
    "official_events": 10,
    "venue_web_discovery": 20,
    "starto_concert": 30,
    "kstyle_music": 30,
    "ticketjam_events": 40,
}
SIGNAL_SOURCE_IDS = {
    "venue_web_discovery",
    "starto_concert",
    "kstyle_music",
    "ticketjam_events",
}
SIGNAL_CATEGORY_MAP = {
    "concert": EVENT_CATEGORY_CONCERT,
    "music": EVENT_CATEGORY_CONCERT,
    "musicevent": EVENT_CATEGORY_CONCERT,
    "music_event": EVENT_CATEGORY_CONCERT,
    "baseball": EVENT_CATEGORY_BASEBALL,
    "baseballevent": EVENT_CATEGORY_BASEBALL,
    "baseball_event": EVENT_CATEGORY_BASEBALL,
    "other": EVENT_CATEGORY_OTHER,
}
SIGNAL_SOURCE_DEFAULT_CATEGORY = {
    "starto_concert": EVENT_CATEGORY_CONCERT,
    "kstyle_music": EVENT_CATEGORY_CONCERT,
}
EVENT_STATUS_SCHEDULED = "scheduled"
SUPPRESSING_EVENT_STATUSES = {"postponed", "cancelled"}
VENUE_WEB_DISCOVERY_STATUS_SOURCE_CLASSES = {
    "venue_official",
    "artist_official",
    "promoter_official",
    "ticket_official",
}


def now_utc_z() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalize_key_part(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", "", text)


def event_group_key(event_date: str, venue_name: str, artist_name: str) -> str:
    raw = "|".join(
        [
            normalize_key_part(event_date),
            normalize_key_part(venue_name),
            normalize_key_part(artist_name),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def normalize_event_start_time(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s+", "", text)


def time_qualified_event_key(base_event_key: str, event_start_time: object) -> str:
    normalized_time = normalize_event_start_time(event_start_time)
    raw = f"{base_event_key}|start_time={normalized_time}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def normalize_supplemental_title(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(
        character for character in text if character.isalnum() or character == "ー"
    )


def supplemental_titles_match(left: object, right: object) -> bool:
    normalized_left = normalize_supplemental_title(left)
    normalized_right = normalize_supplemental_title(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    if min(len(normalized_left), len(normalized_right)) < SUPPLEMENTAL_TITLE_MIN_LENGTH:
        return False
    similarity = SequenceMatcher(
        None,
        normalized_left,
        normalized_right,
        autojunk=False,
    ).ratio()
    return similarity >= SUPPLEMENTAL_TITLE_SIMILARITY_THRESHOLD


def start_times_compatible(left: object, right: object) -> bool:
    normalized_left = normalize_event_start_time(left)
    normalized_right = normalize_event_start_time(right)
    return (
        not normalized_left
        or not normalized_right
        or normalized_left == normalized_right
    )


def normalize_event_status(value: object) -> str:
    key = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    key = re.sub(r"[\s_-]+", "", key)
    if key in {"postponed", "eventpostponed"}:
        return "postponed"
    if key in {"cancelled", "canceled", "eventcancelled", "eventcanceled"}:
        return "cancelled"
    return EVENT_STATUS_SCHEDULED


def is_authoritative_event_suppression(record: dict[str, Any]) -> bool:
    source_id = str(record.get("source_id") or "")
    event_status = normalize_event_status(record.get("event_status"))
    if event_status not in SUPPRESSING_EVENT_STATUSES:
        return False
    if source_id == "official_events":
        return True
    if source_id != "venue_web_discovery":
        return False
    return (
        str(record.get("source_class") or "")
        in VENUE_WEB_DISCOVERY_STATUS_SOURCE_CLASSES
        and bool(str(record.get("evidence_url") or "").strip())
        and bool(str(record.get("evidence_snippet") or "").strip())
    )


def canonicalize_artist_name(
    raw_artist_name: object,
    artist_name: object,
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
) -> str:
    current = str(artist_name or "").strip()
    raw = str(raw_artist_name or current).strip()
    normalized, matched = normalize_with_lookup(
        raw or current,
        artist_keep_map,
        artist_compact_map,
        allow_parenthetical_base=True,
    )
    if matched and normalized:
        return normalized
    return current or normalized


def canonicalize_venue_name(
    raw_venue_name: object,
    venue_name: object,
    venue_keep_map: dict[str, str],
    venue_compact_map: dict[str, str],
) -> str:
    current = str(venue_name or "").strip()
    raw = str(raw_venue_name or current).strip()
    normalized, matched = normalize_venue_with_lookup(
        raw or current,
        venue_keep_map,
        venue_compact_map,
    )
    if matched and normalized:
        return normalized
    return current or normalized


def normalize_event_category(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in {EVENT_CATEGORY_CONCERT, EVENT_CATEGORY_BASEBALL, EVENT_CATEGORY_OTHER}:
        return text
    key = unicodedata.normalize("NFKC", text).casefold().strip()
    key = re.sub(r"[\s-]+", "_", key)
    return SIGNAL_CATEGORY_MAP.get(key, "")


def signal_event_category(source_id: str, labels: dict[str, Any]) -> str:
    for raw in (labels.get("event_category"), labels.get("category")):
        category = normalize_event_category(raw)
        if category:
            return category
    return SIGNAL_SOURCE_DEFAULT_CATEGORY.get(source_id, "")


def load_official_events(
    db_path: Path,
    *,
    history_start_date: str | None,
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
    venue_keep_map: dict[str, str],
    venue_compact_map: dict[str, str],
) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"events db not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.event_uid,
            e.title,
            e.start_date,
            e.start_time,
            e.end_date,
            e.end_time,
            e.status,
            e.url,
            e.description,
            e.performers,
            e.artist_name_resolved,
            e.event_category,
            e.source_type,
            e.source_url,
            e.first_seen_at_utc,
            e.updated_at_utc,
            v.venue_id,
            v.venue_name,
            v.pref_name,
            v.capacity
        FROM events e
        JOIN venues v ON v.venue_id = e.venue_id
        WHERE e.start_date IS NOT NULL
        ORDER BY e.start_date, v.venue_name, e.title
        """
    ).fetchall()
    conn.close()

    events: list[dict[str, Any]] = []
    for row in rows:
        event_date = str(row["start_date"] or "").strip()
        event_end_date = str(row["end_date"] or event_date).strip()
        raw_artist_name = str(
            row["performers"] or row["artist_name_resolved"] or ""
        ).strip()
        artist_name = canonicalize_artist_name(
            raw_artist_name,
            row["artist_name_resolved"] or row["performers"] or "",
            artist_keep_map,
            artist_compact_map,
        )
        raw_venue_name = str(row["venue_name"] or "").strip()
        venue_name = canonicalize_venue_name(
            raw_venue_name,
            row["venue_name"] or "",
            venue_keep_map,
            venue_compact_map,
        )
        if not event_date or not artist_name or not venue_name:
            continue
        if history_start_date and event_end_date < history_start_date:
            continue
        events.append(
            {
                "source_id": "official_events",
                "source_label": "会場公式",
                "source_class": "venue_official",
                "record_id": str(row["event_uid"] or ""),
                "event_date": event_date,
                "event_end_date": event_end_date,
                "event_start_time": row["start_time"],
                "event_end_time": row["end_time"],
                "event_status": normalize_event_status(row["status"]),
                "venue_name": venue_name,
                "raw_venue_name": raw_venue_name,
                "artist_name": artist_name,
                "raw_artist_name": raw_artist_name or artist_name,
                "title": str(row["title"] or "").strip(),
                "event_category": str(row["event_category"] or "").strip(),
                "url": str(row["url"] or row["source_url"] or "").strip(),
                "evidence_url": str(row["url"] or row["source_url"] or "").strip(),
                "evidence_snippet": str(row["description"] or "").strip(),
                "pref_name": row["pref_name"],
                "capacity": row["capacity"],
                "first_seen_at_utc": row["first_seen_at_utc"],
                "updated_at_utc": row["updated_at_utc"],
            }
        )
    return events


def load_signal_events(
    db_path: Path,
    *,
    history_start_date: str | None,
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
    venue_keep_map: dict[str, str],
    venue_compact_map: dict[str, str],
) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"event signals db not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            s.signal_uid,
            s.source_id,
            COALESCE(src.source_name, s.source_id) AS source_name,
            s.published_at_utc,
            s.title,
            s.url,
            s.snippet,
            s.score,
            s.labels_json,
            s.first_seen_at_utc,
            s.updated_at_utc
        FROM signals s
        LEFT JOIN signal_sources src ON src.source_id = s.source_id
        WHERE s.source_id IN (?, ?, ?, ?)
        ORDER BY s.published_at_utc DESC, s.title
        """,
        tuple(sorted(SIGNAL_SOURCE_IDS)),
    ).fetchall()
    conn.close()

    events: list[dict[str, Any]] = []
    for row in rows:
        labels = parse_labels(row["labels_json"])
        event_date = str(labels.get("event_start_date") or "").strip()
        event_end_date = str(labels.get("event_end_date") or event_date).strip()
        raw_artist_name = str(
            labels.get("raw_artist_name") or labels.get("artist_name") or ""
        ).strip()
        artist_name = canonicalize_artist_name(
            raw_artist_name,
            labels.get("artist_name") or "",
            artist_keep_map,
            artist_compact_map,
        )
        raw_venue_name = str(
            labels.get("raw_venue_name") or labels.get("venue_name") or ""
        ).strip()
        venue_name = canonicalize_venue_name(
            raw_venue_name,
            labels.get("venue_name") or "",
            venue_keep_map,
            venue_compact_map,
        )
        if not event_date or not artist_name or not venue_name:
            continue
        if history_start_date and event_end_date < history_start_date:
            continue
        source_id = str(row["source_id"] or "")
        events.append(
            {
                "source_id": source_id,
                "source_label": str(row["source_name"] or row["source_id"] or ""),
                "source_class": str(labels.get("source_class") or "").strip(),
                "record_id": str(row["signal_uid"] or ""),
                "event_date": event_date,
                "event_end_date": event_end_date,
                "event_start_time": labels.get("event_start_time"),
                "event_end_time": labels.get("event_end_time"),
                "event_status": normalize_event_status(labels.get("event_status")),
                "venue_name": venue_name,
                "raw_venue_name": raw_venue_name or venue_name,
                "artist_name": artist_name,
                "raw_artist_name": raw_artist_name or artist_name,
                "title": str(row["title"] or "").strip(),
                "event_category": signal_event_category(source_id, labels),
                "url": str(row["url"] or "").strip(),
                "evidence_url": str(
                    labels.get("evidence_url") or row["url"] or ""
                ).strip(),
                "evidence_snippet": str(
                    labels.get("evidence_snippet") or row["snippet"] or ""
                ).strip(),
                "pref_name": labels.get("pref_name"),
                "capacity": labels.get("capacity"),
                "first_seen_at_utc": row["first_seen_at_utc"],
                "updated_at_utc": row["updated_at_utc"],
                "published_at_utc": row["published_at_utc"],
                "score": row["score"],
                "confidence": labels.get("confidence"),
                "content_extractor": labels.get("content_extractor"),
            }
        )
    return events


def parse_labels(labels_json: object) -> dict[str, Any]:
    if not isinstance(labels_json, str) or not labels_json.strip():
        return {}
    try:
        parsed = json.loads(labels_json)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def source_order_key(record: dict[str, Any]) -> tuple[int, str, str]:
    return (
        SOURCE_PRIORITY.get(str(record.get("source_id") or ""), 999),
        str(record.get("updated_at_utc") or ""),
        str(record.get("record_id") or ""),
    )


def group_representative(group: dict[str, Any]) -> dict[str, Any]:
    return min(group["members"], key=source_order_key)


def group_order_key(group: dict[str, Any]) -> tuple[int, str, str, str]:
    representative = group_representative(group)
    return (*source_order_key(representative), str(group["event_key"]))


def build_strict_event_groups(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        base_key = event_group_key(
            str(record.get("event_date") or ""),
            str(record.get("venue_name") or ""),
            str(record.get("artist_name") or ""),
        )
        groups.setdefault(base_key, []).append(dict(record))

    strict_groups: list[dict[str, Any]] = []
    start_time_split_group_count = 0
    start_time_split_event_count = 0
    for base_key in sorted(groups):
        members = groups[base_key]
        nonempty_start_times = sorted(
            {
                normalize_event_start_time(member.get("event_start_time"))
                for member in members
                if normalize_event_start_time(member.get("event_start_time"))
            }
        )
        if len(nonempty_start_times) <= 1:
            for member in members:
                member["event_key"] = base_key
            strict_groups.append(
                {
                    "event_key": base_key,
                    "strict_base_key": base_key,
                    "event_start_time": nonempty_start_times[0]
                    if nonempty_start_times
                    else "",
                    "members": members,
                }
            )
            continue

        start_time_split_group_count += 1
        start_time_split_event_count += len(nonempty_start_times) - 1
        blank_time_members = [
            member
            for member in members
            if not normalize_event_start_time(member.get("event_start_time"))
        ]
        for start_time in nonempty_start_times:
            event_key = time_qualified_event_key(base_key, start_time)
            child_members = [dict(member) for member in blank_time_members]
            child_members.extend(
                dict(member)
                for member in members
                if normalize_event_start_time(member.get("event_start_time"))
                == start_time
            )
            for member in child_members:
                member["event_key"] = event_key
            strict_groups.append(
                {
                    "event_key": event_key,
                    "strict_base_key": base_key,
                    "event_start_time": start_time,
                    "members": child_members,
                }
            )

    return strict_groups, {
        "start_time_split_group_count": start_time_split_group_count,
        "start_time_split_event_count": start_time_split_event_count,
    }


def supplemental_group_matches(
    representative_group: dict[str, Any], candidate_group: dict[str, Any]
) -> bool:
    representative = group_representative(representative_group)
    candidate = group_representative(candidate_group)
    if str(representative.get("event_date") or "") != str(
        candidate.get("event_date") or ""
    ):
        return False
    if str(representative.get("venue_name") or "") != str(
        candidate.get("venue_name") or ""
    ):
        return False
    if not start_times_compatible(
        representative_group.get("event_start_time"),
        candidate_group.get("event_start_time"),
    ):
        return False
    return supplemental_titles_match(
        representative.get("title"),
        candidate.get("title"),
    )


def merge_supplemental_groups(
    strict_groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for group in strict_groups:
        representative = group_representative(group)
        bucket_key = (
            str(representative.get("event_date") or ""),
            str(representative.get("venue_name") or ""),
        )
        buckets.setdefault(bucket_key, []).append(group)

    final_groups: list[dict[str, Any]] = []
    supplemental_merged_group_count = 0
    supplemental_merged_record_count = 0
    for bucket_key in sorted(buckets):
        ordered_groups = sorted(buckets[bucket_key], key=group_order_key)
        unassigned = set(range(len(ordered_groups)))
        for anchor_index, anchor in enumerate(ordered_groups):
            if anchor_index not in unassigned:
                continue
            candidate_indexes = [
                index
                for index in sorted(unassigned)
                if index != anchor_index
                and supplemental_group_matches(anchor, ordered_groups[index])
            ]

            anchor_start_time = normalize_event_start_time(
                anchor.get("event_start_time")
            )
            candidate_start_times = {
                normalize_event_start_time(
                    ordered_groups[index].get("event_start_time")
                )
                for index in candidate_indexes
                if normalize_event_start_time(
                    ordered_groups[index].get("event_start_time")
                )
            }
            if not anchor_start_time and len(candidate_start_times) > 1:
                raise ValueError(
                    "supplemental grouping is ambiguous across multiple nonempty "
                    f"start times: date={bucket_key[0]} venue={bucket_key[1]} "
                    f"event_key={anchor['event_key']}"
                )

            merged_indexes = [anchor_index, *candidate_indexes]
            for index in merged_indexes:
                unassigned.remove(index)
            merged_groups = [ordered_groups[index] for index in merged_indexes]
            merged_members = [
                member for group in merged_groups for member in group["members"]
            ]
            merged_start_times = {
                normalize_event_start_time(group.get("event_start_time"))
                for group in merged_groups
                if normalize_event_start_time(group.get("event_start_time"))
            }
            if len(merged_start_times) > 1:
                raise ValueError(
                    "supplemental group retained conflicting nonempty start times"
                )
            if len(merged_groups) > 1:
                supplemental_merged_group_count += 1
                supplemental_merged_record_count += len(merged_groups) - 1
            final_groups.append(
                {
                    "event_key": anchor["event_key"],
                    "event_start_time": next(iter(merged_start_times), ""),
                    "members": merged_members,
                }
            )

    return final_groups, {
        "supplemental_merged_group_count": supplemental_merged_group_count,
        "supplemental_merged_record_count": supplemental_merged_record_count,
    }


def consolidate_events(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    strict_groups, split_metrics = build_strict_event_groups(records)
    final_groups, supplemental_metrics = merge_supplemental_groups(strict_groups)

    rows: list[dict[str, Any]] = []
    suppressed_event_count = 0
    for group in final_groups:
        key = str(group["event_key"])
        members = group["members"]
        if any(is_authoritative_event_suppression(row) for row in members):
            suppressed_event_count += 1
            continue

        ordered = sorted(members, key=source_order_key)
        display = dict(ordered[0])
        supporting_sources = [source_summary(row) for row in ordered]
        display_start_time = display.get("event_start_time")
        if not normalize_event_start_time(display_start_time):
            display_start_time = group.get("event_start_time") or display_start_time
        rows.append(
            {
                "event_key": key,
                "event_date": display.get("event_date"),
                "event_end_date": display.get("event_end_date"),
                "event_start_time": display_start_time,
                "event_end_time": display.get("event_end_time"),
                "venue_name": display.get("venue_name"),
                "raw_venue_name": display.get("raw_venue_name"),
                "artist_name": display.get("artist_name"),
                "raw_artist_name": display.get("raw_artist_name"),
                "title": display.get("title"),
                "event_category": display.get("event_category"),
                "pref_name": display.get("pref_name"),
                "capacity": display.get("capacity"),
                "url": display.get("url"),
                "evidence_url": display.get("evidence_url"),
                "evidence_snippet": display.get("evidence_snippet"),
                "display_source_id": display.get("source_id"),
                "display_source_class": display.get("source_class"),
                "display_source_label": display.get("source_label"),
                "source_priority": SOURCE_PRIORITY.get(
                    str(display.get("source_id") or ""), 999
                ),
                "first_seen_at_utc": display.get("first_seen_at_utc"),
                "updated_at_utc": display.get("updated_at_utc"),
                "supporting_sources": supporting_sources,
            }
        )
    rows.sort(
        key=lambda row: (
            str(row.get("event_date") or ""),
            str(row.get("venue_name") or ""),
            str(row.get("artist_name") or ""),
            normalize_event_start_time(row.get("event_start_time")),
            str(row.get("display_source_id") or ""),
            str(row.get("event_key") or ""),
        )
    )
    return rows, {
        "suppressed_event_count": suppressed_event_count,
        **supplemental_metrics,
        **split_metrics,
    }


def source_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": row.get("source_id"),
        "source_class": row.get("source_class"),
        "source_label": row.get("source_label"),
        "record_id": row.get("record_id"),
        "title": row.get("title"),
        "url": row.get("url"),
        "evidence_url": row.get("evidence_url"),
        "updated_at_utc": row.get("updated_at_utc"),
        "priority": SOURCE_PRIORITY.get(str(row.get("source_id") or ""), 999),
        "content_extractor": row.get("content_extractor"),
    }


def build_lp_events(
    *,
    events_db_path: Path = DEFAULT_EVENTS_DB_PATH,
    event_signals_db_path: Path = DEFAULT_EVENT_SIGNALS_DB_PATH,
    include_past: bool = False,
    past_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    if past_days < 0:
        raise ValueError("past_days must be zero or greater")
    reference_date = as_of_date or date.today()
    history_start_date = (
        None
        if include_past
        else (reference_date - timedelta(days=past_days)).isoformat()
    )
    artist_keep_map, artist_compact_map = load_artist_lookup_maps()
    venue_keep_map, venue_compact_map = load_venue_lookup_maps()
    official = load_official_events(
        events_db_path,
        history_start_date=history_start_date,
        artist_keep_map=artist_keep_map,
        artist_compact_map=artist_compact_map,
        venue_keep_map=venue_keep_map,
        venue_compact_map=venue_compact_map,
    )
    signals = load_signal_events(
        event_signals_db_path,
        history_start_date=history_start_date,
        artist_keep_map=artist_keep_map,
        artist_compact_map=artist_compact_map,
        venue_keep_map=venue_keep_map,
        venue_compact_map=venue_compact_map,
    )
    records = official + signals
    for record in records:
        validate_event_text_fields(
            record,
            context=(
                f"source_id={record.get('source_id')} "
                f"record_id={record.get('record_id')} url={record.get('url')}"
            ),
        )
    events, consolidation_metrics = consolidate_events(records)
    counts_by_display_source: dict[str, int] = {}
    for event in events:
        source_id = str(event.get("display_source_id") or "")
        counts_by_display_source[source_id] = (
            counts_by_display_source.get(source_id, 0) + 1
        )
    return {
        "schema_version": 1,
        "generated_at_utc": now_utc_z(),
        "as_of_date": reference_date.isoformat(),
        "include_past": include_past or past_days > 0,
        "history_window_days": None if include_past else past_days,
        "history_start_date": history_start_date,
        "source_priority": [
            "official_events",
            "venue_web_discovery",
            "starto_concert",
            "kstyle_music",
            "ticketjam_events",
        ],
        "summary": {
            "record_count_before_grouping": len(records),
            "event_count": len(events),
            **consolidation_metrics,
            "counts_by_display_source": counts_by_display_source,
        },
        "events": events,
    }


def write_lp_events(
    payload: dict[str, Any], output_path: Path = DEFAULT_OUTPUT_PATH
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build LP-ready consolidated event JSON."
    )
    parser.add_argument("--events-db", type=Path, default=DEFAULT_EVENTS_DB_PATH)
    parser.add_argument(
        "--event-signals-db", type=Path, default=DEFAULT_EVENT_SIGNALS_DB_PATH
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--past-days",
        type=int,
        default=DEFAULT_HISTORY_WINDOW_DAYS,
        help=f"Include events ending within this many days before today (default: {DEFAULT_HISTORY_WINDOW_DAYS}).",
    )
    parser.add_argument(
        "--include-past",
        action="store_true",
        help="Include all past events retained in the source databases.",
    )
    args = parser.parse_args()

    payload = build_lp_events(
        events_db_path=args.events_db,
        event_signals_db_path=args.event_signals_db,
        include_past=bool(args.include_past),
        past_days=args.past_days,
    )
    write_lp_events(payload, args.output)
    print(
        f"lp events written: {args.output} ({payload['summary']['event_count']} events)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
