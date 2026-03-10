"""Build supplement evaluation report for ticketjam_events."""

from __future__ import annotations

import argparse
import json
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .events.registry import load_registry as load_venue_registry
from .signals.artist_registry import ArtistEntry, load_registry as load_artist_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
EVENT_SIGNALS_DB_PATH = DATA_DIR / "event_signals.sqlite"
EVENTS_DB_PATH = DATA_DIR / "events.sqlite"
OUTPUT_JSON_PATH = DATA_DIR / "ticketjam_supplement_report.json"
OUTPUT_MD_PATH = DATA_DIR / "ticketjam_supplement_report.md"
EXCLUDE_TITLE_KEYWORDS = ("駐車場券", "駐車券", "駐車場")


@dataclass(frozen=True)
class ScheduleRecord:
    source_id: str
    event_date: str
    venue_name: str
    artist_name: str
    pref_name: str
    event_category: str

    def schedule_key(self) -> tuple[str, str, str]:
        return (
            self.event_date,
            normalize_compare_text(self.venue_name),
            normalize_compare_text(self.artist_name),
        )


def normalize_compare_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    value = value.replace("\u3000", " ")
    return " ".join(value.split())


def build_artist_alias_map(registry: list[ArtistEntry]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for entry in registry:
        names = [entry.canonical_name, *entry.aliases]
        for name in names:
            normalized = normalize_compare_text(name)
            if normalized:
                alias_map[normalized] = entry.canonical_name
    return alias_map


def canonicalize_artist_name(name: str, alias_map: dict[str, str]) -> str:
    normalized = normalize_compare_text(name)
    if not normalized:
        return ""
    return alias_map.get(normalized, str(name or "").strip())


def split_artist_names(raw: str, alias_map: dict[str, str]) -> tuple[str, ...]:
    text = str(raw or "").strip()
    if not text:
        return tuple()
    candidates = [text]
    for delimiter in [" / ", "/", "／", "、", ",", "\n", "&"]:
        next_candidates: list[str] = []
        for candidate in candidates:
            if delimiter in candidate:
                next_candidates.extend(candidate.split(delimiter))
            else:
                next_candidates.append(candidate)
        candidates = next_candidates
    resolved: list[str] = []
    for candidate in candidates:
        canonical = canonicalize_artist_name(candidate, alias_map)
        if canonical:
            resolved.append(canonical)
    return tuple(dict.fromkeys(resolved))


def load_signal_source_updates(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT source_id, updated_at_utc
        FROM signal_sources
        WHERE source_id IN ('ticketjam_events', 'starto_concert', 'kstyle_music')
        """
    ).fetchall()
    return {str(source_id): str(updated_at_utc) for source_id, updated_at_utc in rows}


def load_signal_records(
    conn: sqlite3.Connection, source_ids: tuple[str, ...], alias_map: dict[str, str]
) -> list[ScheduleRecord]:
    placeholders = ",".join("?" for _ in source_ids)
    rows = conn.execute(
        f"""
        SELECT source_id, title, labels_json
        FROM signals
        WHERE source_id IN ({placeholders})
        """,
        source_ids,
    ).fetchall()
    records: list[ScheduleRecord] = []
    for source_id, title, raw_labels in rows:
        title_text = str(title or "").strip()
        if any(keyword in title_text for keyword in EXCLUDE_TITLE_KEYWORDS):
            continue
        try:
            labels = json.loads(raw_labels)
        except Exception:
            continue
        event_date = str(labels.get("event_start_date", "") or "").strip()
        venue_name = str(labels.get("venue_name", "") or "").strip()
        artist_name = canonicalize_artist_name(
            str(labels.get("artist_name", "") or ""), alias_map
        )
        if not event_date or not venue_name or not artist_name:
            continue
        records.append(
            ScheduleRecord(
                source_id=str(source_id),
                event_date=event_date,
                venue_name=venue_name,
                artist_name=artist_name,
                pref_name=str(labels.get("pref_name", "") or "").strip(),
                event_category=str(labels.get("event_category", "") or "").strip(),
            )
        )
    return records


def load_official_records(
    events_db_path: Path,
    venue_name_by_id: dict[str, str],
    alias_map: dict[str, str],
) -> list[ScheduleRecord]:
    if not events_db_path.exists():
        return []
    conn = sqlite3.connect(str(events_db_path))
    rows = conn.execute(
        """
        SELECT venue_id, start_date, performers, artist_name_resolved, event_category
        FROM events
        WHERE start_date IS NOT NULL
        """
    ).fetchall()
    conn.close()
    records: list[ScheduleRecord] = []
    for venue_id, start_date, performers, artist_name_resolved, event_category in rows:
        venue_name = venue_name_by_id.get(str(venue_id or "").strip(), "").strip()
        event_date = str(start_date or "").strip()
        if not venue_name or not event_date:
            continue
        artists = split_artist_names(str(artist_name_resolved or "").strip(), alias_map)
        if not artists:
            artists = split_artist_names(str(performers or "").strip(), alias_map)
        for artist_name in artists:
            records.append(
                ScheduleRecord(
                    source_id="official_events",
                    event_date=event_date,
                    venue_name=venue_name,
                    artist_name=artist_name,
                    pref_name="",
                    event_category=str(event_category or "").strip(),
                )
            )
    return records


def collect_unique_keys(
    records: list[ScheduleRecord],
) -> tuple[set[tuple[str, str, str]], dict[tuple[str, str, str], ScheduleRecord]]:
    unique: dict[tuple[str, str, str], ScheduleRecord] = {}
    for record in records:
        unique.setdefault(record.schedule_key(), record)
    return set(unique.keys()), unique


def compute_scope_rows(
    ticketjam_by_key: dict[tuple[str, str, str], ScheduleRecord],
    baseline_keys: set[tuple[str, str, str]],
    watched_artist_names: set[str],
    watched_venues_by_name: dict[str, dict[str, object]],
    artist_tiers: dict[str, str],
) -> dict[str, object]:
    artist_rows: list[dict[str, object]] = []
    venue_rows: list[dict[str, object]] = []

    artist_metrics: dict[str, dict[str, object]] = {}
    for artist_name in sorted(watched_artist_names):
        artist_metrics[artist_name] = {
            "artist_name": artist_name,
            "ticketjam_hits": set(),
            "additional_hits": set(),
            "venues": set(),
            "categories": Counter(),
            "tier": artist_tiers.get(artist_name, ""),
        }

    venue_metrics: dict[str, dict[str, object]] = {}
    for venue_name, attrs in watched_venues_by_name.items():
        venue_metrics[venue_name] = {
            "venue_name": venue_name,
            "ticketjam_hits": set(),
            "additional_hits": set(),
            "artists": set(),
            "categories": Counter(),
            "official_fetch_candidate": bool(attrs.get("official_fetch_candidate")),
            "official_gap_reason": str(attrs.get("official_gap_reason", "") or ""),
            "ticketjam_watch": bool(attrs.get("ticketjam_watch")),
        }

    in_scope_keys: set[tuple[str, str, str]] = set()
    artist_scope_keys: set[tuple[str, str, str]] = set()
    venue_scope_keys: set[tuple[str, str, str]] = set()

    for key, record in ticketjam_by_key.items():
        artist_name = record.artist_name
        venue_name = record.venue_name
        matched_artist = artist_name in artist_metrics
        matched_venue = venue_name in venue_metrics
        is_additional = key not in baseline_keys
        if matched_artist:
            metric = artist_metrics[artist_name]
            metric["ticketjam_hits"].add(key)
            metric["venues"].add(record.venue_name)
            metric["categories"][record.event_category or ""] += 1
            artist_scope_keys.add(key)
            in_scope_keys.add(key)
            if is_additional:
                metric["additional_hits"].add(key)
        if matched_venue:
            metric = venue_metrics[venue_name]
            metric["ticketjam_hits"].add(key)
            metric["artists"].add(record.artist_name)
            metric["categories"][record.event_category or ""] += 1
            venue_scope_keys.add(key)
            in_scope_keys.add(key)
            if is_additional:
                metric["additional_hits"].add(key)

    for artist_name, metric in artist_metrics.items():
        hits = len(metric["ticketjam_hits"])
        additional = len(metric["additional_hits"])
        overlap = hits - additional
        artist_rows.append(
            {
                "artist_name": artist_name,
                "tier": metric["tier"],
                "ticketjam_hits": hits,
                "additional_hits": additional,
                "overlap_hits": overlap,
                "noise_rate": round(overlap / hits, 4) if hits else 0.0,
                "venues": sorted(metric["venues"]),
                "category_counts": dict(sorted(metric["categories"].items())),
            }
        )

    for venue_name, metric in venue_metrics.items():
        hits = len(metric["ticketjam_hits"])
        additional = len(metric["additional_hits"])
        overlap = hits - additional
        venue_rows.append(
            {
                "venue_name": venue_name,
                "ticketjam_hits": hits,
                "additional_hits": additional,
                "overlap_hits": overlap,
                "noise_rate": round(overlap / hits, 4) if hits else 0.0,
                "artists": sorted(metric["artists"]),
                "category_counts": dict(sorted(metric["categories"].items())),
                "ticketjam_watch": metric["ticketjam_watch"],
                "official_fetch_candidate": metric["official_fetch_candidate"],
                "official_gap_reason": metric["official_gap_reason"],
            }
        )

    artist_rows.sort(
        key=lambda row: (
            tier_rank(str(row["tier"])),
            -int(row["additional_hits"]),
            -int(row["ticketjam_hits"]),
            str(row["artist_name"]),
        )
    )
    venue_rows.sort(
        key=lambda row: (
            -int(row["additional_hits"]),
            -int(row["ticketjam_hits"]),
            str(row["venue_name"]),
        )
    )

    out_of_scope_keys = set(ticketjam_by_key.keys()) - in_scope_keys
    additional_in_scope = {key for key in in_scope_keys if key not in baseline_keys}
    overlap_in_scope = in_scope_keys - additional_in_scope

    return {
        "artist_rows": artist_rows,
        "venue_rows": venue_rows,
        "scope_summary": {
            "in_scope_unique_schedules": len(in_scope_keys),
            "artist_scope_unique_schedules": len(artist_scope_keys),
            "venue_scope_unique_schedules": len(venue_scope_keys),
            "additional_unique_schedules": len(additional_in_scope),
            "overlap_unique_schedules": len(overlap_in_scope),
            "noise_rate": round(len(overlap_in_scope) / len(in_scope_keys), 4)
            if in_scope_keys
            else 0.0,
            "out_of_scope_unique_schedules": len(out_of_scope_keys),
            "out_of_scope_rate": round(
                len(out_of_scope_keys) / len(ticketjam_by_key), 4
            )
            if ticketjam_by_key
            else 0.0,
        },
    }


def tier_rank(tier: str) -> int:
    order = {"S": 0, "A": 1, "B": 2, "reference": 3, "": 4}
    return order.get(tier, 9)


def build_report_data(
    ticketjam_records: list[ScheduleRecord],
    news_records: list[ScheduleRecord],
    official_records: list[ScheduleRecord],
    watched_artists: list[ArtistEntry],
    watched_venues: list[dict[str, object]],
    source_updates: dict[str, str],
    events_db_path: Path,
) -> dict[str, object]:
    ticketjam_keys, ticketjam_by_key = collect_unique_keys(ticketjam_records)
    news_keys, _ = collect_unique_keys(news_records)
    official_keys, _ = collect_unique_keys(official_records)
    baseline_keys = news_keys | official_keys

    watched_artist_names = {entry.canonical_name for entry in watched_artists}
    artist_tiers = {
        entry.canonical_name: entry.ticketjam_benchmark_tier for entry in watched_artists
    }
    watched_venues_by_name = {
        str(row["venue_name"]): row
        for row in watched_venues
        if str(row.get("venue_name", "")).strip()
    }
    scope = compute_scope_rows(
        ticketjam_by_key=ticketjam_by_key,
        baseline_keys=baseline_keys,
        watched_artist_names=watched_artist_names,
        watched_venues_by_name=watched_venues_by_name,
        artist_tiers=artist_tiers,
    )

    category_counts = Counter(
        record.event_category or "" for record in ticketjam_by_key.values()
    )
    events_db_mtime_utc = ""
    if events_db_path.exists():
        events_db_mtime_utc = datetime.fromtimestamp(
            events_db_path.stat().st_mtime, tz=UTC
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "report_name": "ticketjam_supplement_report",
        "report_version": 1,
        "inputs": {
            "ticketjam_source_updated_at_utc": source_updates.get("ticketjam_events", ""),
            "starto_source_updated_at_utc": source_updates.get("starto_concert", ""),
            "kstyle_source_updated_at_utc": source_updates.get("kstyle_music", ""),
            "events_db_modified_at_utc": events_db_mtime_utc,
        },
        "summary": {
            "ticketjam_unique_schedules": len(ticketjam_keys),
            "baseline_news_unique_schedules": len(news_keys),
            "baseline_official_unique_schedules": len(official_keys),
            "ticketjam_category_counts": dict(sorted(category_counts.items())),
            **scope["scope_summary"],
        },
        "artist_gap": {
            "watch_count": len(watched_artists),
            "rows": scope["artist_rows"],
        },
        "venue_gap": {
            "watch_count": len(watched_venues_by_name),
            "rows": scope["venue_rows"],
        },
        "methodology": {
            "baseline_sources": [
                "events.sqlite",
                "event_signals.sqlite:starto_concert",
                "event_signals.sqlite:kstyle_music",
            ],
            "schedule_key": "event_date + canonical venue_name + canonical artist_name",
            "additional_hits": "Ticketjam schedule key が既存ソース baseline に存在しない件数",
            "noise_rate": "監視スコープ内 Ticketjam schedule のうち baseline と重複した比率",
            "out_of_scope_rate": "Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率",
        },
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    artist_rows = report["artist_gap"]["rows"]
    venue_rows = report["venue_gap"]["rows"]
    lines = [
        "# Ticketjam Supplement Report",
        "",
        "## Summary",
        f"- ticketjam_unique_schedules: {summary['ticketjam_unique_schedules']}",
        f"- additional_unique_schedules: {summary['additional_unique_schedules']}",
        f"- overlap_unique_schedules: {summary['overlap_unique_schedules']}",
        f"- noise_rate: {summary['noise_rate']}",
        f"- out_of_scope_rate: {summary['out_of_scope_rate']}",
        f"- ticketjam_category_counts: {json.dumps(summary['ticketjam_category_counts'], ensure_ascii=False)}",
        "",
        "## Artist Gap",
        "",
        "| tier | artist_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | venues |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in artist_rows:
        lines.append(
            "| {tier} | {artist_name} | {ticketjam_hits} | {additional_hits} | {overlap_hits} | {noise_rate:.4f} | {venues} |".format(
                tier=row["tier"] or "",
                artist_name=row["artist_name"],
                ticketjam_hits=row["ticketjam_hits"],
                additional_hits=row["additional_hits"],
                overlap_hits=row["overlap_hits"],
                noise_rate=float(row["noise_rate"]),
                venues=", ".join(row["venues"]),
            )
        )
    lines.extend(
        [
            "",
            "## Venue Gap",
            "",
            "| venue_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | official_fetch_candidate | official_gap_reason |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in venue_rows:
        lines.append(
            "| {venue_name} | {ticketjam_hits} | {additional_hits} | {overlap_hits} | {noise_rate:.4f} | {official_fetch_candidate} | {official_gap_reason} |".format(
                venue_name=row["venue_name"],
                ticketjam_hits=row["ticketjam_hits"],
                additional_hits=row["additional_hits"],
                overlap_hits=row["overlap_hits"],
                noise_rate=float(row["noise_rate"]),
                official_fetch_candidate="1"
                if row["official_fetch_candidate"]
                else "0",
                official_gap_reason=row["official_gap_reason"] or "",
            )
        )
    lines.extend(
        [
            "",
            "## Inputs",
            "",
            f"- ticketjam_source_updated_at_utc: {report['inputs']['ticketjam_source_updated_at_utc']}",
            f"- starto_source_updated_at_utc: {report['inputs']['starto_source_updated_at_utc']}",
            f"- kstyle_source_updated_at_utc: {report['inputs']['kstyle_source_updated_at_utc']}",
            f"- events_db_modified_at_utc: {report['inputs']['events_db_modified_at_utc']}",
            "",
            "## Methodology",
            "",
            f"- baseline_sources: {', '.join(report['methodology']['baseline_sources'])}",
            f"- schedule_key: {report['methodology']['schedule_key']}",
            f"- additional_hits: {report['methodology']['additional_hits']}",
            f"- noise_rate: {report['methodology']['noise_rate']}",
            f"- out_of_scope_rate: {report['methodology']['out_of_scope_rate']}",
            "",
        ]
    )
    return "\n".join(lines)


def write_if_changed(path: Path, content: str) -> bool:
    previous = ""
    if path.exists():
        previous = path.read_text(encoding="utf-8")
    if previous == content:
        return False
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def build_and_write_report(
    event_signals_db_path: Path = EVENT_SIGNALS_DB_PATH,
    events_db_path: Path = EVENTS_DB_PATH,
    output_json_path: Path = OUTPUT_JSON_PATH,
    output_md_path: Path = OUTPUT_MD_PATH,
) -> tuple[dict[str, object], bool]:
    signal_conn = sqlite3.connect(str(event_signals_db_path))
    artist_registry = load_artist_registry()
    venue_registry = load_venue_registry()
    alias_map = build_artist_alias_map(artist_registry)

    ticketjam_records = load_signal_records(
        signal_conn, ("ticketjam_events",), alias_map=alias_map
    )
    news_records = load_signal_records(
        signal_conn, ("starto_concert", "kstyle_music"), alias_map=alias_map
    )
    source_updates = load_signal_source_updates(signal_conn)
    signal_conn.close()

    venue_name_by_id = {row.venue_id: row.venue_name for row in venue_registry}
    watched_artists = [row for row in artist_registry if row.ticketjam_watch]
    watched_venues = [
        {
            "venue_name": row.venue_name,
            "ticketjam_watch": row.ticketjam_watch,
            "official_fetch_candidate": row.official_fetch_candidate,
            "official_gap_reason": row.official_gap_reason or "",
        }
        for row in venue_registry
        if row.ticketjam_watch or row.official_fetch_candidate
    ]
    official_records = load_official_records(
        events_db_path=events_db_path,
        venue_name_by_id=venue_name_by_id,
        alias_map=alias_map,
    )
    report = build_report_data(
        ticketjam_records=ticketjam_records,
        news_records=news_records,
        official_records=official_records,
        watched_artists=watched_artists,
        watched_venues=watched_venues,
        source_updates=source_updates,
        events_db_path=events_db_path,
    )
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    markdown_text = render_markdown(report)
    changed_json = write_if_changed(output_json_path, json_text)
    changed_md = write_if_changed(output_md_path, markdown_text)
    return report, changed_json or changed_md


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--event-signals-db",
        default=str(EVENT_SIGNALS_DB_PATH),
        help="path to event_signals.sqlite",
    )
    parser.add_argument(
        "--events-db", default=str(EVENTS_DB_PATH), help="path to events.sqlite"
    )
    parser.add_argument(
        "--output-json",
        default=str(OUTPUT_JSON_PATH),
        help="output path for JSON report",
    )
    parser.add_argument(
        "--output-md",
        default=str(OUTPUT_MD_PATH),
        help="output path for Markdown report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, changed = build_and_write_report(
        event_signals_db_path=Path(args.event_signals_db),
        events_db_path=Path(args.events_db),
        output_json_path=Path(args.output_json),
        output_md_path=Path(args.output_md),
    )
    summary = report["summary"]
    print(
        "ticketjam supplement report: "
        f"ticketjam_unique={summary['ticketjam_unique_schedules']} "
        f"additional={summary['additional_unique_schedules']} "
        f"noise_rate={summary['noise_rate']} "
        f"changed={int(changed)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
