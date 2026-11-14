"""Apply automation-written venue discovery candidates to the config idempotently.

Candidates pass through a persistent backlog (data/venue_discovery_backlog.json) so
that an inbox with more findings than one run may apply is never truncated: each run
first ingests the inbox (once per run_at_utc), then applies at most MAX_CANDIDATES
pending rows in first-detected order. Unprocessed rows stay pending across runs even
when later inboxes no longer list them.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .signals.entity_aliases import (
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INBOX = REPO_ROOT / "data" / "venue_discovery_inbox.json"
DEFAULT_CONFIG = REPO_ROOT / "data" / "venue_web_discovery_config.json"
DEFAULT_BACKLOG = REPO_ROOT / "data" / "venue_discovery_backlog.json"
# Per-inbox `candidates` limit and per-run apply limit. Overflow goes to
# `deferred_candidates` and waits in the backlog instead of raising this limit.
MAX_CANDIDATES = 30
MAX_DEFERRED = 120
MAX_SNIPPET_CHARS = 400
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED = ("event_start_date", "venue_name", "artist_name", "title", "source_class",
            "evidence_url", "evidence_snippet")


class InboxSchemaError(ValueError):
    pass


@dataclass
class ApplyResult:
    config: dict[str, Any]
    applied: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)


def _check_schema(inbox: Any) -> None:
    if not isinstance(inbox, dict) or inbox.get("schema_version") != 1:
        raise InboxSchemaError("schema_version must be 1")
    try:
        datetime.fromisoformat(str(inbox.get("run_at_utc", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise InboxSchemaError("run_at_utc must be ISO 8601") from exc
    cands = inbox.get("candidates")
    if not isinstance(cands, list) or not all(isinstance(c, dict) for c in cands):
        raise InboxSchemaError("candidates must be a list of objects")
    if len(cands) > MAX_CANDIDATES:
        raise InboxSchemaError(f"candidates exceeds {MAX_CANDIDATES}")
    deferred = inbox.get("deferred_candidates", [])
    if not isinstance(deferred, list) or not all(isinstance(c, dict) for c in deferred):
        raise InboxSchemaError("deferred_candidates must be a list of objects")
    if len(deferred) > MAX_DEFERRED:
        raise InboxSchemaError(f"deferred_candidates exceeds {MAX_DEFERRED}")


def _watch_venue_names(config: dict[str, Any], venue_maps) -> set[str]:
    names: set[str] = set()
    for venue in config.get("watch_venues", []):
        for raw in [venue.get("venue_name"), *venue.get("aliases", [])]:
            canonical, _ = normalize_venue_with_lookup(raw, *venue_maps)
            if canonical:
                names.add(canonical)
    return names


def _dedup_key(row: dict[str, Any], venue_maps, artist_maps) -> tuple[str, str, str]:
    venue, _ = normalize_venue_with_lookup(row.get("venue_name"), *venue_maps)
    artist, _ = normalize_with_lookup(row.get("artist_name") or row.get("title"), *artist_maps)
    return (str(row.get("event_start_date") or ""), venue, artist.casefold())


def _reject_reason(row: dict[str, Any], config: dict[str, Any], watch: set[str], venue_maps) -> str | None:
    if any(not str(row.get(k) or "").strip() for k in REQUIRED if k != "evidence_snippet"):
        return "required"
    for key in ("event_start_date", "event_end_date"):
        if row.get(key) and not DATE_RE.match(str(row[key])):
            return "date"
    if row["source_class"] not in set(config.get("accepted_source_classes", [])):
        return "source_class"
    url = urlparse(str(row["evidence_url"]))
    if url.scheme != "https" or not url.hostname:
        return "evidence_url"
    host = url.hostname.lower()
    if any(host == d or host.endswith("." + d) for d in config.get("rejected_domains", [])):
        return "rejected_domain"
    snippet = str(row.get("evidence_snippet") or "").strip()
    if not snippet or len(snippet) > MAX_SNIPPET_CHARS:
        return "evidence_snippet"
    venue, _ = normalize_venue_with_lookup(row["venue_name"], *venue_maps)
    if venue not in watch:
        return "venue"
    return None


def _apply_rows(rows: list[dict[str, Any]], result: ApplyResult, *, venue_maps,
                artist_maps) -> list[tuple[str, dict[str, Any]]]:
    """Apply rows to result.config in order; return one (outcome, detail) per row."""
    config = result.config
    events = config.setdefault("confirmed_events", [])
    watch = _watch_venue_names(config, venue_maps)
    seen: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for event in events:
        seen.setdefault(_dedup_key(event, venue_maps, artist_maps), []).append(event)
    outcomes: list[tuple[str, dict[str, Any]]] = []
    for cand in rows:
        reason = _reject_reason(cand, config, watch, venue_maps)
        if reason:
            detail = {"title": cand.get("title"), "reason": reason}
            result.rejected.append(detail)
            outcomes.append(("rejected", detail))
            continue
        key = _dedup_key(cand, venue_maps, artist_maps)
        if key in seen:
            candidate_time = str(cand.get("event_start_time") or "").strip()
            known_times = {str(event.get("event_start_time") or "").strip() for event in seen[key]}
            if candidate_time and any(time and time != candidate_time for time in known_times):
                detail = {"title": cand.get("title"), "reason": "conflicting_start_time_requires_review"}
                result.rejected.append(detail)
                outcomes.append(("rejected", detail))
                continue
            detail = {"title": cand.get("title"), "key": list(key),
                      "matched_event_ids": [e.get("event_id") for e in seen[key] if e.get("event_id")]}
            result.duplicates.append({"title": cand.get("title"), "key": list(key)})
            outcomes.append(("duplicate", detail))
            continue
        row = dict(cand)
        # Store the registry name so prefecture lookup and LP grouping resolve it.
        row.setdefault("raw_venue_name", row["venue_name"])
        row["venue_name"] = key[1]
        row.setdefault("event_end_date", row["event_start_date"])
        row.setdefault("url", row["evidence_url"])
        row["enabled"] = True
        row["event_id"] = "vwd-" + hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:12]
        events.append(row)
        seen.setdefault(key, []).append(row)
        detail = {"title": row["title"], "event_id": row["event_id"]}
        result.applied.append(detail)
        outcomes.append(("applied", detail))
    return outcomes


def apply_inbox(inbox: dict[str, Any], config: dict[str, Any], *, venue_maps, artist_maps) -> ApplyResult:
    _check_schema(inbox)
    result = ApplyResult(config=copy.deepcopy(config))
    _apply_rows(inbox["candidates"], result, venue_maps=venue_maps, artist_maps=artist_maps)
    return result


# --- backlog ---------------------------------------------------------------

def empty_backlog() -> dict[str, Any]:
    return {"schema_version": 1, "last_ingested_inbox_run_at_utc": None, "next_seq": 1,
            "pending_count": 0, "oldest_pending_first_detected_at_utc": None,
            "pending": [], "last_activity": None}


def _check_backlog(backlog: Any) -> None:
    if not isinstance(backlog, dict) or backlog.get("schema_version") != 1:
        raise InboxSchemaError("backlog schema_version must be 1")
    pending = backlog.get("pending")
    if not isinstance(pending, list) or not all(
            isinstance(p, dict) and isinstance(p.get("candidate"), dict) and isinstance(p.get("seq"), int)
            for p in pending):
        raise InboxSchemaError("backlog pending must be a list of {seq, candidate} objects")
    if not isinstance(backlog.get("next_seq"), int):
        raise InboxSchemaError("backlog next_seq must be an integer")


def _refresh_summary(backlog: dict[str, Any]) -> None:
    backlog["pending"].sort(key=lambda p: p["seq"])
    backlog["pending_count"] = len(backlog["pending"])
    backlog["oldest_pending_first_detected_at_utc"] = min(
        (p["first_detected_at_utc"] for p in backlog["pending"]), default=None)


@dataclass
class BacklogRun:
    config: dict[str, Any]
    backlog: dict[str, Any]
    ingest: dict[str, Any]
    process: dict[str, Any]
    applied_count: int = 0
    conflicting_time: bool = False


def ingest_inbox(inbox: dict[str, Any], backlog: dict[str, Any], config: dict[str, Any], *,
                 venue_maps, artist_maps) -> dict[str, Any]:
    """Queue inbox rows into backlog (mutated). Returns an ingest report.

    Rows that cannot be applied (invalid, already confirmed, same-day time clash) are
    settled here and never queued; queued rows are deduplicated by apply key, and a
    re-listed pending row takes the newer evidence while keeping its queue position.
    """
    run_at = str(inbox["run_at_utc"])
    report: dict[str, Any] = {"inbox_run_at_utc": run_at, "status": "ingested", "queued": [],
                              "updated": [], "duplicates": [], "rejected": []}
    if backlog.get("last_ingested_inbox_run_at_utc") == run_at:
        report["status"] = "already_ingested"
        return report
    rows = [(c, "candidates") for c in inbox["candidates"]]
    rows += [(c, "deferred_candidates") for c in inbox.get("deferred_candidates", [])]
    watch = _watch_venue_names(config, venue_maps)
    confirmed: dict[tuple[str, str, str], set[str]] = {}
    for event in config.get("confirmed_events", []):
        confirmed.setdefault(_dedup_key(event, venue_maps, artist_maps), set()).add(
            str(event.get("event_start_time") or "").strip())
    pending = {tuple(p["queue_key"]): p for p in backlog["pending"]}
    this_inbox: dict[tuple[str, str, str], str] = {}
    for cand, origin in rows:
        title = cand.get("title")
        reason = _reject_reason(cand, config, watch, venue_maps)
        if reason:
            report["rejected"].append({"title": title, "origin": origin, "reason": reason})
            continue
        key = _dedup_key(cand, venue_maps, artist_maps)
        start_time = str(cand.get("event_start_time") or "").strip()
        if key in this_inbox:
            if start_time != this_inbox[key]:
                report["rejected"].append({"title": title, "origin": origin,
                                           "reason": "same_day_multiple_start_times_requires_review"})
            else:
                report["duplicates"].append({"title": title, "origin": origin, "reason": "same_inbox"})
            continue
        this_inbox[key] = start_time
        if key in confirmed:
            if start_time and any(t and t != start_time for t in confirmed[key]):
                report["rejected"].append({"title": title, "origin": origin,
                                           "reason": "conflicting_start_time_requires_review"})
            else:
                report["duplicates"].append({"title": title, "origin": origin, "reason": "already_confirmed"})
            continue
        if key in pending:
            entry = pending[key]
            entry["last_seen_at_utc"] = run_at
            if entry["candidate"] != cand:
                entry["candidate"] = copy.deepcopy(cand)
                entry["revisions"] = int(entry.get("revisions", 0)) + 1
                entry["last_revised_inbox_run_at_utc"] = run_at
                report["updated"].append({"title": title, "seq": entry["seq"]})
            continue
        entry = {"seq": backlog["next_seq"], "queue_key": list(key), "origin": origin,
                 "first_detected_at_utc": run_at, "last_seen_at_utc": run_at, "revisions": 0,
                 "candidate": copy.deepcopy(cand)}
        backlog["next_seq"] += 1
        backlog["pending"].append(entry)
        pending[key] = entry
        report["queued"].append({"title": title, "seq": entry["seq"], "origin": origin})
    backlog["last_ingested_inbox_run_at_utc"] = run_at
    return report


def run_with_backlog(inbox: dict[str, Any] | None, config: dict[str, Any], backlog: dict[str, Any], *,
                     venue_maps, artist_maps, now: str, limit: int = MAX_CANDIDATES) -> BacklogRun:
    """Ingest the inbox (if any) and apply up to `limit` pending rows, oldest first."""
    if inbox is not None:
        _check_schema(inbox)
    _check_backlog(backlog)
    backlog = copy.deepcopy(backlog)
    ingest = (ingest_inbox(inbox, backlog, config, venue_maps=venue_maps, artist_maps=artist_maps)
              if inbox is not None else {"status": "no_inbox"})
    backlog["pending"].sort(key=lambda p: p["seq"])
    batch, rest = backlog["pending"][:limit], backlog["pending"][limit:]
    result = ApplyResult(config=copy.deepcopy(config))
    outcomes = _apply_rows([p["candidate"] for p in batch], result,
                           venue_maps=venue_maps, artist_maps=artist_maps)
    settled = [{"seq": p["seq"], "first_detected_at_utc": p["first_detected_at_utc"], "outcome": outcome,
                **detail} for p, (outcome, detail) in zip(batch, outcomes)]
    backlog["pending"] = rest
    _refresh_summary(backlog)
    process = {"limit": limit, "processed": len(batch),
               "applied": sum(1 for s in settled if s["outcome"] == "applied"),
               "duplicates": sum(1 for s in settled if s["outcome"] == "duplicate"),
               "rejected": sum(1 for s in settled if s["outcome"] == "rejected"),
               "settled": settled, "pending_after": backlog["pending_count"],
               "oldest_pending_first_detected_at_utc": backlog["oldest_pending_first_detected_at_utc"]}
    changed = bool(batch) or ingest.get("status") == "ingested"
    if changed:
        backlog["last_activity"] = {"at_utc": now, "ingest": ingest, "process": process}
    return BacklogRun(config=result.config, backlog=backlog, ingest=ingest, process=process,
                      applied_count=len(result.applied),
                      conflicting_time=any(r["reason"] == "conflicting_start_time_requires_review"
                                           for r in result.rejected + ingest.get("rejected", [])))


def _summary_lines(run: BacklogRun) -> list[str]:
    ing, proc = run.ingest, run.process
    lines = []
    if ing.get("status") == "ingested":
        lines.append(f"venue discovery inbox {ing['inbox_run_at_utc']}: queued={len(ing['queued'])} "
                     f"updated={len(ing['updated'])} duplicates={len(ing['duplicates'])} "
                     f"rejected={len(ing['rejected'])}")
    else:
        lines.append(f"venue discovery inbox: {ing.get('status')} {ing.get('inbox_run_at_utc', '')}".rstrip())
    lines.append(f"venue discovery backlog: processed={proc['processed']}/{proc['limit']} "
                 f"applied={proc['applied']} duplicates={proc['duplicates']} rejected={proc['rejected']} "
                 f"pending={proc['pending_after']} "
                 f"oldest_pending_first_detected={proc['oldest_pending_first_detected_at_utc'] or '-'}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--backlog", type=Path, default=None,
                        help="backlog to read and update (default: data/venue_discovery_backlog.json)")
    args = parser.parse_args(argv)
    # A check against a temporary config copy (the automation's pre-push validation) must
    # not touch the tracked backlog: read it so pending rows are visible, but never save.
    save_backlog = args.backlog is not None or args.config.resolve() == DEFAULT_CONFIG.resolve()
    if args.backlog is None:
        args.backlog = DEFAULT_BACKLOG
    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        inbox = json.loads(args.inbox.read_text(encoding="utf-8")) if args.inbox.exists() else None
        backlog = (json.loads(args.backlog.read_text(encoding="utf-8"))
                   if args.backlog.exists() else empty_backlog())
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        run = run_with_backlog(inbox, config, backlog, venue_maps=load_venue_lookup_maps(),
                               artist_maps=load_artist_lookup_maps(), now=now)
    except (InboxSchemaError, json.JSONDecodeError) as exc:
        print(f"invalid inbox or backlog: {exc}", file=sys.stderr)
        return 1
    if inbox is None:
        print(f"inbox not found: {args.inbox}")
    if run.applied_count:
        args.config.write_text(json.dumps(run.config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    if save_backlog and (run.backlog != backlog or not args.backlog.exists()):
        args.backlog.write_text(json.dumps(run.backlog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif not save_backlog:
        print(f"validation run: backlog not saved ({args.backlog})")
    lines = _summary_lines(run)
    for line in lines:
        print(line)
    if run.conflicting_time:
        print("::warning::Venue discovery has conflicting start times; review the inbox and confirmed events.")
    for row in run.ingest.get("rejected", []):
        print(f"  rejected at ingest: {row['reason']}: {row['title']}")
    for row in run.process["settled"]:
        if row["outcome"] == "rejected":
            print(f"  rejected: {row['reason']}: {row['title']}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
