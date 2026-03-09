"""Data types for event hub."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VenueRecord:
    """One row from venue_registry.csv."""

    venue_id: str
    venue_name: str
    pref_code: str
    pref_name: str
    capacity: int | None
    official_url: str
    source_type: str
    source_url: str
    config_json: str | None
    is_enabled: bool
    ticketjam_watch: bool = False
    official_fetch_candidate: bool = False
    official_gap_reason: str | None = None


@dataclass
class EventRecord:
    """Normalised event ready for DB upsert."""

    event_uid: str
    venue_id: str
    title: str
    start_date: str  # YYYY-MM-DD
    start_time: str | None  # HH:MM
    end_date: str | None
    end_time: str | None
    all_day: bool
    status: str  # scheduled / cancelled / postponed / unknown
    url: str | None
    description: str | None
    performers: str | None
    capacity: int | None
    source_type: str
    source_url: str
    source_event_key: str | None
    data_hash: str = field(default="", init=False)
