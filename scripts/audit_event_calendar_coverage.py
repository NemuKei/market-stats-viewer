"""Read-only collection → ID review → publication coverage report (Issue #42).

Uses the existing venue inventory and pending-review generator. Counts identify
where to inspect; neither a zero count nor a same-day pair proves an error.
No source fetches, event approvals, database writes, or publication changes.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from .audit_national_event_coverage import _normal, read_inputs


def event_days(row: dict, start: date, end: date) -> set[str]:
    first = date.fromisoformat(row["event_date"])
    last = date.fromisoformat(row.get("event_end_date") or row["event_date"])
    if first > last:
        raise ValueError("event end precedes start")
    lo, hi = max(first, start), min(last, end)
    return {(lo + timedelta(days=i)).isoformat() for i in range((hi - lo).days + 1)}


def longest_gap(days: set[str], start: date, end: date) -> int:
    longest = current = 0
    for i in range((end - start).days + 1):
        current = 0 if (start + timedelta(days=i)).isoformat() in days else current + 1
        longest = max(longest, current)
    return longest


def audit_runtime(
    inventory: dict,
    official: list[dict],
    signals: list[dict],
    public: dict,
    pending: dict,
    registry: dict,
    *,
    start: date,
    end: date,
    expectations: dict | None = None,
    fetch_report: dict | None = None,
) -> dict:
    if start > end or (end - start).days > 366:
        raise ValueError("coverage window must be 1..367 days")
    expectations = expectations or {}
    venues = {row["venue_id"]: dict(row) for row in inventory["venues"]}
    names = {_normal(row["venue_name"]): key for key, row in venues.items()}
    raw = defaultdict(list)
    for row in official + signals:
        if row["venue_id"] in venues and event_days(row, start, end):
            raw[row["venue_id"]].append(row)
    published, held, programme, registered = (defaultdict(list) for _ in range(4))
    unmapped = Counter()
    for row in public["events"]:
        if not event_days(row, start, end):
            continue
        key = names.get(_normal(row["venue_name"]))
        if key:
            published[key].append(row)
        else:
            unmapped[row["venue_name"]] += 1
    for row in pending["held_records"]:
        identity = row["identity"]
        key = names.get(_normal(identity["venue_name"]))
        if key and event_days(identity, start, end):
            held[key].append(row)
    for row in pending.get("programme_review_candidates", []):
        rec = row["record"]
        key = names.get(_normal(rec["venue_name"]))
        if key and event_days(rec, start, end):
            programme[key].append(row)
    for event in registry["events"]:
        matched = set()
        for observation in event["observations"]:
            identity = observation["identity"]
            key = names.get(_normal(identity["venue_name"]))
            if key and observation["active"] and event_days(identity, start, end):
                matched.add(key)
        for key in matched:
            registered[key].append(event["event_uid"])
    fetch = {row["venue_id"]: row for row in (fetch_report or {}).get("venues", [])}
    result, pairs = [], []
    for key, venue in sorted(venues.items()):
        source_rows, public_rows = raw[key], published[key]
        public_days = set().union(*(event_days(r, start, end) for r in public_rows))
        source_days = set().union(*(event_days(r, start, end) for r in source_rows))
        flags = []
        expected = expectations.get(key, {})
        closed = expected.get("status") == "temporarily_closed"
        if closed:
            # review_after is a monitoring deadline, never an asserted reopening date.
            closed = bool(expected.get("evidence_url")) and date.fromisoformat(
                expected["observed_on"]
            ) <= start <= date.fromisoformat(expected["review_after"])
        if not venue["official_enabled"] and not venue["web_watch_configured"]:
            flags.append("no_active_official_or_web_route")
        if not public_rows:
            flags.append(
                "expected_zero_until_review"
                if closed
                else "public_window_empty_review_required"
            )
        if source_rows and not public_rows:
            flags.append("collected_but_not_public")
        if closed and source_rows:
            flags.append(
                "raw_programmes_during_reported_closure_require_facility_review"
            )
        if held[key]:
            flags.append("id_or_source_review_pending")
        if programme[key]:
            flags.append("programme_overlap_review_pending")
        unresolved = sum(
            r["source_id"] == "official_events" and not r.get("performer")
            for r in source_rows
        )
        if unresolved:
            flags.append("official_performer_unresolved_programmes_reach_review")
        if expected.get("official_horizon_months") is not None:
            flags.append(
                "official_calendar_has_limited_horizon_use_supplementary_sources"
            )
        year_conflicts = fetch.get(key, {}).get("calendar_year_conflict_count", 0)
        if year_conflicts:
            flags.append("retained_calendar_year_conflicts_require_review")
        by_day = defaultdict(list)
        for row in public_rows:
            for day in event_days(row, start, end):
                by_day[day].append(row)
        for day, entries in sorted(by_day.items()):
            if len(entries) < 2:
                continue
            entries = sorted(entries, key=lambda r: r["event_key"])
            times = [r.get("event_start_time") for r in entries]
            subjects = {_normal(r["artist_name"]) for r in entries}
            classification = (
                "distinct_start_times_possible_multiple_performances"
                if len(subjects) == 1 and all(times) and len(set(times)) == len(times)
                else "shared_day_or_facility_review_required"
            )
            pairs.append(
                dict(
                    venue_id=key,
                    event_date=day,
                    classification=classification,
                    event_uids=[r["event_key"] for r in entries],
                    start_times=times,
                    action="inspect_official_programme_no_auto_merge_or_cancellation",
                )
            )
        item = dict(
            venue,
            window_raw_rows=len(source_rows),
            raw_counts_by_source=dict(Counter(r["source_id"] for r in source_rows)),
            window_raw_days=len(source_days),
            last_raw_day=max(source_days, default=None),
            official_unresolved_performer_rows=unresolved,
            registered_ids=len(registered[key]),
            public_events=len(public_rows),
            public_days=len(public_days),
            last_public_day=max(public_days, default=None),
            longest_public_blank_days=longest_gap(public_days, start, end),
            held_by_reason=dict(Counter(r["reason"] for r in held[key])),
            programme_overlap_reviews=len(programme[key]),
            flags=flags,
            coverage_expectation=expected or None,
            runtime_fetch_status=fetch.get(key, {}).get("status", "not_measured"),
            calendar_year_conflict_count=year_conflicts,
        )
        result.append(item)
    return dict(
        report_version=1,
        scope=inventory["scope"],
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        coverage_verified=False,
        interpretation="counts_are_review_signals_not_a_completeness_claim",
        summary=dict(
            registered_venues=len(result),
            public_events=sum(r["public_events"] for r in result),
            collected_but_not_public_venues=sum(
                "collected_but_not_public" in r["flags"] for r in result
            ),
            public_zero_venues=sum(r["public_events"] == 0 for r in result),
            same_day_review_groups=len(pairs),
        ),
        inventory_summary=inventory["summary"],
        identity_conflicts=inventory["identity_conflicts"],
        orphan_web_watch_ids=inventory["orphan_web_watch_ids"],
        orphan_ticketjam_ids=inventory["orphan_ticketjam_ids"],
        unmapped_public_venues=dict(unmapped),
        same_day_candidates=pairs,
        venues=result,
    )


def read_databases(
    events_path: Path, signals_path: Path, inventory: dict
) -> tuple[list, list]:
    def rows(path, query):
        # mode=ro prevents creation, DDL, migration and writes on missing/bad inputs.
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query)]

    official = rows(
        events_path,
        """SELECT venue_id, start_date AS event_date,
        end_date AS event_end_date, performers, artist_name_resolved FROM events
        WHERE status NOT IN ('cancelled', 'postponed')""",
    )
    for row in official:
        row.update(
            source_id="official_events",
            performer=row.pop("performers") or row.pop("artist_name_resolved"),
        )
    names = {_normal(v["venue_name"]): v["venue_id"] for v in inventory["venues"]}
    signals = []
    for rec in rows(signals_path, "SELECT source_id, labels_json FROM signals"):
        labels = json.loads(rec["labels_json"] or "{}")
        start = labels.get("event_start_date")
        if not start:
            continue
        key = names.get(_normal(labels.get("venue_name") or ""))
        if key:
            signals.append(
                dict(
                    venue_id=key,
                    source_id=rec["source_id"],
                    event_date=start,
                    event_end_date=labels.get("event_end_date"),
                )
            )
    return official, signals


def generate_review_diagnostics(*, registry, **paths):
    """Diagnose a stopped producer without treating its candidates as public.

    Only the known unresolved-identity stop is handled here. Malformed maps,
    bad baselines and all other integrity failures still fail the audit.
    """
    from .build_lp_events import build_lp_events, _build_lp_event_candidates
    from .event_identity_registry import apply_to_payload, digest
    from .reviewed_source_map import (
        SourceMapError,
        reviewed_rows_for_publication,
        publication_baseline,
    )

    preview = []
    try:
        result = build_lp_events(**paths, programme_review_preview=preview)
        return result, preview, {"status": "generated", "affected_public_ids": []}
    except SourceMapError as exc:
        if not str(exc).startswith(
            "existing public ID has an unresolved identity change;"
        ):
            raise
    # Reuse the same candidate, selection and identity stages that precede the
    # stop. These rows remain private; audit_runtime uses only hold counts.
    preview = []
    candidates = _build_lp_event_candidates(
        events_db_path=paths["events_db_path"],
        event_signals_db_path=paths["event_signals_db_path"],
        as_of_date=paths["as_of_date"],
        programme_review_preview=preview,
    )
    candidates["events"], _ = reviewed_rows_for_publication(
        candidates["events"],
        registry,
        paths["reviewed_source_map_path"].read_bytes(),
        paths["reviewed_source_baseline_path"].read_bytes(),
        paths["events_db_path"],
        paths["event_signals_db_path"],
    )
    generated = apply_to_payload(
        candidates, registry, digest(paths["identity_registry_path"].read_bytes())
    )
    baseline = publication_baseline(paths["reviewed_source_baseline_path"].read_bytes())
    present = {r["event_key"] for r in generated["events"]}
    affected = sorted(
        {
            uid
            for item in generated["identity_held_records"]
            if item["reason"]
            in {"changed_or_unbound_observation", "multiple_candidates_for_fixed_id"}
            for uid in set(item["related_event_uids"])
            & set(baseline["event_sources"]) - present
        }
    )
    if not affected:
        raise ValueError("identity diagnostic did not reproduce the producer stop")
    return (
        generated,
        preview,
        {
            "status": "blocked_unresolved_public_identity",
            "affected_public_ids": affected,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--fetch-report", type=Path)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--summary", type=Path, help="Append a counts-only Actions summary."
    )
    args = parser.parse_args(argv)
    root = args.data_dir
    try:
        files = [
            root / name
            for name in [
                "venue_registry.csv",
                "venue_web_discovery_config.json",
                "events.sqlite",
                "event_signals.sqlite",
                "event_identity_registry.json",
                "lp_events.json",
            ]
        ]
        map_path, baseline_path = (
            root / "reviewed_event_sources.json",
            root / "reviewed_event_baseline.json",
        )
        if map_path.exists() != baseline_path.exists():
            raise ValueError("source map and baseline must be supplied together")
        if map_path.exists():
            files.extend([map_path, baseline_path])
        if args.fetch_report:
            files.append(args.fetch_report)
        outputs = [p.resolve() for p in (args.output, args.summary) if p]
        if len(outputs) != len(set(outputs)) or set(outputs) & {
            p.resolve() for p in files
        }:
            raise ValueError("report output aliases an input or another output")

        def hashes():
            return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

        for db in files[2:4]:
            wal = Path(str(db) + "-wal")
            if wal.exists() and wal.stat().st_size:
                raise ValueError("audit requires checkpointed source databases")
        before = hashes()
        inventory = read_inputs(*files[:2])
        public = json.loads((root / "lp_events.json").read_text())
        registry = json.loads((root / "event_identity_registry.json").read_text())
        if (
            public["identity_registry"]["sha256"]
            != before[str(root / "event_identity_registry.json")]
        ):
            raise ValueError(
                "public output and fixed-ID registry are different generations"
            )
        # Reuse the producer's real ID/source review path. Candidate details are
        # held only in memory; the report exposes counts and existing public IDs.
        generated, programme_preview, generation = generate_review_diagnostics(
            registry=registry,
            events_db_path=files[2],
            event_signals_db_path=files[3],
            identity_registry_path=root / "event_identity_registry.json",
            reviewed_source_map_path=map_path if map_path.exists() else None,
            reviewed_source_baseline_path=baseline_path if map_path.exists() else None,
            as_of_date=date.fromisoformat(public["as_of_date"]),
        )
        pending = dict(
            held_records=generated["identity_held_records"],
            programme_review_candidates=programme_preview,
        )
        official, signals = read_databases(files[2], files[3], inventory)
        with files[0].open() as stream:
            expectations = {
                r["venue_id"]: json.loads(r.get("config_json") or "{}").get(
                    "coverage_expectation", {}
                )
                for r in csv.DictReader(stream)
            }
        start = date.fromisoformat(public["as_of_date"])
        report = audit_runtime(
            inventory,
            official,
            signals,
            public,
            pending,
            registry,
            start=start,
            end=start + timedelta(days=args.days - 1),
            expectations=expectations,
            fetch_report=json.loads(args.fetch_report.read_text())
            if args.fetch_report
            else None,
        )
        report["generation"] = generation
        report["regenerated_public_rows_match"] = (
            generated["events"] == public["events"]
            if generation["status"] == "generated"
            else None
        )
        if before != hashes():
            raise ValueError(
                "audit inputs changed while reading; rerun from one generation"
            )
        report["input_sha256"] = before
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(text)
        else:
            print(text, end="")
        if args.summary:
            with args.summary.open("a") as stream:
                stream.write(
                    "### Calendar coverage review\n\n"
                    "Counts are review signals; no event was approved or cancelled.\n\n"
                    "|Venue|Raw|Fixed IDs|Public|Pending|Fetch|Review signals|\n|---|---:|---:|---:|---:|---|---|\n"
                )
                if generation["status"] != "generated":
                    stream.write(
                        "\nProducer generation is blocked by unresolved identities. Public counts below use the previous accepted snapshot. Existing affected IDs: "
                        + ", ".join(generation["affected_public_ids"])
                        + ".\n\n"
                    )
                for row in report["venues"]:
                    if row["official_enabled"] or row["web_watch_configured"]:
                        stream.write(
                            f"|{row['venue_name']}|{row['window_raw_rows']}|{row['registered_ids']}|"
                            f"{row['public_events']}|{sum(row['held_by_reason'].values())}|{row['runtime_fetch_status']}|{', '.join(row['flags'])}|\n"
                        )
            bad_fetches = sum(
                row["runtime_fetch_status"]
                in {
                    "failed",
                    "partial_or_failed_collection",
                    "empty_unverified",
                    "not_requested",
                }
                for row in report["venues"]
            )
            unmeasured = sum(
                row["official_enabled"]
                and row["runtime_fetch_status"] == "not_measured"
                for row in report["venues"]
            )
            unexplained_zero = sum(
                "public_window_empty_review_required" in row["flags"]
                and (row["official_enabled"] or row["web_watch_configured"])
                for row in report["venues"]
            )
            print(
                "::warning::Calendar coverage review: "
                f"{report['summary']['collected_but_not_public_venues']} collected-but-unpublished venues; "
                f"{unexplained_zero} active-route venues have unexplained public zeros; "
                f"{len(report['identity_conflicts'])} venue identity conflicts; {bad_fetches} attempted fetches need review; "
                f"{unmeasured} enabled official routes have unmeasured fetch status. "
                "See the counts and hold reasons in the job summary; no automatic approval or cancellation."
            )
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, csv.Error) as exc:
        print(f"Calendar coverage audit failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
