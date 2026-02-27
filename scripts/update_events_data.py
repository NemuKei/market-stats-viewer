"""Update events data: fetch event schedules from venue sources → data/events.sqlite.

Usage:
    uv run python -m scripts.update_events_data
    uv run python -m scripts.update_events_data --limit 3
    uv run python -m scripts.update_events_data --only yokohama_arena,zepp_sapporo
    uv run python -m scripts.update_events_data --verbose
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from .events.registry import load_registry
from .events.types import EventRecord, VenueRecord
from .events.sources.base import EventSource
from .events.sources.html import HtmlSource
from .events.sources.ics import IcsSource
from .events.sources.rss import RssSource
from .events.sources.jsonld import JsonLdSource
from .signals.entity_aliases import load_artist_lookup_maps, normalize_with_lookup

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
EVENTS_DB_PATH = DATA_DIR / "events.sqlite"

USER_AGENT = "market-stats-viewer-events-bot/1.0 (+https://deltahelmlab.com/)"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLite DDL
# ---------------------------------------------------------------------------
DDL_VENUES = """\
CREATE TABLE IF NOT EXISTS venues (
    venue_id TEXT PRIMARY KEY,
    venue_name TEXT NOT NULL,
    pref_code TEXT NOT NULL,
    pref_name TEXT NOT NULL,
    capacity INTEGER,
    official_url TEXT,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    config_json TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    last_signature TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
"""

DDL_EVENTS = """\
CREATE TABLE IF NOT EXISTS events (
    event_uid TEXT PRIMARY KEY,
    venue_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    start_time TEXT,
    end_date TEXT,
    end_time TEXT,
    all_day INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'scheduled',
    url TEXT,
    description TEXT,
    performers TEXT,
    artist_name_resolved TEXT,
    artist_confidence TEXT NOT NULL DEFAULT 'low',
    capacity INTEGER,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_event_key TEXT,
    data_hash TEXT NOT NULL,
    first_seen_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
"""

DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_events_venue_id ON events(venue_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date);",
    "CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);",
]


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create database and tables if not exists."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(DDL_VENUES)
    conn.execute(DDL_EVENTS)
    ensure_events_artist_columns(conn)
    for idx_sql in DDL_INDEXES:
        conn.execute(idx_sql)
    conn.commit()
    return conn


def ensure_events_artist_columns(conn: sqlite3.Connection) -> None:
    cols = {
        str(row[1]).strip()
        for row in conn.execute("PRAGMA table_info(events)").fetchall()
        if len(row) >= 2
    }
    if "artist_name_resolved" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN artist_name_resolved TEXT")
    if "artist_confidence" not in cols:
        conn.execute(
            "ALTER TABLE events ADD COLUMN artist_confidence TEXT NOT NULL DEFAULT 'low'"
        )


# ---------------------------------------------------------------------------
# Source plugin dispatch
# ---------------------------------------------------------------------------
SOURCE_MAP: dict[str, type[EventSource]] = {
    "html": HtmlSource,
    "jsonld": JsonLdSource,
    "ics": IcsSource,
    "rss": RssSource,
}


def get_source(source_type: str, session: requests.Session) -> EventSource | None:
    cls = SOURCE_MAP.get(source_type)
    if cls is None:
        return None
    return cls(session)


# ---------------------------------------------------------------------------
# Signature for no-op detection
# ---------------------------------------------------------------------------
def compute_venue_signature(events: list[EventRecord]) -> str:
    """Compute a SHA-256 signature from unique event_uid → data_hash pairs.

    Using a uid-keyed dict makes the signature immune to duplicate records
    whose count may fluctuate between fetches (e.g. Kyocera Dome month
    boundary overlap).  The signature still changes when the actual event
    set changes (uid added/removed or data_hash updated).
    """
    uid_hash: dict[str, str] = {}
    for e in events:
        uid_hash[e.event_uid] = e.data_hash
    payload = json.dumps(sorted(uid_hash.items()), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Date window for filtering fetched events
DATE_WINDOW_PAST_DAYS = 30
DATE_WINDOW_FUTURE_DAYS = 365


def filter_events_by_date(events: list[EventRecord]) -> list[EventRecord]:
    """Filter events to date window: today-30 to today+365."""
    today = date.today()
    earliest = (today - timedelta(days=DATE_WINDOW_PAST_DAYS)).isoformat()
    latest = (today + timedelta(days=DATE_WINDOW_FUTURE_DAYS)).isoformat()
    return [e for e in events if earliest <= e.start_date <= latest]


class DomainThrottle:
    """Per-domain rate limiter: minimum interval between requests to same netloc."""

    def __init__(self, min_interval: float = 3.0, default_interval: float = 1.0):
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
        else:
            # Different domain: short pause
            if self._last_ts:
                time.sleep(self._default_interval)
        self._last_ts[domain] = time.monotonic()


class ThrottledSession:
    """Wraps requests.Session to apply DomainThrottle on every .get() call."""

    def __init__(self, session: requests.Session, throttle: DomainThrottle):
        self._session = session
        self._throttle = throttle

    def get(self, url: str, **kwargs):
        self._throttle.wait(url)
        return self._session.get(url, **kwargs)

    def __getattr__(self, name):
        return getattr(self._session, name)


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------
def upsert_venue(conn: sqlite3.Connection, venue: VenueRecord, signature: str) -> None:
    """Insert or update venue record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """\
        INSERT INTO venues (
            venue_id, venue_name, pref_code, pref_name, capacity,
            official_url, source_type, source_url, config_json,
            is_enabled, last_signature, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(venue_id) DO UPDATE SET
            venue_name = excluded.venue_name,
            pref_code = excluded.pref_code,
            pref_name = excluded.pref_name,
            capacity = excluded.capacity,
            official_url = excluded.official_url,
            source_type = excluded.source_type,
            source_url = excluded.source_url,
            config_json = excluded.config_json,
            is_enabled = excluded.is_enabled,
            last_signature = excluded.last_signature,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            venue.venue_id, venue.venue_name, venue.pref_code, venue.pref_name,
            venue.capacity, venue.official_url, venue.source_type, venue.source_url,
            venue.config_json, 1 if venue.is_enabled else 0,
            signature, now, now,
        ),
    )


def upsert_events(
    conn: sqlite3.Connection,
    events: list[EventRecord],
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
) -> int:
    """Upsert events. Returns count of actually changed rows."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = 0
    for e in events:
        # Check existing hash
        cur = conn.execute(
            "SELECT data_hash FROM events WHERE event_uid = ?", (e.event_uid,)
        )
        row = cur.fetchone()
        if row and row[0] == e.data_hash:
            continue  # no change
        conn.execute(
            """\
            INSERT INTO events (
                event_uid, venue_id, title, start_date, start_time,
                end_date, end_time, all_day, status, url,
                description, performers, artist_name_resolved, artist_confidence,
                capacity, source_type, source_url, source_event_key, data_hash,
                first_seen_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_uid) DO UPDATE SET
                venue_id = excluded.venue_id,
                title = excluded.title,
                start_date = excluded.start_date,
                start_time = excluded.start_time,
                end_date = excluded.end_date,
                end_time = excluded.end_time,
                all_day = excluded.all_day,
                status = excluded.status,
                url = excluded.url,
                description = excluded.description,
                performers = excluded.performers,
                artist_name_resolved = excluded.artist_name_resolved,
                artist_confidence = excluded.artist_confidence,
                capacity = excluded.capacity,
                source_type = excluded.source_type,
                source_url = excluded.source_url,
                source_event_key = excluded.source_event_key,
                data_hash = excluded.data_hash,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                e.event_uid, e.venue_id, e.title, e.start_date, e.start_time,
                e.end_date, e.end_time, 1 if e.all_day else 0, e.status, e.url,
                e.description,
                e.performers,
                *resolve_source_artist(
                    e.performers, artist_keep_map, artist_compact_map
                ),
                e.capacity,
                e.source_type,
                e.source_url,
                e.source_event_key,
                e.data_hash,
                now,
                now,
            ),
        )
        changed += 1
    return changed


def resolve_source_artist(
    performers: object, artist_keep_map: dict[str, str], artist_compact_map: dict[str, str]
) -> tuple[str, str]:
    text = str(performers or "").strip()
    if not text:
        return "", "low"
    normalized, matched = normalize_with_lookup(text, artist_keep_map, artist_compact_map)
    if matched and normalized and normalized != text:
        return normalized, "source_normalized"
    return text, "source"


def prune_missing_events(
    conn: sqlite3.Connection, venue_id: str, events: list[EventRecord]
) -> int:
    """Delete stale rows for venue_id that are not present in current fetch."""
    keep_uids = sorted({e.event_uid for e in events if e.event_uid})
    if not keep_uids:
        cur = conn.execute("DELETE FROM events WHERE venue_id = ?", (venue_id,))
        return max(cur.rowcount, 0)

    conn.execute("DROP TABLE IF EXISTS tmp_keep_event_uids")
    conn.execute("CREATE TEMP TABLE tmp_keep_event_uids (event_uid TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO tmp_keep_event_uids(event_uid) VALUES (?)",
        [(uid,) for uid in keep_uids],
    )
    cur = conn.execute(
        """
        DELETE FROM events
        WHERE venue_id = ?
          AND event_uid NOT IN (SELECT event_uid FROM tmp_keep_event_uids)
        """,
        (venue_id,),
    )
    conn.execute("DROP TABLE IF EXISTS tmp_keep_event_uids")
    return max(cur.rowcount, 0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Update events data")
    parser.add_argument("--limit", type=int, default=0, help="Process first N enabled venues only")
    parser.add_argument("--only", type=str, default="", help="Comma-separated venue_ids to process")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--skip-artist-inference",
        action="store_true",
        help="Skip rebuilding data/events_artist_inferred.csv after events update",
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    registry = load_registry()
    only_ids = set(args.only.split(",")) if args.only else set()

    # Filter to enabled venues (or --only overrides)
    targets = []
    for v in registry:
        if only_ids:
            if v.venue_id in only_ids:
                targets.append(v)
        elif v.is_enabled:
            targets.append(v)
    if args.limit > 0:
        targets = targets[: args.limit]

    if not targets:
        logger.info("No venues to process.")
        return

    logger.info("Processing %d venue(s)...", len(targets))

    raw_session = requests.Session()
    raw_session.headers.update({"User-Agent": USER_AGENT})
    throttle = DomainThrottle(min_interval=3.0, default_interval=1.0)
    session = ThrottledSession(raw_session, throttle)

    conn = init_db(EVENTS_DB_PATH)
    artist_keep_map, artist_compact_map = load_artist_lookup_maps()
    logger.info(
        "Loaded artist normalization maps: keep=%d compact=%d",
        len(artist_keep_map),
        len(artist_compact_map),
    )

    success_count = 0
    fail_count = 0
    total_events = 0
    total_changed = 0

    for venue in targets:
        logger.info("--- %s (%s) ---", venue.venue_id, venue.venue_name)
        try:
            source = get_source(venue.source_type, session)
            if source is None:
                logger.warning("No plugin for source_type=%s", venue.source_type)
                fail_count += 1
                continue

            events = source.fetch_events(venue)
            unique_uids = len({e.event_uid for e in events})
            logger.info("  fetched %d event(s) (%d unique)", len(events), unique_uids)

            # Apply date window filter
            events = filter_events_by_date(events)
            logger.info("  after date filter: %d event(s)", len(events))
            total_events += len(events)

            if not events:
                pruned = prune_missing_events(conn, venue.venue_id, events)
                if pruned > 0:
                    logger.info("  pruned %d stale event(s)", pruned)
                # Skip DB write if signature is already empty (no-op)
                cur = conn.execute(
                    "SELECT last_signature FROM venues WHERE venue_id = ?",
                    (venue.venue_id,),
                )
                row = cur.fetchone()
                if row and row[0] == "":
                    if pruned > 0:
                        conn.commit()
                        total_changed += pruned
                    logger.info("  no-op: still empty")
                    success_count += 1
                    continue
                upsert_venue(conn, venue, "")
                conn.commit()
                total_changed += pruned
                success_count += 1
                continue

            # Compute venue signature for no-op detection
            sig = compute_venue_signature(events)
            pruned = prune_missing_events(conn, venue.venue_id, events)
            if pruned > 0:
                logger.info("  pruned %d stale event(s)", pruned)
            cur = conn.execute(
                "SELECT last_signature FROM venues WHERE venue_id = ?",
                (venue.venue_id,),
            )
            row = cur.fetchone()
            if row and row[0] == sig:
                if pruned > 0:
                    conn.commit()
                    total_changed += pruned
                logger.info("  no-op: signature unchanged")
                success_count += 1
                continue

            # Signature changed → upsert events + venue
            changed = upsert_events(
                conn,
                events,
                artist_keep_map,
                artist_compact_map,
            )
            upsert_venue(conn, venue, sig)
            conn.commit()
            total_changed += changed + pruned
            logger.info(
                "  upserted %d changed event(s), pruned %d stale event(s)",
                changed,
                pruned,
            )
            success_count += 1

        except Exception:
            logger.exception("  FAILED: %s", venue.venue_id)
            fail_count += 1
            continue

    conn.close()

    logger.info(
        "Done: %d success, %d failed, %d events fetched, %d changed",
        success_count, fail_count, total_events, total_changed,
    )

    if not args.skip_artist_inference:
        cmd = [sys.executable, "-m", "scripts.build_events_artist_inferred"]
        if args.verbose:
            cmd.append("--verbose")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                logger.info("Artist inference rebuild completed.")
            else:
                logger.warning(
                    "Artist inference rebuild failed (exit=%d): %s",
                    result.returncode,
                    (result.stderr or result.stdout).strip(),
                )
        except Exception:
            logger.exception("Artist inference rebuild failed by exception.")

    # Exit code 1 if ALL enabled venues failed
    enabled_count = sum(1 for v in targets if v.is_enabled or only_ids)
    if enabled_count > 0 and success_count == 0:
        logger.error("All enabled venues failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
