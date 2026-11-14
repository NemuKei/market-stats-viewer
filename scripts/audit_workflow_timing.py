"""Read-only scheduled-run timing auditor; never dispatches or changes GitHub.

Input is a JSON object with explicit expected_at (verified against the workflow
at the run's SHA), now, workflow_path, branch, run, jobs, history_complete.
The caller must select the matching run; this tool does not guess which cron
slot a severely delayed execution belongs to. Jobs must belong to that run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone is required')
    return result


def audit(*, expected_at: str, now: str, workflow_path: str, branch: str,
          run: dict | None, jobs: list[dict], history_complete: bool) -> dict:
    result = dict(state='unconfirmed', overdue=False, run_id=None,
                  creation_delay_seconds=None, runner_delay_seconds=None)
    try:
        expected, observed = timestamp(expected_at), timestamp(now)
        if run is None:
            result['overdue'] = (observed - expected).total_seconds() >= 14400
            if history_complete:
                result['state'] = 'not_created'
        elif (run.get('path') == workflow_path and run.get('event') == 'schedule'
              and run.get('head_branch') == branch):
            created = timestamp(run['created_at'])
            if created < expected or created > observed:
                raise ValueError('run is outside the supplied observation window')
            result['run_id'] = run['id']
            result['creation_delay_seconds'] = (created - expected).total_seconds()
            result['overdue'] = result['creation_delay_seconds'] >= 14400
            result['state'] = (run.get('conclusion') or 'unknown_conclusion'
                               if run.get('status') == 'completed'
                               else run.get('status', 'unknown_status'))
            # Latest-attempt job timestamps cannot measure the initial queue on reruns.
            if run.get('run_attempt') == 1:
                starts = [timestamp(j['started_at']) for j in jobs if j.get('started_at')]
                if starts:
                    delay = (min(starts) - created).total_seconds()
                    if delay < 0:
                        raise ValueError('job predates run')
                    result['runner_delay_seconds'] = delay
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        result.update(state='unconfirmed', error=str(exc),
                      creation_delay_seconds=None, runner_delay_seconds=None)
    # Polling alone does not create a new notification. Caller persists last key
    # only after delivery; this is notification de-duplication, not a dispatch lock.
    key = [workflow_path, branch, expected_at, result['run_id'], result['state'], result['overdue']]
    result['notification_key'] = hashlib.sha256(json.dumps(key).encode()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    report = audit(**json.loads(args.input.read_text(encoding='utf-8')))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['state'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
