"""RSS/Atom event source plugin."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from ..types import EventRecord, VenueRecord
from .base import EventSource, compute_data_hash, compute_event_uid

logger = logging.getLogger(__name__)


class RssSource(EventSource):
    """Minimal RSS/Atom feed parser for event extraction."""

    def fetch_events(self, venue: VenueRecord) -> list[EventRecord]:
        resp = self.session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        text = resp.text
        events: list[EventRecord] = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            logger.warning("rss: invalid XML from %s", venue.source_url)
            return []

        # RSS 2.0
        for item in root.iter("item"):
            rec = self._parse_rss_item(item, venue)
            if rec:
                events.append(rec)
        # Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            rec = self._parse_atom_entry(entry, ns, venue)
            if rec:
                events.append(rec)
        return events

    def _parse_rss_item(
        self, item: ET.Element, venue: VenueRecord
    ) -> EventRecord | None:
        title = (item.findtext("title") or "").strip()
        if not title:
            return None
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        start_date = _parse_rss_date(pub_date)
        if not start_date:
            return None
        rec = EventRecord(
            event_uid="",
            venue_id=venue.venue_id,
            title=title,
            start_date=start_date,
            start_time=None,
            end_date=None,
            end_time=None,
            all_day=True,
            status="scheduled",
            url=link or None,
            description=description[:500] if description else None,
            performers=None,
            capacity=None,
            source_type=venue.source_type,
            source_url=venue.source_url,
            source_event_key=guid or link or None,
        )
        rec.event_uid = compute_event_uid(
            venue.venue_id, guid or link, title, start_date
        )
        rec.data_hash = compute_data_hash(rec)
        return rec

    def _parse_atom_entry(
        self, entry: ET.Element, ns: dict, venue: VenueRecord
    ) -> EventRecord | None:
        title_el = entry.find("{http://www.w3.org/2005/Atom}title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            return None
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.get("href", "") if link_el is not None else ""
        id_el = entry.find("{http://www.w3.org/2005/Atom}id")
        entry_id = (id_el.text or "").strip() if id_el is not None else ""
        updated_el = entry.find("{http://www.w3.org/2005/Atom}updated")
        updated = (updated_el.text or "").strip() if updated_el is not None else ""
        start_date = _parse_iso_date(updated)
        if not start_date:
            return None
        rec = EventRecord(
            event_uid="",
            venue_id=venue.venue_id,
            title=title,
            start_date=start_date,
            start_time=None,
            end_date=None,
            end_time=None,
            all_day=True,
            status="scheduled",
            url=link or None,
            description=None,
            performers=None,
            capacity=None,
            source_type=venue.source_type,
            source_url=venue.source_url,
            source_event_key=entry_id or link or None,
        )
        rec.event_uid = compute_event_uid(
            venue.venue_id, entry_id or link, title, start_date
        )
        rec.data_hash = compute_data_hash(rec)
        return rec


def _parse_rss_date(s: str) -> str | None:
    """Parse RFC 2822 date to YYYY-MM-DD."""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return _parse_iso_date(s)


def _parse_iso_date(s: str) -> str | None:
    """Parse ISO date to YYYY-MM-DD."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    return None
