from datetime import date
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import pytest

from scripts.events.sources.base import compute_data_hash
from scripts.events.types import EventRecord, VenueRecord
from scripts.update_events_data import (
    filter_events_by_date,
    init_db,
    main,
    upsert_events,
    upsert_venue,
)


def event(uid, start, end=None, *, status="scheduled", title="Example LIVE"):
    row = EventRecord(
        uid,
        "venue",
        title,
        start,
        "18:00",
        end,
        None,
        False,
        status,
        "https://example.com/event/" + uid,
        None,
        "Artist",
        1000,
        "html",
        "https://example.com/schedule",
        uid,
    )
    row.data_hash = compute_data_hash(row)
    return row


def venue():
    return VenueRecord(
        "venue",
        "Venue",
        "27",
        "大阪府",
        1000,
        "https://example.com",
        "html",
        "https://example.com/schedule",
        None,
        True,
    )


def rows(conn):
    return conn.execute("SELECT * FROM events ORDER BY event_uid").fetchall()


def test_fetch_window_includes_90_day_end_date_boundary_and_ongoing_event():
    source = [
        event("before", "2026-07-05"),
        event("boundary", "2026-07-06"),
        event("span", "2026-07-01", "2026-07-06"),
        event("ongoing", "2026-06-01", "2026-10-04"),
        event("future_boundary", "2027-10-04"),
        event("too_far", "2027-10-05"),
    ]
    with patch("scripts.update_events_data.date", wraps=date) as clock:
        clock.today.return_value = date(2026, 10, 4)
        assert [e.event_uid for e in filter_events_by_date(source)] == [
            "boundary",
            "span",
            "ongoing",
            "future_boundary",
        ]


def run_fetch(path, incoming):
    with (
        patch("scripts.update_events_data.EVENTS_DB_PATH", path),
        patch("scripts.update_events_data.load_registry", return_value=[venue()]),
        patch(
            "scripts.update_events_data.load_artist_lookup_maps", return_value=({}, {})
        ),
        patch(
            "scripts.update_events_data.get_source",
            return_value=SimpleNamespace(fetch_events=lambda _: incoming),
        ),
        patch("scripts.update_events_data.date", wraps=date) as clock,
        patch("sys.argv", ["update_events_data", "--skip-artist-inference"]),
    ):
        clock.today.return_value = date(2026, 10, 4)
        main()


def seeded(path):
    conn = init_db(path)
    upsert_venue(conn, venue(), "old-signature")
    upsert_events(
        conn,
        [
            event("july", "2026-07-20"),
            event("august", "2026-08-20"),
            event("september", "2026-09-20"),
            event("ongoing", "2026-10-01", "2026-10-05"),
            event("future", "2026-11-20"),
        ],
        {},
        {},
    )
    conn.commit()
    return conn


def test_partial_schedule_never_deletes_absent_history_or_future(tmp_path):
    path = tmp_path / "events.sqlite"
    conn = seeded(path)
    before = rows(conn)
    conn.close()
    run_fetch(path, [event("future", "2026-11-20")])
    conn = init_db(path)
    assert rows(conn) == before
    conn.close()


def test_empty_fetch_preserves_every_existing_event_column(tmp_path):
    path = tmp_path / "events.sqlite"
    conn = seeded(path)
    before = rows(conn)
    conn.close()
    run_fetch(path, [])
    conn = init_db(path)
    assert rows(conn) == before
    conn.close()


def test_explicit_cancellation_and_date_correction_still_upsert(tmp_path):
    path = tmp_path / "events.sqlite"
    conn = seeded(path)
    before = {r[0]: r for r in rows(conn)}
    conn.close()
    corrected = event("future", "2026-12-01", status="cancelled")
    run_fetch(path, [corrected])
    conn = init_db(path)
    assert conn.execute(
        "SELECT start_date,status FROM events WHERE event_uid='future'"
    ).fetchone() == ("2026-12-01", "cancelled")
    assert {r[0]: r for r in rows(conn) if r[0] != "future"} == {
        k: v for k, v in before.items() if k != "future"
    }
    before_second = rows(conn)
    conn.close()
    run_fetch(path, [corrected])
    conn = init_db(path)
    assert rows(conn) == before_second
    conn.close()


def test_invalid_end_date_is_reported_and_existing_future_is_preserved(tmp_path):
    path = tmp_path / "events.sqlite"
    conn = seeded(path)
    before = rows(conn)
    conn.close()
    invalid = event("future", "2026-12-30", "2026-01-02")
    with pytest.raises(ValueError, match="invalid.*date|negative"):
        filter_events_by_date([invalid])
    with pytest.raises(SystemExit):
        run_fetch(path, [invalid])
    conn = init_db(path)
    assert rows(conn) == before
    conn.close()


def test_failed_venue_upsert_cannot_leak_partial_event_into_next_commit(tmp_path):
    path = tmp_path / "events.sqlite"
    conn = seeded(path)
    before = {r[0]: r for r in rows(conn)}
    conn.close()
    second = replace(venue(), venue_id="second")
    second_event = replace(event("second-new", "2026-12-01"), venue_id="second")
    second_event.data_hash = compute_data_hash(second_event)
    original_upsert = upsert_venue

    def fail_first(conn, target, signature):
        if target.venue_id == "venue":
            raise RuntimeError("synthetic first venue write failure")
        return original_upsert(conn, target, signature)

    def fetched(target):
        return (
            [event("future", "2026-12-20")]
            if target.venue_id == "venue"
            else [second_event]
        )

    with (
        patch("scripts.update_events_data.EVENTS_DB_PATH", path),
        patch(
            "scripts.update_events_data.load_registry", return_value=[venue(), second]
        ),
        patch(
            "scripts.update_events_data.load_artist_lookup_maps", return_value=({}, {})
        ),
        patch(
            "scripts.update_events_data.get_source",
            return_value=SimpleNamespace(fetch_events=fetched),
        ),
        patch("scripts.update_events_data.upsert_venue", side_effect=fail_first),
        patch("scripts.update_events_data.date", wraps=date) as clock,
        patch("sys.argv", ["update_events_data", "--skip-artist-inference"]),
    ):
        clock.today.return_value = date(2026, 10, 4)
        main()
    conn = init_db(path)
    after = {r[0]: r for r in rows(conn)}
    assert {uid: after[uid] for uid in before} == before
    assert "second-new" in after
    conn.close()
