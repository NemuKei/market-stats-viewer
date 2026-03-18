"""Update event signals data: fetch news-like signals into data/event_signals.sqlite.

Usage:
    uv run python -m scripts.update_event_signals_data
    uv run python -m scripts.update_event_signals_data --only starto_concert
    uv run python -m scripts.update_event_signals_data --only ticketjam_events --ticketjam-bootstrap-full
    uv run python -m scripts.update_event_signals_data --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from .events.category import (
    EVENT_CATEGORY_BASEBALL,
    EVENT_CATEGORY_CONCERT,
    EVENT_CATEGORY_OTHER,
    classify_event_category,
)
from .events.registry import load_registry as load_venue_registry
from .signals.entity_aliases import (
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
)
from .signals.sources.base import SignalSource, canonical_labels_json, compute_content_hash
from .signals.sources.kstyle import KstyleMusicSource
from .signals.sources.starto import StartoConcertSource
from .signals.sources.ticketjam import TicketjamEventsSource
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
        "source_url": "https://kstyle.com/search.ksn?searchWord=%E2%96%A0%E5%85%AC%E6%BC%94%E6%83%85%E5%A0%B1",
        "source_type": "html_list",
        "config_json": json.dumps(
            {"pages": 2, "category": "music"}, ensure_ascii=False
        ),
    },
    {
        "source_id": "ticketjam_events",
        "source_name": "Ticketjam Events (Secondary)",
        "source_url": "https://ticketjam.jp/shared/sitemaps/sitemaps_events.xml.gz",
        "source_type": "hybrid_events",
        "config_json": json.dumps(
            {
                "discovery_mode": "hybrid",
                "venue_pages_csv": "data/ticketjam_venue_pages.csv",
                "prefecture_month_urls": [
                    "https://ticketjam.jp/prefectures/osaka/month"
                ],
                "prefecture_month_page_param": "events_page",
                "prefecture_month_max_pages": 8,
                "bootstrap_prefecture_month_max_pages": 60,
                "sitemap_index_url": "https://ticketjam.jp/shared/sitemaps/sitemaps_events.xml.gz",
                "bootstrap_max_sitemaps": 8000,
                "bootstrap_max_event_urls": 50000,
                "max_sitemaps": 120,
                "max_event_urls": 400,
                "timeout_sec": 30,
                "request_retries": 3,
                "allowed_event_types": ["Event", "MusicEvent", "SportsEvent"],
                "future_only": True,
                "lookback_days": 0,
                "exclude_title_keywords": ["駐車場券", "駐車券", "駐車場"],
                "venue_min_capacity": 1000,
                "require_known_venue": True,
                "prune_missing": False,
                "drop_past_events": True,
                "prune_nonconforming": True,
                "upsert_existing": False,
            },
            ensure_ascii=False,
        ),
    },
]


class DomainThrottle:
    """Per-domain polite rate limiter."""

    def __init__(
        self,
        min_interval: float = 4.0,
        default_interval: float = 1.5,
        domain_intervals: dict[str, float] | None = None,
    ):
        self._last_ts: dict[str, float] = {}
        self._min_interval = min_interval
        self._default_interval = default_interval
        self._domain_intervals = {
            str(k).strip().lower(): float(v)
            for k, v in (domain_intervals or {}).items()
            if str(k).strip() and float(v) > 0
        }

    def _resolve_interval(self, domain: str) -> float:
        return self._domain_intervals.get(domain.lower(), self._min_interval)

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        min_interval = self._resolve_interval(domain)
        now = time.monotonic()
        last = self._last_ts.get(domain)
        if last is not None:
            elapsed = now - last
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
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
    "ticketjam_events": TicketjamEventsSource,
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
                config_json = CASE
                    WHEN signal_sources.source_id = 'ticketjam_events'
                    THEN excluded.config_json
                    ELSE COALESCE(signal_sources.config_json, excluded.config_json)
                END
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


def upsert_signals(
    conn: sqlite3.Connection,
    signals: list[SignalRecord],
    *,
    update_existing: bool = True,
) -> int:
    now = now_utc_z()
    changed = 0
    for row in signals:
        cur = conn.execute(
            "SELECT content_hash FROM signals WHERE signal_uid = ?",
            (row.signal_uid,),
        )
        existing = cur.fetchone()
        if existing:
            if existing[0] == row.content_hash:
                continue
            if not update_existing:
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


def prune_missing_signals(
    conn: sqlite3.Connection, source_id: str, signals: list[SignalRecord]
) -> int:
    keep_uids = sorted({row.signal_uid for row in signals if row.signal_uid})
    if not keep_uids:
        return 0

    conn.execute("DROP TABLE IF EXISTS tmp_keep_signal_uids")
    conn.execute(
        "CREATE TEMP TABLE tmp_keep_signal_uids (signal_uid TEXT PRIMARY KEY)"
    )
    conn.executemany(
        "INSERT INTO tmp_keep_signal_uids(signal_uid) VALUES (?)",
        [(uid,) for uid in keep_uids],
    )
    cur = conn.execute(
        """
        DELETE FROM signals
        WHERE source_id = ?
          AND signal_uid NOT IN (SELECT signal_uid FROM tmp_keep_signal_uids)
        """,
        (source_id,),
    )
    conn.execute("DROP TABLE IF EXISTS tmp_keep_signal_uids")
    return max(cur.rowcount, 0)


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


def load_source_config(config_json: str | None) -> dict[str, object]:
    if not isinstance(config_json, str) or not config_json.strip():
        return {}
    try:
        parsed = json.loads(config_json)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def should_prune_missing_for_source(source: SignalSourceRecord) -> bool:
    cfg = load_source_config(source.config_json)
    if source.source_id == "ticketjam_events":
        return bool(cfg.get("prune_missing", False))
    return bool(cfg.get("prune_missing", True))


def should_drop_past_events_for_source(source: SignalSourceRecord) -> bool:
    cfg = load_source_config(source.config_json)
    if source.source_id == "ticketjam_events":
        return bool(cfg.get("drop_past_events", True))
    return bool(cfg.get("drop_past_events", False))


def should_prune_nonconforming_for_source(source: SignalSourceRecord) -> bool:
    cfg = load_source_config(source.config_json)
    if source.source_id == "ticketjam_events":
        return bool(cfg.get("prune_nonconforming", True))
    return bool(cfg.get("prune_nonconforming", False))


def should_upsert_existing_for_source(source: SignalSourceRecord) -> bool:
    cfg = load_source_config(source.config_json)
    if source.source_id == "ticketjam_events":
        return bool(cfg.get("upsert_existing", False))
    return bool(cfg.get("upsert_existing", True))


def apply_ticketjam_runtime_overrides(
    source: SignalSourceRecord,
    *,
    bootstrap_full: bool,
    bootstrap_max_sitemaps: int,
    bootstrap_max_event_urls: int,
    discovery_mode_override: str | None,
) -> SignalSourceRecord:
    if source.source_id != "ticketjam_events":
        return source

    cfg = load_source_config(source.config_json)
    if discovery_mode_override:
        cfg["discovery_mode"] = discovery_mode_override

    if not bootstrap_full:
        if discovery_mode_override:
            source.config_json = json.dumps(cfg, ensure_ascii=False)
        return source

    cfg["bootstrap_max_sitemaps"] = max(1, int(bootstrap_max_sitemaps))
    cfg["bootstrap_max_event_urls"] = max(1, int(bootstrap_max_event_urls))
    cfg["max_sitemap_attempts"] = max(
        int(cfg.get("max_sitemap_attempts", 0)),
        int(cfg["bootstrap_max_sitemaps"]) * 5,
    )
    source.config_json = json.dumps(cfg, ensure_ascii=False)
    return source


def prune_past_event_signals(
    conn: sqlite3.Connection,
    source_id: str,
    today_iso: str,
) -> int:
    cur = conn.execute(
        "SELECT signal_uid, labels_json FROM signals WHERE source_id = ?",
        (source_id,),
    )
    delete_uids: list[tuple[str]] = []
    for uid, labels_json in cur.fetchall():
        if not isinstance(labels_json, str) or not labels_json.strip():
            continue
        try:
            labels = json.loads(labels_json)
        except Exception:
            continue
        if not isinstance(labels, dict):
            continue

        end_date = str(
            labels.get("event_end_date") or labels.get("event_start_date") or ""
        ).strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
            continue
        if end_date < today_iso:
            delete_uids.append((str(uid),))

    if not delete_uids:
        return 0

    conn.executemany(
        "DELETE FROM signals WHERE signal_uid = ?",
        delete_uids,
    )
    return len(delete_uids)


def load_venue_capacity_map() -> dict[str, int]:
    try:
        registry = load_venue_registry()
    except Exception:
        return {}

    out: dict[str, int] = {}
    for row in registry:
        name = str(getattr(row, "venue_name", "") or "").strip()
        capacity = getattr(row, "capacity", None)
        if not name:
            continue
        if isinstance(capacity, int) and capacity > 0:
            out[name] = capacity
    return out


def _to_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _resolve_ticketjam_venue_gate(source: SignalSourceRecord) -> tuple[int, bool]:
    cfg = load_source_config(source.config_json)
    try:
        min_capacity = int(cfg.get("venue_min_capacity", 1000))
    except Exception:
        min_capacity = 1000
    min_capacity = max(0, min_capacity)
    require_known_venue = _to_bool(cfg.get("require_known_venue", True), True)
    return min_capacity, require_known_venue


_TICKETJAM_CONCERT_CATEGORY_GROUPS = {"live_domestic", "live_international"}
_TICKETJAM_CONCERT_SLUG_HINTS = (
    "music",
    "band",
    "idol",
    "classical",
    "jazz",
    "fusion",
    "festival",
    "artist",
)
_TICKETJAM_BASEBALL_HINTS = ("baseball", "yakyu", "npb")


def classify_ticketjam_category(title: object, labels: dict[str, object]) -> str:
    group = str(labels.get("ticketjam_category_group") or "").strip().lower()
    slug = str(labels.get("ticketjam_category_slug") or "").strip().lower()
    artist_name = str(labels.get("artist_name") or "").strip()
    event_info = str(labels.get("event_info") or "").strip()

    if any(hint in group for hint in _TICKETJAM_BASEBALL_HINTS) or any(
        hint in slug for hint in _TICKETJAM_BASEBALL_HINTS
    ):
        return EVENT_CATEGORY_BASEBALL
    if group in _TICKETJAM_CONCERT_CATEGORY_GROUPS:
        return EVENT_CATEGORY_CONCERT
    if any(hint in slug for hint in _TICKETJAM_CONCERT_SLUG_HINTS):
        return EVENT_CATEGORY_CONCERT

    fallback_artist_name = (
        artist_name
        if group in _TICKETJAM_CONCERT_CATEGORY_GROUPS
        or any(hint in slug for hint in _TICKETJAM_CONCERT_SLUG_HINTS)
        else ""
    )
    category = classify_event_category(title, fallback_artist_name, event_info)
    if category not in {
        EVENT_CATEGORY_CONCERT,
        EVENT_CATEGORY_BASEBALL,
        EVENT_CATEGORY_OTHER,
    }:
        return EVENT_CATEGORY_OTHER
    return category


def apply_ticketjam_selection_rules(
    signals: list[SignalRecord],
    source: SignalSourceRecord,
    venue_capacity_by_name: dict[str, int],
) -> tuple[list[SignalRecord], dict[str, object]]:
    if source.source_id != "ticketjam_events":
        return signals, {}

    min_capacity, require_known_venue = _resolve_ticketjam_venue_gate(source)
    kept: list[SignalRecord] = []
    dropped_missing_fields = 0
    dropped_unknown_venue = 0
    dropped_low_capacity = 0
    category_counts: Counter[str] = Counter()

    for row in signals:
        labels: dict[str, object] = {}
        if isinstance(row.labels_json, str) and row.labels_json.strip():
            try:
                parsed = json.loads(row.labels_json)
                if isinstance(parsed, dict):
                    labels = parsed
            except Exception:
                labels = {}

        title = str(row.title or "").strip()
        start_date = str(labels.get("event_start_date") or "").strip()
        venue_name = str(labels.get("venue_name") or "").strip()
        artist_name = str(labels.get("artist_name") or "").strip()
        if not (title and start_date and venue_name and artist_name):
            dropped_missing_fields += 1
            continue

        capacity = venue_capacity_by_name.get(venue_name)
        if capacity is None:
            if require_known_venue:
                dropped_unknown_venue += 1
                continue
        elif capacity < min_capacity:
            dropped_low_capacity += 1
            continue

        category = classify_ticketjam_category(title, labels)
        labels["event_category"] = category
        if capacity is not None:
            labels["venue_capacity"] = capacity
        row.labels_json = canonical_labels_json(labels)
        row.content_hash = compute_content_hash(row)
        kept.append(row)
        category_counts[category] += 1

    return kept, {
        "min_capacity": min_capacity,
        "require_known_venue": require_known_venue,
        "kept": len(kept),
        "dropped_missing_fields": dropped_missing_fields,
        "dropped_unknown_venue": dropped_unknown_venue,
        "dropped_low_capacity": dropped_low_capacity,
        "category_counts": dict(category_counts),
    }


def prune_ticketjam_nonconforming_signals(
    conn: sqlite3.Connection,
    source: SignalSourceRecord,
    venue_capacity_by_name: dict[str, int],
) -> int:
    if source.source_id != "ticketjam_events":
        return 0

    min_capacity, require_known_venue = _resolve_ticketjam_venue_gate(source)

    cur = conn.execute(
        "SELECT signal_uid, title, labels_json FROM signals WHERE source_id = ?",
        (source.source_id,),
    )
    delete_uids: list[tuple[str]] = []
    for signal_uid, title, labels_json in cur.fetchall():
        if not isinstance(labels_json, str) or not labels_json.strip():
            delete_uids.append((str(signal_uid),))
            continue
        try:
            labels = json.loads(labels_json)
        except Exception:
            delete_uids.append((str(signal_uid),))
            continue
        if not isinstance(labels, dict):
            delete_uids.append((str(signal_uid),))
            continue

        title_text = str(title or "").strip()
        start_date = str(labels.get("event_start_date") or "").strip()
        venue_name = str(labels.get("venue_name") or "").strip()
        artist = str(labels.get("artist_name") or "").strip()
        if not (title_text and start_date and venue_name and artist):
            delete_uids.append((str(signal_uid),))
            continue

        capacity = venue_capacity_by_name.get(venue_name)
        if capacity is None and require_known_venue:
            delete_uids.append((str(signal_uid),))
            continue
        if capacity is not None and capacity < min_capacity:
            delete_uids.append((str(signal_uid),))

    if not delete_uids:
        return 0
    conn.executemany("DELETE FROM signals WHERE signal_uid = ?", delete_uids)
    return len(delete_uids)


def prune_ticketjam_duplicate_event_ids(
    conn: sqlite3.Connection,
    source_id: str,
) -> int:
    if source_id != "ticketjam_events":
        return 0
    cur = conn.execute(
        """
        SELECT signal_uid, url, published_at_utc, updated_at_utc
        FROM signals
        WHERE source_id = ?
        """,
        (source_id,),
    )

    best_by_event_id: dict[str, tuple[str, str, str]] = {}
    duplicate_uids: list[tuple[str]] = []
    for signal_uid, url, published_at_utc, updated_at_utc in cur.fetchall():
        match = re.search(r"/event/(\d+)$", str(url or "").strip())
        if not match:
            continue
        event_id = match.group(1)
        current = (
            str(signal_uid),
            str(published_at_utc or ""),
            str(updated_at_utc or ""),
        )
        prev = best_by_event_id.get(event_id)
        if prev is None:
            best_by_event_id[event_id] = current
            continue
        if (current[1], current[2], current[0]) > (prev[1], prev[2], prev[0]):
            duplicate_uids.append((prev[0],))
            best_by_event_id[event_id] = current
        else:
            duplicate_uids.append((current[0],))

    if not duplicate_uids:
        return 0
    conn.executemany("DELETE FROM signals WHERE signal_uid = ?", duplicate_uids)
    return len(duplicate_uids)


def prune_ticketjam_duplicate_performances(
    conn: sqlite3.Connection,
    source_id: str,
) -> int:
    """Drop duplicate rows that represent the same performance."""
    if source_id != "ticketjam_events":
        return 0
    cur = conn.execute(
        """
        SELECT signal_uid, title, labels_json, published_at_utc, updated_at_utc
        FROM signals
        WHERE source_id = ?
        """,
        (source_id,),
    )

    best_by_key: dict[tuple[str, str, str, str, str], tuple[str, str, str]] = {}
    duplicate_uids: list[tuple[str]] = []
    for signal_uid, title, labels_json, published_at_utc, updated_at_utc in cur.fetchall():
        labels: dict[str, object] = {}
        if isinstance(labels_json, str) and labels_json.strip():
            try:
                parsed = json.loads(labels_json)
                if isinstance(parsed, dict):
                    labels = parsed
            except Exception:
                labels = {}
        key = (
            str(labels.get("event_start_date") or "").strip(),
            str(labels.get("event_start_time") or "").strip(),
            str(labels.get("venue_name") or "").strip(),
            str(labels.get("artist_name") or "").strip(),
            str(title or "").strip(),
        )
        current = (
            str(signal_uid),
            str(published_at_utc or ""),
            str(updated_at_utc or ""),
        )
        prev = best_by_key.get(key)
        if prev is None:
            best_by_key[key] = current
            continue
        if (current[1], current[2], current[0]) > (prev[1], prev[2], prev[0]):
            duplicate_uids.append((prev[0],))
            best_by_key[key] = current
        else:
            duplicate_uids.append((current[0],))

    if not duplicate_uids:
        return 0
    conn.executemany("DELETE FROM signals WHERE signal_uid = ?", duplicate_uids)
    return len(duplicate_uids)


def normalize_signal_labels(
    signals: list[SignalRecord],
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
    venue_keep_map: dict[str, str],
    venue_compact_map: dict[str, str],
) -> dict[str, object]:
    changed_rows = 0
    artist_normalized = 0
    venue_normalized = 0
    unknown_artists: Counter[str] = Counter()
    unknown_venues: Counter[str] = Counter()

    for row in signals:
        if not isinstance(row.labels_json, str) or not row.labels_json.strip():
            continue
        try:
            labels = json.loads(row.labels_json)
        except Exception:
            continue
        if not isinstance(labels, dict):
            continue

        row_changed = False

        current_artist = str(labels.get("artist_name", "")).strip()
        raw_artist = str(labels.get("raw_artist_name", current_artist)).strip()
        if raw_artist and labels.get("raw_artist_name") != raw_artist:
            labels["raw_artist_name"] = raw_artist
            row_changed = True
        if raw_artist:
            normalized_artist, artist_matched = normalize_with_lookup(
                raw_artist,
                artist_keep_map,
                artist_compact_map,
            )
            if normalized_artist and normalized_artist != current_artist:
                labels["artist_name"] = normalized_artist
                row_changed = True
                if normalized_artist != raw_artist:
                    artist_normalized += 1
            if not artist_matched:
                unknown_artists[raw_artist] += 1

        current_venue = str(labels.get("venue_name", "")).strip()
        raw_venue = str(labels.get("raw_venue_name", current_venue)).strip()
        if raw_venue and labels.get("raw_venue_name") != raw_venue:
            labels["raw_venue_name"] = raw_venue
            row_changed = True
        if raw_venue:
            normalized_venue, venue_matched = normalize_venue_with_lookup(
                raw_venue,
                venue_keep_map,
                venue_compact_map,
            )
            if normalized_venue and normalized_venue != current_venue:
                labels["venue_name"] = normalized_venue
                row_changed = True
                if normalized_venue != raw_venue:
                    venue_normalized += 1
            if not venue_matched:
                unknown_venues[raw_venue] += 1

        if row_changed:
            row.labels_json = canonical_labels_json(labels)
            row.content_hash = compute_content_hash(row)
            changed_rows += 1

    return {
        "changed_rows": changed_rows,
        "artist_normalized": artist_normalized,
        "venue_normalized": venue_normalized,
        "unknown_artists": unknown_artists,
        "unknown_venues": unknown_venues,
    }


def log_unknown_aliases(counter: Counter[str], label: str, top_n: int = 5) -> None:
    if not counter:
        return
    top_items = ", ".join(f"{name}({count})" for name, count in counter.most_common(top_n))
    logger.info("  unknown %s candidates: %s", label, top_items)


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
    parser.add_argument(
        "--ticketjam-bootstrap-full",
        action="store_true",
        help="Force ticketjam full rebuild once (usually with --only ticketjam_events)",
    )
    parser.add_argument(
        "--ticketjam-bootstrap-max-sitemaps",
        type=int,
        default=8000,
        help="Legacy sitemap mode only: scan this many ticketjam sitemaps",
    )
    parser.add_argument(
        "--ticketjam-bootstrap-max-event-urls",
        type=int,
        default=50000,
        help="Legacy sitemap mode only: keep up to this many ticketjam event URLs",
    )
    parser.add_argument(
        "--ticketjam-discovery-mode",
        choices=[
            "hybrid",
            "sitemap",
            "venue_pages",
            "prefecture_month",
            "prefecture_month_hybrid",
        ],
        default="",
        help="Override ticketjam discovery mode for this run",
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
    if (
        args.ticketjam_bootstrap_full
        and only_ids
        and "ticketjam_events" not in only_ids
    ):
        parser.error(
            "--ticketjam-bootstrap-full requires --only to include ticketjam_events"
        )

    raw_session = requests.Session()
    raw_session.headers.update({"User-Agent": USER_AGENT})
    throttle = DomainThrottle(
        min_interval=4.0,
        default_interval=1.5,
        domain_intervals={"ticketjam.jp": 1.0},
    )
    session = ThrottledSession(raw_session, throttle)

    conn = init_db(SIGNALS_DB_PATH)
    ensure_default_sources(conn)
    targets = load_target_sources(conn, only_ids)

    if not targets:
        logger.info("No sources to process.")
        conn.close()
        return

    logger.info("Processing %d source(s)...", len(targets))
    artist_keep_map, artist_compact_map = load_artist_lookup_maps()
    venue_keep_map, venue_compact_map = load_venue_lookup_maps()
    venue_capacity_by_name = load_venue_capacity_map()
    target_venue_count_1000 = sum(
        1 for cap in venue_capacity_by_name.values() if int(cap) >= 1000
    )
    logger.info(
        "Loaded normalization maps: artist keep=%d compact=%d, venue keep=%d compact=%d",
        len(artist_keep_map),
        len(artist_compact_map),
        len(venue_keep_map),
        len(venue_compact_map),
    )
    logger.info(
        "Loaded venue capacity map: total=%d, capacity>=1000=%d",
        len(venue_capacity_by_name),
        target_venue_count_1000,
    )

    success_count = 0
    fail_count = 0
    total_fetched = 0
    total_changed = 0

    for source in targets:
        logger.info("--- %s (%s) ---", source.source_id, source.source_name)
        try:
            source = apply_ticketjam_runtime_overrides(
                source,
                bootstrap_full=args.ticketjam_bootstrap_full,
                bootstrap_max_sitemaps=args.ticketjam_bootstrap_max_sitemaps,
                bootstrap_max_event_urls=args.ticketjam_bootstrap_max_event_urls,
                discovery_mode_override=args.ticketjam_discovery_mode or None,
            )
            if args.ticketjam_bootstrap_full and source.source_id == "ticketjam_events":
                clear_source_for_rebuild(conn, source.source_id)
                source.last_signature = None
                source_cfg = load_source_config(source.config_json)
                discovery_mode = str(
                    source_cfg.get("discovery_mode", "sitemap")
                ).strip() or "sitemap"
                if discovery_mode == "venue_pages":
                    logger.info(
                        "  ticketjam bootstrap full: force rebuild (venue-page mode; bootstrap_max_* ignored)"
                    )
                elif discovery_mode == "prefecture_month":
                    logger.info(
                        "  ticketjam bootstrap full: force rebuild (prefecture-month mode; Osaka spike route only)"
                    )
                elif discovery_mode == "prefecture_month_hybrid":
                    logger.info(
                        "  ticketjam bootstrap full: force rebuild (prefecture-month priority + existing routes)"
                    )
                elif discovery_mode == "hybrid":
                    logger.info(
                        "  ticketjam bootstrap full: force rebuild (hybrid mode; venue pages + sitemap supplement)"
                    )
                else:
                    logger.info(
                        "  ticketjam bootstrap full: force rebuild + max_sitemaps=%d max_event_urls=%d",
                        args.ticketjam_bootstrap_max_sitemaps,
                        args.ticketjam_bootstrap_max_event_urls,
                    )

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

            norm_stats = normalize_signal_labels(
                signals,
                artist_keep_map,
                artist_compact_map,
                venue_keep_map,
                venue_compact_map,
            )
            logger.info(
                "  normalized labels: rows=%d artist=%d venue=%d",
                int(norm_stats.get("changed_rows", 0)),
                int(norm_stats.get("artist_normalized", 0)),
                int(norm_stats.get("venue_normalized", 0)),
            )
            log_unknown_aliases(
                norm_stats.get("unknown_artists", Counter()),
                label="artist",
            )
            log_unknown_aliases(
                norm_stats.get("unknown_venues", Counter()),
                label="venue",
            )
            selection_stats: dict[str, object] = {}
            signals, selection_stats = apply_ticketjam_selection_rules(
                signals,
                source,
                venue_capacity_by_name,
            )
            if selection_stats:
                category_counts = selection_stats.get("category_counts", {})
                category_summary = ", ".join(
                    f"{k}:{v}" for k, v in sorted(dict(category_counts).items())
                )
                logger.info(
                    "  ticketjam gate: min_capacity=%s require_known_venue=%s kept=%s dropped_missing=%s dropped_unknown_venue=%s dropped_low_capacity=%s categories=%s",
                    selection_stats.get("min_capacity"),
                    selection_stats.get("require_known_venue"),
                    selection_stats.get("kept"),
                    selection_stats.get("dropped_missing_fields"),
                    selection_stats.get("dropped_unknown_venue"),
                    selection_stats.get("dropped_low_capacity"),
                    category_summary or "-",
                )

            if args.rebuild:
                clear_source_for_rebuild(conn, source.source_id)
                logger.info("  rebuild: cleared existing rows and reset last_signature")

            sig = compute_source_signature(signals)
            prune_missing_enabled = should_prune_missing_for_source(source)
            pruned = 0
            if prune_missing_enabled:
                pruned = prune_missing_signals(conn, source.source_id, signals)
                if pruned > 0:
                    logger.info("  pruned %d stale signal(s)", pruned)
            else:
                logger.info("  prune_missing disabled for this source")

            pruned_past = 0
            if should_drop_past_events_for_source(source):
                pruned_past = prune_past_event_signals(
                    conn,
                    source.source_id,
                    today_iso=date.today().isoformat(),
                )
                if pruned_past > 0:
                    logger.info("  pruned %d past signal(s)", pruned_past)

            pruned_nonconforming = 0
            if should_prune_nonconforming_for_source(source):
                pruned_nonconforming = prune_ticketjam_nonconforming_signals(
                    conn,
                    source,
                    venue_capacity_by_name,
                )
                if pruned_nonconforming > 0:
                    logger.info(
                        "  pruned %d nonconforming signal(s)",
                        pruned_nonconforming,
                    )

            pruned_duplicates = prune_ticketjam_duplicate_event_ids(
                conn,
                source.source_id,
            )
            if pruned_duplicates > 0:
                logger.info("  pruned %d duplicate event_id signal(s)", pruned_duplicates)
            pruned_performances = prune_ticketjam_duplicate_performances(
                conn,
                source.source_id,
            )
            if pruned_performances > 0:
                logger.info(
                    "  pruned %d duplicate performance signal(s)",
                    pruned_performances,
                )

            if not args.rebuild and source.last_signature == sig:
                if (
                    pruned == 0
                    and pruned_past == 0
                    and pruned_nonconforming == 0
                    and pruned_duplicates == 0
                    and pruned_performances == 0
                ):
                    logger.info("  no-op: signature unchanged")
                else:
                    conn.commit()
                success_count += 1
                total_changed += (
                    pruned
                    + pruned_past
                    + pruned_nonconforming
                    + pruned_duplicates
                    + pruned_performances
                )
                continue

            update_existing = should_upsert_existing_for_source(source)
            if not update_existing:
                logger.info("  upsert mode: new_only (existing rows are not updated)")
            changed = upsert_signals(
                conn,
                signals,
                update_existing=update_existing,
            )
            post_pruned_duplicates = prune_ticketjam_duplicate_event_ids(
                conn,
                source.source_id,
            )
            post_pruned_performances = prune_ticketjam_duplicate_performances(
                conn,
                source.source_id,
            )
            if post_pruned_duplicates > 0:
                logger.info(
                    "  post-upsert pruned %d duplicate event_id signal(s)",
                    post_pruned_duplicates,
                )
            if post_pruned_performances > 0:
                logger.info(
                    "  post-upsert pruned %d duplicate performance signal(s)",
                    post_pruned_performances,
                )
            update_source_signature(conn, source.source_id, sig)
            conn.commit()

            total_changed += (
                changed
                + pruned
                + pruned_past
                + pruned_nonconforming
                + pruned_duplicates
                + pruned_performances
                + post_pruned_duplicates
                + post_pruned_performances
            )
            logger.info(
                "  upserted %d changed signal(s), pruned %d stale signal(s), %d past signal(s), %d nonconforming signal(s), %d duplicate event_id signal(s), %d duplicate performance signal(s), post-upsert %d duplicate event_id signal(s), %d duplicate performance signal(s)",
                changed,
                pruned,
                pruned_past,
                pruned_nonconforming,
                pruned_duplicates,
                pruned_performances,
                post_pruned_duplicates,
                post_pruned_performances,
            )
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
