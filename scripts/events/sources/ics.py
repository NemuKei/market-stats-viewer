"""ICS (iCalendar) event source plugin."""
from __future__ import annotations

import logging
import re
from datetime import datetime

from ..types import EventRecord, VenueRecord
from .base import EventSource, compute_data_hash, compute_event_uid

logger = logging.getLogger(__name__)


class IcsSource(EventSource):
    """Minimal iCalendar parser for VEVENT entries."""

    def fetch_events(self, venue: VenueRecord) -> list[EventRecord]:
        resp = self.session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        text = resp.text
        events: list[EventRecord] = []
        for block in _split_vevents(text):
            rec = _parse_vevent(block, venue)
            if rec:
                events.append(rec)
        return events


def _split_vevents(text: str) -> list[str]:
    """Extract VEVENT blocks from ICS text."""
    blocks: list[str] = []
    current: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.strip() == "BEGIN:VEVENT":
            inside = True
            current = []
        elif line.strip() == "END:VEVENT":
            inside = False
            blocks.append("\n".join(current))
        elif inside:
            current.append(line)
    return blocks


def _get_field(block: str, field: str) -> str | None:
    """Get a field value from a VEVENT block."""
    pattern = rf"^{re.escape(field)}[;:](.+)$"
    m = re.search(pattern, block, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


def _parse_dt(val: str | None) -> tuple[str | None, str | None]:
    """Parse DTSTART/DTEND value to (date_str, time_str)."""
    if not val:
        return None, None
    # Remove VALUE=DATE: prefix etc.
    val = re.sub(r"^[^:]*:", "", val) if ":" in val and not val[0].isdigit() else val
    val = val.strip()
    if len(val) == 8:  # 20260301
        d = datetime.strptime(val, "%Y%m%d")
        return d.strftime("%Y-%m-%d"), None
    if len(val) >= 15:  # 20260301T180000 or 20260301T180000Z
        val = val.rstrip("Z")
        d = datetime.strptime(val[:15], "%Y%m%dT%H%M%S")
        return d.strftime("%Y-%m-%d"), d.strftime("%H:%M")
    return None, None


def _parse_vevent(block: str, venue: VenueRecord) -> EventRecord | None:
    """Parse a single VEVENT block into an EventRecord."""
    summary = _get_field(block, "SUMMARY")
    if not summary:
        return None
    uid = _get_field(block, "UID")
    url = _get_field(block, "URL")
    description = _get_field(block, "DESCRIPTION")
    dtstart_raw = _get_field(block, "DTSTART")
    dtend_raw = _get_field(block, "DTEND")
    start_date, start_time = _parse_dt(dtstart_raw)
    end_date, end_time = _parse_dt(dtend_raw)
    if not start_date:
        return None
    all_day = start_time is None
    status_raw = (_get_field(block, "STATUS") or "").upper()
    status_map = {"CONFIRMED": "scheduled", "CANCELLED": "cancelled", "TENTATIVE": "scheduled"}
    status = status_map.get(status_raw, "scheduled")
    rec = EventRecord(
        event_uid="",
        venue_id=venue.venue_id,
        title=summary,
        start_date=start_date,
        start_time=start_time,
        end_date=end_date,
        end_time=end_time,
        all_day=all_day,
        status=status,
        url=url,
        description=description[:500] if description else None,
        performers=None,
        capacity=None,
        source_type=venue.source_type,
        source_url=venue.source_url,
        source_event_key=uid,
    )
    rec.event_uid = compute_event_uid(venue.venue_id, uid, summary, start_date)
    rec.data_hash = compute_data_hash(rec)
    return rec
