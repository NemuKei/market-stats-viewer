"""Build LP-ready consolidated event data.

The output keeps the display row to the highest-priority source and retains
lower-priority matches as supporting_sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .signals.entity_aliases import (
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DEFAULT_EVENTS_DB_PATH = DATA_DIR / "events.sqlite"
DEFAULT_EVENT_SIGNALS_DB_PATH = DATA_DIR / "event_signals.sqlite"
DEFAULT_OUTPUT_PATH = DATA_DIR / "lp_events.json"

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


def now_utc_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def load_official_events(
    db_path: Path,
    *,
    include_past: bool,
    today_iso: str,
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
        raw_artist_name = str(row["performers"] or row["artist_name_resolved"] or "").strip()
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
        if not include_past and event_end_date < today_iso:
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
    include_past: bool,
    today_iso: str,
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
        raw_artist_name = str(labels.get("raw_artist_name") or labels.get("artist_name") or "").strip()
        artist_name = canonicalize_artist_name(
            raw_artist_name,
            labels.get("artist_name") or "",
            artist_keep_map,
            artist_compact_map,
        )
        raw_venue_name = str(labels.get("raw_venue_name") or labels.get("venue_name") or "").strip()
        venue_name = canonicalize_venue_name(
            raw_venue_name,
            labels.get("venue_name") or "",
            venue_keep_map,
            venue_compact_map,
        )
        if not event_date or not artist_name or not venue_name:
            continue
        if not include_past and event_end_date < today_iso:
            continue
        events.append(
            {
                "source_id": str(row["source_id"] or ""),
                "source_label": str(row["source_name"] or row["source_id"] or ""),
                "source_class": str(labels.get("source_class") or "").strip(),
                "record_id": str(row["signal_uid"] or ""),
                "event_date": event_date,
                "event_end_date": event_end_date,
                "event_start_time": labels.get("event_start_time"),
                "event_end_time": labels.get("event_end_time"),
                "venue_name": venue_name,
                "raw_venue_name": raw_venue_name or venue_name,
                "artist_name": artist_name,
                "raw_artist_name": raw_artist_name or artist_name,
                "title": str(row["title"] or "").strip(),
                "event_category": str(labels.get("event_category") or "").strip(),
                "url": str(row["url"] or "").strip(),
                "evidence_url": str(labels.get("evidence_url") or row["url"] or "").strip(),
                "evidence_snippet": str(labels.get("evidence_snippet") or row["snippet"] or "").strip(),
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


def consolidate_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = event_group_key(
            str(record.get("event_date") or ""),
            str(record.get("venue_name") or ""),
            str(record.get("artist_name") or ""),
        )
        record["event_key"] = key
        groups.setdefault(key, []).append(record)

    rows: list[dict[str, Any]] = []
    for key, members in groups.items():
        ordered = sorted(
            members,
            key=lambda row: (
                SOURCE_PRIORITY.get(str(row.get("source_id") or ""), 999),
                str(row.get("updated_at_utc") or ""),
                str(row.get("record_id") or ""),
            ),
        )
        display = dict(ordered[0])
        supporting_sources = [source_summary(row) for row in ordered]
        rows.append(
            {
                "event_key": key,
                "event_date": display.get("event_date"),
                "event_end_date": display.get("event_end_date"),
                "event_start_time": display.get("event_start_time"),
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
                "source_priority": SOURCE_PRIORITY.get(str(display.get("source_id") or ""), 999),
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
            str(row.get("display_source_id") or ""),
        )
    )
    return rows


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
) -> dict[str, Any]:
    today_iso = date.today().isoformat()
    artist_keep_map, artist_compact_map = load_artist_lookup_maps()
    venue_keep_map, venue_compact_map = load_venue_lookup_maps()
    official = load_official_events(
        events_db_path,
        include_past=include_past,
        today_iso=today_iso,
        artist_keep_map=artist_keep_map,
        artist_compact_map=artist_compact_map,
        venue_keep_map=venue_keep_map,
        venue_compact_map=venue_compact_map,
    )
    signals = load_signal_events(
        event_signals_db_path,
        include_past=include_past,
        today_iso=today_iso,
        artist_keep_map=artist_keep_map,
        artist_compact_map=artist_compact_map,
        venue_keep_map=venue_keep_map,
        venue_compact_map=venue_compact_map,
    )
    records = official + signals
    events = consolidate_events(records)
    counts_by_display_source: dict[str, int] = {}
    for event in events:
        source_id = str(event.get("display_source_id") or "")
        counts_by_display_source[source_id] = counts_by_display_source.get(source_id, 0) + 1
    return {
        "schema_version": 1,
        "generated_at_utc": now_utc_z(),
        "include_past": include_past,
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
            "counts_by_display_source": counts_by_display_source,
        },
        "events": events,
    }


def write_lp_events(payload: dict[str, Any], output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build LP-ready consolidated event JSON.")
    parser.add_argument("--events-db", type=Path, default=DEFAULT_EVENTS_DB_PATH)
    parser.add_argument("--event-signals-db", type=Path, default=DEFAULT_EVENT_SIGNALS_DB_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--include-past", action="store_true", help="Include past events in output.")
    args = parser.parse_args()

    payload = build_lp_events(
        events_db_path=args.events_db,
        event_signals_db_path=args.event_signals_db,
        include_past=bool(args.include_past),
    )
    write_lp_events(payload, args.output)
    print(f"lp events written: {args.output} ({payload['summary']['event_count']} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
