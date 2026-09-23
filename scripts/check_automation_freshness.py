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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--max-age-days", type=float, required=True)
    args = parser.parse_args(argv)
    ok, message = check_freshness(args.file, max_age_days=args.max_age_days, now=datetime.now(timezone.utc))
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
