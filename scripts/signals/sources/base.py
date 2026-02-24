"""Base interfaces and helpers for signal source plugins."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import requests

from ..types import SignalRecord, SignalSourceRecord

JST = timezone(timedelta(hours=9))


class SignalSource(ABC):
    """Interface for event signal source plugins."""

    def __init__(self, session: requests.Session) -> None:
        self.session = session

    @abstractmethod
    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        """Fetch and normalize signals for one source."""
        ...


def compute_signal_uid(source_id: str, url: str, extra_key: str | None = None) -> str:
    """Generate stable UID from source + URL (+ optional extra key)."""
    raw = f"{source_id}|{url.strip()}"
    if extra_key:
        raw = f"{raw}|{extra_key.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_labels_json(labels: dict[str, object] | None) -> str | None:
    """Serialize labels to canonical JSON or return None."""
    if not labels:
        return None
    return json.dumps(labels, ensure_ascii=False, sort_keys=True)


def compute_content_hash(rec: SignalRecord) -> str:
    """Compute content hash for diff detection."""
    payload = json.dumps(
        {
            "source_id": rec.source_id,
            "published_at_utc": rec.published_at_utc,
            "title": rec.title,
            "url": rec.url,
            "snippet": rec.snippet,
            "score": rec.score,
            "labels_json": rec.labels_json,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def to_utc_z(dt: datetime) -> str:
    """Format datetime to UTC ISO8601 with Z suffix."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc_z_from_jst_date(date_text: str, fmt: str) -> str | None:
    """Parse JST date string and convert to UTC Z."""
    try:
        dt_local = datetime.strptime(date_text, fmt).replace(tzinfo=JST)
    except ValueError:
        return None
    return to_utc_z(dt_local)


def trim_snippet(text: str | None, max_len: int = 180) -> str | None:
    """Trim snippet to short list-safe text."""
    if not text:
        return None
    compact = " ".join(text.split())
    if not compact:
        return None
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"
