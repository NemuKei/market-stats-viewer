"""R1: a failing source must not starve the rest of the national scope."""

from copy import deepcopy

import pytest

from scripts.national_event_state import empty_state, plan_run, record_run


def plan(state, day=20, targets=None, limit=2, scope="v1", at=None):
    return plan_run(
        state,
        stream="announcement",
        observed_at_utc=at or f"2030-09-{day:02d}T01:00:00Z",
        scope_revision=scope,
        target_ids=targets or ["01", "02", "03"],
        limit=limit,
    )


def observations(ids, day=20, failed=("01", "02"), at=None):
    return [
        dict(
            target_id=target,
            status="fetch_failed" if target in failed else "checked",
            observed_at_utc=at or f"2030-09-{day:02d}T01:01:00Z",
            covered_range=None if target in failed else "synthetic full schedule",
            reason="synthetic failure" if target in failed else "synthetic check",
        )
        for target in ids
    ]


def test_r1_persistent_failures_do_not_starve_unvisited_across_three_days():
    state = empty_state()
    selections = []
    for day in (20, 21, 22):
        p = plan(state, day)
        selections.append(p["selected_ids"])
        state = record_run(state, p, observations(p["selected_ids"], day))
    assert selections[0] == ["01", "02"]
    assert "03" in selections[1]
    assert all(
        "announcement|" + target not in state["last_success"] for target in ("01", "02")
    )
    assert state["last_success"]["announcement|03"]
    assert len(state["runs"]) == 3
    assert (
        state["runs"]["announcement|2030-09-20|v1"]["observations"]["01"]["status"]
        == "fetch_failed"
    )


def test_r1_same_day_resume_counts_and_full_scope_do_not_repeat_targets():
    state = empty_state()
    first = plan(state)
    state = record_run(state, first, observations(first["selected_ids"]))
    resumed = plan(state, at="2030-09-20T02:00:00Z")
    assert resumed["selected_ids"] == ["03"]
    assert resumed["counts"] == dict(target=3, checked=0, fetch_failed=2, unvisited=1)
    state = record_run(state, resumed, observations(["03"], at="2030-09-20T02:01:00Z"))
    assert plan(state, at="2030-09-20T03:00:00Z")["status"] == "finished_with_failures"
    all_success = empty_state()
    first = plan(all_success, limit=3)
    all_success = record_run(
        all_success, first, observations(first["selected_ids"], failed=())
    )
    assert plan(all_success, at="2030-09-20T02:00:00Z")["status"] == "collected"
    assert len(plan(all_success, 21, limit=3)["selected_ids"]) == 3


def test_r1_scope_change_keeps_retry_wait_and_prioritizes_new_targets():
    state = empty_state()
    first = plan(state)
    state = record_run(state, first, observations(first["selected_ids"]))
    revised = plan(
        state, targets=["01", "02", "03", "04"], scope="v2", at="2030-09-20T02:00:00Z"
    )
    assert revised["selected_ids"] == ["03", "04"]
    assert revised["counts"]["unvisited"] == 4
    assert revised["deferred_retry_count"] == 2
    assert revised["retry_after_by_target"]["01"] == "2030-09-20T15:00:00Z"
    assert revised["never_attempted"] == 2
    assert revised["max_elapsed_since_attempt_seconds"] == 59 * 60


def test_r1_retry_becomes_eligible_at_jst_midnight_not_utc_midnight():
    state = empty_state()
    p = plan(state, targets=["01"])
    state = record_run(state, p, observations(["01"]))
    before = plan(state, targets=["01"], scope="v2", at="2030-09-20T14:59:00Z")
    assert before["selected_ids"] == []
    assert before["status"] == "waiting_for_retry"
    after = plan(state, targets=["01"], scope="v2", at="2030-09-20T15:00:00Z")
    assert after["selected_ids"] == ["01"]


def test_r1_legacy_v1_history_preserves_attempt_order_without_cached_fields():
    state = empty_state()
    p = plan(state)
    state = record_run(state, p, observations(p["selected_ids"]))
    legacy = {
        k: deepcopy(state[k])
        for k in ("schema_version", "runs", "last_success", "proposals")
    }
    assert plan(legacy, 21)["selected_ids"][0] == "03"


def test_r1_duplicate_and_older_failure_do_not_rewrite_attempt_history():
    state = empty_state()
    p = plan(state)
    with pytest.raises(ValueError, match="duplicate"):
        record_run(state, p, observations(["01", "01"]))
    state = record_run(state, p, observations(["01"]))
    with pytest.raises(ValueError, match="predates"):
        plan(state, day=19)
