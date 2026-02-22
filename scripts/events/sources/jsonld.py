"""JSON-LD (schema.org/Event) event source plugin."""
from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from ..types import EventRecord, VenueRecord
from .base import EventSource, compute_data_hash, compute_event_uid

logger = logging.getLogger(__name__)


class JsonLdSource(EventSource):
    """Extract Event objects from JSON-LD in HTML pages."""

    def fetch_events(self, venue: VenueRecord) -> list[EventRecord]:
        resp = self.session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = _extract_events(data)
            for item in items:
                rec = _to_event_record(item, venue)
                if rec:
                    events.append(rec)
        return events


def _extract_events(data) -> list[dict]:
    """Recursively find Event objects in JSON-LD."""
    results: list[dict] = []
    if isinstance(data, list):
        for item in data:
            results.extend(_extract_events(item))
    elif isinstance(data, dict):
        t = data.get("@type", "")
        if isinstance(t, list):
            types = t
        else:
            types = [t]
        if any(tp in ("Event", "MusicEvent", "SportsEvent") for tp in types):
            results.append(data)
        # Check @graph
        if "@graph" in data:
            results.extend(_extract_events(data["@graph"]))
    return results


def _to_event_record(item: dict, venue: VenueRecord) -> EventRecord | None:
    """Convert a JSON-LD Event dict to EventRecord."""
    name = item.get("name", "").strip()
    if not name:
        return None
    start = item.get("startDate", "")
    start_date, start_time = _split_datetime(start)
    if not start_date:
        return None
    end = item.get("endDate", "")
    end_date, end_time = _split_datetime(end)
    url = item.get("url") or None
    uid = item.get("@id") or item.get("identifier") or url
    description = (item.get("description") or "")[:500] or None
    performers = None
    perf = item.get("performer") or item.get("performers")
    if perf:
        if isinstance(perf, dict):
            performers = perf.get("name")
        elif isinstance(perf, list):
            names = [p.get("name", "") for p in perf if isinstance(p, dict)]
            performers = ", ".join(n for n in names if n) or None
    status_raw = (item.get("eventStatus") or "").lower()
    if "cancelled" in status_raw:
        status = "cancelled"
    elif "postponed" in status_raw:
        status = "postponed"
    else:
        status = "scheduled"
    rec = EventRecord(
        event_uid="",
        venue_id=venue.venue_id,
        title=name,
        start_date=start_date,
        start_time=start_time,
        end_date=end_date,
        end_time=end_time,
        all_day=not bool(start_time),
        status=status,
        url=url,
        description=description,
        performers=performers,
        capacity=None,
        source_type=venue.source_type,
        source_url=venue.source_url,
        source_event_key=uid,
    )
    rec.event_uid = compute_event_uid(venue.venue_id, uid, name, start_date)
    rec.data_hash = compute_data_hash(rec)
    return rec


def _split_datetime(s: str) -> tuple[str | None, str | None]:
    """Split ISO datetime to (date, time)."""
    if not s:
        return None, None
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?", s)
    if m:
        return m.group(1), m.group(2) or None
    return None, None
