"""HTML-based event source plugin with per-venue strategies."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from ..types import EventRecord, VenueRecord
from .base import EventSource, compute_data_hash, compute_event_uid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------
_STRATEGIES: dict[str, type["_BaseStrategy"]] = {}


def _register(name: str):
    def decorator(cls):
        _STRATEGIES[name] = cls
        return cls
    return decorator


class _BaseStrategy:
    """Per-venue HTML parsing strategy."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Yokohama Arena JSON API
# ---------------------------------------------------------------------------
@_register("yokohama_arena_json")
class _YokohamaArenaJson(_BaseStrategy):
    """Yokohama Arena provides a JSON API at /event/YYYYMM?_format=json."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        events: list[EventRecord] = []
        today = date.today()
        # Fetch current month + next 3 months
        for offset in range(4):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            ym = d.strftime("%Y%m")
            url = f"https://www.yokohama-arena.co.jp/event/{ym}?_format=json"
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                logger.warning("yokohama_arena: %s returned %s", url, resp.status_code)
                continue
            try:
                data = resp.json()
            except (ValueError, TypeError):
                logger.warning("yokohama_arena: invalid JSON from %s", url)
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                title = item.get("title", "").strip()
                if not title:
                    continue
                start_date = item.get("date1", "")
                end_date = item.get("date2", "") or None
                if not start_date:
                    continue
                # start_time: take first element if list
                start_times = item.get("ev_start", [])
                start_time = start_times[0] if start_times else None
                end_times = item.get("ev_end", [])
                end_time = end_times[-1] if end_times else None
                # Normalise times to HH:MM
                start_time = _normalise_time(start_time)
                end_time = _normalise_time(end_time)
                artist = item.get("artist") or None
                if artist is False:
                    artist = None
                detail_path = item.get("path", "")
                event_url = (
                    f"https://www.yokohama-arena.co.jp{detail_path}"
                    if detail_path
                    else item.get("url")
                )
                source_key = detail_path or None
                rec = EventRecord(
                    event_uid="",
                    venue_id=venue.venue_id,
                    title=title,
                    start_date=start_date,
                    start_time=start_time,
                    end_date=end_date if end_date != start_date else None,
                    end_time=end_time,
                    all_day=not bool(start_time),
                    status="scheduled",
                    url=event_url,
                    description=None,
                    performers=artist if isinstance(artist, str) else None,
                    capacity=None,
                    source_type=venue.source_type,
                    source_url=url,
                    source_event_key=source_key,
                )
                rec.event_uid = compute_event_uid(
                    venue.venue_id, source_key, title, start_date
                )
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)
        return events


# ---------------------------------------------------------------------------
# Tokyo International Forum calendar
# ---------------------------------------------------------------------------
@_register("tif_calendar")
class _TifCalendar(_BaseStrategy):
    """Parse Tokyo International Forum calendar page."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        # TIF redirects /calendar/ to /visitors/event/
        resp = session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        current_date: str | None = None
        for li in soup.find_all("li"):
            # Date is in <em> or <time> tags
            for tag in li.find_all(["em", "time"]):
                raw = tag.get_text(strip=True)
                m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw)
                if m:
                    current_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    break
            inner_links = li.find_all("a")
            for a in inner_links:
                href = a.get("href", "")
                if "detail.html" not in href:
                    continue
                title = a.get_text(strip=True)
                if not title or not current_date:
                    continue
                event_url = href
                if not event_url.startswith("http"):
                    base = resp.url if hasattr(resp, "url") else venue.source_url
                    # Resolve relative to the actual response URL
                    if base.endswith("/"):
                        event_url = f"{base}{href}"
                    else:
                        event_url = f"{base}/{href}"
                source_key = href
                rec = EventRecord(
                    event_uid="",
                    venue_id=venue.venue_id,
                    title=title,
                    start_date=current_date,
                    start_time=None,
                    end_date=None,
                    end_time=None,
                    all_day=True,
                    status="scheduled",
                    url=event_url,
                    description=None,
                    performers=None,
                    capacity=None,
                    source_type=venue.source_type,
                    source_url=venue.source_url,
                    source_event_key=source_key,
                )
                rec.event_uid = compute_event_uid(
                    venue.venue_id, source_key, title, current_date
                )
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)
        return events


# ---------------------------------------------------------------------------
# Zepp schedule pages
# ---------------------------------------------------------------------------
@_register("zepp_schedule")
class _ZeppSchedule(_BaseStrategy):
    """Parse Zepp venue schedule pages."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        events: list[EventRecord] = []
        today = date.today()
        # Fetch current + next 2 months
        for offset in range(3):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            ym = d.strftime("%Y%m")
            url = venue.source_url
            if not url.endswith("/"):
                url += "/"
            month_url = f"{url}?ym={ym}"
            resp = session.get(month_url, timeout=30)
            if resp.status_code != 200:
                logger.warning("zepp: %s returned %s", month_url, resp.status_code)
                # Fallback: try base URL
                if offset == 0:
                    resp = session.get(venue.source_url, timeout=30)
                    if resp.status_code != 200:
                        continue
                else:
                    continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(self._parse_page(venue, soup, month_url))
        return events

    def _parse_page(
        self, venue: VenueRecord, soup: BeautifulSoup, source_url: str
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        # Zepp pages: <a class="sch-content" href="...?rid=XXXXX">
        # Text inside: "2026 2.1 SUN [artist] [title] [OPEN] HH:MM [START] HH:MM ..."
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "rid=" not in href:
                continue
            full_text = a_tag.get_text(" ", strip=True)
            # Extract date: "2026 2.1" or "2026 12.25" pattern
            date_str = self._extract_zepp_date(full_text)
            if not date_str:
                continue
            # Extract title from h3/h4
            title_tag = a_tag.find("h3") or a_tag.find("h4")
            if not title_tag:
                continue
            title = re.sub(r"\s+", " ", title_tag.get_text(strip=True)).strip()
            if not title:
                continue
            # Extract times
            start_time = None
            m = re.search(r"\[START\]\s*(\d{1,2}:\d{2})", full_text)
            if m:
                start_time = _normalise_time(m.group(1))
            if not start_time:
                m = re.search(r"\[OPEN\]\s*(\d{1,2}:\d{2})", full_text)
                if m:
                    start_time = _normalise_time(m.group(1))
            event_url = href
            if not event_url.startswith("http"):
                event_url = f"https://www.zepp.co.jp{href}"
            source_key = href
            uid = compute_event_uid(venue.venue_id, source_key, title, date_str)
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=date_str,
                start_time=start_time,
                end_date=None,
                end_time=None,
                all_day=not bool(start_time),
                status="scheduled",
                url=event_url,
                description=None,
                performers=None,
                capacity=None,
                source_type=venue.source_type,
                source_url=source_url,
                source_event_key=source_key,
            )
            rec.data_hash = compute_data_hash(rec)
            events.append(rec)
        return events

    @staticmethod
    def _extract_zepp_date(text: str) -> str | None:
        """Extract date from Zepp format: '2026 2.1 SUN' or '2026 12.25 WED'."""
        # Pattern: year(4) space month.day
        m = re.search(r"(\d{4})\s+(\d{1,2})\.(\d{1,2})", text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        # Fallback: YYYY/MM/DD or YYYY-MM-DD
        m = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return None


# ---------------------------------------------------------------------------
# Budokan schedule (disabled by default, placeholder)
# ---------------------------------------------------------------------------
@_register("budokan_schedule")
class _BudokanSchedule(_BaseStrategy):
    """Parse Nippon Budokan schedule. Placeholder – returns empty."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        logger.info("budokan_schedule: not yet implemented, returning empty")
        return []


# ---------------------------------------------------------------------------
# Generic fallback (returns empty, for disabled venues)
# ---------------------------------------------------------------------------
@_register("generic")
class _GenericStrategy(_BaseStrategy):
    """Fallback for venues without a dedicated strategy."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        logger.info("generic: no strategy for %s, returning empty", venue.venue_id)
        return []


# ---------------------------------------------------------------------------
# HTML source plugin (dispatcher)
# ---------------------------------------------------------------------------
class HtmlSource(EventSource):
    """Dispatch to per-venue strategy based on config_json."""

    def fetch_events(self, venue: VenueRecord) -> list[EventRecord]:
        config: dict = {}
        if venue.config_json:
            try:
                config = json.loads(venue.config_json)
            except (json.JSONDecodeError, TypeError):
                pass
        strategy_name = config.get("strategy", "generic")
        strategy_cls = _STRATEGIES.get(strategy_name)
        if strategy_cls is None:
            logger.warning("Unknown strategy %s for %s", strategy_name, venue.venue_id)
            return []
        strategy = strategy_cls()
        return strategy.parse(venue, self.session, config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalise_time(t: str | None) -> str | None:
    """Normalise time string to HH:MM."""
    if not t:
        return None
    t = t.strip()
    m = re.match(r"(\d{1,2}):(\d{2})", t)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None
