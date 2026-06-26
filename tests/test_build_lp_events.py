import json
import sqlite3
from pathlib import Path

from scripts.build_lp_events import build_lp_events
from scripts.signals.sources.base import canonical_labels_json, compute_content_hash, compute_signal_uid
from scripts.signals.types import SignalRecord


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
    conn.commit()
    conn.close()


def _signal(
    source_id: str,
    title: str,
    event_date: str,
    venue_name: str,
    artist_name: str,
    *,
    source_class: str,
) -> SignalRecord:
    url = f"https://example.com/{source_id}/{event_date}/{artist_name}"
    labels = {
        "event_start_date": event_date,
        "event_end_date": event_date,
        "venue_name": venue_name,
        "raw_venue_name": venue_name,
        "artist_name": artist_name,
        "raw_artist_name": artist_name,
        "event_category": "コンサート",
        "source_class": source_class,
        "evidence_url": url,
        "evidence_snippet": "official evidence",
    }
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
    assert json.dumps(payload, ensure_ascii=False)
