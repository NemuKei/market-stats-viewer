from datetime import date

import pytest
import requests

from scripts.audit_event_calendar_coverage import audit_runtime, event_days
from scripts.update_events_data import ThrottledSession


def inventory(enabled=True):
    return dict(
        scope="current_registry_only_not_national_census",
        summary={},
        identity_conflicts=[],
        orphan_web_watch_ids=[],
        orphan_ticketjam_ids=[],
        venues=[
            dict(
                venue_id="arena",
                venue_name="テスト会場",
                official_enabled=enabled,
                web_watch_configured=False,
            )
        ],
    )


def run(*, raw=None, public=None, pending=None, expected=None, enabled=True):
    return audit_runtime(
        inventory(enabled),
        raw or [],
        [],
        {"events": public or []},
        pending or {"held_records": []},
        {"events": []},
        start=date(2026, 11, 7),
        end=date(2026, 11, 9),
        expectations=expected,
    )


def show(uid, time="18:00", subject="公演"):
    return dict(
        event_date="2026-11-07",
        event_end_date="2026-11-08",
        event_key=uid,
        venue_name="テスト会場",
        artist_name=subject,
        event_start_time=time,
    )


def test_empty_configured_route_is_not_healthy_and_disabled_venue_is_visible():
    report = run(enabled=False)
    venue = report["venues"][0]
    assert "no_active_official_or_web_route" in venue["flags"]
    assert "public_window_empty_review_required" in venue["flags"]
    assert venue["runtime_fetch_status"] == "not_measured"
    assert report["coverage_verified"] is False


def test_collected_sport_and_id_hold_are_reported_without_claiming_missing_count():
    raw = dict(
        venue_id="arena",
        event_date="2026-11-08",
        source_id="official_events",
        performer=None,
    )
    pending = {
        "held_records": [dict(identity=show("raw"), reason="unregistered_candidate")]
    }
    item = run(raw=[raw], pending=pending)["venues"][0]
    assert item["window_raw_rows"] == item["registered_ids"] + 1
    assert item["held_by_reason"] == {"unregistered_candidate": 1}
    assert "collected_but_not_public" in item["flags"]
    assert item["official_unresolved_performer_rows"] == 1


def test_finite_sourced_closure_is_separate_from_unexplained_zero():
    notes = {
        "arena": dict(
            status="temporarily_closed",
            observed_on="2026-11-07",
            review_after="2026-12-31",
            evidence_url="https://venue.example/renovation",
        )
    }
    assert "expected_zero_until_review" in run(expected=notes)["venues"][0]["flags"]
    raw = dict(
        venue_id="arena",
        event_date="2026-11-08",
        source_id="official_events",
        performer=None,
    )
    assert (
        "raw_programmes_during_reported_closure_require_facility_review"
        in run(raw=[raw], expected=notes)["venues"][0]["flags"]
    )
    notes["arena"]["review_after"] = "2026-11-06"
    assert (
        "public_window_empty_review_required"
        in run(expected=notes)["venues"][0]["flags"]
    )


def test_multiple_show_times_and_shared_day_are_review_signals_never_auto_merge():
    report = run(public=[show("a", "13:00"), show("b", "18:00")])
    assert report["venues"][0]["public_events"] == 2
    assert report["venues"][0]["public_days"] == 2
    assert report["venues"][0]["longest_public_blank_days"] == 1
    assert len(report["same_day_candidates"]) == 2  # includes the second day of a range
    assert all(
        r["classification"] == "distinct_start_times_possible_multiple_performances"
        for r in report["same_day_candidates"]
    )
    report = run(public=[show("a"), show("b", subject="別の公演")])
    assert (
        report["same_day_candidates"][0]["classification"]
        == "shared_day_or_facility_review_required"
    )


def test_limited_calendar_horizon_does_not_claim_the_source_has_no_later_events():
    notes = {
        "arena": dict(
            official_horizon_months=1, evidence_url="https://venue.example/calendar"
        )
    }
    assert (
        "official_calendar_has_limited_horizon_use_supplementary_sources"
        in run(expected=notes)["venues"][0]["flags"]
    )


def test_invalid_dates_fail_instead_of_silent_empty_coverage():
    with pytest.raises(ValueError):
        event_days(
            dict(event_date="2026-11-08", event_end_date="2026-11-07"),
            date(2026, 11, 7),
            date(2026, 11, 9),
        )


class NoThrottle:
    def wait(self, url):
        pass


class RawSession:
    def __init__(self):
        self.code = 200

    def get(self, url, **kwargs):
        if self.code is None:
            raise requests.ConnectionError(
                "private request detail must not be reported"
            )
        return type("Response", (), {"status_code": self.code})()


def test_fetch_report_distinguishes_partial_empty_and_unimplemented_source():
    raw = RawSession()
    session = ThrottledSession(raw, NoThrottle())
    assert session.fetch_status(failed=False, raw_count=0)["status"] == "not_requested"
    session.get("https://venue.example")
    assert (
        session.fetch_status(failed=False, raw_count=0)["status"] == "empty_unverified"
    )
    assert (
        session.fetch_status(failed=False, raw_count=2)["status"]
        == "fetched_completeness_unverified"
    )
    raw.code = 503
    session.get("https://venue.example")
    assert (
        session.fetch_status(failed=False, raw_count=2)["status"]
        == "partial_or_failed_collection"
    )
    raw.code = None
    with pytest.raises(requests.ConnectionError):
        session.get("https://venue.example")
    report = session.fetch_status(failed=False, raw_count=2)
    assert report["request_count"] == 3
    assert report["http_error_count"] == report["transport_error_count"] == 1
    assert "private" not in str(report)
    session.begin_venue()
    assert session.fetch_status(failed=True, raw_count=0)["status"] == "failed"
    assert session.request_count == 0
