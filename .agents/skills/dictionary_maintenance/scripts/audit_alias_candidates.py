"""Audit event dictionary and category maintenance candidates.

This script is read-only. It inspects event_signals.sqlite and events.sqlite,
then reports candidates that need venue aliases, artist aliases, or category
review before downstream consumers such as LP pages rely on the data.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.events.category import (  # noqa: E402
    EVENT_CATEGORY_CONCERT,
    EVENT_CATEGORY_OTHER,
    classify_event_category,
)
from scripts.signals.artist_registry import (  # noqa: E402
    build_artist_index,
    choose_primary_match,
    load_registry as load_artist_registry,
    match_artists_in_title,
)
from scripts.signals.entity_aliases import (  # noqa: E402
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
)

SIGNALS_DB_PATH = REPO_ROOT / "data" / "event_signals.sqlite"
EVENTS_DB_PATH = REPO_ROOT / "data" / "events.sqlite"
DEFAULT_SOURCE_IDS = ("kstyle_music", "starto_concert", "ticketjam_events")

CONCERT_HINT_RE = re.compile(
    r"(ライブ|コンサート|公演|ツアー|フェス|fan meeting|showcase|live|concert|tour|dome|arena|zepp)",
    re.IGNORECASE,
)
NON_MUSIC_HINT_RE = re.compile(
    r"(展示会|見本市|就活|就職|説明会|式典|授与式|卒業式|入学式|テレビ|放送|配信|受賞式|サッカー|マラソン)",
    re.IGNORECASE,
)


@dataclass
class CandidateBucket:
    count: int = 0
    source_ids: Counter[str] = field(default_factory=Counter)
    examples: list[dict[str, object]] = field(default_factory=list)

    def add(self, source_id: str, example: dict[str, object], max_examples: int = 3) -> None:
        self.count += 1
        if source_id:
            self.source_ids[source_id] += 1
        if len(self.examples) < max_examples:
            self.examples.append(example)

    def to_row(self, name: str, candidate_type: str, suggested_action: str) -> dict[str, object]:
        return {
            "name": name,
            "candidate_type": candidate_type,
            "count": self.count,
            "source_ids": dict(sorted(self.source_ids.items())),
            "suggested_action": suggested_action,
            "examples": self.examples,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit alias and category candidates")
    parser.add_argument(
        "--db-path",
        default=str(SIGNALS_DB_PATH),
        help="Path to event_signals.sqlite",
    )
    parser.add_argument(
        "--events-db",
        default=str(EVENTS_DB_PATH),
        help="Path to events.sqlite",
    )
    parser.add_argument(
        "--source-ids",
        default=",".join(DEFAULT_SOURCE_IDS),
        help="Comma-separated signal source IDs to inspect",
    )
    parser.add_argument("--top", type=int, default=20, help="Top N candidates to include")
    parser.add_argument("--output-json", default="", help="Optional JSON output path")
    parser.add_argument("--output-md", default="", help="Optional Markdown output path")
    return parser.parse_args()


def parse_source_ids(raw: str) -> tuple[str, ...]:
    values = [value.strip() for value in str(raw or "").split(",") if value.strip()]
    return tuple(dict.fromkeys(values))


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


def load_signal_rows(db_path: Path, source_ids: tuple[str, ...]) -> list[sqlite3.Row]:
    if not db_path.exists() or not source_ids:
        return []
    placeholders = ",".join("?" for _ in source_ids)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"""
            SELECT signal_uid, source_id, title, url, labels_json, updated_at_utc
            FROM signals
            WHERE source_id IN ({placeholders})
            AND labels_json IS NOT NULL
            AND TRIM(labels_json) <> ''
            """,
            source_ids,
        ).fetchall()


def load_event_rows(db_path: Path) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT
                e.event_uid,
                e.title,
                e.description,
                e.performers,
                e.artist_name_resolved,
                e.artist_confidence,
                e.event_category,
                e.start_date,
                e.url,
                e.source_url,
                e.updated_at_utc,
                v.venue_name
            FROM events e
            LEFT JOIN venues v ON e.venue_id = v.venue_id
            """
        ).fetchall()


def build_signal_example(row: sqlite3.Row, labels: dict[str, object]) -> dict[str, object]:
    return {
        "source_id": str(row["source_id"] or "").strip(),
        "record_id": str(row["signal_uid"] or "").strip(),
        "event_date": first_nonblank(labels.get("event_start_date"), labels.get("event_date")),
        "title": str(row["title"] or "").strip(),
        "url": str(row["url"] or "").strip(),
    }


def build_event_example(row: sqlite3.Row) -> dict[str, object]:
    return {
        "source_id": "official_events",
        "record_id": str(row["event_uid"] or "").strip(),
        "event_date": str(row["start_date"] or "").strip(),
        "title": str(row["title"] or "").strip(),
        "url": str(row["url"] or row["source_url"] or "").strip(),
    }


def classify_venue_candidate(raw_value: str) -> str:
    text = str(raw_value or "").strip()
    if re.search(r"(北海道|東京都|府|県|市|区|町|村)[/／・\s]", text):
        return "venue_with_area_prefix"
    if re.search(r"(会場|場所|venue)\s*[:：]", text, flags=re.IGNORECASE):
        return "venue_with_label"
    if re.search(r"[（(].{1,20}[）)]$", text):
        return "venue_with_parenthetical_suffix"
    return "unmatched_venue"


def inspect_signals(
    rows: list[sqlite3.Row],
    artist_keep: dict[str, str],
    artist_compact: dict[str, str],
    venue_keep: dict[str, str],
    venue_compact: dict[str, str],
) -> tuple[dict[str, CandidateBucket], dict[str, CandidateBucket], list[dict[str, object]]]:
    venue_candidates: dict[str, CandidateBucket] = defaultdict(CandidateBucket)
    artist_candidates: dict[str, CandidateBucket] = defaultdict(CandidateBucket)
    category_candidates: list[dict[str, object]] = []

    for row in rows:
        labels = parse_labels(row["labels_json"])
        source_id = str(row["source_id"] or "").strip()
        example = build_signal_example(row, labels)

        raw_venue = first_nonblank(labels.get("raw_venue_name"), labels.get("venue_name"))
        if raw_venue:
            _, venue_matched = normalize_venue_with_lookup(raw_venue, venue_keep, venue_compact)
            if not venue_matched:
                venue_candidates[raw_venue].add(source_id, example)

        raw_artist = first_nonblank(
            labels.get("raw_artist_name"),
            labels.get("artist_raw"),
            labels.get("artist_name"),
        )
        if raw_artist:
            _, artist_matched = normalize_with_lookup(raw_artist, artist_keep, artist_compact)
            if not artist_matched:
                artist_candidates[raw_artist].add(source_id, example)

        artist_confidence = str(labels.get("artist_confidence") or "").strip()
        if artist_confidence in {"low", "medium"} and raw_artist:
            review_key = f"{raw_artist} / confidence={artist_confidence}"
            artist_candidates[review_key].add(
                source_id,
                {**example, "artist_confidence": artist_confidence},
            )

        category = first_nonblank(labels.get("event_category"), labels.get("category"))
        artist_name = first_nonblank(labels.get("artist_name"), raw_artist)
        title = str(row["title"] or "").strip()
        expected_category = classify_event_category(title, artist_name, "")
        reason = ""
        if not category:
            reason = "missing_category"
        elif category == EVENT_CATEGORY_OTHER and expected_category == EVENT_CATEGORY_CONCERT:
            reason = "other_but_music_likely"
        elif category in {EVENT_CATEGORY_CONCERT, "concert"} and NON_MUSIC_HINT_RE.search(title):
            reason = "concert_but_non_music_hint"
        if reason:
            category_candidates.append(
                {
                    "candidate_type": reason,
                    "source_id": source_id,
                    "record_id": str(row["signal_uid"] or "").strip(),
                    "event_date": example["event_date"],
                    "title": title,
                    "url": str(row["url"] or "").strip(),
                    "current_category": category,
                    "expected_category": expected_category,
                    "artist_name": artist_name,
                    "lp_impact": "category_change",
                }
            )

    return venue_candidates, artist_candidates, category_candidates


def inspect_events(
    rows: list[sqlite3.Row],
    artist_index: dict[str, object],
    artist_keep: dict[str, str],
    artist_compact: dict[str, str],
) -> tuple[dict[str, CandidateBucket], list[dict[str, object]]]:
    artist_candidates: dict[str, CandidateBucket] = defaultdict(CandidateBucket)
    category_candidates: list[dict[str, object]] = []

    for row in rows:
        title = str(row["title"] or "").strip()
        description = str(row["description"] or "").strip()
        current_artist = str(row["artist_name_resolved"] or "").strip()
        current_category = str(row["event_category"] or "").strip()
        example = build_event_example(row)

        inferred_artist = current_artist
        inferred_confidence = str(row["artist_confidence"] or "").strip()
        if not inferred_artist and title:
            primary, confidence = choose_primary_match(match_artists_in_title(title, artist_index))
            if primary:
                inferred_artist = str(primary.get("canonical_name") or "").strip()
                inferred_confidence = confidence

        if inferred_artist:
            _, artist_matched = normalize_with_lookup(
                inferred_artist, artist_keep, artist_compact
            )
            if not artist_matched:
                artist_candidates[inferred_artist].add("official_events", example)

        if inferred_confidence in {"low", "medium"} and inferred_artist:
            review_key = f"{inferred_artist} / confidence={inferred_confidence}"
            artist_candidates[review_key].add(
                "official_events",
                {**example, "artist_confidence": inferred_confidence},
            )

        expected_category = classify_event_category(title, inferred_artist, description)
        reason = ""
        if not current_category:
            reason = "missing_category"
        elif current_category == EVENT_CATEGORY_OTHER and expected_category == EVENT_CATEGORY_CONCERT:
            reason = "other_but_music_likely"
        elif current_category == EVENT_CATEGORY_CONCERT and NON_MUSIC_HINT_RE.search(
            " ".join([title, description])
        ):
            reason = "concert_but_non_music_hint"
        elif current_category == EVENT_CATEGORY_OTHER and CONCERT_HINT_RE.search(title):
            reason = "other_but_concert_keyword"

        if reason:
            category_candidates.append(
                {
                    "candidate_type": reason,
                    "source_id": "official_events",
                    "record_id": str(row["event_uid"] or "").strip(),
                    "event_date": str(row["start_date"] or "").strip(),
                    "venue_name": str(row["venue_name"] or "").strip(),
                    "title": title,
                    "url": str(row["url"] or row["source_url"] or "").strip(),
                    "current_category": current_category,
                    "expected_category": expected_category,
                    "artist_name": current_artist,
                    "inferred_artist_name": inferred_artist,
                    "inferred_artist_confidence": inferred_confidence,
                    "lp_impact": "category_change",
                }
            )

    return artist_candidates, category_candidates


def sort_candidate_rows(rows: list[dict[str, object]], top_n: int) -> list[dict[str, object]]:
    rows.sort(
        key=lambda row: (
            -int(row.get("count", 0)),
            str(row.get("candidate_type", "")),
            str(row.get("name", "")),
        )
    )
    return rows[:top_n]


def category_candidate_rank(candidate_type: object) -> int:
    order = {
        "other_but_music_likely": 0,
        "other_but_concert_keyword": 1,
        "concert_but_non_music_hint": 2,
        "missing_category": 3,
    }
    return order.get(str(candidate_type or ""), 9)


def build_report(
    signal_rows: list[sqlite3.Row],
    event_rows: list[sqlite3.Row],
    source_ids: tuple[str, ...],
    top_n: int,
) -> dict[str, object]:
    artist_keep, artist_compact = load_artist_lookup_maps()
    venue_keep, venue_compact = load_venue_lookup_maps()
    artist_index = build_artist_index(load_artist_registry())

    venue_buckets, signal_artist_buckets, signal_category_candidates = inspect_signals(
        signal_rows,
        artist_keep,
        artist_compact,
        venue_keep,
        venue_compact,
    )
    event_artist_buckets, event_category_candidates = inspect_events(
        event_rows,
        artist_index,
        artist_keep,
        artist_compact,
    )

    artist_buckets: dict[str, CandidateBucket] = defaultdict(CandidateBucket)
    for source in (signal_artist_buckets, event_artist_buckets):
        for name, bucket in source.items():
            artist_buckets[name].count += bucket.count
            artist_buckets[name].source_ids.update(bucket.source_ids)
            artist_buckets[name].examples.extend(bucket.examples)
            artist_buckets[name].examples = artist_buckets[name].examples[:3]

    venue_alias_candidates = sort_candidate_rows(
        [
            bucket.to_row(
                name=name,
                candidate_type=classify_venue_candidate(name),
                suggested_action="review data/venue_aliases.csv",
            )
            for name, bucket in venue_buckets.items()
        ],
        top_n=top_n,
    )
    artist_alias_candidates = sort_candidate_rows(
        [
            bucket.to_row(
                name=name,
                candidate_type="artist_alias_or_match_review"
                if "confidence=" in name
                else "unmatched_artist",
                suggested_action="review data/artist_registry.manual.csv",
            )
            for name, bucket in artist_buckets.items()
        ],
        top_n=top_n,
    )
    category_review_candidates_all = sorted(
        signal_category_candidates + event_category_candidates,
        key=lambda row: (
            category_candidate_rank(row.get("candidate_type", "")),
            str(row.get("candidate_type", "")),
            str(row.get("source_id", "")),
            str(row.get("event_date", "")),
            str(row.get("title", "")),
        ),
    )
    category_review_candidates = category_review_candidates_all[:top_n]
    category_counts = Counter(
        str(row.get("candidate_type", "")) for row in category_review_candidates_all
    )

    return {
        "report_name": "dictionary_maintenance_audit",
        "report_version": 2,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "event_signals_db": str(SIGNALS_DB_PATH),
            "events_db": str(EVENTS_DB_PATH),
            "signal_source_ids": list(source_ids),
            "signal_rows": len(signal_rows),
            "official_event_rows": len(event_rows),
        },
        "summary": {
            "venue_alias_candidates": len(venue_alias_candidates),
            "artist_alias_candidates": len(artist_alias_candidates),
            "category_review_candidates": len(category_review_candidates),
            "category_review_candidates_total": len(category_review_candidates_all),
            "category_review_counts": dict(sorted(category_counts.items())),
            "lp_impact": "none",
            "lp_impact_reason": "監査レポート生成のみで、配布DB、manifest、Release assetは変更しない。",
        },
        "venue_alias_candidates": venue_alias_candidates,
        "artist_alias_candidates": artist_alias_candidates,
        "category_review_candidates": category_review_candidates,
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Dictionary Maintenance Audit",
        "",
        "## Summary",
        f"- venue_alias_candidates: {summary['venue_alias_candidates']}",
        f"- artist_alias_candidates: {summary['artist_alias_candidates']}",
        f"- category_review_candidates: {summary['category_review_candidates']}",
        f"- category_review_counts: {json.dumps(summary['category_review_counts'], ensure_ascii=False)}",
        f"- lp_impact: {summary['lp_impact']}",
        f"- lp_impact_reason: {summary['lp_impact_reason']}",
        "",
        "## Venue Alias Candidates",
        "",
        "| count | type | name | source_ids |",
        "| ---: | --- | --- | --- |",
    ]
    for row in report["venue_alias_candidates"]:
        lines.append(
            f"| {row['count']} | {row['candidate_type']} | {row['name']} | {json.dumps(row['source_ids'], ensure_ascii=False)} |"
        )
    lines.extend(
        [
            "",
            "## Artist Alias Candidates",
            "",
            "| count | type | name | source_ids |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for row in report["artist_alias_candidates"]:
        lines.append(
            f"| {row['count']} | {row['candidate_type']} | {row['name']} | {json.dumps(row['source_ids'], ensure_ascii=False)} |"
        )
    lines.extend(
        [
            "",
            "## Category Review Candidates",
            "",
            "| type | source_id | event_date | current | expected | artist | title |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["category_review_candidates"]:
        title = str(row.get("title", "")).replace("|", "/")
        artist = str(row.get("artist_name") or row.get("inferred_artist_name") or "")
        lines.append(
            "| {candidate_type} | {source_id} | {event_date} | {current_category} | {expected_category} | {artist} | {title} |".format(
                candidate_type=row.get("candidate_type", ""),
                source_id=row.get("source_id", ""),
                event_date=row.get("event_date", ""),
                current_category=row.get("current_category", ""),
                expected_category=row.get("expected_category", ""),
                artist=artist,
                title=title,
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_if_requested(path_text: str, content: str) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def print_text_summary(report: dict[str, object]) -> None:
    summary = report["summary"]
    print(f"signals_rows={report['inputs']['signal_rows']}")
    print(f"official_event_rows={report['inputs']['official_event_rows']}")
    print(f"venue_alias_candidates={summary['venue_alias_candidates']}")
    print(f"artist_alias_candidates={summary['artist_alias_candidates']}")
    print(f"category_review_candidates={summary['category_review_candidates']}")
    print(f"lp_impact={summary['lp_impact']}")
    print("")
    print("=== Venue Alias Candidates ===")
    for row in report["venue_alias_candidates"]:
        print(f"{row['count']:4d} | {row['candidate_type']} | {row['name']}")
    print("")
    print("=== Artist Alias Candidates ===")
    for row in report["artist_alias_candidates"]:
        print(f"{row['count']:4d} | {row['candidate_type']} | {row['name']}")
    print("")
    print("=== Category Review Candidates ===")
    for row in report["category_review_candidates"]:
        print(
            "{candidate_type} | {source_id} | {event_date} | {current_category} -> {expected_category} | {title}".format(
                candidate_type=row.get("candidate_type", ""),
                source_id=row.get("source_id", ""),
                event_date=row.get("event_date", ""),
                current_category=row.get("current_category", ""),
                expected_category=row.get("expected_category", ""),
                title=row.get("title", ""),
            )
        )


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    events_db_path = Path(args.events_db)
    source_ids = parse_source_ids(args.source_ids)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    if not events_db_path.exists():
        raise SystemExit(f"Events DB not found: {events_db_path}")

    signal_rows = load_signal_rows(db_path, source_ids)
    event_rows = load_event_rows(events_db_path)
    report = build_report(signal_rows, event_rows, source_ids, max(1, int(args.top)))
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_if_requested(args.output_json, json_text)
    if args.output_md:
        write_if_requested(args.output_md, render_markdown(report))
    if args.output_json:
        summary = report["summary"]
        print(
            "dictionary maintenance audit: "
            f"venue={summary['venue_alias_candidates']} "
            f"artist={summary['artist_alias_candidates']} "
            f"category={summary['category_review_candidates']} "
            f"lp_impact={summary['lp_impact']}"
        )
    else:
        print_text_summary(report)


if __name__ == "__main__":
    main()
