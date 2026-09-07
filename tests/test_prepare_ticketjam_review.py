from scripts.prepare_ticketjam_review import prepare_batch, resolve_covered_candidates
from scripts.ticketjam_review_state import fingerprint


def candidate(key="lead", **extra):
    return {
        "event_key": key,
        "event_date": "2026-09-20",
        "event_start_time": "18:00",
        "venue_name": "Hall",
        "artist_name": "Artist",
        "title": "Concert",
        "status": "pending_official",
        "review_due": True,
        "search_queries": ["Artist Hall official"],
        **extra,
    }


def test_only_strict_existing_coverage_is_resolved_without_new_web_claim():
    lead = candidate()
    target = {
        **lead,
        "display_source_id": "official_events",
        "evidence_url": "https://venue.example/event",
    }
    alias = candidate(
        "alias", artist_name="Artist (reading)", matching_event_keys=["lead"]
    )
    state, resolved = resolve_covered_candidates(
        {"events": [target]},
        {"candidates": [lead, alias]},
        {"schema_version": 1, "events": {}},
        "2026-09-07T00:00:00Z",
    )
    assert resolved == ["lead"]
    latest = state["events"]["lead"]["history"][-1]
    assert latest["status"] == "duplicate"
    assert latest["duplicate_target_fingerprint"] == fingerprint(target)


def test_due_batch_is_bounded_and_prefers_existing_verification_url():
    due = candidate(verification_urls=["https://artist.example/tour"])
    not_due = candidate("later", review_due=False)
    expired = candidate("past", status="expired")
    plan = prepare_batch(
        {
            "as_of_date": "2026-09-07",
            "candidates": [not_due, due, expired],
            "official_rechecks": [],
        },
        max_candidates=1,
    )
    assert plan["selected_count"] == 1
    assert plan["groups"][0]["reference_urls"] == ["https://artist.example/tour"]
    assert plan["groups"][0]["candidates"][0]["candidate_fingerprint"] == fingerprint(
        due
    )


def test_already_confirmed_history_is_not_downgraded_to_duplicate():
    lead = candidate()
    target = {**lead, "display_source_id": "venue_web_discovery"}
    state = {
        "schema_version": 1,
        "events": {"lead": {"history": [{"status": "confirmed"}]}},
    }
    updated, resolved = resolve_covered_candidates(
        {"events": [target]}, {"candidates": [lead]}, state, "2026-09-07T00:00:00Z"
    )
    assert resolved == []
    assert updated == state
