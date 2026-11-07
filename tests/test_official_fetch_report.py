"""Exercise the real per-venue update loop with a failed route and report failure."""

from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import sys

import pytest
import requests

from scripts import update_events_data as update
from scripts.events.types import EventRecord, VenueRecord
from scripts.events.sources.base import compute_data_hash


@pytest.mark.parametrize("report_write_fails", [False, True])
def test_update_keeps_valid_fixture_and_per_venue_failures_without_report_side_effects(
    tmp_path, monkeypatch, caplog, report_write_fails
):
    database, report = tmp_path / "events.sqlite", tmp_path / "fetch-report.json"
    venues = [
        VenueRecord(
            key,
            key,
            "13",
            "東京都",
            10000,
            f"https://venue.example/{key}",
            "fixture",
            f"https://venue.example/{key}",
            None,
            True,
        )
        for key in ["working", "failed"]
    ]

    class RawSession:
        headers = {}

        def get(self, url, **kwargs):
            return type(
                "Response", (), {"status_code": 404 if url.endswith("/failed") else 200}
            )()

    class Throttle:
        def wait(self, url):
            pass

    class Source:
        def __init__(self, session):
            self.session = session

        def fetch_events(self, venue):
            response = self.session.get(venue.source_url)
            if response.status_code == 404:
                raise requests.HTTPError("fixture route failed")
            row = EventRecord(
                "fixture:one",
                venue.venue_id,
                "大会",
                (date.today() + timedelta(days=1)).isoformat(),
                "15:00",
                None,
                None,
                False,
                "scheduled",
                venue.source_url,
                None,
                None,
                None,
                "fixture",
                venue.source_url,
                "one",
            )
            row.data_hash = compute_data_hash(row)
            return [row]

    monkeypatch.setattr(update, "EVENTS_DB_PATH", database)
    monkeypatch.setattr(update, "load_registry", lambda: venues)
    monkeypatch.setattr(update, "load_artist_lookup_maps", lambda: ({}, {}))
    monkeypatch.setattr(update.requests, "Session", RawSession)
    monkeypatch.setattr(update, "DomainThrottle", lambda **kwargs: Throttle())
    monkeypatch.setattr(
        update, "get_source", lambda source_type, session: Source(session)
    )
    monkeypatch.setattr(
        sys, "argv", ["update", "--skip-artist-inference", "--run-report", str(report)]
    )
    if report_write_fails:
        original = Path.write_text

        def fail_report(path, *args, **kwargs):
            if path == report:
                raise PermissionError("fixture report is unwritable")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_report)
    update.main()
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT event_uid FROM events").fetchall() == [
            ("fixture:one",)
        ]
    if report_write_fails:
        assert not report.exists()
        assert "fetch coverage remains unmeasured" in caplog.text
    else:
        result = json.loads(report.read_text())
        assert [r["status"] for r in result["venues"]] == [
            "fetched_completeness_unverified",
            "failed",
        ]
        assert [r["request_count"] for r in result["venues"]] == [1, 1]
        assert [r["http_error_count"] for r in result["venues"]] == [0, 1]
        assert "https://" not in report.read_text() and "大会" not in report.read_text()
