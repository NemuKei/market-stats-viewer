"""Data types for event signals."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SignalSourceRecord:
    """One source definition row from signal_sources."""

    source_id: str
    source_name: str
    source_url: str
    source_type: str
    config_json: str | None
    is_enabled: bool
    last_signature: str | None = None


@dataclass
class SignalRecord:
    """Normalised signal row for DB upsert."""

    signal_uid: str
    source_id: str
    published_at_utc: str
    title: str
    url: str
    snippet: str | None
    score: int
    labels_json: str | None
    content_hash: str = field(default="", init=False)
