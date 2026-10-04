import importlib
from datetime import date

import pytest
from unittest.mock import patch

from scripts.update_events_data import init_db, upsert_events, upsert_venue
from test_event_history_retention import event, venue, rows


def make_db(path, records):
    conn = init_db(path)
    upsert_venue(conn, venue(), "test")
    upsert_events(conn, records, {}, {})
    conn.commit()
    conn.close()
    return path


def restore(conn, snapshots, *, apply=True):
    assert importlib.util.find_spec("scripts.restore_event_history") is not None, (
        "Missing conservative history restore capability"
    )
    module = importlib.import_module("scripts.restore_event_history")
    return module.restore_history(
        conn, snapshots, as_of_date=date(2026, 10, 4), apply=apply
    )


def test_addition_preserves_all_existing_columns_and_second_run_is_noop(tmp_path):
    target = make_db(
        tmp_path / "current.sqlite",
        [event("future", "2026-12-01"), event("ongoing", "2026-09-01", "2026-10-05")],
    )
    old = make_db(
        tmp_path / "old.sqlite",
        [event("old", "2026-08-01", title="Past LIVE"), event("future", "2026-11-01")],
    )
    conn = init_db(target)
    before = {r[0]: r for r in rows(conn)}
    result = restore(conn, [old])
    assert result["inserted_count"] == 1
    assert {r[0]: r for r in rows(conn) if r[0] in before} == before
    after = rows(conn)
    assert restore(conn, [old])["inserted_count"] == 0
    assert rows(conn) == after
    conn.close()


def test_dry_run_and_end_date_boundary_do_not_restore_ongoing_or_future(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(
        tmp_path / "history.sqlite",
        [
            event("boundary", "2026-07-01", "2026-07-06"),
            event("expired", "2026-07-05"),
            event("today", "2026-09-01", "2026-10-04"),
            event("future", "2026-12-01"),
        ],
    )
    conn = init_db(target)
    assert restore(conn, [history], apply=False)["candidate_count"] == 1
    assert rows(conn) == []
    assert restore(conn, [history])["inserted_count"] == 1
    assert [r[0] for r in rows(conn)] == ["boundary"]
    conn.close()


def test_current_cancellation_is_never_overwritten(tmp_path):
    target = make_db(
        tmp_path / "current.sqlite", [event("old", "2026-08-01", status="cancelled")]
    )
    history = make_db(tmp_path / "history.sqlite", [event("old", "2026-08-01")])
    conn = init_db(target)
    before = rows(conn)
    assert restore(conn, [history])["inserted_count"] == 0
    assert rows(conn) == before
    conn.close()


def test_newest_snapshot_cancellation_wins_over_old_scheduled(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    newer = make_db(
        tmp_path / "new.sqlite", [event("old", "2026-08-01", status="cancelled")]
    )
    older = make_db(tmp_path / "old.sqlite", [event("old", "2026-08-01")])
    conn = init_db(target)
    assert restore(conn, [newer, older])["inserted_count"] == 1
    assert conn.execute("SELECT status FROM events").fetchone()[0] == "cancelled"
    conn.close()


def test_date_corrected_in_newer_snapshot_does_not_resurrect_old_date(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    newer = make_db(tmp_path / "new.sqlite", [event("stable", "2026-11-01")])
    older = make_db(tmp_path / "old.sqlite", [event("stable", "2026-08-01")])
    conn = init_db(target)
    assert restore(conn, [newer, older])["inserted_count"] == 0
    assert rows(conn) == []
    conn.close()


def test_changed_uid_same_source_or_title_is_held_for_review(tmp_path):
    current = event("new", "2026-11-01", title="Corrected LIVE")
    historic = event("old", "2026-08-01", title="Corrected LIVE")
    current.source_event_key = "https://example.com/detail#d=2026-11-01#t=18:00"
    historic.source_event_key = "https://example.com/detail#d=2026-08-01#t=18:00"
    target = make_db(tmp_path / "current.sqlite", [current])
    history = make_db(tmp_path / "old.sqlite", [historic])
    conn = init_db(target)
    result = restore(conn, [history])
    assert result["inserted_count"] == 0
    assert result["held_count"] == 1
    conn.close()


def test_semantic_duplicate_uid_is_not_inserted(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(
        tmp_path / "old.sqlite", [event("a", "2026-08-01"), event("b", "2026-08-01")]
    )
    conn = init_db(target)
    result = restore(conn, [history])
    assert result["inserted_count"] == 1
    assert result["held_count"] == 1
    conn.close()


def test_missing_venue_is_held_and_unknown_schema_fails_before_write(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(tmp_path / "old.sqlite", [event("a", "2026-08-01")])
    conn = init_db(target)
    conn.execute("DELETE FROM venues")
    conn.commit()
    assert restore(conn, [history])["held_count"] == 1
    conn.close()
    old_conn = init_db(history)
    old_conn.execute("ALTER TABLE events ADD COLUMN unexpected TEXT")
    old_conn.commit()
    old_conn.close()
    conn = init_db(target)
    with pytest.raises(ValueError, match="schema"):
        restore(conn, [history])
    assert rows(conn) == []
    conn.close()


def test_conflicting_status_duplicate_is_entirely_held(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(
        tmp_path / "old.sqlite",
        [event("a", "2026-08-01"), event("b", "2026-08-01", status="cancelled")],
    )
    conn = init_db(target)
    result = restore(conn, [history])
    assert result["inserted_count"] == 0
    assert result["held_count"] == 2
    assert rows(conn) == []
    conn.close()


def test_conflicting_status_different_dates_same_identity_is_held(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(
        tmp_path / "old.sqlite",
        [event("a", "2026-08-01"), event("b", "2026-08-02", status="postponed")],
    )
    conn = init_db(target)
    result = restore(conn, [history])
    assert result["inserted_count"] == 0
    assert result["held_count"] == 2
    conn.close()


def test_restore_is_rolled_back_when_caller_rolls_back(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(tmp_path / "old.sqlite", [event("a", "2026-08-01")])
    conn = init_db(target)
    assert restore(conn, [history])["inserted_count"] == 1
    conn.rollback()
    conn.close()
    conn = init_db(target)
    assert rows(conn) == []
    conn.close()


def test_uncheckpointed_wal_snapshot_is_rejected_before_any_restore(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(tmp_path / "history.sqlite", [event("old", "2026-08-01")])
    history_conn = init_db(history)
    history_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    history_conn.execute("UPDATE events SET status='cancelled'")
    history_conn.commit()
    assert history.with_name(history.name + "-wal").stat().st_size > 0
    conn = init_db(target)
    with pytest.raises(ValueError, match="WAL|wal"):
        restore(conn, [history])
    assert rows(conn) == []
    conn.close()
    history_conn.close()


def test_noncanonical_date_is_held_for_review(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(tmp_path / "history.sqlite", [event("old", "2026-08-01")])
    history_conn = init_db(history)
    history_conn.execute("UPDATE events SET start_date='20260801'")
    history_conn.commit()
    history_conn.close()
    conn = init_db(target)
    result = restore(conn, [history])
    assert result["inserted_count"] == 0
    assert result["held_counts_by_reason"] == {"invalid_date": 1}
    conn.close()


def test_cli_apply_report_failure_rolls_back_and_dry_run_never_writes(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    history = make_db(tmp_path / "history.sqlite", [event("old", "2026-08-01")])
    module = importlib.import_module("scripts.restore_event_history")
    argv = [
        "restore_event_history",
        "--target-db",
        str(target),
        "--snapshot",
        str(history),
        "--as-of-date",
        "2026-10-04",
    ]
    with patch("sys.argv", argv):
        assert module.main() == 0
    conn = init_db(target)
    assert rows(conn) == []
    conn.close()
    with patch("sys.argv", argv + ["--apply", "--report", str(tmp_path)]):
        with pytest.raises(IsADirectoryError):
            module.main()
    conn = init_db(target)
    assert rows(conn) == []
    conn.close()
    with patch(
        "sys.argv", argv + ["--apply", "--report", str(tmp_path / "applied.json")]
    ):
        assert module.main() == 0
    conn = init_db(target)
    assert [r[0] for r in rows(conn)] == ["old"]
    conn.close()


def test_newer_snapshot_changed_uid_and_current_cancelled_identity_are_held(tmp_path):
    target = make_db(tmp_path / "current.sqlite", [])
    newer = make_db(tmp_path / "new.sqlite", [event("new", "2026-11-01")])
    older = make_db(tmp_path / "old.sqlite", [event("old", "2026-08-01")])
    conn = init_db(target)
    result = restore(conn, [newer, older])
    assert result["inserted_count"] == 0
    assert result["held_count"] == 1
    conn.close()
    current = event("cancelled-new", "2026-08-01", status="cancelled")
    conn = init_db(target)
    upsert_events(conn, [current], {}, {})
    conn.commit()
    result = restore(conn, [older])
    assert result["inserted_count"] == 0
    assert result["held_count"] == 1
    conn.close()
