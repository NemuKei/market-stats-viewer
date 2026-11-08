"""Opt-in public SQLite projection using the existing Git-reviewed LP decisions.

The collection DB stays outside Git. This is neither a licence engine nor a
second approval ledger. Unchanged legacy rows keep their complete v1 shape.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

from .build_lp_events import _build_lp_event_candidates
from .event_identity_registry import load_registry, parse_json, resolve_rows, registry_lock
from .events.sources.base import compute_data_hash
from .events.registry import REGISTRY_PATH, load_registry as load_venue_registry
from .events.types import EventRecord, requires_publication_review
from .public_lp_projection import check_timestamp, embedded_urls, host, publication_is_reviewed
from .reviewed_source_map import reviewed_rows_for_publication


def reviewed_official_rows(*, candidate_db, registry_path, source_map_path,
                          baseline_path, signals_db):
    """Return only exact, active-ID-bound official SQLite publication decisions."""
    registry, _ = load_registry(registry_path)
    map_bytes = source_map_path.read_bytes()
    candidates = _build_lp_event_candidates(events_db_path=candidate_db,
        event_signals_db_path=signals_db, include_past=True)["events"]
    mapped, failed = reviewed_rows_for_publication(candidates, registry, map_bytes,
        baseline_path.read_bytes(), candidate_db, signals_db)
    resolved, _ = resolve_rows(mapped, registry)
    records = {rec["event_uid"]: rec for rec in parse_json(map_bytes)["records"]}
    result, ambiguous = {}, set()
    for row in resolved:
        rec = records.get(row["event_key"])
        if rec is None or row["event_key"] in failed or rec.get("fact_review") != "reviewed":
            continue
        try:
            if not publication_is_reviewed(rec, row):
                continue
        except ValueError:
            continue  # A stale field/URL decision is a per-row hold, not approval.
        if rec.get("mode") == "preserve_source":
            official = [s["record_id"] for s in rec["observation"]["source_records"]
                        if s["source_id"] == "official_events"]
        elif rec.get("mode") == "artist_source_link":
            continue
        else:
            official = [rec["source"]["record_id"]]
        if len(official) != 1:
            continue  # Do not choose among multiple raw observations implicitly.
        uid = official[0]
        if uid in result:
            ambiguous.add(uid)
        result[uid] = {"row": row, "public_urls": rec["publication"]["public_urls"]}
    return {uid: rec for uid, rec in result.items() if uid not in ambiguous}


def _snapshot(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"regular input file required: {path.name}")
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError(f"checkpoint input DB before projection: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tables(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        return {table: {row[key]: dict(row) for row in conn.execute(f"SELECT * FROM {table}")}
                for table, key in (("events", "event_uid"), ("venues", "venue_id"))}


def _data_hash(row):
    names = {field.name for field in fields(EventRecord) if field.init}
    return compute_data_hash(EventRecord(**{k: bool(v) if k == "all_day" else v for k, v in row.items() if k in names}))


def _identity_and_source(row):
    return tuple(row[k] for k in ("venue_id", "title", "artist_name_resolved", "start_date", "end_date",
        "start_time", "end_time", "all_day", "source_type", "source_url", "url", "source_event_key"))


def _public_row(raw, decision):
    row, urls = decision["row"], set(decision["public_urls"])
    if (raw["status"] != "scheduled" or raw["all_day"] not in (0, 1)
            or raw["artist_confidence"] not in {"low", "medium", "high", "source", "source_normalized", "cross_venue_title"}
            or row["event_date"] != raw["start_date"]
            or (row.get("event_end_date") or row["event_date"]) != (raw["end_date"] or raw["start_date"])
            or (row.get("event_start_time") or "") != (raw["start_time"] or "")
            or (row.get("event_end_time") or "") != (raw["end_time"] or "")
            or row.get("evidence_url") != raw["source_url"] or row.get("url") != raw["url"]):
        raise ValueError("reviewed SQLite facts/source do not match observation")
    if any(not host(u) or u not in urls for u in (raw["source_url"], raw["url"])):
        raise ValueError("SQLite public URL has no publication decision")
    # Descriptions, performers and capacity have no public LP fact decision.
    # Never copy their arbitrary text just because the source ID was reviewed.
    result = {**raw, "title": row["title"], "artist_name_resolved": row.get("artist_name"),
        "event_category": row["event_category"], "description": None, "performers": None, "capacity": None}
    for key in ("first_seen_at_utc", "updated_at_utc"):
        check_timestamp(result[key])
    if set(embedded_urls(result)) - urls:
        raise ValueError("unreviewed URL in public SQLite fields")
    result["data_hash"] = _data_hash(result)
    return result


def build_reviewed_events_db(*, previous_db: Path, candidate_db: Path, output: Path,
                            reviewed_venues: set[str], registry_path: Path,
                            source_map_path: Path, baseline_path: Path, signals_db: Path,
                            venue_registry_path: Path = REGISTRY_PATH):
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reuse the existing exclusive-file primitive; no new lock protocol/ledger.
    # Non-cooperating writers must still be excluded by Actions repo-write.
    with registry_lock(output):
        return _build_reviewed_events_db(previous_db=previous_db, candidate_db=candidate_db,
            output=output, reviewed_venues=reviewed_venues, registry_path=registry_path,
            source_map_path=source_map_path, baseline_path=baseline_path, signals_db=signals_db,
            venue_registry_path=venue_registry_path)


def _build_reviewed_events_db(*, previous_db, candidate_db, output, reviewed_venues,
                            registry_path, source_map_path, baseline_path, signals_db, venue_registry_path):
    """Merge approved gated observations; retain held rows without blocking others.

    Missing observations never imply cancellation. A same-source, same-identity
    explicit withdrawal only updates status on the previous public row.
    """
    if not reviewed_venues or any(not v or v.strip() != v for v in reviewed_venues):
        raise ValueError("explicit nonempty reviewed venues required")
    inputs = (previous_db, candidate_db, registry_path, source_map_path, baseline_path, signals_db, venue_registry_path)
    if (output.is_symlink() or output.resolve() in {p.resolve() for p in inputs[1:]}
            or output.exists() and any(p.exists() and output.samefile(p) for p in inputs[1:])):
        raise ValueError("output must not replace private inputs or review files")
    if previous_db.resolve() == candidate_db.resolve() or previous_db.samefile(candidate_db):
        raise ValueError("public and private DBs must be separate")
    output_before = _snapshot(output) if output.exists() else None
    snapshots = {p: _snapshot(p) for p in inputs}
    decisions = reviewed_official_rows(candidate_db=candidate_db, registry_path=registry_path,
        source_map_path=source_map_path, baseline_path=baseline_path, signals_db=signals_db)
    old, current = _tables(previous_db), _tables(candidate_db)
    required_venues = {venue.venue_id for venue in load_venue_registry(venue_registry_path)
                       if requires_publication_review(venue.config_json)}
    dated_venues = {uid for uid, venue in current["venues"].items()
                    if requires_publication_review(venue["config_json"])}
    if (dated_venues | required_venues) - reviewed_venues:
        raise ValueError("every dated venue or reviewed venue must be explicitly gated before publication")
    merged = {table: dict(rows) for table, rows in old.items()}
    report = dict(reviewed=0, held_new=0, held_changed=0, withdrawals=0, normal_changes=0,
                  held_venue_metadata=0, absent_retained=0)
    for uid, row in current["events"].items():
        previous = old["events"].get(uid)
        if previous == row:
            continue
        # A UID changing venues must not escape the original venue's gate.
        gated = row["venue_id"] in reviewed_venues or previous and previous["venue_id"] in reviewed_venues
        if not gated:
            merged["events"][uid] = row
            report["normal_changes"] += 1
        elif previous and row["status"] in {"cancelled", "postponed"}:
            if _identity_and_source(previous) != _identity_and_source(row):
                raise ValueError("ambiguous withdrawal changed identity/source; review before replacement")
            withdrawal = {**previous, "status": row["status"], "updated_at_utc": row["updated_at_utc"]}
            check_timestamp(withdrawal["updated_at_utc"])
            withdrawal["data_hash"] = _data_hash(withdrawal)
            merged["events"][uid] = withdrawal
            report["withdrawals"] += 1
        elif previous and previous["status"] in {"cancelled", "postponed"}:
            # Publication hashes do not contain status. An old review must not
            # undo a later withdrawal merely because a stale page reappears.
            # Reinstatement needs an explicit Git-reviewed data correction.
            report["held_changed"] += 1
        elif uid in decisions:
            merged["events"][uid] = _public_row(row, decisions[uid])
            report["reviewed"] += 1
        else:
            report["held_changed" if previous else "held_new"] += 1
    for uid, previous in old["events"].items():
        if uid not in current["events"] and previous["venue_id"] in reviewed_venues:
            report["absent_retained"] += 1
    for uid, venue in current["venues"].items():
        if uid in reviewed_venues:
            if uid not in old["venues"]:
                raise ValueError("new gated venue requires a separate metadata review")
            report["held_venue_metadata"] += venue != old["venues"][uid]
        else:
            merged["venues"][uid] = venue
    # Prepare in the output directory and replace only after rechecking inputs.
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".events-public-", suffix=".sqlite", dir=output.parent)
    os.close(fd)
    temp = Path(name)
    try:
        shutil.copyfile(previous_db, temp)
        if merged != old:
            with closing(sqlite3.connect(temp)) as conn, conn:
                for table in ("events", "venues"):
                    for uid, row in merged[table].items():
                        if row == old[table].get(uid):
                            continue
                        columns = list(row)
                        conn.execute(f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(row.values()))
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("public SQLite integrity check failed")
            # No live WAL may be left behind when a single-file asset is replaced.
            with closing(sqlite3.connect(temp)) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if any(_snapshot(p) != before for p, before in snapshots.items()):
            raise ValueError("projection input changed; regenerate from one generation")
        if (_snapshot(output) if output.exists() else None) != output_before:
            raise ValueError("public output changed; regenerate before replacement")
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(temp) + suffix).unlink(missing_ok=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("previous-db", "candidate-db", "output", "registry-path", "source-map-path", "baseline-path", "signals-db"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--reviewed-venues", required=True, help="Comma-separated opted-in venue IDs")
    parser.add_argument("--venue-registry-path", type=Path, default=REGISTRY_PATH)
    args = vars(parser.parse_args())
    args["reviewed_venues"] = set(args["reviewed_venues"].split(","))
    report = build_reviewed_events_db(**args)
    print(json.dumps(report, sort_keys=True))
    if report["held_new"] or report["held_changed"] or report["held_venue_metadata"]:
        print("::warning::Reviewed SQLite publication retained prior rows; "
              f"held_new={report['held_new']}, held_changed={report['held_changed']}, "
              f"held_venue_metadata={report['held_venue_metadata']}. Inspect private candidates before review.")


if __name__ == "__main__":
    main()
