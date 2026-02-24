"""Update event signals data: fetch news-like signals into data/event_signals.sqlite.

Usage:
    uv run python -m scripts.update_event_signals_data
    uv run python -m scripts.update_event_signals_data --only starto_concert
    uv run python -m scripts.update_event_signals_data --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from .signals.sources.base import SignalSource
from .signals.sources.kstyle import KstyleMusicSource
from .signals.sources.starto import StartoConcertSource
from .signals.types import SignalRecord, SignalSourceRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SIGNALS_DB_PATH = DATA_DIR / "event_signals.sqlite"

USER_AGENT = "market-stats-viewer-signals-bot/1.0 (+https://deltahelmlab.com/)"

logger = logging.getLogger(__name__)


DDL_SIGNAL_SOURCES = """\
CREATE TABLE IF NOT EXISTS signal_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    config_json TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    last_signature TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
"""

DDL_SIGNALS = """\
CREATE TABLE IF NOT EXISTS signals (
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
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES signal_sources(source_id)
);
"""

DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_signals_published_at ON signals(published_at_utc);",
    "CREATE INDEX IF NOT EXISTS idx_signals_source_id ON signals(source_id);",
]

DEFAULT_SOURCES = [
    {
        "source_id": "starto_concert",
        "source_name": "STARTO NEWS (CONCERT)",
        "source_url": "https://starto.jp/s/p/live?ct=concert",
        "source_type": "html_list",
        "config_json": json.dumps({"pages": 1}, ensure_ascii=False),
    },
    {
        "source_id": "kstyle_music",
        "source_name": "Kstyle MUSIC",
        "source_url": "https://kstyle.com/category.ksn?categoryCode=KP",
        "source_type": "html_list",
        "config_json": json.dumps(
            {"pages": 2, "category": "music"}, ensure_ascii=False
        ),
    },
]


class DomainThrottle:
    """Per-domain polite rate limiter."""

    def __init__(self, min_interval: float = 4.0, default_interval: float = 1.5):
        self._last_ts: dict[str, float] = {}
        self._min_interval = min_interval
        self._default_interval = default_interval

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        now = time.monotonic()
        last = self._last_ts.get(domain)
        if last is not None:
            elapsed = now - last
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        elif self._last_ts:
            time.sleep(self._default_interval)
        self._last_ts[domain] = time.monotonic()


class ThrottledSession:
    """Apply DomainThrottle on every GET."""

    def __init__(self, session: requests.Session, throttle: DomainThrottle):
        self._session = session
        self._throttle = throttle

    def get(self, url: str, **kwargs):
        self._throttle.wait(url)
        return self._session.get(url, **kwargs)

    def __getattr__(self, name):
        return getattr(self._session, name)


SOURCE_MAP: dict[str, type[SignalSource]] = {
    "starto_concert": StartoConcertSource,
    "kstyle_music": KstyleMusicSource,
}


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(DDL_SIGNAL_SOURCES)
    conn.execute(DDL_SIGNALS)
    for idx_sql in DDL_INDEXES:
        conn.execute(idx_sql)
    conn.commit()
    return conn


def now_utc_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_default_sources(conn: sqlite3.Connection) -> None:
    now = now_utc_z()
    for s in DEFAULT_SOURCES:
        conn.execute(
            """\
            INSERT INTO signal_sources (
                source_id, source_name, source_url, source_type, config_json,
                is_enabled, last_signature, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, 1, NULL, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_name = excluded.source_name,
                source_url = excluded.source_url,
                source_type = excluded.source_type,
                config_json = COALESCE(signal_sources.config_json, excluded.config_json)
            """,
            (
                s["source_id"],
                s["source_name"],
                s["source_url"],
                s["source_type"],
                s["config_json"],
                now,
                now,
            ),
        )
    conn.commit()


def load_target_sources(
    conn: sqlite3.Connection, only_ids: set[str]
) -> list[SignalSourceRecord]:
    if only_ids:
        placeholders = ",".join("?" for _ in sorted(only_ids))
        cur = conn.execute(
            f"""
            SELECT source_id, source_name, source_url, source_type,
                   config_json, is_enabled, last_signature
            FROM signal_sources
            WHERE source_id IN ({placeholders})
            ORDER BY source_id
            """,
            tuple(sorted(only_ids)),
        )
    else:
        cur = conn.execute(
            """
            SELECT source_id, source_name, source_url, source_type,
                   config_json, is_enabled, last_signature
            FROM signal_sources
            WHERE is_enabled = 1
            ORDER BY source_id
            """
        )
    rows = cur.fetchall()
    return [
        SignalSourceRecord(
            source_id=str(row[0]),
            source_name=str(row[1]),
            source_url=str(row[2]),
            source_type=str(row[3]),
            config_json=row[4],
            is_enabled=bool(row[5]),
            last_signature=row[6],
        )
        for row in rows
    ]


def get_source(source_id: str, session: requests.Session) -> SignalSource | None:
    cls = SOURCE_MAP.get(source_id)
    if cls is None:
        return None
    return cls(session)


def compute_source_signature(signals: list[SignalRecord]) -> str:
    uid_hash = {row.signal_uid: row.content_hash for row in signals}
    payload = json.dumps(sorted(uid_hash.items()), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def update_source_signature(
    conn: sqlite3.Connection, source_id: str, signature: str
) -> None:
    now = now_utc_z()
    conn.execute(
        """
        UPDATE signal_sources
        SET last_signature = ?,
            updated_at_utc = ?
        WHERE source_id = ?
        """,
        (signature, now, source_id),
    )


def upsert_signals(conn: sqlite3.Connection, signals: list[SignalRecord]) -> int:
    now = now_utc_z()
    changed = 0
    for row in signals:
        cur = conn.execute(
            "SELECT content_hash FROM signals WHERE signal_uid = ?",
            (row.signal_uid,),
        )
        existing = cur.fetchone()
        if existing and existing[0] == row.content_hash:
            continue
        conn.execute(
            """
            INSERT INTO signals (
                signal_uid, source_id, published_at_utc, title, url, snippet,
                score, labels_json, content_hash, first_seen_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_uid) DO UPDATE SET
                source_id = excluded.source_id,
                published_at_utc = excluded.published_at_utc,
                title = excluded.title,
                url = excluded.url,
                snippet = excluded.snippet,
                score = excluded.score,
                labels_json = excluded.labels_json,
                content_hash = excluded.content_hash,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                row.signal_uid,
                row.source_id,
                row.published_at_utc,
                row.title,
                row.url,
                row.snippet,
                row.score,
                row.labels_json,
                row.content_hash,
                now,
                now,
            ),
        )
        changed += 1
    return changed


def clear_source_for_rebuild(conn: sqlite3.Connection, source_id: str) -> None:
    now = now_utc_z()
    conn.execute("DELETE FROM signals WHERE source_id = ?", (source_id,))
    conn.execute(
        """
        UPDATE signal_sources
        SET last_signature = NULL,
            updated_at_utc = ?
        WHERE source_id = ?
        """,
        (now, source_id),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Update event signals data")
    parser.add_argument(
        "--only", type=str, default="", help="Comma-separated source_ids to process"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild target source rows (requires --only)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    only_ids = (
        {s.strip() for s in args.only.split(",") if s.strip()} if args.only else set()
    )

    if args.rebuild and not only_ids:
        parser.error("--rebuild requires --only with one or more source_ids")

    raw_session = requests.Session()
    raw_session.headers.update({"User-Agent": USER_AGENT})
    throttle = DomainThrottle(min_interval=4.0, default_interval=1.5)
    session = ThrottledSession(raw_session, throttle)

    conn = init_db(SIGNALS_DB_PATH)
    ensure_default_sources(conn)
    targets = load_target_sources(conn, only_ids)

    if not targets:
        logger.info("No sources to process.")
        conn.close()
        return

    logger.info("Processing %d source(s)...", len(targets))

    success_count = 0
    fail_count = 0
    total_fetched = 0
    total_changed = 0

    for source in targets:
        logger.info("--- %s (%s) ---", source.source_id, source.source_name)
        try:
            plugin = get_source(source.source_id, session)
            if plugin is None:
                logger.warning("No plugin for source_id=%s", source.source_id)
                fail_count += 1
                continue

            signals = plugin.fetch_signals(source)
            total_fetched += len(signals)
            logger.info("  fetched %d signal(s)", len(signals))

            if not signals:
                logger.warning("  fetched 0 signal(s); skip DB update for this source")
                success_count += 1
                continue

            if args.rebuild:
                clear_source_for_rebuild(conn, source.source_id)
                logger.info("  rebuild: cleared existing rows and reset last_signature")

            sig = compute_source_signature(signals)
            if not args.rebuild and source.last_signature == sig:
                logger.info("  no-op: signature unchanged")
                success_count += 1
                continue

            changed = upsert_signals(conn, signals)
            update_source_signature(conn, source.source_id, sig)
            conn.commit()

            total_changed += changed
            logger.info("  upserted %d changed signal(s)", changed)
            success_count += 1

        except Exception:
            logger.exception("  FAILED: %s", source.source_id)
            fail_count += 1
            continue

    conn.close()

    logger.info(
        "Done: %d success, %d failed, %d signals fetched, %d changed",
        success_count,
        fail_count,
        total_fetched,
        total_changed,
    )

    if targets and success_count == 0:
        logger.error("All sources failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
