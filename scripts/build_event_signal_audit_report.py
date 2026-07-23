"""Build a unified event-signal audit report for Codex automation.

The unified report combines:

- K-Style coverage audit output, when provided as JSON.
- Event-level normalization audit output.
- Dictionary/category maintenance audit output.

This script does not mutate events.sqlite, event_signals.sqlite, manifest.json,
or release assets. Its own LP impact is always none; candidate rows may still
describe the LP impact that would occur if a proposed fix is applied later.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .audit_event_normalization_candidates import (
    DEFAULT_SIGNAL_SOURCE_IDS,
    EVENTS_DB_PATH,
    EVENT_SIGNALS_DB_PATH,
    build_audit_report as build_normalization_audit_report,
    parse_source_ids,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DEFAULT_OUTPUT_JSON_PATH = DATA_DIR / "event_signal_audit_report.json"
DEFAULT_OUTPUT_MD_PATH = DATA_DIR / "event_signal_audit_report.md"
DICTIONARY_AUDIT_SCRIPT_PATH = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "dictionary-maintenance"
    / "scripts"
    / "audit_alias_candidates.py"
)


def load_json(path_text: str) -> dict[str, object] | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        parsed = json.load(f)
    if not isinstance(parsed, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return parsed


def load_dictionary_audit_module():
    spec = importlib.util.spec_from_file_location(
        "dictionary_audit_candidates", DICTIONARY_AUDIT_SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load: {DICTIONARY_AUDIT_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_dictionary_report(
    *, source_ids: tuple[str, ...], top_n: int
) -> dict[str, object]:
    module = load_dictionary_audit_module()
    signal_rows = module.load_signal_rows(EVENT_SIGNALS_DB_PATH, source_ids)
    event_rows = module.load_event_rows(EVENTS_DB_PATH)
    report = module.build_report(signal_rows, event_rows, source_ids, top_n)
    if not isinstance(report, dict):
        raise RuntimeError("dictionary audit report did not return a dict")
    return report


def normalize_kstyle_report(report: dict[str, object] | None) -> dict[str, object]:
    if report is None:
        return {
            "status": "skipped",
            "summary": {},
            "missed_articles": [],
            "missed_occurrences": [],
            "needs_review": [],
        }
    rows = [row for row in report.get("candidates", []) if isinstance(row, dict)]
    missed_articles: list[dict[str, object]] = []
    missed_occurrences: list[dict[str, object]] = []
    needs_review: list[dict[str, object]] = []
    for row in rows:
        if bool(row.get("exists_in_db")):
            continue
        reasons = [str(item) for item in row.get("miss_reason") or []]
        parser_occurrences = [
            item for item in row.get("parser_occurrences") or [] if isinstance(item, dict)
        ]
        bucket = "human_review" if "parser_gap" in reasons else "pr_candidate"
        missed = {
            "source_id": "kstyle_music",
            "url": row.get("url", ""),
            "title": row.get("title", ""),
            "published_at_utc": row.get("published_at_utc", ""),
            "entry_points": row.get("entry_points", []),
            "miss_reason": reasons,
            "parser_occurrence_count": row.get("parser_occurrence_count", 0),
            "automation_bucket": bucket,
            "lp_impact": "display_count_change",
            "needs_review_reason": reasons,
        }
        missed_articles.append(missed)
        needs_review.append(
            {
                "source_section": "missed_articles",
                "automation_bucket": bucket,
                "reason": reasons,
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                "lp_impact": "display_count_change",
            }
        )
        for occurrence in parser_occurrences:
            missed_occurrences.append(
                {
                    "source_id": "kstyle_music",
                    "url": row.get("url", ""),
                    "title": row.get("title", ""),
                    "event_start_date": occurrence.get("event_start_date", ""),
                    "venue_name": occurrence.get("venue_name", ""),
                    "pref_name": occurrence.get("pref_name", ""),
                    "event_info": occurrence.get("event_info", ""),
                    "lp_impact": "display_count_change",
                }
            )
    return {
        "status": "loaded",
        "summary": report.get("summary", {}),
        "missed_articles": missed_articles,
        "missed_occurrences": missed_occurrences,
        "needs_review": needs_review,
    }


def normalize_event_report(report: dict[str, object]) -> dict[str, object]:
    same_event_candidates = [
        {
            **row,
            "automation_bucket": "report_only",
            "lp_impact": "duplicate_grouping_change",
            "needs_review_reason": [],
        }
        for row in report.get("same_event_candidates", [])
        if isinstance(row, dict)
    ]
    normalization_gap = [
        {
            **row,
            "automation_bucket": "human_review",
            "lp_impact": "duplicate_grouping_change",
            "needs_review_reason": row.get("normalization_gaps", []),
        }
        for row in report.get("normalization_gap", [])
        if isinstance(row, dict)
    ]
    return {
        "summary": report.get("summary", {}),
        "same_event_candidates": same_event_candidates,
        "normalization_gap": normalization_gap,
        "needs_review": [
            {
                "source_section": "normalization_gap",
                "automation_bucket": "human_review",
                "reason": row.get("normalization_gaps", []),
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                "lp_impact": "duplicate_grouping_change",
            }
            for row in normalization_gap
        ],
    }


def normalize_dictionary_report(report: dict[str, object]) -> dict[str, object]:
    venue_alias_candidates = [
        {
            **row,
            "automation_bucket": "human_review",
            "lp_impact": "duplicate_grouping_change",
            "needs_review_reason": [row.get("candidate_type", "venue_alias_candidate")],
        }
        for row in report.get("venue_alias_candidates", [])
        if isinstance(row, dict)
    ]
    artist_alias_candidates = [
        {
            **row,
            "automation_bucket": "human_review",
            "lp_impact": "duplicate_grouping_change",
            "needs_review_reason": [row.get("candidate_type", "artist_alias_candidate")],
        }
        for row in report.get("artist_alias_candidates", [])
        if isinstance(row, dict)
    ]
    category_review_candidates = [
        {
            **row,
            "automation_bucket": "human_review",
            "lp_impact": row.get("lp_impact") or "category_change",
            "needs_review_reason": [row.get("candidate_type", "category_review")],
        }
        for row in report.get("category_review_candidates", [])
        if isinstance(row, dict)
    ]
    needs_review: list[dict[str, object]] = []
    for section_name, rows in [
        ("venue_alias_candidates", venue_alias_candidates),
        ("artist_alias_candidates", artist_alias_candidates),
        ("category_review_candidates", category_review_candidates),
    ]:
        for row in rows:
            needs_review.append(
                {
                    "source_section": section_name,
                    "automation_bucket": row.get("automation_bucket", "human_review"),
                    "reason": row.get("needs_review_reason", []),
                    "title": row.get("title") or row.get("name") or "",
                    "url": row.get("url", ""),
                    "lp_impact": row.get("lp_impact", ""),
                }
            )
    return {
        "summary": report.get("summary", {}),
        "venue_alias_candidates": venue_alias_candidates,
        "artist_alias_candidates": artist_alias_candidates,
        "category_review_candidates": category_review_candidates,
        "needs_review": needs_review,
    }


def count_lp_impacts(rows: Iterable[dict[str, object]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = row.get("lp_impact")
        if isinstance(value, list):
            counts.update(str(item) for item in value if str(item))
        elif value:
            counts[str(value)] += 1
    return dict(sorted(counts.items()))


def build_unified_report(
    *,
    kstyle_report: dict[str, object] | None,
    normalization_report: dict[str, object],
    dictionary_report: dict[str, object],
) -> dict[str, object]:
    kstyle = normalize_kstyle_report(kstyle_report)
    normalization = normalize_event_report(normalization_report)
    dictionary = normalize_dictionary_report(dictionary_report)

    missed_articles = kstyle["missed_articles"]
    missed_occurrences = kstyle["missed_occurrences"]
    same_event_candidates = normalization["same_event_candidates"]
    venue_alias_candidates = dictionary["venue_alias_candidates"]
    artist_alias_candidates = dictionary["artist_alias_candidates"]
    category_review_candidates = dictionary["category_review_candidates"]
    needs_review = (
        list(kstyle["needs_review"])
        + list(normalization["needs_review"])
        + list(dictionary["needs_review"])
    )

    candidate_rows = (
        list(missed_articles)
        + list(missed_occurrences)
        + list(same_event_candidates)
        + list(venue_alias_candidates)
        + list(artist_alias_candidates)
        + list(category_review_candidates)
    )
    bucket_counts = Counter(
        str(row.get("automation_bucket") or "report_only") for row in candidate_rows
    )
    return {
        "report_name": "event_signal_audit_report",
        "report_version": 1,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component_status": {
            "kstyle_coverage": kstyle["status"],
            "event_normalization": "loaded",
            "dictionary_maintenance": "loaded",
        },
        "summary": {
            "missed_articles": len(missed_articles),
            "missed_occurrences": len(missed_occurrences),
            "same_event_candidates": len(same_event_candidates),
            "venue_alias_candidates": len(venue_alias_candidates),
            "artist_alias_candidates": len(artist_alias_candidates),
            "category_review_candidates": len(category_review_candidates),
            "needs_review_count": len(needs_review),
            "automation_bucket_counts": dict(sorted(bucket_counts.items())),
            "candidate_lp_impact_counts": count_lp_impacts(candidate_rows),
            "lp_impact": "none",
            "lp_impact_reason": "統合監査レポート生成のみで、配布DB、manifest、Release assetは変更しない。",
        },
        "source_summaries": {
            "kstyle_coverage": kstyle["summary"],
            "event_normalization": normalization["summary"],
            "dictionary_maintenance": dictionary["summary"],
        },
        "missed_articles": missed_articles,
        "missed_occurrences": missed_occurrences,
        "same_event_candidates": same_event_candidates,
        "normalization_gap": normalization["normalization_gap"],
        "venue_alias_candidates": venue_alias_candidates,
        "artist_alias_candidates": artist_alias_candidates,
        "category_review_candidates": category_review_candidates,
        "needs_review": needs_review,
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Event Signal Audit Report",
        "",
        "## Summary",
        f"- missed_articles: {summary['missed_articles']}",
        f"- missed_occurrences: {summary['missed_occurrences']}",
        f"- same_event_candidates: {summary['same_event_candidates']}",
        f"- venue_alias_candidates: {summary['venue_alias_candidates']}",
        f"- artist_alias_candidates: {summary['artist_alias_candidates']}",
        f"- category_review_candidates: {summary['category_review_candidates']}",
        f"- needs_review_count: {summary['needs_review_count']}",
        f"- automation_bucket_counts: {json.dumps(summary['automation_bucket_counts'], ensure_ascii=False)}",
        f"- candidate_lp_impact_counts: {json.dumps(summary['candidate_lp_impact_counts'], ensure_ascii=False)}",
        f"- lp_impact: {summary['lp_impact']}",
        f"- lp_impact_reason: {summary['lp_impact_reason']}",
        "",
        "## Needs Review",
        "",
        "| section | bucket | lp_impact | reason | title |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["needs_review"][:80]:
        title = str(row.get("title", "")).replace("|", "/")
        reason = json.dumps(row.get("reason", []), ensure_ascii=False)
        lines.append(
            "| {section} | {bucket} | {lp_impact} | {reason} | {title} |".format(
                section=row.get("source_section", ""),
                bucket=row.get("automation_bucket", ""),
                lp_impact=row.get("lp_impact", ""),
                reason=reason,
                title=title,
            )
        )

    lines.extend(
        [
            "",
            "## Same Event Candidates",
            "",
            "| event_date | venue | artist | source_ids | record_count |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for row in report["same_event_candidates"][:40]:
        lines.append(
            "| {event_date} | {venue} | {artist} | {sources} | {record_count} |".format(
                event_date=row.get("event_date", ""),
                venue=row.get("canonical_venue_name", ""),
                artist=row.get("canonical_artist_name", ""),
                sources=", ".join(row.get("source_ids", [])),
                record_count=row.get("record_count", 0),
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kstyle-json", default="")
    parser.add_argument("--normalization-json", default="")
    parser.add_argument("--dictionary-json", default="")
    parser.add_argument(
        "--source-ids",
        default=",".join(DEFAULT_SIGNAL_SOURCE_IDS),
        help="comma-separated signal source IDs for local audits",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dictionary-top", type=int, default=100)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON_PATH))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD_PATH))
    parser.add_argument("--indent", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    source_ids = parse_source_ids(args.source_ids)
    kstyle_report = load_json(args.kstyle_json)
    normalization_report = load_json(args.normalization_json)
    if normalization_report is None:
        normalization_report = build_normalization_audit_report(
            events_db_path=EVENTS_DB_PATH,
            event_signals_db_path=EVENT_SIGNALS_DB_PATH,
            source_ids=source_ids,
            limit=max(1, int(args.limit)),
        )
    dictionary_report = load_json(args.dictionary_json)
    if dictionary_report is None:
        dictionary_report = build_dictionary_report(
            source_ids=source_ids,
            top_n=max(1, int(args.dictionary_top)),
        )

    report = build_unified_report(
        kstyle_report=kstyle_report,
        normalization_report=normalization_report,
        dictionary_report=dictionary_report,
    )
    json_text = json.dumps(report, ensure_ascii=False, indent=args.indent) + "\n"
    write_text(Path(args.output_json), json_text)
    if args.output_md:
        write_text(Path(args.output_md), render_markdown(report))
    summary = report["summary"]
    print(
        "event signal audit report: "
        f"missed_articles={summary['missed_articles']} "
        f"same_event_candidates={summary['same_event_candidates']} "
        f"venue_alias_candidates={summary['venue_alias_candidates']} "
        f"artist_alias_candidates={summary['artist_alias_candidates']} "
        f"category_review_candidates={summary['category_review_candidates']} "
        f"lp_impact={summary['lp_impact']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
