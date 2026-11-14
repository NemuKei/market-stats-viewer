"""Fail when an automation-written JSON file has not been refreshed recently."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def check_freshness(path: Path, *, max_age_days: float, now: datetime) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path}"
    try:
        run_at = datetime.fromisoformat(
            str(json.loads(path.read_text(encoding="utf-8"))["run_at_utc"]).replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError) as exc:
        return False, f"unreadable run_at_utc in {path}: {exc}"
    age = now - run_at
    if age > timedelta(days=max_age_days):
        return False, f"stale: {path} run_at_utc={run_at.isoformat()} age={age}"
    return True, f"fresh: {path} age={age}"


def check_backlog(path: Path, *, max_pending_age_days: float, now: datetime) -> tuple[bool, str]:
    """Fail when the oldest pending venue discovery candidate has waited too long."""
    if not path.exists():
        return False, f"missing: {path}"
    try:
        backlog = json.loads(path.read_text(encoding="utf-8"))
        pending = backlog["pending"]
        oldest = min((str(p["first_detected_at_utc"]) for p in pending), default=None)
        oldest_at = datetime.fromisoformat(oldest.replace("Z", "+00:00")) if oldest else None
    except (ValueError, KeyError, TypeError) as exc:
        return False, f"unreadable backlog {path}: {exc}"
    if oldest_at is None:
        return True, f"drained: {path} pending=0"
    age = now - oldest_at
    message = f"{path} pending={len(pending)} oldest_first_detected={oldest_at.isoformat()} age={age}"
    if age > timedelta(days=max_pending_age_days):
        return False, f"stale backlog: {message}"
    return True, f"draining: {message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", type=Path, help="automation-written JSON with run_at_utc")
    target.add_argument("--backlog", type=Path, help="venue discovery backlog to check for stuck rows")
    parser.add_argument("--max-age-days", type=float, help="for --file")
    parser.add_argument("--max-pending-age-days", type=float, help="for --backlog")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.file is not None:
        if args.max_age_days is None:
            parser.error("--file requires --max-age-days")
        ok, message = check_freshness(args.file, max_age_days=args.max_age_days, now=now)
    else:
        if args.max_pending_age_days is None:
            parser.error("--backlog requires --max-pending-age-days")
        ok, message = check_backlog(args.backlog, max_pending_age_days=args.max_pending_age_days, now=now)
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
