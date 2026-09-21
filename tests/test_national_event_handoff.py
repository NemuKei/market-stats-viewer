from copy import deepcopy
import json
import csv
from pathlib import Path

import pytest

from scripts.national_event_handoff import (
    digest,
    load_json,
    scope_bundle,
    stage_official_event,
    validate_proposal,
    validate_submission_paths,
)

from scripts.national_event_state import (
    empty_state,
    plan_run,
    record_proposal,
    record_run,
    save_state,
)
from scripts.ticketjam_review_state import fingerprint


@pytest.mark.parametrize(
    "path,mode,status",
    [
        ("scripts/update_event_signals_data.py", "100644", "modified"),
        ("docs/ai/event-proposals/example.json", "120000", "added"),
        ("docs/ai/event-proposals/../../code.json", "100644", "added"),
        ("docs/ai/event-proposals/example.json", "100644", "removed"),
    ],
)
def test_runtime_submission_rejects_code_symlink_traversal_and_removal(
    path, mode, status
):
    with pytest.raises(ValueError, match="only regular"):
        validate_submission_paths([dict(path=path, mode=mode, status=status)])


def test_regular_data_only_proposal_path_is_accepted():
    validate_submission_paths(
        [
            dict(
                path="docs/ai/event-proposals/synthetic-1.json",
                mode="100644",
                status="added",
            )
        ]
    )


def test_work_cannot_add_hidden_code_or_invent_unannounced_start_time():
    p = proposal()
    d = decision(p)
    d["official_event"]["command"] = "ignored is not sufficient; reject"
    with pytest.raises(ValueError, match="unsupported official"):
        stage_official_event(p, d, REGISTRY, **context())
    d = decision(p)
    d["official_event"]["event_start_time"] = "18:00"
    with pytest.raises(ValueError, match="start time disagrees"):
        stage_official_event(p, d, REGISTRY, **context())


BASE = "a" * 40
REGISTRY = [
    dict(
        venue_id="arena",
        venue_name="試験アリーナ",
        pref_code="47",
        pref_name="沖縄県",
        capacity="",
        is_enabled="0",
        official_url="https://venue.example/",
    )
]
CONFIG = {"watch_venues": []}


def bundle():
    return scope_bundle(REGISTRY, CONFIG, [], [])


def proposal():
    return dict(
        schema_version=1,
        stream="announcement",
        scope_revision=bundle()["scope_revision"],
        base_commit=BASE,
        venue_id="arena",
        event_key=None,
        candidate_fingerprint=None,
        change_type="new",
        current_values={},
        proposed_values=dict(
            event_date="2030-12-01",
            event_start_time=None,
            venue_name="試験アリーナ",
            artist_name="試験出演者",
            title="試験公演",
        ),
        source_class="news",
        discovery_url="https://news.example/notice",
        evidence_url=None,
        evidence_summary="合成データ。実公演ではない。",
        published_at_utc=None,
        observed_at_utc="2030-09-20T15:30:00Z",
        retrieval_method="web_open",
        evidence_status="lead_only",
        unresolved_fields=[],
        next_check_date="2030-09-22",
    )


def context():
    return dict(base_commit=BASE, scope_revision=bundle()["scope_revision"])


@pytest.mark.parametrize("change", ["time", "date", "cancelled", "postponed"])
def test_published_non_ticketjam_correction_keeps_real_origin(change):
    from scripts.national_event_handoff import published_snapshot

    p, d, queue = correction_case(change)
    p["stream"] = "venue_official"
    row = dict(queue["candidates"][0], display_source_id="official_events")
    payload = {"schema_version": 1, "events": [row]}
    p["candidate_fingerprint"] = digest(row)
    d["proposal_hash"] = digest(p)
    snapshot = published_snapshot(payload, base_commit=BASE)
    before = deepcopy((snapshot, p))
    staged = stage_official_event(p, d, REGISTRY, published=snapshot, **context())
    assert staged["origin"]["event_key"] == row["event_key"]
    assert staged["origin"]["kind"] == "published_event"
    assert staged["origin"]["published_input_fingerprint"] == digest(payload)
    assert staged["candidate_review_state"] is None
    assert not staged["can_publish"]
    assert (snapshot, p) == before


@pytest.mark.parametrize(
    "bad", ["base", "payload", "fingerprint", "current", "unknown", "duplicate"]
)
def test_published_corrections_reject_stale_or_ambiguous_inputs(bad):
    from scripts.national_event_handoff import published_snapshot

    p, _, queue = correction_case()
    p["stream"] = "announcement"
    row = dict(queue["candidates"][0], display_source_id="official_events")
    payload = {"schema_version": 1, "events": [row]}
    p["candidate_fingerprint"] = digest(row)
    snapshot = published_snapshot(payload, base_commit=BASE)
    if bad == "base":
        snapshot["base_commit"] = "b" * 40
    elif bad == "payload":
        snapshot["payload"]["events"][0]["event_status"] = "cancelled"
    elif bad == "fingerprint":
        p["candidate_fingerprint"] = "0" * 64
    elif bad == "current":
        p["current_values"]["event_start_time"] = "16:00"
    elif bad == "unknown":
        p["event_key"] = "unknown"
    else:
        snapshot["payload"]["events"].append(deepcopy(row))
        snapshot["lp_fingerprint"] = digest(snapshot["payload"])
    with pytest.raises(ValueError):
        validate_proposal(p, REGISTRY, published=snapshot, **context())


def decision(p):
    return dict(
        proposal_hash=digest(p),
        base_commit=BASE,
        status="confirmed",
        reason="Work synthetic verification",
        checked_at_utc="2030-09-21T00:00:00Z",
        next_check_date="2030-09-22",
        official_event=dict(
            event_id="synthetic-2030",
            title="試験公演",
            artist_name="試験出演者",
            venue_name="試験アリーナ",
            pref_name="沖縄県",
            event_start_date="2030-12-01",
            source_class="artist_official",
            evidence_url="https://artist.example/tour",
            url="https://artist.example/tour",
            evidence_snippet="合成fixture: 2030-12-01 試験アリーナ 試験出演者",
            content_extractor="requests_bs4",
        ),
    )


def test_scope_keeps_disabled_unknown_capacity_and_all_empty_prefectures():
    scopes = bundle()["scopes"]
    assert len(scopes) == 47
    assert scopes[0]["venues"] == [] and scopes[0]["review_status"] == "pending"
    assert scopes[-1]["venues"][0]["venue_id"] == "arena"
    assert not bundle()["national_census_complete"]


def test_news_and_unannounced_date_can_be_received_but_not_published():
    p = proposal()
    p["proposed_values"]["event_date"] = None
    r = validate_proposal(p, REGISTRY, **context())
    assert r["missing_event_date"] and not r["can_publish"]
    with pytest.raises(ValueError, match="unannounced"):
        stage_official_event(p, decision(p), REGISTRY, **context())


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_commit", "b" * 40),
        ("scope_revision", "stale"),
        ("venue_id", "unregistered"),
        ("venue_id", None),
        ("stream", "untrusted"),
        ("evidence_status", "approved"),
        ("source_class", "admin"),
        ("discovery_url", "https://user:secret@news.example/"),
        ("observed_at_utc", "2030-09-20T00:00:00"),
        ("next_check_date", "2020-01-01"),
    ],
)
def test_invalid_or_stale_proposals_stop(field, value):
    p = proposal()
    p[field] = value
    with pytest.raises(ValueError):
        validate_proposal(p, REGISTRY, **context())


def test_instructions_and_unknown_event_fields_are_not_executable_inputs():
    p = proposal()
    p["command"] = "touch unexpected-file"
    with pytest.raises(ValueError, match="data-only"):
        validate_proposal(p, REGISTRY, **context())
    p = proposal()
    p["proposed_values"]["code"] = "print('unsafe')"
    with pytest.raises(ValueError, match="unsupported event fields"):
        validate_proposal(p, REGISTRY, **context())


def test_unknown_stadium_identity_is_not_silently_coerced():
    p = proposal()
    p["proposed_values"]["venue_name"] = "別のスタジアム"
    with pytest.raises(ValueError, match="ID and name"):
        validate_proposal(p, REGISTRY, **context())


def test_separate_work_verification_stages_existing_shape_without_publishing():
    p = proposal()
    d = decision(p)
    before = deepcopy((p, d, REGISTRY))
    r = stage_official_event(p, d, REGISTRY, **context())
    assert r["status"] == "verified_draft" and not r["can_publish"]
    assert "event_key" not in r["official_event"]
    assert r["official_event"]["event_start_date"] == "2030-12-01"
    assert (p, d, REGISTRY) == before


@pytest.mark.parametrize(
    "host",
    ["x.com", "twitter.com", "instagram.com", "ticketjam.jp", "www.wikipedia.org"],
)
def test_official_assertion_does_not_promote_standalone_social_or_secondary(host):
    p = proposal()
    p.update(source_class="artist_official", evidence_status="official_body")
    d = decision(p)
    d["official_event"]["evidence_url"] = f"https://{host}/post"
    with pytest.raises(ValueError, match="cannot be promoted"):
        stage_official_event(p, d, REGISTRY, **context())


@pytest.mark.parametrize(
    "field,value",
    [
        ("artist_name", "別の出演者"),
        ("pref_name", "東京都"),
        ("event_start_date", "2030-12-02"),
        ("event_status", "cancelled"),
    ],
)
def test_work_evidence_must_match_proposed_facts(field, value):
    p = proposal()
    d = decision(p)
    d["official_event"][field] = value
    with pytest.raises(ValueError):
        stage_official_event(p, d, REGISTRY, **context())


def test_ticketjam_reuses_actual_candidate_fingerprint_and_review_validator():
    p = proposal()
    p["stream"] = "ticketjam"
    candidate = dict(event_key="existing-real-key", **p["proposed_values"])
    p.update(
        event_key=candidate["event_key"], candidate_fingerprint=fingerprint(candidate)
    )
    queue = {"candidates": [candidate]}
    assert (
        stage_official_event(p, decision(p), REGISTRY, queue=queue, **context())[
            "status"
        ]
        == "verified_draft"
    )
    queue["candidates"][0]["title"] = "changed input"
    with pytest.raises(ValueError, match="stale"):
        validate_proposal(p, REGISTRY, queue=queue, **context())


def test_strict_json_rejects_duplicate_keys_and_oversize(tmp_path):
    path = tmp_path / "proposal.json"
    path.write_text('{"stream":"news","stream":"venue_official"}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        load_json(path)
    path.write_text(" " * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="256 KiB"):
        load_json(path)


def plan(state, **kwargs):
    return plan_run(
        state,
        stream="announcement",
        observed_at_utc="2030-09-20T15:30:00Z",
        scope_revision="v1",
        target_ids=["01", "47", "13"],
        limit=2,
        **kwargs,
    )


def observation(target, status="checked"):
    return dict(
        target_id=target,
        status=status,
        observed_at_utc="2030-09-20T15:40:00Z",
        covered_range="official schedule September-December"
        if status == "checked"
        else None,
        reason="fixture only",
    )


def test_daily_jst_identity_failure_counts_and_resume_do_not_drop_unvisited():
    state = empty_state()
    first = plan(state)
    assert "|2030-09-21|" in first["run_key"]
    state = record_run(
        state, first, [observation("01"), observation("13", "fetch_failed")]
    )
    second = plan(state)
    assert second["selected_ids"] == ["47"]
    assert second["counts"] == dict(target=3, checked=1, fetch_failed=1, unvisited=1)
    assert "announcement|13" not in state["last_success"]
    state = record_run(state, second, [observation("47")])
    assert plan(state)["status"] == "finished_with_failures"
    assert plan(state)["publication_status"] == "not_started"


def test_oldest_unchecked_priority_and_no_progress_stop():
    state = empty_state()
    state["last_success"]["announcement|01"] = "2030-09-20T00:00:00Z"
    p = plan(state)
    assert p["selected_ids"] == ["13", "47"]
    with pytest.raises(ValueError, match="no progress"):
        record_run(state, p, [])


def test_stale_writer_duplicate_observation_and_scope_change_stop():
    state = empty_state()
    p = plan(state)
    newer = record_run(state, p, [observation("01")])
    with pytest.raises(ValueError, match="state advanced"):
        record_run(newer, p, [observation("13")])
    with pytest.raises(ValueError, match="duplicate"):
        record_run(state, p, [observation("01"), observation("01")])
    with pytest.raises(ValueError, match="scope revision"):
        plan_run(
            newer,
            stream="announcement",
            observed_at_utc="2030-09-20T15:30:00Z",
            scope_revision="v1",
            target_ids=["01"],
            limit=1,
        )


def test_cross_stream_same_change_coalesces_but_start_times_remain_distinct():
    state = empty_state()
    a = proposal()
    b = deepcopy(a)
    b.update(stream="venue_official", discovery_url="https://venue.example/calendar")
    for p in (a, b, b):
        state = record_proposal(state, validate_proposal(p, REGISTRY, **context()), p)
    assert len(state["proposals"]) == 1
    assert len(next(iter(state["proposals"].values()))["evidence"]) == 2
    c = deepcopy(a)
    c["proposed_values"]["event_start_time"] = "18:00"
    state = record_proposal(state, validate_proposal(c, REGISTRY, **context()), c)
    assert len(state["proposals"]) == 2


def test_local_atomic_state_rejects_stale_revision_and_existing_lock(tmp_path):
    path = tmp_path / "state.json"
    state = empty_state()
    newer = record_run(state, plan(state), [observation("01")])
    save_state(path, newer, expected_revision=digest(state))
    with pytest.raises(ValueError, match="state advanced"):
        save_state(path, state, expected_revision=digest(state))
    lock = path.with_name("state.json.lock")
    lock.write_text("another writer")
    with pytest.raises(ValueError, match="another writer"):
        save_state(path, state, expected_revision=digest(newer))
    assert json.loads(path.read_text()) == newer and lock.exists()


def test_real_nationwide_tour_fixture_keeps_every_stop_and_stops_unknown_venues():
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads(
        (
            root / "tests/fixtures/national_event_monitoring/sekai_no_owari_2027.json"
        ).read_text()
    )
    with (root / "data/venue_registry.csv").open() as handle:
        registry = list(csv.DictReader(handle))
    assert len(fixture["events"]) == 23
    assert len({r["venue_name"] for r in fixture["events"]}) == 11
    assert fixture["published_at_utc"] is None
    assert fixture["publication_status"] == "not_imported"
    checked, held = 0, 0
    for row in fixture["events"]:
        assert row["event_date"].startswith("2027-")
        assert row["open_time"] != row["event_start_time"]
        p = proposal()
        p.update(
            venue_id=row["registry_venue_id"],
            source_class="artist_official",
            evidence_url=fixture["evidence_url"],
            discovery_url=fixture["evidence_url"],
            evidence_status="official_body",
        )
        p["proposed_values"].update(
            event_date=row["event_date"],
            event_start_time=row["event_start_time"],
            venue_name=row["canonical_venue_name"],
            artist_name=fixture["artist_name"],
            title=fixture["title"],
        )
        if row["registry_venue_id"] is None:
            with pytest.raises(ValueError, match="unknown venue"):
                validate_proposal(p, registry, **context())
            held += 1
        else:
            receipt = validate_proposal(p, registry, **context())
            assert not receipt["can_publish"]
            checked += 1
    assert checked + held == 23 and held > 0


def test_census_review_queue_covers_all_prefectures_without_claiming_completeness():
    root = Path(__file__).resolve().parents[1]
    census = json.loads(
        (
            root / "docs/ai/national-event-monitoring-20260916/CENSUS_REVIEW_QUEUE.json"
        ).read_text()
    )
    assert not census["national_census_complete"]
    assert {r["pref_code"] for r in census["candidates"]} == {
        f"{i:02d}" for i in range(1, 48)
    }
    assert all(r["evidence"] for r in census["candidates"])
    for row in census["candidates"]:
        if row["scope_review"] == "operator_and_visible_schedule_reviewed":
            assert not row["missing_fields"]
            assert row["operator"] and row["address"] and row["capacity_basis"]
        else:
            assert row["missing_fields"]
    assert any(r["capacity"] is None for r in census["candidates"])
    assert any(r["venue_kind"] == "dome" for r in census["candidates"])


def test_synthetic_work_draft_reuses_existing_db_lp_and_manifest_pipeline(
    tmp_path, monkeypatch
):
    from datetime import date
    import requests
    from scripts.signals.sources.venue_web_discovery import VenueWebDiscoverySource
    from scripts.signals.types import SignalSourceRecord
    from scripts.update_events_data import init_db as init_events
    from scripts.update_event_signals_data import (
        init_db,
        ensure_default_sources,
        upsert_signals,
    )
    from scripts.build_lp_events import load_lp_records
    from scripts.ticketjam_discovery import build_discovery_bundle
    from scripts.build_external_events_manifest import _build_manifest
    from scripts.validate_external_events import validate_package

    init_events(tmp_path / "events.sqlite").close()
    conn = init_db(tmp_path / "event_signals.sqlite")
    ensure_default_sources(conn)
    p = proposal()
    staged = stage_official_event(p, decision(p), REGISTRY, **context())
    assert staged["can_publish"] is False
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(dict(future_only=False, confirmed_events=[staged["official_event"]]))
    )
    source = SignalSourceRecord(
        "venue_web_discovery",
        "Synthetic source",
        "https://artist.example/",
        "codex_web_discovery",
        json.dumps({"config_path": str(config_path)}),
        True,
    )
    # No network: the established plugin reads the staged local config.
    signals = VenueWebDiscoverySource(requests.Session()).fetch_signals(source)
    assert len(signals) == 1
    assert upsert_signals(conn, signals) == 1
    assert upsert_signals(conn, signals) == 0
    conn.commit()
    conn.close()
    records = load_lp_records(
        events_db_path=tmp_path / "events.sqlite",
        event_signals_db_path=tmp_path / "event_signals.sqlite",
        as_of_date=date(2030, 9, 21),
    )
    payload, _ = build_discovery_bundle(
        records,
        as_of_date=date(2030, 9, 21),
        review_state={"schema_version": 1, "events": {}},
    )
    assert len(payload["events"]) == 1
    assert payload["events"][0]["pref_name"] == "沖縄県"
    assert not payload["events"][0]["event_start_time"]
    assert payload["events"][0]["url"] == "https://artist.example/tour"
    (tmp_path / "lp_events.json").write_text(json.dumps(payload))
    monkeypatch.setenv("GITHUB_SHA", BASE)
    (tmp_path / "manifest.json").write_text(
        json.dumps(_build_manifest(tmp_path, "external-events-latest"))
    )
    assert (
        validate_package(tmp_path, expected_date="2030-09-21", expected_commit=BASE)[
            "event_count"
        ]
        == 1
    )


def correction_case(change="time"):
    p = proposal()
    old = dict(p["proposed_values"], event_start_time="19:00")
    new = dict(old)
    if change == "time":
        new["event_start_time"] = "18:30"
    elif change == "date":
        new["event_date"] = "2030-12-02"
    else:
        new["event_status"] = change
    candidate = dict(event_key="existing-ticketjam-key", **old)
    p.update(
        stream="ticketjam",
        current_values=old,
        proposed_values=new,
        event_key=candidate["event_key"],
        candidate_fingerprint=fingerprint(candidate),
        change_type=change if change in {"cancelled", "postponed"} else "correction",
    )
    d = decision(p)
    d["official_event"].update(
        event_start_date=new["event_date"],
        event_start_time=new["event_start_time"],
        event_status=new.get("event_status", "scheduled"),
    )
    return p, d, {"candidates": [candidate]}


@pytest.mark.parametrize(
    "change,field",
    [
        ("time", "event_start_time"),
        ("date", "event_date"),
        ("cancelled", "event_status"),
        ("postponed", "event_status"),
    ],
)
def test_r2_ticketjam_correction_keeps_conflict_separate_from_official_draft(
    change, field
):
    p, d, queue = correction_case(change)
    assert (
        validate_proposal(p, REGISTRY, queue=queue, **context())["status"]
        == "needs_work_verification"
    )
    staged = stage_official_event(p, d, REGISTRY, queue=queue, **context())
    assert staged["status"] == "verified_draft" and not staged["can_publish"]
    review = staged["candidate_review_state"]["events"][p["event_key"]]
    assert review["candidate_fingerprint"] == p["candidate_fingerprint"]
    assert review["candidate_snapshot"] == queue["candidates"][0]
    assert review["history"][-1]["status"] == "conflict"
    assert (
        review["history"][-1]["official_values"][field] == p["proposed_values"][field]
    )
    assert staged["origin"]["event_key"] == p["event_key"]
    assert staged["publication_status"] == "approval_pending"


def test_r2_keeps_prior_history_and_requires_exact_config_origin_and_replacement():
    from scripts.ticketjam_review_state import (
        apply_reviews,
        config_fingerprint,
        promote_confirmed,
    )

    p, d, queue = correction_case()
    old_decision = {
        k: deepcopy(d[k])
        for k in (
            "status",
            "reason",
            "checked_at_utc",
            "next_check_date",
            "official_event",
        )
    }
    old_decision.update(
        event_key=p["event_key"],
        candidate_fingerprint=p["candidate_fingerprint"],
        checked_at_utc="2030-09-20T16:00:00Z",
    )
    old_decision["official_event"]["event_start_time"] = "19:00"
    state = apply_reviews({}, queue["candidates"], [old_decision])
    config = promote_confirmed({"confirmed_events": []}, state)
    before = deepcopy((state, config))
    d["replaces_config_fingerprint"] = config_fingerprint(config["confirmed_events"][0])
    staged = stage_official_event(
        p, d, REGISTRY, queue=queue, review_state=state, config=config, **context()
    )
    history = staged["candidate_review_state"]["events"][p["event_key"]]["history"]
    assert (
        history == [old_decision, history[-1]] and history[-1]["status"] == "conflict"
    )
    assert (state, config) == before
    assert staged["config_review_status"] == "replacement_checked"
    changed = deepcopy(config)
    changed["confirmed_events"][0]["title"] = "concurrently changed"
    with pytest.raises(ValueError, match="conflicting existing"):
        stage_official_event(
            p, d, REGISTRY, queue=queue, review_state=state, config=changed, **context()
        )
    other = deepcopy(config)
    other["confirmed_events"][0]["discovery_event_key"] = "other-origin"
    d["replaces_config_fingerprint"] = config_fingerprint(other["confirmed_events"][0])
    with pytest.raises(ValueError, match="conflicting existing"):
        stage_official_event(
            p, d, REGISTRY, queue=queue, review_state=state, config=other, **context()
        )


@pytest.mark.parametrize("bad", ["fingerprint", "official", "venue"])
def test_r2_corrections_still_reject_stale_or_mismatched_evidence(bad):
    p, d, queue = correction_case()
    if bad == "fingerprint":
        queue["candidates"][0]["event_start_time"] = "20:00"
    elif bad == "official":
        d["official_event"]["event_start_time"] = "17:00"
    else:
        p["venue_id"] = "unknown"
        d["proposal_hash"] = digest(p)
    with pytest.raises(ValueError):
        stage_official_event(p, d, REGISTRY, queue=queue, **context())


@pytest.mark.parametrize(
    "observed,jst_day,previous",
    [
        ("2030-09-20T14:59:00Z", "2030-09-20", "2030-09-19"),
        ("2030-09-20T15:00:00Z", "2030-09-21", "2030-09-20"),
        ("2030-09-20T23:59:00Z", "2030-09-21", "2030-09-20"),
        ("2030-09-21T00:00:00Z", "2030-09-21", "2030-09-20"),
    ],
)
@pytest.mark.parametrize("entrypoint", ["proposal", "work", "ticketjam_review"])
def test_r3_next_check_uses_jst_at_both_midnight_boundaries(
    observed, jst_day, previous, entrypoint
):
    from datetime import date, timedelta
    from scripts.ticketjam_review_state import apply_reviews

    p = proposal()
    p.update(observed_at_utc=observed, next_check_date=jst_day)
    d = decision(p)
    d.update(checked_at_utc=observed, next_check_date=jst_day)
    candidate = dict(event_key="timing-test", **p["proposed_values"])

    def run(day):
        if entrypoint == "proposal":
            return validate_proposal(
                dict(p, next_check_date=day), REGISTRY, **context()
            )
        if entrypoint == "work":
            return stage_official_event(
                p, dict(d, next_check_date=day), REGISTRY, **context()
            )
        review = {
            k: deepcopy(d[k])
            for k in ("status", "reason", "checked_at_utc", "official_event")
        }
        review.update(
            event_key=candidate["event_key"],
            candidate_fingerprint=fingerprint(candidate),
            next_check_date=day,
        )
        return apply_reviews({}, [candidate], [review])

    with pytest.raises(ValueError, match="next check|review timing"):
        run(previous)
    assert run(jst_day)
    assert run((date.fromisoformat(jst_day) + timedelta(days=1)).isoformat())
