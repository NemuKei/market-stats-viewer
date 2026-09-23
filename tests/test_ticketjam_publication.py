from datetime import date

from scripts.ticketjam_discovery import build_discovery_bundle


def record(source, key, time=None, **extra):
    return dict(
        source_id=source,
        record_id=key,
        source_label=source,
        event_date="2026-09-20",
        event_end_date="2026-09-20",
        event_start_time=time,
        venue_name="Hall",
        artist_name="Artist",
        title="Artist concert",
        event_category="コンサート",
        event_status="scheduled",
        pref_name="東京都",
        url="https://official.example/" + key,
        evidence_url="https://official.example/" + key,
        evidence_snippet="official evidence",
        updated_at_utc="2026-09-07T00:00:00Z",
        **extra,
    )


def test_secondary_times_cannot_split_or_fill_authoritative_performance():
    pub, queue = build_discovery_bundle(
        [
            record("official_events", "official"),
            record("ticketjam_events", "noon", "12:00"),
            record("ticketjam_events", "evening", "18:00"),
        ],
        as_of_date=date(2026, 9, 7),
        review_state={"schema_version": 1, "events": {}},
    )
    assert len(pub["events"]) == 1
    assert not pub["events"][0]["event_start_time"]
    assert all(
        s["source_id"] != "ticketjam_events"
        for s in pub["events"][0]["supporting_sources"]
    )
    assert len(queue["candidates"]) == 2
    assert pub["ticketjam_policy"] == "discovery"


def test_pending_secondary_only_event_is_queued_but_not_published():
    pub, queue = build_discovery_bundle(
        [record("ticketjam_events", "candidate", "18:00")],
        as_of_date=date(2026, 9, 7),
        review_state={"schema_version": 1, "events": {}},
    )
    assert pub["events"] == []
    assert queue["candidates"][0]["status"] == "pending_official"
    assert queue["candidates"][0]["review_due"] is True


def test_later_conflict_holds_only_the_promoted_record_with_that_origin():
    state = {
        "schema_version": 1,
        "events": {
            "origin": {
                "history": [{"status": "conflict", "reason": "Venue conflict"}],
            }
        },
    }
    pub, _ = build_discovery_bundle(
        [
            record(
                "venue_web_discovery", "promoted", "18:00", discovery_event_key="origin"
            ),
            record("official_events", "independent", "18:00"),
        ],
        as_of_date=date(2026, 9, 7),
        review_state=state,
    )
    assert len(pub["events"]) == 1
    assert pub["events"][0]["display_source_id"] == "official_events"
    assert all(
        s["record_id"] != "promoted" for s in pub["events"][0]["supporting_sources"]
    )
    assert pub["summary"]["ticketjam_promoted_held_record_count"] == 1


def test_cli_default_uses_isolated_publication_input(tmp_path, monkeypatch):
    import json
    import scripts.build_lp_events as module

    (tmp_path / "ticketjam_review_state.json").write_text(
        json.dumps({"schema_version": 1, "events": {}})
    )
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        module,
        "load_lp_records",
        lambda **kwargs: [record("ticketjam_events", "lead", "18:00")],
    )
    monkeypatch.setattr(
        "sys.argv", ["build_lp_events", "--output", str(tmp_path / "lp.json")]
    )
    assert module.main() == 0
    assert json.loads((tmp_path / "lp.json").read_text())["events"] == []
    assert (
        len(
            json.loads((tmp_path / "ticketjam_review_queue.json").read_text())[
                "candidates"
            ]
        )
        == 1
    )


def test_default_as_of_date_uses_japan_date_at_utc_day_boundary(monkeypatch):
    from datetime import datetime, timezone
    import scripts.build_lp_events as module

    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)
    assert module.today_jst() == date(2026, 9, 8)


def test_discovery_namespace_without_authoritative_evidence_is_rejected():
    import pytest

    bad = record(
        "venue_web_discovery", "unverified", "18:00", source_class="general_news"
    )
    with pytest.raises(ValueError, match="unverified"):
        build_discovery_bundle(
            [bad],
            as_of_date=date(2026, 9, 8),
            review_state={"schema_version": 1, "events": {}},
        )


def test_unknown_domestic_location_is_held_without_inventing_a_prefecture():
    item = record("kstyle_music", "bad-place", "18:00")
    item["venue_name"] = "1部"
    item["pref_name"] = None
    pub, _ = build_discovery_bundle(
        [item],
        as_of_date=date(2026, 9, 8),
        review_state={"schema_version": 1, "events": {}},
    )
    assert pub["events"] == []
    assert pub["summary"]["location_held_record_count"] == 1
    assert item["pref_name"] is None


def test_only_exact_latest_status_notice_can_pass_candidate_conflict():
    from copy import deepcopy
    from scripts.ticketjam_review_state import apply_reviews, fingerprint
    from scripts.signals.sources.base import compute_signal_uid

    old = record("official_events", "independent", "18:00")
    candidate = dict(old, event_key="origin")
    event = {
        k: old[k]
        for k in (
            "title",
            "artist_name",
            "venue_name",
            "event_start_time",
            "evidence_url",
            "evidence_snippet",
            "url",
        )
    }
    event.update(
        event_id="status-notice",
        event_start_date=old["event_date"],
        source_class="venue_official",
        content_extractor="requests_bs4",
        event_status="cancelled",
    )
    review = dict(
        event_key="origin",
        candidate_fingerprint=fingerprint(candidate),
        status="conflict",
        reason="Verified cancellation",
        checked_at_utc="2026-09-07T00:00:00Z",
        next_check_date="2026-09-08",
        official_values={"event_status": "cancelled"},
        official_suppression=event,
    )
    state = apply_reviews({}, [candidate], [review])
    notice = dict(
        old,
        source_id="venue_web_discovery",
        discovery_event_key="origin",
        record_id=compute_signal_uid(
            "venue_web_discovery", event["url"], extra_key=event["event_id"]
        ),
        event_status="cancelled",
        source_class="venue_official",
        content_extractor="requests_bs4",
    )

    def publish(row, reviews):
        return build_discovery_bundle(
            [old, row], as_of_date=date(2026, 9, 7), review_state=reviews
        )[0]

    assert publish(notice, state)["events"] == []
    for field, value in [
        ("record_id", "other-row"),
        ("event_start_time", None),
        ("event_status", "scheduled"),
        ("evidence_url", "https://other.example/"),
        ("artist_name", "Other"),
        ("venue_name", "Other"),
        ("title", "Other"),
    ]:
        result = publish(dict(notice, **{field: value}), state)
        assert len(result["events"]) == 1
        assert result["summary"]["ticketjam_promoted_held_record_count"] == 1
    stale = deepcopy(state)
    stale["events"]["origin"]["candidate_snapshot"]["title"] = "Changed input"
    assert len(publish(notice, stale)["events"]) == 1
    later = dict(
        review,
        checked_at_utc="2026-09-08T00:00:00Z",
        next_check_date="2026-09-09",
        official_values={"venue_name": "Other"},
        reason="New conflicting evidence",
    )
    del later["official_suppression"]
    updated = apply_reviews(state, [candidate], [later])
    assert len(publish(notice, updated)["events"]) == 1
