"""Base interface for event source plugins."""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod

import requests

from ..types import EventRecord, VenueRecord


class EventSource(ABC):
    """Interface for event source plugins."""

    def __init__(self, session: requests.Session) -> None:
        self.session = session

    @abstractmethod
    def fetch_events(self, venue: VenueRecord) -> list[EventRecord]:
        """Fetch and normalise events for a venue. Raise on fatal error."""
        ...


def compute_data_hash(rec: EventRecord) -> str:
    """SHA-256 of key fields for diff detection."""
    payload = json.dumps(
        {
            "venue_id": rec.venue_id,
            "title": rec.title,
            "start_date": rec.start_date,
            "start_time": rec.start_time,
            "end_date": rec.end_date,
            "end_time": rec.end_time,
            "all_day": rec.all_day,
            "status": rec.status,
            "url": rec.url,
            "performers": rec.performers,
            "capacity": rec.capacity,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_event_uid(
    venue_id: str, key: str | None, title: str, start_date: str,
    *, start_time: str | None = None, url: str | None = None,
) -> str:
    """Generate a stable event UID.

    When *key* (source_event_key / href / guid) is available, it takes priority.
    Fallback hashes include start_time and url to avoid collisions on
    same-day, same-title events (e.g. matinee / evening shows).
    Backward-compatible: when both start_time and url are empty the hash
    matches the legacy format.
    """
    if key:
        return f"{venue_id}:{key}"
    if start_time or url:
        title_norm = re.sub(r"\s+", " ", title).strip()
        raw = f"{venue_id}|{title_norm}|{start_date}|{start_time or ''}|{url or ''}"
    else:
        raw = f"{venue_id}:{title}:{start_date}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{venue_id}:h:{h}"
