"""Official programmes must reach review even without a performer dictionary match."""

import sqlite3

from scripts.build_lp_events import (
    consolidate_events,
    defer_programme_subject_overlaps,
    load_official_events,
)


def official_records(tmp_path, programmes):
    path = tmp_path / "events.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE venues (venue_id TEXT, venue_name TEXT, pref_name TEXT, capacity INTEGER)"
    )
    conn.execute("INSERT INTO venues VALUES ('main', 'テスト会場', '東京都', 10000)")
    conn.execute("""CREATE TABLE events (event_uid TEXT, venue_id TEXT, title TEXT,
        start_date TEXT, start_time TEXT, end_date TEXT, end_time TEXT, status TEXT,
        url TEXT, description TEXT, performers TEXT, artist_name_resolved TEXT,
        event_category TEXT, source_type TEXT, source_url TEXT,
        first_seen_at_utc TEXT, updated_at_utc TEXT)""")
    for uid, title, time, performer in programmes:
        conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                "main",
                title,
                "2026-11-21",
                time,
                None,
                None,
                "scheduled",
                "https://venue.example/programme/" + uid,
                "",
                performer,
                performer,
                "その他",
                "html",
                "https://venue.example/schedule/",
                "2026-11-07T00:00:00Z",
                "2026-11-07T00:00:00Z",
            ),
        )
    conn.commit()
    conn.close()
    return load_official_events(
        path,
        history_start_date="2026-08-09",
        artist_keep_map={},
        artist_compact_map={},
        venue_keep_map={},
        venue_compact_map={},
    )


def test_sport_without_artist_reaches_candidate_review_using_exact_programme_label(
    tmp_path,
):
    records = official_records(
        tmp_path, [("game", "ホームクラブ 対 アウェイクラブ", "15:00", None)]
    )
    assert len(records) == 1
    assert (
        records[0]["title"]
        == records[0]["artist_name"]
        == "ホームクラブ 対 アウェイクラブ"
    )
    assert records[0]["raw_artist_name"] == ""  # Do not invent a source performer.
    assert records[0]["source_id"] == "official_events"


def test_unresolved_programmes_and_two_performances_are_not_collapsed(tmp_path):
    records = official_records(
        tmp_path,
        [
            ("game-a", "大会A", "13:00", None),
            ("game-b", "大会B", "13:00", None),
            ("matinee", "公演C", "13:00", None),
            ("evening", "公演C", "18:00", None),
        ],
    )
    rows, _ = consolidate_events(records)
    assert len(rows) == 4
    assert len({r["event_key"] for r in rows}) == 4


def test_resolved_performer_and_existing_group_key_remain_unchanged(tmp_path):
    records = official_records(
        tmp_path, [("concert", "歌手のコンサート", "18:00", "既知の歌手")]
    )
    assert records[0]["artist_name"] == records[0]["raw_artist_name"] == "既知の歌手"


def test_fallback_cannot_replace_resolved_source_without_review(tmp_path):
    records = official_records(
        tmp_path,
        [
            ("unknown", "同じ公演", "18:00", None),
            ("resolved", "同じ公演", "18:00", "既知の歌手"),
        ],
    )
    preview = []
    retained = defer_programme_subject_overlaps(records, preview)
    assert [r["record_id"] for r in retained] == ["resolved"]
    assert preview[0]["record"]["record_id"] == "unknown"
    assert preview[0]["reason"] == "programme_subject_matches_resolved_event"


def test_different_time_show_is_not_deferred_as_same_programme(tmp_path):
    records = official_records(
        tmp_path,
        [
            ("matinee", "同じ公演", "13:00", None),
            ("evening", "同じ公演", "18:00", "既知の歌手"),
        ],
    )
    assert len(defer_programme_subject_overlaps(records)) == 2


def test_new_time_for_existing_subject_is_reviewed_without_splitting_existing_key(
    tmp_path,
):
    records = official_records(
        tmp_path,
        [
            ("unresolved", "歌手A", "18:45", None),
            ("resolved", "歌手Aのツアー", "19:00", "歌手A"),
        ],
    )
    private = []
    kept = defer_programme_subject_overlaps(records, private)
    assert [r["record_id"] for r in kept] == ["resolved"]
    assert private[0]["reason"] == "programme_subject_time_conflict"
    assert private[0]["record"]["event_start_time"] == "18:45"
