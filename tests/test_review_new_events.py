"""Fictional end-to-end new-review transactions, with no external writes."""
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest

from scripts import build_lp_events as builder
from scripts import event_identity_registry as ids
from scripts import review_new_events as review

NOW = "2026-10-28T11:00:00Z"


def row(name="A", **changes):
    value = dict(source_id="official_events", record_id="fictional-" + name,
        source_class="venue_official", source_label="Fictional official venue",
        event_date="2026-11-01", event_end_date="2026-11-01", event_start_time="18:00",
        venue_name="架空会場" + name, pref_name="東京都", artist_name="架空出演者" + name,
        title="架空公演" + name, url="https://example.com/event/" + name,
        evidence_url="https://example.com/event/" + name, evidence_snippet="fictional schedule",
        first_seen_at_utc="2026-10-27T00:00:00Z", updated_at_utc=NOW, event_status="scheduled")
    value.update(changes)
    return value


def payload(rows):
    return builder.assemble_lp_payload(rows, as_of_date=date(2026, 10, 28))


def seed(seed_row=None):
    r = payload([seed_row or row("SEED")])["events"][0]
    public = dict(event_uid=r["event_key"], title=r["title"], venue_name=r["venue_name"],
        artist_name=r["artist_name"], start_date=r["event_date"], end_date=r["event_end_date"],
        start_time=r["event_start_time"], source_id="official_events",
        source_record_id="fictional-SEED", source_policy_status="approved")
    raw = ids.canonical_bytes({"events": {"items": [public], "publicationPolicy": {
        "status": "enforced", "defaultDeny": True, "publishedCount": 1}}})
    return ids.seed_registry(raw, expected_count=1, expected_sha256=ids.digest(raw))


def setup(names=("A",), **changes):
    registry = seed()
    p = payload([row("SEED"), *[row(name, **changes) for name in names]])
    state = review.initial_state(p, registry, now=NOW, source_sha="a" * 40)
    return p, registry, state


def evidence_for(h):
    identity = h["identity"]
    text = f"{identity['event_date']} {identity['venue_name']} {identity['artist_name']} 開演 {identity['event_start_time']}"
    return dict(fingerprint=h["fingerprint"], identity=deepcopy(identity), url="https://example.com/event/" + identity["venue_name"].removeprefix("架空会場"),
        source_class="venue_official", reviewed_at_utc=NOW, context=text,
        date_text=identity["event_date"], end_date_text=identity["event_end_date"],
        venue_text=identity["venue_name"], artist_text=identity["artist_name"], time_text="開演 " + identity["event_start_time"])


def page(e):
    return SimpleNamespace(success=True, status_code=200, text=e["context"])


def baseline(p, registry):
    result = ids.apply_to_payload(p, registry, ids.digest(review.registry_bytes(registry)))
    result.pop("identity_held_records")
    return result


def run(p, registry, state, *, limit=50, now=NOW):
    plan = review.prepare(p, registry, state, now=now, limit=limit)
    evidence = [evidence_for(h) for h in plan["eligible"]]
    pages = {e["url"]: page(e) for e in evidence}
    return review.stage(p, registry, plan, evidence, public_baseline=baseline(p, registry), now=now, fetch=pages.__getitem__)


def test_additive_review_replay_and_same_day_rerun_do_not_create_duplicates():
    p, registry, state = setup()
    before = deepcopy(registry)
    result = run(p, registry, state)
    assert registry == before
    assert len(result["report"]["new_ids"]) == 1
    assert result["registry"]["events"][0] == registry["events"][0]
    assert result["state"]["batches"][0]["items"][0]["cohort"] == "backlog"
    again = run(p, result["registry"], result["state"])
    assert again["registry"] == result["registry"]
    assert again["report"]["new_ids"] == []


def test_fifty_is_a_daily_budget_across_runs_and_overflow_is_retained():
    p, registry, state = setup(tuple(f"N{i:02}" for i in range(53)))
    result = run(p, registry, state, limit=49)
    assert len(result["report"]["new_ids"]) == 49
    second = run(p, result["registry"], result["state"])
    assert len(second["report"]["new_ids"]) == 1
    third = run(p, second["registry"], second["state"])
    assert third["report"]["new_ids"] == []
    assert len(review.prepare(p, second["registry"], second["state"], now=NOW)["eligible"]) == 3


def test_lost_state_cannot_reset_committed_quota():
    p, registry, state = setup()
    result = run(p, registry, state)
    corrupted = deepcopy(result["state"])
    corrupted["batches"] = []
    with pytest.raises(ValueError, match="lost automated transactions"):
        review.prepare(p, result["registry"], corrupted, now=NOW)


def test_existing_identity_change_stops_promotion_and_never_gets_new_id():
    p, registry, state = setup()
    changed = payload([row("SEED", event_start_time="19:00"), row("A")])
    plan = review.prepare(changed, registry, state, now=NOW)
    assert plan["stops"][0]["reason"] == "existing_identity_review_required"
    assert all(not h["related_event_uids"] and h["reason"] == "unregistered_candidate" for h in plan["eligible"])
    result = run(changed, registry, state)
    assert result["report"]["status"] == "stopped"
    assert result["registry"]["events"][0] == registry["events"][0]


def test_possible_published_duplicate_with_different_source_is_held():
    p, registry, state = setup()
    duplicate = row("SEED", record_id="different-id", event_start_time="")
    plan = review.prepare(payload([row("SEED"), duplicate]), registry, state, now=NOW)
    assert not plan["eligible"]


def retimed_source(*, old_time="15:00", new_time="17:00", **changes):
    old = row("SEED", event_date="2026-12-06", event_end_date="2026-12-06",
        event_start_time=old_time, artist_name="BIGBANG", title="BIGBANG 2026 WORLD TOUR IN JAPAN")
    registry = seed(old)
    current = {**old, "record_id": "new-official-record", "event_start_time": new_time,
        "title": "BIGBANG 2026-2027 WORLD TOUR XX : COSMOS IN JAPAN", **changes}
    # The old source can disappear entirely; registry history still matters.
    p = payload([current])
    state = review.initial_state(p, registry, now=NOW, source_sha="a" * 40)
    h = ids.resolve_rows(p["events"], registry)[1][0]
    assert h["reason"] == "unregistered_candidate" and not h["related_event_uids"]
    return p, registry, state, h


def test_bigbang_style_1500_to_1700_with_disjoint_source_and_missing_old_candidate_is_held():
    p, registry, state, h = retimed_source()
    plan = review.prepare(p, registry, state, now=NOW)
    assert plan["eligible"] == []
    assert plan["deferred"] == [{"fingerprint": h["fingerprint"],
        "reason": "possible_existing_correction_or_multiple_performances"}]
    assert registry == seed(row("SEED", event_date="2026-12-06", event_end_date="2026-12-06",
        event_start_time="15:00", artist_name="BIGBANG", title="BIGBANG 2026 WORLD TOUR IN JAPAN"))


def test_real_separate_same_day_performance_needs_separate_identity_review():
    # Even an actual matinee/evening pair cannot be distinguished from a time
    # correction by disjoint source IDs, matching text and different times alone.
    p, registry, state, h = retimed_source(title="別の夜公演", new_time="20:00")
    plan = review.prepare(p, registry, state, now=NOW)
    assert plan["eligible"] == []
    assert plan["deferred"][0]["fingerprint"] == h["fingerprint"]
    assert p["events"][0]["event_start_time"] == "20:00"
    assert registry["events"][0]["observations"][0]["identity"]["event_start_time"] == "15:00"


@pytest.mark.parametrize("old_time,new_time", [("", "17:00"), ("15:00", ""), ("", "")])
def test_missing_start_time_never_proves_a_new_occurrence(old_time, new_time):
    p, registry, state, _ = retimed_source(old_time=old_time, new_time=new_time)
    assert not review.prepare(p, registry, state, now=NOW)["eligible"]


@pytest.mark.parametrize("changes", [
    {"artist_name": "無関係な出演者", "title": "まったく別の公演"},
    {"venue_name": "別の会場"},
    {"event_date": "2026-12-07", "event_end_date": "2026-12-07"},
])
def test_unrelated_artist_venue_or_day_can_still_be_new(changes):
    p, registry, state, h = retimed_source(**changes)
    assert review.prepare(p, registry, state, now=NOW)["eligible"] == [h]


def test_similar_title_with_changed_artist_label_is_also_held():
    p, registry, state, _ = retimed_source(artist_name="BIGBANG 表記追加",
        title="BIGBANG 2026 WORLD TOUR IN JAPAN")
    assert not review.prepare(p, registry, state, now=NOW)["eligible"]


def test_consumer_published_time_mismatch_is_held_even_without_registry_source_link():
    p, registry, state = setup()
    h = ids.resolve_rows(p["events"], registry)[1][0]
    public = {**h["identity"], "event_start_time": "15:00"}
    assert not review.prepare(p, registry, state, now=NOW, published_identities=[public])["eligible"]


def test_stage_defends_against_an_old_plan_that_eligible_time_changed_existing_event():
    p, registry, state, h = retimed_source()
    plan = review.prepare(p, registry, state, now=NOW)
    plan["eligible"], plan["deferred"] = [h], []  # Simulate an old unsafe selection.
    e = evidence_for(h)
    result = review.stage(p, registry, plan, [e], public_baseline=baseline(p, registry), now=NOW,
        fetch=lambda _: pytest.fail("existing occurrence must be held before fetching"))
    assert result["report"]["new_ids"] == []
    assert result["registry"] == registry and result["requests"] == []
    assert result["report"]["held"][0]["reason"] == "possible_existing_correction_or_multiple_performances"


def test_audit_rejects_legacy_staged_time_changed_new_event_even_with_exact_plan_binding(monkeypatch):
    p, registry, state, h = retimed_source()
    # Produce the self-consistent private transaction that the old time check
    # allowed. Restore the guard before auditing the plan and all staged files.
    with monkeypatch.context() as old:
        old.setattr(review, "duplicate_occurrence", lambda *_: False)
        plan = review.prepare(p, registry, state, now=NOW)
        e = evidence_for(h)
        e["url"] = p["events"][0]["url"]
        result = review.stage(p, registry, plan, [e], public_baseline=baseline(p, registry),
            now=NOW, fetch=lambda _: page(e))
    assert len(result["report"]["new_ids"]) == 1
    with pytest.raises(ValueError, match="existing identity correction or multiple performances"):
        review.audit_bundle(p, registry, plan, baseline(p, registry), after=result["registry"],
            after_sha=ids.digest(review.registry_bytes(result["registry"])), lp=result["lp"], state=result["state"],
            report=result["report"], requests=result["requests"], evidence=result["evidence"], now=NOW)


def test_time_difference_within_one_batch_is_not_automatic_proof_of_two_new_performances():
    registry = seed()
    p = payload([row("SEED"), row("A", event_start_time="15:00", record_id="matinee"),
        row("A", event_start_time="17:00", record_id="evening")])
    state = review.initial_state(p, registry, now=NOW, source_sha="a" * 40)
    plan = review.prepare(p, registry, state, now=NOW)
    assert len(plan["eligible"]) == 2
    evidence = [evidence_for(h) for h in plan["eligible"]]
    context = " / ".join(e["context"] for e in evidence)
    for e in evidence:
        e["context"] = context
    result = review.stage(p, registry, plan, evidence, public_baseline=baseline(p, registry),
        now=NOW, fetch=lambda _: page(evidence[0]))
    assert len(result["report"]["new_ids"]) == 1
    assert result["report"]["held"][0]["reason"] == "possible_batch_duplicate"
    assert len(result["registry"]["events"]) == len(registry["events"]) + 1
    assert sorted(r["event_start_time"] for r in p["events"] if r["artist_name"] == "架空出演者A") == ["15:00", "17:00"]


def test_existing_two_day_unit_cannot_be_automatically_split_into_a_new_second_day():
    old = row("SEED", event_date="2027-03-13", event_end_date="2027-03-14", event_start_time="")
    registry = seed(old)
    p = payload([{**old, "event_date": "2027-03-14", "event_start_time": "16:00",
        "record_id": "new-second-day-record", "title": old["title"] + " 日別表記"}])
    state = review.initial_state(p, registry, now=NOW, source_sha="a" * 40)
    assert not review.prepare(p, registry, state, now=NOW)["eligible"]


def test_same_batch_duplicate_is_held_instead_of_allocating_second_id():
    p, registry, state = setup()
    # Differing titles/source keys can still describe one occurrence.
    # Group keys ordinarily consolidate these; emulate two separately keyed candidates.
    candidate = deepcopy(p["events"][0] if p["events"][0]["venue_name"] == "架空会場A" else p["events"][1])
    candidate["event_key"] = "different-candidate"
    candidate["title"] += " 追加表記"
    candidate["supporting_sources"][0]["record_id"] = "other"
    combined = deepcopy(p)
    combined["events"].append(candidate)
    combined["summary"]["event_count"] += 1
    combined["summary"]["counts_by_display_source"]["official_events"] += 1
    _, held = ids.resolve_rows(combined["events"], registry)
    state = review.initial_state(combined, registry, now=NOW, source_sha="a" * 40)
    plan = review.prepare(combined, registry, state, now=NOW)
    evidence = [evidence_for(h) for h in held]
    result = review.stage(combined, registry, plan, evidence, public_baseline=baseline(combined, registry), now=NOW, fetch=lambda _: page(evidence[0]))
    assert len(result["report"]["new_ids"]) == 1
    assert any(h["reason"] == "possible_batch_duplicate" for h in result["report"]["held"])


def test_official_failure_holds_only_that_candidate():
    p, registry, state = setup(("A", "B"))
    plan = review.prepare(p, registry, state, now=NOW)
    evidence = [evidence_for(h) for h in plan["eligible"]]
    def fetch(url):
        if url.endswith("A"):
            raise ConnectionError("fictional outage")
        return page(evidence[1])
    result = review.stage(p, registry, plan, evidence, public_baseline=baseline(p, registry), now=NOW, fetch=fetch)
    assert len(result["report"]["new_ids"]) == 1
    assert result["report"]["held"][0]["error_type"] == "ConnectionError"


@pytest.mark.parametrize("change", [
    {"source_class": "news"}, {"url": "https://unrelated.example/event"},
    {"reviewed_at_utc": "2026-10-27T00:00:00Z"},
    {"time_text": "OPEN 18:00"}, {"time_text": "OPEN 18:00 START 19:00"}, {"date_text": "2026-11-011"},
    {"artist_text": "別の出演者"}, {"identity": {}},
])
def test_ambiguous_or_unofficial_evidence_is_not_applied(change):
    p, registry, state = setup()
    plan = review.prepare(p, registry, state, now=NOW)
    e = evidence_for(plan["eligible"][0])
    e.update(change)
    result = review.stage(p, registry, plan, [e], public_baseline=baseline(p, registry), now=NOW, fetch=lambda _: page(e))
    assert result["registry"] == registry
    assert result["report"]["new_ids"] == []


def test_context_must_be_present_on_live_official_page():
    p, registry, state = setup()
    plan = review.prepare(p, registry, state, now=NOW)
    e = evidence_for(plan["eligible"][0])
    result = review.stage(p, registry, plan, [e], public_baseline=baseline(p, registry), now=NOW,
        fetch=lambda _: SimpleNamespace(success=True, status_code=200, text="unrelated calendar"))
    assert result["registry"] == registry


def test_daily_and_backlog_cohorts_and_surge_are_distinct():
    p, registry, state = setup()
    p2 = payload([row("SEED"), row("A"), row("NEW", first_seen_at_utc="2026-10-28T11:01:00Z")])
    plan = review.prepare(p2, registry, state, now="2026-10-28T11:02:00Z", cohort="daily")
    assert [h["identity"]["artist_name"] for h in plan["eligible"]] == ["架空出演者NEW"]
    many = payload([row("SEED"), *[row(str(i), first_seen_at_utc="2026-10-28T11:01:00Z") for i in range(51)]])
    plan = review.prepare(many, registry, state, now="2026-10-28T11:02:00Z", cohort="daily")
    assert plan["stops"][0]["reason"] == "candidate_surge"
    assert not review.prepare(p, registry, state, now=NOW)["stops"]


def test_consumer_excluded_candidates_are_not_reviewed():
    p, registry, state = setup()
    plan = review.prepare(p, registry, state, now=NOW, publishable_keys=set())
    assert plan["eligible"] == []
    assert plan["deferred"][0]["reason"] == "consumer_policy_excluded"


def test_already_published_consumer_occurrence_blocks_a_new_unrelated_source_key():
    p, registry, state = setup()
    held = ids.resolve_rows(p["events"], registry)[1][0]
    plan = review.prepare(p, registry, state, now=NOW, published_identities=[held["identity"]])
    assert plan["eligible"] == []
    assert plan["deferred"][0]["reason"] == "possible_published_duplicate"


def test_prepared_review_cannot_cross_jst_midnight():
    p, registry, state = setup()
    plan = review.prepare(p, registry, state, now="2026-10-28T14:59:00Z")
    with pytest.raises(ValueError, match="crossed JST"):
        review.stage(p, registry, plan, [], public_baseline=baseline(p, registry), now="2026-10-28T15:00:00Z")


def test_additive_audit_rejects_existing_id_mutation_or_row_deletion():
    p, registry, state = setup()
    result = run(p, registry, state)
    tampered = deepcopy(result["registry"])
    tampered["events"][0]["observations"][0]["identity"]["title"] = "changed"
    with pytest.raises(ValueError):
        review.assert_additive(registry, tampered, [], [], set())
    before_rows, _ = ids.resolve_rows(p["events"], registry)
    with pytest.raises(ValueError, match="strictly additive"):
        review.assert_additive(registry, result["registry"], before_rows, [], set(result["report"]["new_ids"]))


def test_ingestion_needs_success_current_inbox_correct_workflow_and_fresh_time():
    run = dict(id=12, repository={"full_name": review.REPOSITORY}, path=review.WORKFLOW,
        head_branch="main", head_sha="a" * 40, status="completed", conclusion="success", updated_at=NOW)
    def check(value, **kwargs):
        return review.ingestion_receipt(value, now=NOW, ancestor=lambda _: True,
            inbox_at_head=b"same", current_inbox=kwargs.get("current", b"same"))
    assert check(run)["run_id"] == 12
    for key, value in (("conclusion", "failure"), ("status", "in_progress"), ("head_branch", "other"), ("path", "other.yml"), ("updated_at", "2026-10-26T00:00:00Z")):
        with pytest.raises(ValueError):
            check({**run, key: value})
    with pytest.raises(ValueError, match="not covered"):
        check(run, current=b"new inbox")


@pytest.mark.parametrize("url", ["http://example.com", "https://localhost/a", "https://127.0.0.1/a", "https://example.com:8443/a", "https://user:password@example.com/a"])
def test_credentials_and_non_public_fetch_targets_are_refused(url):
    with pytest.raises(ValueError):
        review.safe_url(url)
