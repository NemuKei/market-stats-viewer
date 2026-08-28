import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from scripts.build_lp_events import build_lp_events
from scripts.signals.sources.base import canonical_labels_json, compute_content_hash, compute_signal_uid
from scripts.signals.types import SignalRecord
from scripts.signals.text_quality import EventTextQualityError


def _create_events_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE venues (
            venue_id TEXT PRIMARY KEY,
            venue_name TEXT NOT NULL,
            pref_name TEXT,
            capacity INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE events (
            event_uid TEXT PRIMARY KEY,
            venue_id TEXT NOT NULL,
            title TEXT,
            start_date TEXT,
            start_time TEXT,
            end_date TEXT,
            end_time TEXT,
            status TEXT,
            url TEXT,
            description TEXT,
            performers TEXT,
            artist_name_resolved TEXT,
            event_category TEXT,
            source_type TEXT,
            source_url TEXT,
            first_seen_at_utc TEXT,
            updated_at_utc TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO venues VALUES (?, ?, ?, ?)",
        ("kyocera_dome_osaka", "京セラドーム大阪", "大阪府", 55000),
    )
    conn.execute(
        """
        INSERT INTO events VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            "official-bruno",
            "kyocera_dome_osaka",
            "Bruno Mars - The Romantic Tour in Japan",
            "2027-01-19",
            "19:00",
            "2027-01-19",
            None,
            "scheduled",
            "https://www.kyoceradome-osaka.jp/schedule/",
            "official venue row",
            "Bruno Mars",
            "Bruno Mars",
            "コンサート",
            "html",
            "https://www.kyoceradome-osaka.jp/schedule/",
            "2026-06-24T00:00:00Z",
            "2026-06-24T00:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO events VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            "official-exile",
            "kyocera_dome_osaka",
            "EXILE 25th ANNIVERSARY BEST LIVE ～LDH PERFECT YEAR 2026～",
            "2026-12-06",
            None,
            "2026-12-06",
            None,
            "scheduled",
            "https://www.kyoceradome-osaka.jp/schedule/",
            "official venue row",
            "EXILE",
            "EXILE",
            "コンサート",
            "html",
            "https://www.kyoceradome-osaka.jp/schedule/",
            "2026-06-24T00:00:00Z",
            "2026-06-24T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()


def _insert_official_event(
    path: Path,
    *,
    event_uid: str,
    title: str,
    event_date: str,
    artist_name: str,
) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        INSERT INTO events VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            event_uid,
            "kyocera_dome_osaka",
            title,
            event_date,
            None,
            event_date,
            None,
            "scheduled",
            f"https://example.com/{event_uid}",
            "official venue row",
            artist_name,
            artist_name,
            "コンサート",
            "html",
            "https://www.kyoceradome-osaka.jp/schedule/",
            "2026-04-01T00:00:00Z",
            "2026-04-01T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()


def _create_signals_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE signal_sources (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE signals (
            signal_uid TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            published_at_utc TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            snippet TEXT,
            score INTEGER NOT NULL DEFAULT 0,
            labels_json TEXT,
            content_hash TEXT NOT NULL,
            first_seen_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
        """
    )
    for source_id, source_name in [
        ("venue_web_discovery", "Venue Web Discovery"),
        ("starto_concert", "STARTO NEWS (CONCERT)"),
        ("kstyle_music", "Kstyle MUSIC"),
        ("ticketjam_events", "Ticketjam Events"),
    ]:
        conn.execute("INSERT INTO signal_sources VALUES (?, ?)", (source_id, source_name))
    for rec in [
        _signal(
            "venue_web_discovery",
            "Bruno Mars - The Romantic Tour in Japan",
            "2027-01-19",
            "京セラドーム大阪",
            "Bruno Mars",
            source_class="promoter_official",
        ),
        _signal(
            "venue_web_discovery",
            "Stray Kids World Tour <RUN IT JAPAN>",
            "2026-09-19",
            "京セラドーム大阪",
            "Stray Kids",
            source_class="artist_official",
        ),
        _signal(
            "kstyle_music",
            "Stray Kids World Tour <RUN IT JAPAN>",
            "2026-09-19",
            "京セラドーム大阪",
            "Stray Kids",
            source_class="general_news",
        ),
        _signal(
            "starto_concert",
            "STARTO legacy category concert",
            "2027-02-01",
            "京セラドーム大阪",
            "STARTO Artist",
            source_class="general_news",
            event_category=None,
            category="concert",
        ),
        _signal(
            "kstyle_music",
            "Kstyle missing category concert",
            "2027-02-02",
            "京セラドーム大阪",
            "Kstyle Artist",
            source_class="general_news",
            event_category=None,
        ),
        _signal(
            "ticketjam_events",
            "Stray Kids World Tour <RUN IT JAPAN>",
            "2026-09-19",
            "京セラドーム大阪",
            "Stray Kids",
            source_class="secondary_market",
        ),
        _signal(
            "ticketjam_events",
            "”EXILE 25th ANNIVERSARY BEST LIVE” ～LDH PERFECT YEAR 2026～",
            "2026-12-06",
            "京セラドーム大阪",
            "EXILE（エグザイル）",
            source_class="secondary_market",
        ),
    ]:
        _insert_signal_with_connection(conn, rec)
    conn.commit()
    conn.close()


def _insert_signal_with_connection(conn: sqlite3.Connection, rec: SignalRecord) -> None:
    conn.execute(
        """
        INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec.signal_uid,
            rec.source_id,
            rec.published_at_utc,
            rec.title,
            rec.url,
            rec.snippet,
            rec.score,
            rec.labels_json,
            rec.content_hash,
            "2026-06-23T00:00:00Z",
            "2026-06-23T00:00:00Z",
        ),
    )


def _insert_signal(path: Path, rec: SignalRecord) -> None:
    conn = sqlite3.connect(str(path))
    _insert_signal_with_connection(conn, rec)
    conn.commit()
    conn.close()


def test_build_rejects_mojibake_before_output_payload(tmp_path: Path) -> None:
    events_db = tmp_path / "events.sqlite"
    signals_db = tmp_path / "signals.sqlite"
    _create_events_db(events_db)
    _create_signals_db(signals_db)
    good = "GRe4N BOYZ イマーシブライブシアター2026"
    bad = good.encode("utf-8").decode("ptcp154")
    conn = sqlite3.connect(str(signals_db))
    conn.execute(
        "UPDATE signals SET title = ? WHERE source_id = 'ticketjam_events'",
        (bad,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(EventTextQualityError, match="title=probable_utf8_mojibake"):
        build_lp_events(
            events_db_path=events_db,
            event_signals_db_path=signals_db,
        )


def _signal(
    source_id: str,
    title: str,
    event_date: str,
    venue_name: str,
    artist_name: str,
    *,
    source_class: str,
    event_category: str | None = "コンサート",
    category: str | None = None,
    event_status: str | None = None,
) -> SignalRecord:
    url = f"https://example.com/{source_id}/{event_date}/{artist_name}"
    labels = {
        "event_start_date": event_date,
        "event_end_date": event_date,
        "venue_name": venue_name,
        "raw_venue_name": venue_name,
        "artist_name": artist_name,
        "raw_artist_name": artist_name,
        "source_class": source_class,
        "evidence_url": url,
        "evidence_snippet": "official evidence",
    }
    if event_category is not None:
        labels["event_category"] = event_category
    if category is not None:
        labels["category"] = category
    if event_status is not None:
        labels["event_status"] = event_status
    rec = SignalRecord(
        signal_uid=compute_signal_uid(source_id, url),
        source_id=source_id,
        published_at_utc="2026-06-23T00:00:00Z",
        title=title,
        url=url,
        snippet="official evidence",
        score=95,
        labels_json=canonical_labels_json(labels),
    )
    rec.content_hash = compute_content_hash(rec)
    return rec


def test_lp_events_prefers_official_then_venue_web_discovery(tmp_path: Path):
    events_db = tmp_path / "events.sqlite"
    signals_db = tmp_path / "event_signals.sqlite"
    _create_events_db(events_db)
    _create_signals_db(signals_db)

    payload = build_lp_events(
        events_db_path=events_db,
        event_signals_db_path=signals_db,
        include_past=True,
    )

    by_artist = {row["artist_name"]: row for row in payload["events"]}
    assert by_artist["Bruno Mars"]["display_source_id"] == "official_events"
    assert by_artist["EXILE"]["display_source_id"] == "official_events"
    assert [
        item["source_id"] for item in by_artist["EXILE"]["supporting_sources"]
    ] == ["official_events", "ticketjam_events"]
    assert by_artist["Stray Kids"]["display_source_id"] == "venue_web_discovery"
    assert [
        item["source_id"] for item in by_artist["Stray Kids"]["supporting_sources"]
    ] == ["venue_web_discovery", "kstyle_music", "ticketjam_events"]
    assert by_artist["STARTO Artist"]["display_source_id"] == "starto_concert"
    assert by_artist["STARTO Artist"]["event_category"] == "コンサート"
    assert by_artist["Kstyle Artist"]["display_source_id"] == "kstyle_music"
    assert by_artist["Kstyle Artist"]["event_category"] == "コンサート"
    assert payload["summary"]["suppressed_event_count"] == 0
    assert json.dumps(payload, ensure_ascii=False)


def test_authoritative_postponement_suppresses_lower_priority_sources(tmp_path: Path) -> None:
    events_db = tmp_path / "events.sqlite"
    signals_db = tmp_path / "event_signals.sqlite"
    _create_events_db(events_db)
    _create_signals_db(signals_db)

    for rec in [
        _signal(
            "venue_web_discovery",
            "Post Malone official postponement",
            "2026-10-06",
            "京セラドーム大阪",
            "Post Malone",
            source_class="promoter_official",
            event_status="postponed",
        ),
        _signal(
            "ticketjam_events",
            "Post Malone Presents The BIG ASS Stadium World Tour",
            "2026-10-06",
            "京セラドーム大阪",
            "Post Malone",
            source_class="secondary_market",
        ),
    ]:
        _insert_signal(signals_db, rec)

    payload = build_lp_events(
        events_db_path=events_db,
        event_signals_db_path=signals_db,
        include_past=True,
    )

    assert "Post Malone" not in {row["artist_name"] for row in payload["events"]}
    assert payload["summary"]["suppressed_event_count"] == 1

    conn = sqlite3.connect(str(signals_db))
    source_ids = {
        row[0]
        for row in conn.execute(
            "SELECT source_id FROM signals WHERE title LIKE 'Post Malone%'"
        ).fetchall()
    }
    conn.close()
    assert source_ids == {"venue_web_discovery", "ticketjam_events"}


def test_secondary_market_status_does_not_suppress_event(tmp_path: Path) -> None:
    events_db = tmp_path / "events.sqlite"
    signals_db = tmp_path / "event_signals.sqlite"
    _create_events_db(events_db)
    _create_signals_db(signals_db)
    _insert_signal(
        signals_db,
        _signal(
            "ticketjam_events",
            "Secondary-only status must not suppress",
            "2026-10-07",
            "京セラドーム大阪",
            "Secondary Status Artist",
            source_class="secondary_market",
            event_status="cancelled",
        ),
    )

    payload = build_lp_events(
        events_db_path=events_db,
        event_signals_db_path=signals_db,
        include_past=True,
    )

    by_artist = {row["artist_name"]: row for row in payload["events"]}
    assert by_artist["Secondary Status Artist"]["display_source_id"] == "ticketjam_events"
    assert payload["summary"]["suppressed_event_count"] == 0


def test_lp_events_default_history_window_is_bounded_to_90_days(tmp_path: Path) -> None:
    events_db = tmp_path / "events.sqlite"
    signals_db = tmp_path / "event_signals.sqlite"
    _create_events_db(events_db)
    _create_signals_db(signals_db)
    _insert_official_event(
        events_db,
        event_uid="history-boundary",
        title="History Boundary Event",
        event_date="2026-05-02",
        artist_name="Boundary Artist",
    )
    _insert_official_event(
        events_db,
        event_uid="history-too-old",
        title="History Too Old Event",
        event_date="2026-05-01",
        artist_name="Older Artist",
    )

    payload = build_lp_events(
        events_db_path=events_db,
        event_signals_db_path=signals_db,
        as_of_date=date(2026, 7, 31),
    )
    artists = {row["artist_name"] for row in payload["events"]}

    assert "Boundary Artist" in artists
    assert "Older Artist" not in artists
    assert payload["as_of_date"] == "2026-07-31"
    assert payload["include_past"] is True
    assert payload["history_window_days"] == 90
    assert payload["history_start_date"] == "2026-05-02"

    all_history = build_lp_events(
        events_db_path=events_db,
        event_signals_db_path=signals_db,
        include_past=True,
        as_of_date=date(2026, 7, 31),
    )
    assert "Older Artist" in {row["artist_name"] for row in all_history["events"]}
    assert all_history["history_window_days"] is None
    assert all_history["history_start_date"] is None


def test_lp_events_rejects_negative_history_window(tmp_path: Path) -> None:
    events_db = tmp_path / "events.sqlite"
    signals_db = tmp_path / "event_signals.sqlite"
    _create_events_db(events_db)
    _create_signals_db(signals_db)

    with pytest.raises(ValueError, match="past_days must be zero or greater"):
        build_lp_events(
            events_db_path=events_db,
            event_signals_db_path=signals_db,
            past_days=-1,
        )
