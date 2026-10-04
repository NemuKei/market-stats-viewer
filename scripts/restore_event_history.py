"""Add missing past official rows from explicitly ordered historical snapshots.

Default is a dry run. Snapshots must be supplied newest first. Existing event
and venue rows are never overwritten; ambiguous origins are held for review.
This is an offline repair tool, not part of the scheduled update pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .events.types import EVENT_HISTORY_WINDOW_DAYS
from .build_lp_events import normalize_event_status, SUPPRESSING_EVENT_STATUSES


def _read_rows(conn: sqlite3.Connection, table: str) -> tuple[list[str], list[dict]]:
    cursor = conn.execute(f'SELECT * FROM "{table}"')
    columns = [column[0] for column in cursor.description]
    return columns, [dict(zip(columns, row)) for row in cursor.fetchall()]


def _title(row: dict) -> str:
    return " ".join(unicodedata.normalize("NFKC", row["title"]).split()).casefold()


def _identities(row: dict) -> set[tuple]:
    # Conservative review keys, NOT automatic assertions that two events match.
    # A repeated tour/title can be held unnecessarily rather than resurrecting
    # an old date after an identity-changing correction.
    keys = {(row["venue_id"], "title", _title(row))}
    source_key = str(row.get("source_event_key") or "").strip()
    if source_key:
        source_key = re.sub(r"#[dt]=[^#]*", "", source_key)
        keys.add((row["venue_id"], "source_key", source_key))
    url = str(row.get("url") or "").strip()
    if url and url != row.get("source_url"):
        keys.add((row["venue_id"], "detail_url", url.split("#")[0]))
    return keys


def _valid_url(value: object) -> bool:
    parsed = urlsplit(str(value or ""))
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


def restore_history(
    conn: sqlite3.Connection,
    snapshots: list[Path],
    *,
    as_of_date: date,
    apply: bool = False,
    history_days: int = EVENT_HISTORY_WINDOW_DAYS,
) -> dict:
    """Plan/apply add-only restore in a savepoint; preserve every existing column.

    The caller owns committing its connection. Snapshot ordering is explicit:
    newest first, including their out-of-window records as correction evidence.
    Publication eligibility is deliberately left to the unchanged LP builder
    and consumer source policy; inserted rows are not public event counts.
    """
    if history_days < 0 or not snapshots:
        raise ValueError("nonnegative history_days and at least one snapshot required")
    columns, current = _read_rows(conn, "events")
    venue_columns, venues = _read_rows(conn, "venues")
    before = {row["event_uid"]: row for row in current}
    venue_ids = {row["venue_id"] for row in venues}
    by_uid: dict[str, tuple[int, dict]] = {}
    origins: dict[tuple, list[tuple[int, str]]] = defaultdict(list)
    for row in current:
        for key in _identities(row):
            origins[key].append((-1, row["event_uid"]))
    snapshot_info = []
    for index, path in enumerate(snapshots):
        path = Path(path).resolve(strict=True)
        wal = path.with_name(path.name + "-wal")
        if wal.exists() and wal.stat().st_size:
            raise ValueError(f"snapshot has uncheckpointed WAL: {path.name}")
        with closing(
            sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        ) as source:
            if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"invalid snapshot: {path.name}")
            source_columns, source_rows = _read_rows(source, "events")
        if source_columns != columns:
            raise ValueError(f"snapshot events schema mismatch: {path.name}")
        snapshot_info.append(
            {
                "snapshot": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "row_count": len(source_rows),
            }
        )
        for row in source_rows:
            uid = row["event_uid"]
            if uid not in by_uid:
                by_uid[uid] = (index, row)
                # Older versions of this UID must not act as current evidence.
                for key in _identities(row):
                    origins[key].append((index, uid))

    cutoff = as_of_date - timedelta(days=history_days)
    candidates: list[dict] = []
    held = []
    skipped = Counter()
    semantic_keys = set()
    for uid, (index, row) in sorted(by_uid.items()):
        if uid in before:
            skipped["already_present"] += 1
            continue
        try:
            start = date.fromisoformat(row["start_date"])
            end = date.fromisoformat(row["end_date"] or row["start_date"])
            if (
                start.isoformat() != row["start_date"]
                or (row["end_date"] and end.isoformat() != row["end_date"])
                or end < start
            ):
                raise ValueError("invalid date interval")
        except (TypeError, ValueError):
            held.append({"event_uid": uid, "reason": "invalid_date"})
            continue
        if end < cutoff or end >= as_of_date:
            skipped["outside_past_window"] += 1
            continue
        if row["venue_id"] not in venue_ids:
            held.append({"event_uid": uid, "reason": "missing_current_venue"})
            continue
        if not _title(row) or not _valid_url(row.get("url") or row.get("source_url")):
            held.append({"event_uid": uid, "reason": "invalid_source_or_title"})
            continue
        status = normalize_event_status(row["status"])
        status_conflicts = {
            other_uid
            for key in _identities(row)
            for other_index, other_uid in origins[key]
            if other_uid != uid
            and other_index == index
            and normalize_event_status(by_uid[other_uid][1]["status"]) != status
            and (
                status in SUPPRESSING_EVENT_STATUSES
                or normalize_event_status(by_uid[other_uid][1]["status"])
                in SUPPRESSING_EVENT_STATUSES
            )
        }
        if status_conflicts:
            held.append(
                {
                    "event_uid": uid,
                    "reason": "conflicting_status_same_snapshot",
                    "conflicting_uids": sorted(status_conflicts),
                }
            )
            continue
        conflicts = sorted(
            {
                other_uid
                for key in _identities(row)
                for other_index, other_uid in origins[key]
                if other_uid != uid and other_index < index
            }
        )
        if conflicts:
            held.append(
                {
                    "event_uid": uid,
                    "reason": "possible_correction_or_repeated_event",
                    "conflicting_uids": conflicts,
                }
            )
            continue
        semantic_key = (
            row["venue_id"],
            row["start_date"],
            row["start_time"] or "",
            _title(row),
        )
        if semantic_key in semantic_keys:
            held.append({"event_uid": uid, "reason": "duplicate_event_different_uid"})
            continue
        semantic_keys.add(semantic_key)
        candidates.append(row)

    if apply:
        quoted = ",".join('"' + column + '"' for column in columns)
        placeholders = ",".join("?" for _ in columns)
        if not conn.in_transaction:
            conn.execute("BEGIN")
        conn.execute("SAVEPOINT history_restore")
        try:
            conn.executemany(
                f"INSERT INTO events ({quoted}) VALUES ({placeholders})",
                [tuple(row[column] for column in columns) for row in candidates],
            )
            after_columns, after_rows = _read_rows(conn, "events")
            after = {row["event_uid"]: row for row in after_rows}
            after_venue_columns, after_venues = _read_rows(conn, "venues")
            if after_columns != columns or any(
                after.get(uid) != row for uid, row in before.items()
            ):
                raise ValueError("existing event row changed during restore")
            if after_venue_columns != venue_columns or after_venues != venues:
                raise ValueError("venue rows changed during restore")
            conn.execute("RELEASE history_restore")
        except Exception:
            conn.execute("ROLLBACK TO history_restore")
            conn.execute("RELEASE history_restore")
            raise
    return {
        "mode": "apply" if apply else "dry_run",
        "as_of_date": as_of_date.isoformat(),
        "history_start_date": cutoff.isoformat(),
        "snapshots_newest_first": snapshot_info,
        "existing_count": len(current),
        "existing_rows_preserved": True,
        "existing_future_or_ongoing_count": sum(
            (row["end_date"] or row["start_date"]) >= as_of_date.isoformat()
            for row in current
        ),
        "candidate_count": len(candidates),
        "inserted_count": len(candidates) if apply else 0,
        "candidate_counts_by_month": dict(
            sorted(Counter(row["start_date"][:7] for row in candidates).items())
        ),
        "candidate_uids": [row["event_uid"] for row in candidates],
        "held_count": len(held),
        "held_counts_by_reason": dict(Counter(row["reason"] for row in held)),
        "held": held,
        "skipped_counts": dict(skipped),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-db", required=True, type=Path)
    parser.add_argument(
        "--snapshot",
        required=True,
        action="append",
        type=Path,
        help="Repeat in newest-first order",
    )
    parser.add_argument("--as-of-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Explicitly apply add-only repair; otherwise dry run",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    mode = "rw" if args.apply else "ro"
    with closing(
        sqlite3.connect(
            args.target_db.resolve(strict=True).as_uri() + "?mode=" + mode, uri=True
        )
    ) as conn:
        with conn:
            report = restore_history(
                conn, args.snapshot, as_of_date=args.as_of_date, apply=args.apply
            )
            text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            # An audit-report failure must abort an apply before its commit.
            if args.report:
                args.report.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"held", "candidate_uids", "snapshots_newest_first"}
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
