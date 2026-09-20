"""Versioned offline run ledger for one Work writer; no scheduler or publisher.

The local compare-and-swap protects this checkout only. A cloud deployment must
also prove its single-writer lock and remote Git compare-and-swap before cutover.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile

from .national_event_handoff import STREAMS, _utc, digest


def empty_state() -> dict:
    return {"schema_version": 1, "runs": {}, "last_success": {}, "proposals": {}}


def run_key(stream: str, observed_at_utc: str, scope_revision: str) -> str:
    if stream not in STREAMS or not scope_revision:
        raise ValueError("stream and scope revision required")
    day = (
        _utc(observed_at_utc)
        .astimezone(timezone(timedelta(hours=9)))
        .date()
        .isoformat()
    )
    return f"{stream}|{day}|{scope_revision}"


def plan_run(
    state: dict,
    *,
    stream: str,
    observed_at_utc: str,
    scope_revision: str,
    target_ids: list[str],
    limit: int,
) -> dict:
    if (
        state.get("schema_version") != 1
        or limit < 1
        or len(set(target_ids)) != len(target_ids)
    ):
        raise ValueError("invalid state, limit, or duplicate targets")
    if any(not isinstance(x, str) or not x for x in target_ids):
        raise ValueError("nonempty target IDs required")
    key = run_key(stream, observed_at_utc, scope_revision)
    run = state["runs"].get(key, {"targets": sorted(target_ids), "observations": {}})
    if run["targets"] != sorted(target_ids):
        raise ValueError("target list changed without a scope revision")
    observations = run["observations"]
    pending = [x for x in target_ids if x not in observations]
    pending.sort(key=lambda x: (state["last_success"].get(f"{stream}|{x}", ""), x))
    failures = sum(r["status"] == "fetch_failed" for r in observations.values())
    now = _utc(observed_at_utc)
    ages = [
        (now - _utc(state["last_success"][f"{stream}|{x}"])).total_seconds()
        for x in target_ids
        if f"{stream}|{x}" in state["last_success"]
    ]
    return {
        "run_key": key,
        "state_revision": digest(state),
        "targets": sorted(target_ids),
        "selected_ids": pending[:limit],
        "next_cursor": pending[limit] if len(pending) > limit else None,
        "counts": {
            "target": len(target_ids),
            "checked": len(observations) - failures,
            "fetch_failed": failures,
            "unvisited": len(pending),
        },
        "never_checked": sum(
            f"{stream}|{x}" not in state["last_success"] for x in target_ids
        ),
        "max_elapsed_since_success_seconds": max(ages) if ages else None,
        "status": "ready"
        if pending
        else ("finished_with_failures" if failures else "collected"),
        "publication_status": "not_started",
    }


def record_run(state: dict, plan: dict, observations: list[dict]) -> dict:
    if digest(state) != plan["state_revision"]:
        raise ValueError("state advanced: reload and replan")
    if not observations:
        raise ValueError("no progress: pause and report instead of repeating")
    result = deepcopy(state)
    key = plan["run_key"]
    stream, day, scope = key.split("|")
    date.fromisoformat(day)
    run = result["runs"].setdefault(
        key, {"targets": plan["targets"], "observations": {}}
    )
    seen = set()
    for row in observations:
        if set(row) != {
            "target_id",
            "status",
            "observed_at_utc",
            "covered_range",
            "reason",
        }:
            raise ValueError("invalid observation fields")
        target = row["target_id"]
        if (
            target not in plan["selected_ids"]
            or target in seen
            or target in run["observations"]
        ):
            raise ValueError("duplicate or unassigned target")
        seen.add(target)
        if row["status"] not in {"checked", "fetch_failed"} or not row["reason"]:
            raise ValueError("explicit checked/failed status and reason required")
        if row["status"] == "checked" and not row["covered_range"]:
            raise ValueError("checked needs actual page/date/search extent")
        if run_key(stream, row["observed_at_utc"], scope) != key:
            raise ValueError("observation belongs to another JST day")
        previous = result["last_success"].get(f"{stream}|{target}")
        if previous and _utc(row["observed_at_utc"]) < _utc(previous):
            raise ValueError("observation predates last success")
        run["observations"][target] = deepcopy(row)
        if row["status"] == "checked":
            result["last_success"][f"{stream}|{target}"] = row["observed_at_utc"]
    return result


def record_proposal(state: dict, receipt: dict, proposal: dict) -> dict:
    """Coalesce identical changes across streams while keeping all evidence."""
    if receipt.get("proposal_hash") != digest(proposal):
        raise ValueError("receipt does not match proposal")
    identity = {
        "venue_id": proposal["venue_id"],
        "change_type": proposal["change_type"],
        "current_values": proposal["current_values"],
        "proposed_values": proposal["proposed_values"],
    }
    if receipt.get("proposal_id") != digest(identity):
        raise ValueError("receipt identity mismatch")
    result = deepcopy(state)
    record = result["proposals"].setdefault(
        receipt["proposal_id"],
        {
            "status": "needs_work_verification",
            "evidence": [],
            "publication_status": "not_started",
        },
    )
    timing = record.setdefault(
        "timing",
        {
            "first_detected_at_utc": proposal["observed_at_utc"],
            "notified_at_utc": None,
            "verified_at_utc": None,
            "git_applied_at_utc": None,
            "release_published_at_utc": None,
            "consumer_verified_at_utc": None,
        },
    )
    if _utc(proposal["observed_at_utc"]) < _utc(timing["first_detected_at_utc"]):
        timing["first_detected_at_utc"] = proposal["observed_at_utc"]
    # A missing START is compatible with several performances, never proof that
    # noon/evening shows are the same. Flag for Work review instead of merging.
    values = proposal["proposed_values"]
    for other_id, other in result["proposals"].items():
        if other_id == receipt["proposal_id"]:
            continue
        for evidence in other["evidence"]:
            other_values = evidence["proposed_values"]
            if (
                evidence["venue_id"] == proposal["venue_id"]
                and values.get("event_date") == other_values.get("event_date")
                and values.get("artist_name") == other_values.get("artist_name")
                and (
                    not values.get("event_start_time")
                    or not other_values.get("event_start_time")
                    or values["event_start_time"] == other_values["event_start_time"]
                )
            ):
                for target, candidate_id in (
                    (record, other_id),
                    (other, receipt["proposal_id"]),
                ):
                    ids = target.setdefault("possible_duplicate_ids", [])
                    if candidate_id not in ids:
                        ids.append(candidate_id)
                        ids.sort()
                break
    if proposal not in record["evidence"]:
        record["evidence"].append(deepcopy(proposal))
    return result


def save_state(path: Path, state: dict, *, expected_revision: str) -> None:
    """Fail on another local writer or changed state; never overwrite a stale lock."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "another writer or stale lock: operator review required"
        ) from exc
    temp = None
    try:
        os.close(fd)
        current = json.loads(path.read_text()) if path.exists() else empty_state()
        if digest(current) != expected_revision:
            raise ValueError("state advanced: reload and replan")
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".national-state-",
            delete=False,
        ) as handle:
            temp = Path(handle.name)
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()
        lock.unlink()
