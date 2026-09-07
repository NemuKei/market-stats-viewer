from copy import deepcopy

from scripts.ticketjam_discovery import apply_discovery_policy, build_review_queue


def event(key, source="ticketjam_events", **kwargs):
    return {
        "event_key": key,
        "display_source_id": source,
        "event_date": "2026-09-16",
        "event_start_time": "18:00",
        "venue_name": "大阪城ホール",
        "artist_name": "HANA（ハナ）",
        "title": "Born to Bloom",
        "url": "https://ticketjam.jp/example",
        **kwargs,
    }


def payload(*rows):
    return {
        "events": list(rows),
        "as_of_date": "2026-09-07",
        "summary": {"event_count": len(rows), "counts_by_display_source": {}},
    }


def test_existing_official_and_web_discovery_are_match_candidates_only():
    for source in [
        "official_events",
        "venue_web_discovery",
        "starto_concert",
        "kstyle_music",
    ]:
        p = payload(event("lead"), event("official", source, artist_name="HANA"))
        q = build_review_queue(p)
        assert q["candidates"][0]["status"] == "possible_existing_match"
        assert q["candidates"][0]["matching_event_keys"] == ["official"]
        assert q["candidates"][0]["official_confirmed"] is False


def test_different_showtime_or_venue_does_not_match():
    p = payload(
        event("lead"),
        event("other", "official_events", event_start_time="13:00"),
        event("wrong", "official_events", venue_name="東京ドーム"),
    )
    assert build_review_queue(p)["candidates"][0]["status"] == "pending_official"


def test_ancillary_and_expired_do_not_trigger_search():
    p = payload(
        event("parking", title="ガンバ大阪【南駐車場駐車券】"),
        event("past", event_date="2026-09-01"),
    )
    candidates = build_review_queue(p)["candidates"]
    assert {r["status"] for r in candidates} == {"ancillary_ticket", "expired"}
    assert all(not r["search_queries"] for r in candidates)


def test_discovery_excludes_only_ticketjam_display_preserving_supporting_sources():
    official = event(
        "official",
        "official_events",
        supporting_sources=[{"source_id": "ticketjam_events"}],
    )
    p = payload(event("lead"), official)
    before = deepcopy(p)
    result = apply_discovery_policy(p)
    assert p == before
    assert result["events"] == [official]
    assert result["summary"]["event_count"] == 1
    assert result["summary"]["ticketjam_withheld_event_count"] == 1
    assert result["summary"]["counts_by_display_source"] == {"official_events": 1}


def test_queue_is_deterministic_and_preserves_provenance():
    rows = [event("b"), event("a")]
    a = build_review_queue(payload(*rows))
    b = build_review_queue(payload(*reversed(rows)))
    assert a == b
    assert a["candidates"][0]["discovery_url"] == rows[0]["url"]
    assert a["candidates"][0]["search_queries"]


def test_cli_requires_separate_review_output(monkeypatch):
    import pytest
    from scripts.build_lp_events import main

    for args in [
        [
            "build_lp_events",
            "--output",
            "/tmp/same.json",
            "--review-output",
            "/tmp/same.json",
        ],
    ]:
        monkeypatch.setattr("sys.argv", args)
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2


def test_missing_time_and_bracket_variants_are_not_auto_confirmed():
    p = payload(
        event("lead"),
        event("other", "official_events", artist_name="HANA", event_start_time=None),
    )
    q = build_review_queue(p)
    assert q["candidates"][0]["status"] == "possible_existing_match"
    assert q["candidates"][0]["official_confirmed"] is False
    assert len(apply_discovery_policy(p)["events"]) == 1


def test_reviewed_policy_only_withholds_unchanged_reviewed_ticketjam_rows():
    from scripts.ticketjam_discovery import apply_reviewed_policy
    from scripts.ticketjam_review_state import fingerprint

    rows = [
        event("blocked"),
        event("unreviewed"),
        event("changed", event_start_time="19:00"),
        event("official", "official_events"),
    ]
    state = {
        "schema_version": 1,
        "events": {
            key: {
                "candidate_fingerprint": fingerprint(event(key)),
                "history": [{"status": "conflict", "reason": "公式会場と不一致"}],
            }
            for key in ["blocked", "changed", "official"]
        },
    }
    result = apply_reviewed_policy(payload(*rows), state)
    assert {r["event_key"] for r in result["events"]} == {
        "unreviewed",
        "changed",
        "official",
    }
    assert result["summary"]["ticketjam_reviewed_withheld_event_count"] == 1
    assert result["ticketjam_reviewed_withheld"][0]["event_key"] == "blocked"


def test_reviewed_duplicate_requires_unchanged_existing_target_and_preserves_evidence():
    from scripts.ticketjam_discovery import apply_reviewed_policy
    from scripts.ticketjam_review_state import fingerprint

    lead = event(
        "lead",
        supporting_sources=[{"source_id": "ticketjam_events", "record_id": "ticket"}],
    )
    target = event(
        "target", "official_events", artist_name="HANA", supporting_sources=[]
    )
    state = {
        "schema_version": 1,
        "events": {
            "lead": {
                "candidate_fingerprint": fingerprint(lead),
                "history": [
                    {
                        "status": "duplicate",
                        "reason": "公式本文と既存行を照合",
                        "duplicate_of_event_key": "target",
                        "duplicate_target_fingerprint": fingerprint(target),
                    }
                ],
            }
        },
    }
    result = apply_reviewed_policy(payload(lead, target), state)
    assert len(result["events"]) == 1
    assert result["events"][0]["supporting_sources"][0]["record_id"] == "ticket"
    assert len(apply_reviewed_policy(payload(lead), state)["events"]) == 1
    changed = {**target, "title": "Different show"}
    assert len(apply_reviewed_policy(payload(lead, changed), state)["events"]) == 2


def test_reviewed_confirmation_does_not_hide_unpromoted_candidate():
    from scripts.ticketjam_discovery import apply_reviewed_policy
    from scripts.ticketjam_review_state import fingerprint

    lead = event("lead")
    state = {
        "schema_version": 1,
        "events": {
            "lead": {
                "candidate_fingerprint": fingerprint(lead),
                "history": [{"status": "confirmed"}],
            }
        },
    }
    assert apply_reviewed_policy(payload(lead), state)["events"] == [lead]


def test_cli_explicit_reviewed_policy_writes_queue(tmp_path, monkeypatch):
    import json
    import scripts.build_lp_events as module
    from scripts.ticketjam_review_state import fingerprint

    lead = event("lead")
    state = {
        "schema_version": 1,
        "events": {
            "lead": {
                "candidate_fingerprint": fingerprint(lead),
                "history": [
                    {
                        "status": "ancillary",
                        "reason": "駐車券",
                        "checked_at_utc": "2026-09-07T00:00:00Z",
                        "next_check_date": "2026-09-09",
                    }
                ],
            }
        },
    }
    (tmp_path / "ticketjam_review_state.json").write_text(json.dumps(state))
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(module, "build_lp_events", lambda **kwargs: payload(lead))
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_lp_events",
            "--ticketjam-policy",
            "reviewed",
            "--output",
            str(tmp_path / "lp.json"),
        ],
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


def test_cli_does_not_overwrite_review_history(monkeypatch):
    import pytest
    from scripts.build_lp_events import main

    for flag in ["--output", "--review-output"]:
        monkeypatch.setattr(
            "sys.argv",
            [
                "build_lp_events",
                "--review-state",
                "/tmp/history.json",
                flag,
                "/tmp/history.json",
            ],
        )
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
