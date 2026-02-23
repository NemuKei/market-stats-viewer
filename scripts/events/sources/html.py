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
                    venue.venue_id, source_key, title, start_date,
                    start_time=start_time, url=event_url,
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
                    venue.venue_id, source_key, title, current_date,
                    url=event_url,
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
            uid = compute_event_uid(
                venue.venue_id, source_key, title, date_str,
                start_time=start_time, url=event_url,
            )
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
# Saitama Super Arena schedule
# ---------------------------------------------------------------------------
@_register("saitama_arena_schedule")
class _SaitamaArenaSchedule(_BaseStrategy):
    """Parse Saitama Super Arena event schedule page."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        resp = session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        # Structure: <h3><a href="...">Title</a></h3>
        # Date in parent/sibling text: "2026/01/30(金) ～ 2026/02/01(日)"
        for h3 in soup.find_all("h3"):
            a_tag = h3.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if not title:
                continue
            href = a_tag["href"]
            # Look for date in surrounding context
            parent = h3.parent
            if not parent:
                continue
            parent_text = parent.get_text(" ", strip=True)
            # Pattern: YYYY/MM/DD or YYYY年MM月DD日
            m = re.search(r"(\d{4})[/年](\d{1,2})[/月](\d{1,2})", parent_text)
            if not m:
                continue
            start_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            # Check for end date after ～
            end_date = None
            m2 = re.search(r"～\s*(\d{4})[/年](\d{1,2})[/月](\d{1,2})", parent_text)
            if m2:
                end_date = f"{m2.group(1)}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
                if end_date == start_date:
                    end_date = None
            # Extract times: 開場 HH:MM or OPEN HH:MM
            start_time = None
            tm = re.search(r"(?:開演|START|start)\s*(\d{1,2}:\d{2})", parent_text, re.IGNORECASE)
            if tm:
                start_time = _normalise_time(tm.group(1))
            if not start_time:
                tm = re.search(r"(?:開場|OPEN|open)\s*(\d{1,2}:\d{2})", parent_text, re.IGNORECASE)
                if tm:
                    start_time = _normalise_time(tm.group(1))
            event_url = href
            if not event_url.startswith("http"):
                event_url = f"https://www.saitama-arena.co.jp{href}"
            source_key = href
            uid = compute_event_uid(
                venue.venue_id, source_key, title, start_date,
                start_time=start_time, url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=start_date,
                start_time=start_time,
                end_date=end_date,
                end_time=None,
                all_day=not bool(start_time),
                status="scheduled",
                url=event_url,
                description=None,
                performers=None,
                capacity=None,
                source_type=venue.source_type,
                source_url=venue.source_url,
                source_event_key=source_key,
            )
            rec.data_hash = compute_data_hash(rec)
            events.append(rec)
        return events


# ---------------------------------------------------------------------------
# Tokyo Dome calendar
# ---------------------------------------------------------------------------
@_register("tokyo_dome_calendar")
class _TokyoDomeCalendar(_BaseStrategy):
    """Parse Tokyo Dome event schedule (calendar table, all months on single page)."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        resp = session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        # Year-month headers: <p class="c-ttl-set-calender">2026年02月</p>
        current_year = None
        current_month = None
        for elem in soup.find_all(True):
            # Check for year-month header
            if elem.name == "p" and "c-ttl-set-calender" in " ".join(elem.get("class", [])):
                text = elem.get_text(strip=True)
                m = re.search(r"(\d{4})年(\d{1,2})月", text)
                if m:
                    current_year = int(m.group(1))
                    current_month = int(m.group(2))
                continue
            # Calendar rows: <tr class="c-mod-calender__item">
            if elem.name != "tr":
                continue
            classes = " ".join(elem.get("class", []))
            if "c-mod-calender__item" not in classes:
                continue
            if current_year is None or current_month is None:
                continue
            # Day: <span class="c-mod-calender__day">01</span>
            day_span = elem.find("span", class_="c-mod-calender__day")
            if not day_span:
                continue
            day_text = day_span.get_text(strip=True)
            if not day_text.isdigit():
                continue
            day = int(day_text)
            start_date = f"{current_year}-{current_month:02d}-{day:02d}"
            # Detail cell: <td class="c-mod-calender__detail">
            detail_td = elem.find("td", class_="c-mod-calender__detail")
            if not detail_td:
                continue
            # Multiple events possible in one day
            # Look for links or text blocks
            links = detail_td.find_all("a", href=True)
            if links:
                for a_tag in links:
                    title = a_tag.get_text(strip=True)
                    if not title:
                        continue
                    href = a_tag["href"]
                    event_url = href
                    if not event_url.startswith("http"):
                        event_url = f"https://www.tokyo-dome.co.jp{href}"
                    source_key = href
                    # Extract times from surrounding text
                    row_text = detail_td.get_text(" ", strip=True)
                    start_time = self._extract_time(row_text)
                    uid = compute_event_uid(
                        venue.venue_id, source_key, title, start_date,
                        start_time=start_time, url=event_url,
                    )
                    if uid in seen_uids:
                        continue
                    seen_uids.add(uid)
                    rec = EventRecord(
                        event_uid=uid,
                        venue_id=venue.venue_id,
                        title=title,
                        start_date=start_date,
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
                        source_url=venue.source_url,
                        source_event_key=source_key,
                    )
                    rec.data_hash = compute_data_hash(rec)
                    events.append(rec)
            else:
                # No links, extract text as event
                text = detail_td.get_text(strip=True)
                if not text:
                    continue
                title = re.sub(r"\s+", " ", text).strip()
                start_time = self._extract_time(title)
                uid = compute_event_uid(
                    venue.venue_id, None, title, start_date,
                    start_time=start_time,
                )
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                rec = EventRecord(
                    event_uid=uid,
                    venue_id=venue.venue_id,
                    title=title,
                    start_date=start_date,
                    start_time=start_time,
                    end_date=None,
                    end_time=None,
                    all_day=not bool(start_time),
                    status="scheduled",
                    url=None,
                    description=None,
                    performers=None,
                    capacity=None,
                    source_type=venue.source_type,
                    source_url=venue.source_url,
                    source_event_key=None,
                )
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)
        return events

    @staticmethod
    def _extract_time(text: str) -> str | None:
        """Extract start time from text like '開演 17:30' or '開場 15:00／開演 17:30'."""
        m = re.search(r"(?:開演|START)\s*(\d{1,2}:\d{2})", text, re.IGNORECASE)
        if m:
            return _normalise_time(m.group(1))
        m = re.search(r"(?:開場|OPEN)\s*(\d{1,2}:\d{2})", text, re.IGNORECASE)
        if m:
            return _normalise_time(m.group(1))
        return None


# ---------------------------------------------------------------------------
# Vantelin Dome Nagoya (Nagoya Dome) schedule
# ---------------------------------------------------------------------------
@_register("vantelin_dome_schedule")
class _VantelinDomeSchedule(_BaseStrategy):
    """Parse Vantelin Dome Nagoya event schedule table."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        resp = session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        today = date.today()
        base_year = today.year
        # Table rows with date, open, start, end, event columns
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                # First cell: date like "3/1(土)" or "12/25(木)"
                date_text = cells[0].get_text(strip=True)
                dm = re.match(r"(\d{1,2})/(\d{1,2})", date_text)
                if not dm:
                    continue
                month = int(dm.group(1))
                day = int(dm.group(2))
                # Infer year: if month is far behind current month, assume next year
                inferred_year = base_year
                if month < today.month and (today.month - month) > 6:
                    inferred_year = base_year + 1
                start_date = f"{inferred_year}-{month:02d}-{day:02d}"
                # Last cell is usually the event name
                title_cell = cells[-1]
                title = title_cell.get_text(strip=True)
                if not title:
                    continue
                # Extract times from cells (open, start columns)
                start_time = None
                for cell in cells[1:-1]:
                    ct = cell.get_text(strip=True)
                    tm = re.match(r"(\d{1,2}:\d{2})", ct)
                    if tm:
                        start_time = _normalise_time(tm.group(1))
                        # Prefer second time column (start) over first (open)
                # Links
                event_url = None
                source_key = None
                a_tag = title_cell.find("a", href=True)
                if a_tag:
                    href = a_tag["href"]
                    event_url = href
                    if not event_url.startswith("http"):
                        event_url = f"https://www.nagoya-dome.co.jp{href}"
                    source_key = href
                uid = compute_event_uid(
                    venue.venue_id, source_key, title, start_date,
                    start_time=start_time, url=event_url,
                )
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                rec = EventRecord(
                    event_uid=uid,
                    venue_id=venue.venue_id,
                    title=title,
                    start_date=start_date,
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
                    source_url=venue.source_url,
                    source_event_key=source_key,
                )
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)
        return events


# ---------------------------------------------------------------------------
# Kyocera Dome Osaka schedule
# ---------------------------------------------------------------------------
@_register("kyocera_dome_schedule")
class _KyoceraDomeSchedule(_BaseStrategy):
    """Parse Kyocera Dome Osaka event schedule.

    Fetches current month + months_ahead pages via query params:
        /schedule/?monthId=MM&yearId=YYYY
    Each page has nested <section> blocks; wrapper sections (h2 = "イベント詳細"
    or "イベントスケジュール") are skipped. Individual event sections contain
    h2/h3 title + date in YYYY年MM月DD日 format + optional times.
    """

    # Wrapper section titles to skip (these contain all events, not one event)
    _SKIP_TITLES = {"イベント詳細", "イベントスケジュール", "SCHEDULE", "DETAIL"}

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 4))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            month_url = (
                f"{venue.source_url}?monthId={d.month:02d}&yearId={d.year}"
            )
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "kyocera_dome: %s returned %s", month_url, resp.status_code
                    )
                    continue
            except Exception:
                logger.warning("kyocera_dome: failed to fetch %s", month_url)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(
                self._parse_page(venue, soup, month_url, seen_uids)
            )

        if not events:
            logger.warning(
                "kyocera_dome: 0 events from %s (months 0..%d). "
                "HTML structure may have changed.",
                venue.source_url, months_ahead,
            )
        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        for section in soup.find_all("section"):
            heading = section.find(["h2", "h3"])
            if not heading:
                continue
            title = heading.get_text(strip=True)
            if not title:
                continue
            # Skip wrapper sections
            if title in self._SKIP_TITLES:
                continue
            # Must contain a date to be a real event
            section_text = section.get_text(" ", strip=True)
            dates = re.findall(r"(\d{4})年(\d{1,2})月(\d{1,2})日", section_text)
            if not dates:
                continue
            y, m, d = dates[0]
            start_date = f"{y}-{int(m):02d}-{int(d):02d}"
            end_date = None
            if len(dates) > 1:
                y2, m2, d2 = dates[-1]
                ed = f"{y2}-{int(m2):02d}-{int(d2):02d}"
                if ed != start_date:
                    end_date = ed
            # URL: prefer link in heading, else "詳細を見る" link
            event_url = None
            source_key = None
            a_tag = heading.find("a", href=True)
            if not a_tag:
                # Look for "詳細を見る" or any detail link
                for a in section.find_all("a", href=True):
                    link_text = a.get_text(strip=True)
                    if "詳細" in link_text:
                        a_tag = a
                        break
            if a_tag:
                href = a_tag["href"]
                event_url = href
                if not event_url.startswith("http"):
                    event_url = f"https://www.kyoceradome-osaka.jp{href}"
                source_key = href
                # Use heading text for title (not link text from 詳細を見る)
                if heading.find("a"):
                    title = heading.find("a").get_text(strip=True) or title
            # Times: 開始時間：17:00 or 開場時間：15:00
            start_time = None
            tm = re.search(r"(?:開始時間|開演)[：:]\s*(\d{1,2}:\d{2})", section_text)
            if tm:
                start_time = _normalise_time(tm.group(1))
            if not start_time:
                tm = re.search(r"(?:開場時間|開場)[：:]\s*(\d{1,2}:\d{2})", section_text)
                if tm:
                    start_time = _normalise_time(tm.group(1))
            uid = compute_event_uid(
                venue.venue_id, source_key, title, start_date,
                start_time=start_time, url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=start_date,
                start_time=start_time,
                end_date=end_date,
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


# ---------------------------------------------------------------------------
# Belluna Dome schedule
# ---------------------------------------------------------------------------
@_register("belluna_dome_schedule")
class _BellunaDomeSchedule(_BaseStrategy):
    """Parse Belluna Dome (Seibu Lions) event schedule."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        resp = session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        # Look for event entries with date patterns
        # Try multiple selectors: links with schedule paths, date containers
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Skip navigation/non-event links
            if not re.search(r"(?:schedule|game|event|detail)", href):
                continue
            parent = a_tag.parent
            if not parent:
                continue
            context = parent.get_text(" ", strip=True)
            # Look for date: YYYY/MM/DD, YYYY年MM月DD日, or MM/DD with year context
            m = re.search(r"(\d{4})[/年.](\d{1,2})[/月.](\d{1,2})", context)
            if not m:
                # Try MM/DD format with page-level year
                continue
            start_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 2:
                # Try parent text minus date
                title = re.sub(r"\d{4}[/年.]\d{1,2}[/月.]\d{1,2}[日]?\s*[(（].[)）]?\s*", "", context).strip()
            if not title:
                continue
            event_url = href
            if not event_url.startswith("http"):
                event_url = f"https://bellunadome.seibulions.co.jp{href}"
            source_key = href
            # Times
            start_time = None
            tm = re.search(r"(?:開演|試合開始|START|開始)\s*(\d{1,2}:\d{2})", context, re.IGNORECASE)
            if tm:
                start_time = _normalise_time(tm.group(1))
            if not start_time:
                tm = re.search(r"(\d{1,2}:\d{2})\s*(?:開始|試合)", context)
                if tm:
                    start_time = _normalise_time(tm.group(1))
            uid = compute_event_uid(
                venue.venue_id, source_key, title, start_date,
                start_time=start_time, url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=start_date,
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
                source_url=venue.source_url,
                source_event_key=source_key,
            )
            rec.data_hash = compute_data_hash(rec)
            events.append(rec)
        return events


# ---------------------------------------------------------------------------
# Osaka-jo Hall schedule
# ---------------------------------------------------------------------------
@_register("osaka_jo_hall_schedule")
class _OsakaJoHallSchedule(_BaseStrategy):
    """Parse Osaka-jo Hall event schedule.

    Fetches current month + months_ahead pages via ?ym=YYYYMM.
    Each event is <li class="event-detail"> inside <ul class="event-list-wrap">.
    Year-month comes from <h2><span class="event-date">2026年2月</span></h2>.
    """

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 3))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            ym = d.strftime("%Y%m")
            month_url = f"{venue.source_url}?ym={ym}"
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning("osaka_jo_hall: %s returned %s", month_url, resp.status_code)
                    continue
            except Exception:
                logger.warning("osaka_jo_hall: failed to fetch %s", month_url)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(self._parse_page(venue, soup, month_url, d.year, d.month, seen_uids))

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        year: int,
        month: int,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        event_list = soup.find("ul", class_="event-list-wrap")
        if not event_list:
            return events

        for li in event_list.find_all("li", class_="event-detail"):
            # Day number
            day_span = li.find("span", class_="date-num")
            if not day_span:
                continue
            day_text = day_span.get_text(strip=True)
            if not day_text.isdigit():
                continue
            day = int(day_text)
            start_date = f"{year}-{month:02d}-{day:02d}"

            # Title + URL
            title_dt = li.find("dt", class_="event-ttl")
            if not title_dt:
                continue
            a_tag = title_dt.find("a", href=True)
            if a_tag:
                title = a_tag.get_text(strip=True)
                event_url = a_tag["href"]
                source_key = event_url
            else:
                title = title_dt.get_text(strip=True)
                event_url = None
                source_key = None
            if not title:
                continue

            # Start time: look for 開演 in dd.event-schedule
            start_time = None
            for dd in li.find_all("dd", class_="event-schedule"):
                ttl = dd.find("span", class_="d-ttl")
                txt = dd.find("span", class_="d-txt")
                if ttl and txt:
                    label = ttl.get_text(strip=True)
                    if label == "開演":
                        start_time = _normalise_time(txt.get_text(strip=True))
                    elif label == "開場" and not start_time:
                        start_time = _normalise_time(txt.get_text(strip=True))
                # Also check inner-list pattern
                for inner_li in dd.find_all("li"):
                    it = inner_li.find("span", class_="d-ttl")
                    iv = inner_li.find("span", class_="d-txt")
                    if it and iv:
                        il = it.get_text(strip=True)
                        if il == "開演":
                            start_time = _normalise_time(iv.get_text(strip=True))
                        elif il == "開場" and not start_time:
                            start_time = _normalise_time(iv.get_text(strip=True))

            uid = compute_event_uid(
                venue.venue_id, source_key, title, start_date,
                start_time=start_time, url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=start_date,
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


# ---------------------------------------------------------------------------
# Festival Hall schedule
# ---------------------------------------------------------------------------
@_register("festival_hall_schedule")
class _FestivalHallSchedule(_BaseStrategy):
    """Parse Festival Hall event schedule.

    Fetches current month + months_ahead pages via /events/list/YYYY/MM/.
    Each day is <li> inside <ul class="performance-list">.
    Days with events have <div class="_detail"> containing <h2 class="_title">.
    """

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 3))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            month_url = f"https://www.festivalhall.jp/events/list/{d.year}/{d.month:02d}/"
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning("festival_hall: %s returned %s", month_url, resp.status_code)
                    continue
            except Exception:
                logger.warning("festival_hall: failed to fetch %s", month_url)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(self._parse_page(venue, soup, month_url, d.year, d.month, seen_uids))

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        year: int,
        month: int,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        perf_list = soup.find("ul", class_="performance-list")
        if not perf_list:
            return events

        for li in perf_list.find_all("li", recursive=False):
            # Skip days without events (no _detail div)
            detail = li.find("div", class_="_detail")
            if not detail:
                continue

            # Day number from <p class="_date"><span>1</span>（日）</p>
            date_p = li.find("p", class_=re.compile(r"_date"))
            if not date_p:
                continue
            day_span = date_p.find("span")
            if not day_span:
                continue
            day_text = day_span.get_text(strip=True)
            if not day_text.isdigit():
                continue
            day = int(day_text)
            start_date = f"{year}-{month:02d}-{day:02d}"

            # Title + URL from <h2 class="_title"><a href="...">...</a></h2>
            title_h2 = detail.find("h2", class_="_title")
            if not title_h2:
                continue
            a_tag = title_h2.find("a", href=True)
            if a_tag:
                title = a_tag.get_text(strip=True)
                event_url = a_tag["href"]
                source_key = event_url
            else:
                title = title_h2.get_text(strip=True)
                event_url = None
                source_key = None
            if not title:
                continue

            # Start time from <table class="tbl-perform-info"> th=開演 → td
            start_time = None
            info_table = detail.find("table", class_="tbl-perform-info")
            if info_table:
                for tr in info_table.find_all("tr"):
                    th = tr.find("th")
                    td = tr.find("td")
                    if th and td:
                        label = th.get_text(strip=True)
                        if label == "開演":
                            tm = re.search(r"(\d{1,2}:\d{2})", td.get_text(strip=True))
                            if tm:
                                start_time = _normalise_time(tm.group(1))

            uid = compute_event_uid(
                venue.venue_id, source_key, title, start_date,
                start_time=start_time, url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=start_date,
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


# ---------------------------------------------------------------------------
# Ariake Arena schedule
# ---------------------------------------------------------------------------
@_register("ariake_arena_schedule")
class _AriakeArenaSchedule(_BaseStrategy):
    """Parse Ariake Arena event schedule.

    Pages use fixed slug paths: /event/, /event/next/, /event/two/,
    /event/three/, /event/last/ for upcoming months.
    Each event is <li id="detail-..."> inside <ul class="event_detail_list">.
    """

    _SLUGS = ["", "next/", "two/", "three/", "last/"]

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        base = venue.source_url.rstrip("/")

        for slug in self._SLUGS:
            page_url = f"{base}/{slug}" if slug else f"{base}/"
            try:
                resp = session.get(page_url, timeout=30)
                if resp.status_code != 200:
                    continue
            except Exception:
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            # Determine year+month from tab navigation
            year, month = self._detect_year_month(soup, slug)
            if not year:
                continue

            events.extend(self._parse_page(venue, soup, page_url, year, month, seen_uids))

        return events

    @staticmethod
    def _detect_year_month(soup: BeautifulSoup, slug: str) -> tuple[int | None, int | None]:
        """Detect year and month from the active tab or page content."""
        # Look for the active tab's year/month spans
        for li in soup.find_all("li"):
            a_tag = li.find("a", href=True)
            if not a_tag:
                continue
            href = a_tag.get("href", "")
            # Match current slug
            if slug and slug.rstrip("/") in href:
                pass
            elif not slug and href.rstrip("/").endswith("/event"):
                pass
            else:
                continue
            year_span = a_tag.find("span", class_="year")
            month_span = a_tag.find("span", class_="month_number")
            if year_span and month_span:
                try:
                    return int(year_span.get_text(strip=True)), int(month_span.get_text(strip=True))
                except ValueError:
                    pass
        # Fallback: search for active class
        active = soup.find("li", class_="active")
        if active:
            a_tag = active.find("a")
            if a_tag:
                year_span = a_tag.find("span", class_="year")
                month_span = a_tag.find("span", class_="month_number")
                if year_span and month_span:
                    try:
                        return int(year_span.get_text(strip=True)), int(month_span.get_text(strip=True))
                    except ValueError:
                        pass
        return None, None

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        year: int,
        month: int,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        event_list = soup.find("ul", class_="event_detail_list")
        if not event_list:
            return events

        for li in event_list.find_all("li", id=re.compile(r"^detail-")):
            # Date from div.event_day spans: "M.D DOW"
            day_div = li.find("div", class_="event_day")
            if not day_div:
                continue
            spans = day_div.find_all("span")
            if not spans:
                continue
            first_span_text = spans[0].get_text(strip=True)
            dm = re.match(r"(\d{1,2})\.(\d{1,2})", first_span_text)
            if not dm:
                continue
            ev_month = int(dm.group(1))
            ev_day = int(dm.group(2))
            # Year: if event month < page month, it might be next year
            ev_year = year
            if ev_month < month and (month - ev_month) > 6:
                ev_year = year + 1
            start_date = f"{ev_year}-{ev_month:02d}-{ev_day:02d}"

            # End date from second span
            end_date = None
            if len(spans) > 1:
                end_text = spans[1].get_text(strip=True)
                edm = re.match(r"(\d{1,2})\.(\d{1,2})", end_text)
                if edm:
                    ed_m, ed_d = int(edm.group(1)), int(edm.group(2))
                    ed_y = ev_year if ed_m >= ev_month else ev_year + 1
                    ed = f"{ed_y}-{ed_m:02d}-{ed_d:02d}"
                    if ed != start_date:
                        end_date = ed

            # Title
            name_div = li.find("div", class_="event_name")
            if not name_div:
                continue
            title = name_div.get_text(strip=True)
            if not title:
                continue

            # External URL from detail table
            event_url = None
            source_key = li.get("id")
            url_a = li.find("a", class_="other_link")
            if url_a:
                event_url = url_a.get("href")

            # Start time from detail table
            start_time = None
            detail_table = li.find("table", class_="detail_table")
            if detail_table:
                first_td = detail_table.find("td")
                if first_td:
                    td_text = first_td.get_text(" ", strip=True)
                    tm = re.search(r"開演\s*(\d{1,2}:\d{2})", td_text)
                    if tm:
                        start_time = _normalise_time(tm.group(1))
                    if not start_time:
                        tm = re.search(r"開場\s*(\d{1,2}:\d{2})", td_text)
                        if tm:
                            start_time = _normalise_time(tm.group(1))

            uid = compute_event_uid(
                venue.venue_id, source_key, title, start_date,
                start_time=start_time, url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=start_date,
                start_time=start_time,
                end_date=end_date,
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


# ---------------------------------------------------------------------------
# Yoyogi National Gymnasium schedule
# ---------------------------------------------------------------------------
@_register("yoyogi_gymnasium_schedule")
class _YoyogiGymnasiumSchedule(_BaseStrategy):
    """Parse Yoyogi National Gymnasium First Arena event schedule.

    Single page with 2-3 tables (current month, next month, month after next).
    Each table has class="event-calendar" with simple date/title rows.
    """

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        resp = session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for table in soup.find_all("table", class_="event-calendar"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                # Date: "YYYY/MM/DD(曜)"
                date_text = cells[0].get_text(strip=True)
                dm = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_text)
                if not dm:
                    continue
                start_date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

                # Title + URL
                a_tag = cells[1].find("a", href=True)
                if a_tag:
                    title = a_tag.get_text(strip=True)
                    event_url = a_tag["href"]
                    if not event_url.startswith("http"):
                        event_url = f"https://www.jpnsport.go.jp{event_url}"
                    source_key = a_tag["href"]
                else:
                    title = cells[1].get_text(strip=True)
                    event_url = None
                    source_key = None
                if not title:
                    continue

                uid = compute_event_uid(
                    venue.venue_id, source_key, title, start_date,
                    url=event_url,
                )
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                rec = EventRecord(
                    event_uid=uid,
                    venue_id=venue.venue_id,
                    title=title,
                    start_date=start_date,
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
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)
        return events


# ---------------------------------------------------------------------------
# Tokyo Garden Theater schedule
# ---------------------------------------------------------------------------
@_register("garden_theater_schedule")
class _GardenTheaterSchedule(_BaseStrategy):
    """Parse Tokyo Garden Theater event schedule.

    Month pages via ?date=YYYY-MM query param.
    Each event is <li class="event_all"> inside <ul class="list_schedule">.
    """

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 3))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            month_url = f"{venue.source_url}?date={d.year}-{d.month:02d}"
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    continue
            except Exception:
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(self._parse_page(venue, soup, month_url, d.year, seen_uids))

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        year: int,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        schedule_list = soup.find("ul", class_="list_schedule")
        if not schedule_list:
            return events

        for li in schedule_list.find_all("li", class_="event_all"):
            a_tag = li.find("a", href=True)
            if not a_tag:
                continue

            # Date from div.ymd blocks
            ymd_divs = li.find_all("div", class_="ymd")
            if not ymd_divs:
                continue
            first_ymd = ymd_divs[0]
            m_div = first_ymd.find("div", class_="m")
            d_div = first_ymd.find("div", class_="d")
            if not m_div or not d_div:
                continue
            try:
                ev_month = int(m_div.get_text(strip=True))
                ev_day = int(d_div.get_text(strip=True))
            except ValueError:
                continue
            start_date = f"{year}-{ev_month:02d}-{ev_day:02d}"

            # End date from last ymd block
            end_date = None
            if len(ymd_divs) > 1:
                last_ymd = ymd_divs[-1]
                em = last_ymd.find("div", class_="m")
                ed = last_ymd.find("div", class_="d")
                if em and ed:
                    try:
                        end_m, end_d = int(em.get_text(strip=True)), int(ed.get_text(strip=True))
                        end_y = year if end_m >= ev_month else year + 1
                        ed_str = f"{end_y}-{end_m:02d}-{end_d:02d}"
                        if ed_str != start_date:
                            end_date = ed_str
                    except ValueError:
                        pass

            # Title: div.title text, performer: div.player text
            title_div = li.find("div", class_="title")
            player_div = li.find("div", class_="player")
            title = title_div.get_text(strip=True) if title_div else ""
            performer = player_div.get_text(strip=True) if player_div else ""
            if not title and not performer:
                continue
            display_title = f"{performer} {title}".strip() if performer and title else (title or performer)

            event_url = a_tag["href"]
            source_key = event_url

            uid = compute_event_uid(
                venue.venue_id, source_key, display_title, start_date,
                url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=display_title,
                start_date=start_date,
                start_time=None,
                end_date=end_date,
                end_time=None,
                all_day=True,
                status="scheduled",
                url=event_url,
                description=None,
                performers=performer or None,
                capacity=None,
                source_type=venue.source_type,
                source_url=source_url,
                source_event_key=source_key,
            )
            rec.data_hash = compute_data_hash(rec)
            events.append(rec)
        return events


# ---------------------------------------------------------------------------
# TOKYO DOME CITY HALL (Kanadevia Hall) schedule
# ---------------------------------------------------------------------------
@_register("tdc_hall_schedule")
class _TdcHallSchedule(_BaseStrategy):
    """Parse TOKYO DOME CITY HALL event schedule.

    Single page at /tdc-hall/event/ contains two months in tab sections.
    Structure is similar to Tokyo Dome calendar but with different detail layout.
    """

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        resp = session.get(venue.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        current_year = None
        current_month = None

        for elem in soup.find_all(True):
            # Year-month header: <p class="c-ttl-set-calender">2026年02月</p>
            if elem.name == "p" and "c-ttl-set-calender" in " ".join(elem.get("class", [])):
                text = elem.get_text(strip=True)
                m = re.search(r"(\d{4})年(\d{1,2})月", text)
                if m:
                    current_year = int(m.group(1))
                    current_month = int(m.group(2))
                continue

            if elem.name != "tr":
                continue
            classes = " ".join(elem.get("class", []))
            if "c-mod-calender__item" not in classes:
                continue
            if current_year is None or current_month is None:
                continue

            # Day
            day_span = elem.find("span", class_="c-mod-calender__day")
            if not day_span:
                continue
            day_text = day_span.get_text(strip=True)
            if not day_text.isdigit():
                continue
            day = int(day_text)
            start_date = f"{current_year}-{current_month:02d}-{day:02d}"

            # Detail cell
            detail_td = elem.find("td", class_="c-mod-calender__detail")
            if not detail_td:
                continue
            detail_in = detail_td.find("div", class_="c-mod-calender__detail-in")
            if not detail_in:
                continue

            # Multiple events possible: each pair of detail-col divs
            links_p = detail_in.find_all("p", class_="c-mod-calender__links")
            captions = detail_in.find_all("p", class_="c-txt-caption-01")

            for link_p in links_p:
                a_tag = link_p.find("a", href=True)
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                if not title:
                    continue
                event_url = a_tag["href"]
                source_key = event_url

                # Try to extract time from adjacent caption
                start_time = None
                for cap in captions:
                    cap_text = cap.get_text(" ", strip=True)
                    tm = re.search(r"開演\s*(\d{1,2}:\d{2})", cap_text)
                    if tm:
                        start_time = _normalise_time(tm.group(1))
                        break
                    tm = re.search(r"開場\s*(\d{1,2}:\d{2})", cap_text)
                    if tm:
                        start_time = _normalise_time(tm.group(1))
                        break

                uid = compute_event_uid(
                    venue.venue_id, source_key, title, start_date,
                    start_time=start_time, url=event_url,
                )
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                rec = EventRecord(
                    event_uid=uid,
                    venue_id=venue.venue_id,
                    title=title,
                    start_date=start_date,
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
                    source_url=venue.source_url,
                    source_event_key=source_key,
                )
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)
        return events


# ---------------------------------------------------------------------------
# Toyosu PIT schedule
# ---------------------------------------------------------------------------
@_register("toyosu_pit_schedule")
class _ToyosuPitSchedule(_BaseStrategy):
    """Parse Toyosu PIT event schedule.

    Monthly pages at /schedule-list/YYYY/MM/index.html.
    Each event is <a class="schedule_list"> inside <ul class="schedule_block">.
    """

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 3))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            month_url = f"https://toyosu.pia-pit.jp/schedule-list/{d.year}/{d.month:02d}/index.html"
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    continue
            except Exception:
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(self._parse_page(venue, soup, month_url, d.year, seen_uids))

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        year: int,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        schedule_block = soup.find("ul", class_="schedule_block")
        if not schedule_block:
            return events

        for li in schedule_block.find_all("li", recursive=False):
            a_tag = li.find("a", class_="schedule_list")
            if not a_tag:
                continue

            # Date: div.schedule_list__date > p = "MM.DD"
            date_div = a_tag.find("div", class_="schedule_list__date")
            if not date_div:
                continue
            date_p = date_div.find("p")
            if not date_p:
                continue
            date_text = date_p.get_text(strip=True)
            dm = re.match(r"(\d{2})\.(\d{2})", date_text)
            if not dm:
                continue
            ev_month = int(dm.group(1))
            ev_day = int(dm.group(2))
            start_date = f"{year}-{ev_month:02d}-{ev_day:02d}"

            # Title: h3 inside div.title
            title_div = a_tag.find("div", class_="title")
            if not title_div:
                continue
            h3 = title_div.find("h3")
            subtitle_p = title_div.find("p")
            artist = h3.get_text(strip=True) if h3 else ""
            subtitle = subtitle_p.get_text(strip=True) if subtitle_p else ""
            title = f"{artist} {subtitle}".strip() if artist and subtitle else (artist or subtitle)
            if not title:
                continue

            # URL
            href = a_tag.get("href", "")
            if href:
                # Resolve relative URL
                if href.startswith("../"):
                    event_url = f"https://toyosu.pia-pit.jp/{href.lstrip('./')}"
                elif not href.startswith("http"):
                    event_url = f"https://toyosu.pia-pit.jp{href}"
                else:
                    event_url = href
                source_key = href
            else:
                event_url = None
                source_key = None

            uid = compute_event_uid(
                venue.venue_id, source_key, title, start_date,
                url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=title,
                start_date=start_date,
                start_time=None,
                end_date=None,
                end_time=None,
                all_day=True,
                status="scheduled",
                url=event_url,
                description=None,
                performers=artist or None,
                capacity=None,
                source_type=venue.source_type,
                source_url=source_url,
                source_event_key=source_key,
            )
            rec.data_hash = compute_data_hash(rec)
            events.append(rec)
        return events


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
