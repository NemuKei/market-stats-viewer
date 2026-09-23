"""Apply automation-written venue discovery candidates to the config idempotently."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
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
MAX_CANDIDATES = 30
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


def apply_inbox(inbox: dict[str, Any], config: dict[str, Any], *, venue_maps, artist_maps) -> ApplyResult:
    _check_schema(inbox)
    result = ApplyResult(config=copy.deepcopy(config))
    events = result.config.setdefault("confirmed_events", [])
    watch = _watch_venue_names(config, venue_maps)
    seen = {_dedup_key(e, venue_maps, artist_maps) for e in events}
    for cand in inbox["candidates"]:
        reason = _reject_reason(cand, config, watch, venue_maps)
        if reason:
            result.rejected.append({"title": cand.get("title"), "reason": reason})
            continue
        key = _dedup_key(cand, venue_maps, artist_maps)
        if key in seen:
            result.duplicates.append({"title": cand.get("title"), "key": list(key)})
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
        seen.add(key)
        result.applied.append({"title": row["title"], "event_id": row["event_id"]})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    if not args.inbox.exists():
        print(f"inbox not found: {args.inbox}")
        return 0
    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        result = apply_inbox(json.loads(args.inbox.read_text(encoding="utf-8")), config,
                             venue_maps=load_venue_lookup_maps(), artist_maps=load_artist_lookup_maps())
    except (InboxSchemaError, json.JSONDecodeError) as exc:
        print(f"invalid inbox: {exc}", file=sys.stderr)
        return 1
    if result.applied:
        args.config.write_text(json.dumps(result.config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = (f"venue discovery inbox: applied={len(result.applied)} "
               f"duplicates={len(result.duplicates)} rejected={len(result.rejected)}")
    print(summary)
    for row in result.rejected:
        print(f"  rejected: {row['reason']}: {row['title']}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
