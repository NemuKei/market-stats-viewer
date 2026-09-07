from copy import deepcopy

import pytest

from scripts.ticketjam_review_state import (
    apply_reviews,
    due_review,
    promote_confirmed,
    fingerprint,
)


def candidate():
    return {
        "event_key": "one",
        "event_date": "2026-09-13",
        "event_start_time": "13:00",
        "venue_name": "Zepp Namba",
        "artist_name": "Persona",
        "title": "Persona LIVE",
    }


def decision(status="confirmed"):
    return {
        "event_key": "one",
        "candidate_fingerprint": fingerprint(candidate()),
        "status": status,
        "checked_at_utc": "2026-09-07T03:00:00Z",
        "next_check_date": "2026-09-10",
        "reason": "本文で日付・会場・公演を確認",
        "official_event": {
            "event_id": "ticketjam-one",
            "title": "Persona LIVE",
            "artist_name": "Persona",
            "venue_name": "Zepp Namba",
            "event_start_date": "2026-09-13",
            "event_start_time": "13:00",
            "source_class": "promoter_official",
            "url": "https://official.example/concert",
            "evidence_url": "https://official.example/concert",
            "evidence_snippet": "2026-09-13 Zepp Namba Persona LIVE 13:00",
            "content_extractor": "requests_bs4",
        },
    }


def test_history_is_idempotent_and_new_candidate_data_invalidates_schedule():
    c = candidate()
    d = decision()
    state = apply_reviews({}, [c], [d])
    assert apply_reviews(state, [c], [d]) == state
    assert not due_review(c, state, "2026-09-09")
    assert due_review(c, state, "2026-09-10")
    changed = {**c, "event_start_time": "18:00"}
    assert due_review(changed, state, "2026-09-09")
    assert len(state["events"]["one"]["history"]) == 1


def test_conflict_and_incomplete_never_promote():
    for status in [
        "conflict",
        "insufficient",
        "fetch_failed",
        "duplicate",
        "ancillary",
    ]:
        d = decision(status)
        if status == "conflict":
            d["official_values"] = {"venue_name": "Different official venue"}
        state = apply_reviews({}, [candidate()], [d])
        assert (
            promote_confirmed({"confirmed_events": []}, state)["confirmed_events"] == []
        )


def test_mismatched_official_date_rejected_without_mutation():
    d = decision()
    d["official_event"]["event_start_date"] = "2026-09-14"
    state = {}
    before = deepcopy(state)
    with pytest.raises(ValueError):
        apply_reviews(state, [candidate()], [d])
    assert state == before


def test_config_conflict_is_not_silently_overwritten():
    state = apply_reviews({}, [candidate()], [decision()])
    config = promote_confirmed({"confirmed_events": []}, state)
    assert promote_confirmed(config, state) == config
    config["confirmed_events"][0]["venue_name"] = "Other"
    with pytest.raises(ValueError):
        promote_confirmed(config, state)


def test_missing_evidence_and_unknown_candidate_rejected():
    d = decision()
    del d["official_event"]["evidence_snippet"]
    with pytest.raises(ValueError):
        apply_reviews({}, [candidate()], [d])
    with pytest.raises(ValueError):
        apply_reviews({}, [], [decision()])


def test_confirmed_event_remains_scheduled_after_leaving_ticketjam_queue():
    from scripts.ticketjam_discovery import build_review_queue

    c = candidate()
    state = apply_reviews({}, [c], [decision()])
    p = {
        "as_of_date": "2026-09-10",
        "events": [{**c, "display_source_id": "venue_web_discovery"}],
    }
    q = build_review_queue(p, state)
    assert q["candidates"] == []
    assert q["official_rechecks"][0]["review_due"] is True
    later = decision()
    later["checked_at_utc"] = "2026-09-10T03:00:00Z"
    config = promote_confirmed({"confirmed_events": []}, state)
    updated = apply_reviews(state, q["official_rechecks"], [later])
    assert len(promote_confirmed(config, updated)["confirmed_events"]) == 1


def test_stale_review_cannot_be_applied_to_changed_candidate():
    changed = {**candidate(), "title": "New title"}
    with pytest.raises(ValueError, match="fingerprint"):
        apply_reviews({}, [changed], [decision()])


def test_conflict_needs_an_actual_structured_disagreement():
    d = decision("conflict")
    d["official_values"] = {"event_start_time": "13:00"}
    with pytest.raises(ValueError, match="disagreement"):
        apply_reviews({}, [candidate()], [d])
    d["official_values"] = {"event_start_time": "16:00"}
    assert (
        apply_reviews({}, [candidate()], [d])["events"]["one"]["history"][-1]["status"]
        == "conflict"
    )


def test_explicit_config_amendment_requires_exact_previous_fingerprint():
    from scripts.ticketjam_review_state import config_fingerprint

    state = apply_reviews({}, [candidate()], [decision()])
    config = promote_confirmed({"confirmed_events": []}, state)
    later = decision()
    later["checked_at_utc"] = "2026-09-08T03:00:00Z"
    later["official_event"]["artist_name"] = "Official band name"
    later["replaces_config_fingerprint"] = config_fingerprint(
        config["confirmed_events"][0]
    )
    updated = apply_reviews(state, [candidate()], [later])
    result = promote_confirmed(config, updated)
    assert result["confirmed_events"][0]["artist_name"] == "Official band name"
    config["confirmed_events"][0]["title"] = "Concurrent change"
    with pytest.raises(ValueError):
        promote_confirmed(config, updated)


def test_official_alternative_times_only_conflict_when_candidate_is_absent():
    d = decision("conflict")
    d["official_values"] = {"event_start_time": ["13:00", "18:00"]}
    with pytest.raises(ValueError, match="disagreement"):
        apply_reviews({}, [candidate()], [d])
    d["official_values"] = {"event_start_time": ["14:00", "18:00"]}
    assert (
        apply_reviews({}, [candidate()], [d])["events"]["one"]["history"][-1]["status"]
        == "conflict"
    )
