"""Audit event-level normalization candidates across official and signal DBs."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .signals.artist_registry import normalize_text
from .signals.entity_aliases import (
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
EVENTS_DB_PATH = DATA_DIR / "events.sqlite"
EVENT_SIGNALS_DB_PATH = DATA_DIR / "event_signals.sqlite"
DEFAULT_SIGNAL_SOURCE_IDS = ("kstyle_music", "starto_concert", "ticketjam_events")
DEFAULT_OUTPUT_JSON_PATH = DATA_DIR / "event_normalization_audit.json"
DEFAULT_OUTPUT_MD_PATH = DATA_DIR / "event_normalization_audit.md"


@dataclass(frozen=True)
class NormalizedEventRecord:
    source_id: str
    source_kind: str
    source_record_id: str
    event_date: str
    raw_venue_name: str
    venue_name: str
    canonical_venue_name: str
    venue_matched: bool
    raw_artist_name: str
    artist_name: str
    canonical_artist_name: str
    artist_matched: bool
    title: str
    url: str
    event_category: str
    artist_confidence: str
    updated_at_utc: str

    def normalization_gaps(self) -> tuple[str, ...]:
        gaps: list[str] = []
        if not self.event_date:
            gaps.append("missing_event_date")
        if not self.venue_name and not self.raw_venue_name:
            gaps.append("missing_venue")
        elif not self.venue_matched:
            gaps.append("unmatched_venue")
        if not self.artist_name and not self.raw_artist_name:
            gaps.append("missing_artist")
        elif not self.artist_matched:
            gaps.append("unmatched_artist")
        if not self.event_category:
            gaps.append("missing_category")
        return tuple(gaps)

    def event_key(self) -> tuple[str, str, str] | None:
        if not (
            self.event_date
            and self.canonical_venue_name
            and self.canonical_artist_name
            and self.venue_matched
            and self.artist_matched
        ):
            return None
        return (
            self.event_date,
            normalize_compare_text(self.canonical_venue_name),
            normalize_compare_text(self.canonical_artist_name),
        )

    def to_report_row(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "source_record_id": self.source_record_id,
            "event_date": self.event_date,
            "raw_venue_name": self.raw_venue_name,
            "venue_name": self.venue_name,
            "canonical_venue_name": self.canonical_venue_name,
            "venue_matched": self.venue_matched,
            "raw_artist_name": self.raw_artist_name,
            "artist_name": self.artist_name,
            "canonical_artist_name": self.canonical_artist_name,
            "artist_matched": self.artist_matched,
            "title": self.title,
            "url": self.url,
            "event_category": self.event_category,
            "artist_confidence": self.artist_confidence,
            "updated_at_utc": self.updated_at_utc,
            "normalization_gaps": list(self.normalization_gaps()),
        }


def normalize_compare_text(text: object) -> str:
    return normalize_text(str(text or ""), mode="keep")


def split_artist_names(raw: object) -> tuple[str, ...]:
    text = str(raw or "").strip()
    if not text:
        return tuple()
    parts = [text]
    for delimiter in (" / ", "/", "／", "、", ",", "\n", "&", "＆"):
        next_parts: list[str] = []
        for part in parts:
            if delimiter in part:
                next_parts.extend(part.split(delimiter))
            else:
                next_parts.append(part)
        parts = next_parts
    cleaned = [_strip_artist_noise(part) for part in parts]
    return tuple(dict.fromkeys(part for part in cleaned if part))


def _strip_artist_noise(text: object) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^(出演|主演|アーティスト|artist)\s*[:：]\s*", "", value, flags=re.I)
    return " ".join(value.split())


def load_official_records(
    events_db_path: Path,
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
    venue_keep_map: dict[str, str],
    venue_compact_map: dict[str, str],
) -> list[NormalizedEventRecord]:
    if not events_db_path.exists():
        return []
    conn = sqlite3.connect(str(events_db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.event_uid,
            e.title,
            e.start_date,
            e.url,
            e.source_url,
            e.performers,
            e.artist_name_resolved,
            e.artist_confidence,
            e.event_category,
            e.updated_at_utc,
            v.venue_name
        FROM events e
        LEFT JOIN venues v ON e.venue_id = v.venue_id
        WHERE e.start_date IS NOT NULL
        """
    ).fetchall()
    conn.close()

    records: list[NormalizedEventRecord] = []
    for row in rows:
        venue_raw = str(row["venue_name"] or "").strip()
        canonical_venue, venue_matched = normalize_venue_with_lookup(
            venue_raw, venue_keep_map, venue_compact_map
        )
        raw_artists = split_artist_names(row["artist_name_resolved"])
        if not raw_artists:
            raw_artists = split_artist_names(row["performers"])
        if not raw_artists:
            raw_artists = ("",)
        for raw_artist in raw_artists:
            canonical_artist, artist_matched = normalize_with_lookup(
                raw_artist,
                artist_keep_map,
                artist_compact_map,
                allow_parenthetical_base=True,
            )
            records.append(
                NormalizedEventRecord(
                    source_id="official_events",
                    source_kind="official",
                    source_record_id=str(row["event_uid"] or "").strip(),
                    event_date=str(row["start_date"] or "").strip(),
                    raw_venue_name=venue_raw,
                    venue_name=venue_raw,
                    canonical_venue_name=canonical_venue,
                    venue_matched=venue_matched,
                    raw_artist_name=raw_artist,
                    artist_name=raw_artist,
                    canonical_artist_name=canonical_artist,
                    artist_matched=artist_matched,
                    title=str(row["title"] or "").strip(),
                    url=str(row["url"] or row["source_url"] or "").strip(),
                    event_category=str(row["event_category"] or "").strip(),
                    artist_confidence=str(row["artist_confidence"] or "").strip(),
                    updated_at_utc=str(row["updated_at_utc"] or "").strip(),
                )
            )
    return records


def load_signal_records(
    event_signals_db_path: Path,
    source_ids: tuple[str, ...],
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
    venue_keep_map: dict[str, str],
    venue_compact_map: dict[str, str],
) -> list[NormalizedEventRecord]:
    if not event_signals_db_path.exists() or not source_ids:
        return []
    conn = sqlite3.connect(str(event_signals_db_path))
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in source_ids)
    rows = conn.execute(
        f"""
        SELECT
            signal_uid,
            source_id,
            title,
            url,
            labels_json,
            updated_at_utc
        FROM signals
        WHERE source_id IN ({placeholders})
        """,
        source_ids,
    ).fetchall()
    conn.close()

    records: list[NormalizedEventRecord] = []
    for row in rows:
        labels = parse_labels(row["labels_json"])
        raw_venue = first_nonblank(labels.get("raw_venue_name"), labels.get("venue_raw"))
        venue_name = first_nonblank(labels.get("venue_name"), raw_venue)
        raw_artist = first_nonblank(
            labels.get("raw_artist_name"),
            labels.get("artist_raw"),
            labels.get("artist_name"),
        )
        artist_name = first_nonblank(labels.get("artist_name"), raw_artist)
        canonical_venue, venue_matched = normalize_venue_with_lookup(
            venue_name or raw_venue, venue_keep_map, venue_compact_map
        )
        canonical_artist, artist_matched = normalize_with_lookup(
            artist_name or raw_artist,
            artist_keep_map,
            artist_compact_map,
            allow_parenthetical_base=True,
        )
        records.append(
            NormalizedEventRecord(
                source_id=str(row["source_id"] or "").strip(),
                source_kind=source_kind(str(row["source_id"] or "")),
                source_record_id=str(row["signal_uid"] or "").strip(),
                event_date=first_nonblank(
                    labels.get("event_start_date"),
                    labels.get("event_date"),
                    labels.get("start_date"),
                ),
                raw_venue_name=raw_venue,
                venue_name=venue_name,
                canonical_venue_name=canonical_venue,
                venue_matched=venue_matched,
                raw_artist_name=raw_artist,
                artist_name=artist_name,
                canonical_artist_name=canonical_artist,
                artist_matched=artist_matched,
                title=str(row["title"] or "").strip(),
                url=str(row["url"] or "").strip(),
                event_category=first_nonblank(
                    labels.get("event_category"), labels.get("category")
                ),
                artist_confidence=str(labels.get("artist_confidence") or "").strip(),
                updated_at_utc=str(row["updated_at_utc"] or "").strip(),
            )
        )
    return records


def parse_labels(raw: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def first_nonblank(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def source_kind(source_id: str) -> str:
    if source_id == "ticketjam_events":
        return "secondary"
    if source_id in {"kstyle_music", "starto_concert"}:
        return "news"
    return "signal"


def build_same_event_candidates(records: list[NormalizedEventRecord]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[NormalizedEventRecord]] = defaultdict(list)
    for record in records:
        key = record.event_key()
        if key is not None:
            grouped[key].append(record)

    candidates: list[dict[str, object]] = []
    for key, group in grouped.items():
        source_ids = sorted({record.source_id for record in group})
        source_kinds = sorted({record.source_kind for record in group})
        if len(source_ids) < 2:
            continue
        group_sorted = sorted(
            group,
            key=lambda row: (
                row.source_kind,
                row.source_id,
                row.event_date,
                row.canonical_venue_name,
                row.canonical_artist_name,
                row.source_record_id,
            ),
        )
        candidates.append(
            {
                "event_date": group_sorted[0].event_date,
                "canonical_venue_name": group_sorted[0].canonical_venue_name,
                "canonical_artist_name": group_sorted[0].canonical_artist_name,
                "source_count": len(source_ids),
                "record_count": len(group_sorted),
                "source_ids": source_ids,
                "source_kinds": source_kinds,
                "same_event_key": {
                    "event_date": key[0],
                    "venue_key": key[1],
                    "artist_key": key[2],
                },
                "records": [record.to_report_row() for record in group_sorted],
            }
        )

    candidates.sort(
        key=lambda row: (
            -int(row["source_count"]),
            -int(row["record_count"]),
            str(row["event_date"]),
            str(row["canonical_venue_name"]),
            str(row["canonical_artist_name"]),
        )
    )
    return candidates


def build_normalization_gap_rows(
    records: list[NormalizedEventRecord], limit: int
) -> list[dict[str, object]]:
    rows = [record.to_report_row() for record in records if record.normalization_gaps()]
    rows.sort(
        key=lambda row: (
            str(row["source_id"]),
            str(row["event_date"]),
            str(row["raw_venue_name"] or row["venue_name"]),
            str(row["raw_artist_name"] or row["artist_name"]),
            str(row["source_record_id"]),
        )
    )
    return rows[:limit]


def build_audit_report(
    events_db_path: Path,
    event_signals_db_path: Path,
    source_ids: tuple[str, ...],
    limit: int,
) -> dict[str, object]:
    artist_keep_map, artist_compact_map = load_artist_lookup_maps()
    venue_keep_map, venue_compact_map = load_venue_lookup_maps()
    official_records = load_official_records(
        events_db_path,
        artist_keep_map,
        artist_compact_map,
        venue_keep_map,
        venue_compact_map,
    )
    signal_records = load_signal_records(
        event_signals_db_path,
        source_ids,
        artist_keep_map,
        artist_compact_map,
        venue_keep_map,
        venue_compact_map,
    )
    records = official_records + signal_records
    same_event_candidates_all = build_same_event_candidates(records)
    same_event_candidates = same_event_candidates_all[:limit]
    normalization_gap = build_normalization_gap_rows(records, limit=limit)
    gap_counts = Counter()
    for record in records:
        gap_counts.update(record.normalization_gaps())

    source_counts = Counter(record.source_id for record in records)
    comparable_counts = Counter(
        record.source_id for record in records if record.event_key() is not None
    )
    official_overlap_groups = sum(
        1
        for row in same_event_candidates_all
        if "official_events" in set(row["source_ids"])
    )
    news_ticketjam_overlap_groups = sum(
        1
        for row in same_event_candidates_all
        if "ticketjam_events" in set(row["source_ids"])
        and {"kstyle_music", "starto_concert"} & set(row["source_ids"])
    )
    return {
        "report_name": "event_normalization_audit",
        "report_version": 1,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "events_db": str(events_db_path),
            "event_signals_db": str(event_signals_db_path),
            "signal_source_ids": list(source_ids),
            "artist_lookup_entries_keep": len(artist_keep_map),
            "venue_lookup_entries_keep": len(venue_keep_map),
        },
        "summary": {
            "records_total": len(records),
            "official_records": len(official_records),
            "signal_records": len(signal_records),
            "records_by_source": dict(sorted(source_counts.items())),
            "comparable_records_by_source": dict(sorted(comparable_counts.items())),
            "same_event_candidate_groups": len(same_event_candidates_all),
            "same_event_candidate_groups_output": len(same_event_candidates),
            "official_overlap_groups": official_overlap_groups,
            "news_ticketjam_overlap_groups": news_ticketjam_overlap_groups,
            "normalization_gap_records": sum(
                1 for record in records if record.normalization_gaps()
            ),
            "normalization_gap_counts": dict(sorted(gap_counts.items())),
        },
        "methodology": {
            "event_key": "event_date + canonical venue_name + canonical artist_name",
            "same_event_candidates": "同じ event_key に複数 source_id のレコードがある候補。重複削除ではなく、同一イベントとして扱う候補を出力する。",
            "normalization_gap": "event_key を作るために必要な日付、会場、アーティスト、カテゴリが欠けている、または辞書で正規化できないレコード。",
        },
        "same_event_candidates": same_event_candidates,
        "normalization_gap": normalization_gap,
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    candidates = report["same_event_candidates"]
    gaps = report["normalization_gap"]
    lines = [
        "# Event Normalization Audit",
        "",
        "## Summary",
        f"- records_total: {summary['records_total']}",
        f"- official_records: {summary['official_records']}",
        f"- signal_records: {summary['signal_records']}",
        f"- same_event_candidate_groups: {summary['same_event_candidate_groups']}",
        f"- normalization_gap_records: {summary['normalization_gap_records']}",
        f"- records_by_source: {json.dumps(summary['records_by_source'], ensure_ascii=False)}",
        f"- comparable_records_by_source: {json.dumps(summary['comparable_records_by_source'], ensure_ascii=False)}",
        f"- normalization_gap_counts: {json.dumps(summary['normalization_gap_counts'], ensure_ascii=False)}",
        "",
        "## Same Event Candidates",
        "",
        "| event_date | venue | artist | source_count | record_count | source_ids |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in candidates[:30]:
        lines.append(
            "| {event_date} | {venue} | {artist} | {source_count} | {record_count} | {source_ids} |".format(
                event_date=row["event_date"],
                venue=row["canonical_venue_name"],
                artist=row["canonical_artist_name"],
                source_count=row["source_count"],
                record_count=row["record_count"],
                source_ids=", ".join(row["source_ids"]),
            )
        )
    lines.extend(
        [
            "",
            "## Normalization Gap",
            "",
            "| source_id | event_date | venue | artist | gaps | title |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in gaps[:50]:
        lines.append(
            "| {source_id} | {event_date} | {venue} | {artist} | {gaps} | {title} |".format(
                source_id=row["source_id"],
                event_date=row["event_date"],
                venue=row["raw_venue_name"] or row["venue_name"],
                artist=row["raw_artist_name"] or row["artist_name"],
                gaps=", ".join(row["normalization_gaps"]),
                title=str(row["title"]).replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Methodology",
            "",
            f"- event_key: {report['methodology']['event_key']}",
            f"- same_event_candidates: {report['methodology']['same_event_candidates']}",
            f"- normalization_gap: {report['methodology']['normalization_gap']}",
            "",
        ]
    )
    return "\n".join(lines)


def write_if_requested(output_path: str, content: str) -> None:
    if not output_path:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def parse_source_ids(raw: str) -> tuple[str, ...]:
    ids = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    return tuple(dict.fromkeys(ids))


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-db", default=str(EVENTS_DB_PATH))
    parser.add_argument("--event-signals-db", default=str(EVENT_SIGNALS_DB_PATH))
    parser.add_argument(
        "--source-ids",
        default=",".join(DEFAULT_SIGNAL_SOURCE_IDS),
        help="comma-separated signal source IDs",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--indent", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_audit_report(
        events_db_path=Path(args.events_db),
        event_signals_db_path=Path(args.event_signals_db),
        source_ids=parse_source_ids(args.source_ids),
        limit=max(1, int(args.limit)),
    )
    json_text = json.dumps(report, ensure_ascii=False, indent=args.indent) + "\n"
    write_if_requested(args.output_json, json_text)
    if args.output_md:
        write_if_requested(args.output_md, render_markdown(report))
    if not args.output_json:
        print(json_text, end="")
    else:
        summary = report["summary"]
        print(
            "event normalization audit: "
            f"records={summary['records_total']} "
            f"same_event_groups={summary['same_event_candidate_groups']} "
            f"normalization_gap_records={summary['normalization_gap_records']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
