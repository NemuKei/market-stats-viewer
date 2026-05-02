"""HTML-based event source plugin with per-venue strategies."""

from __future__ import annotations

import io
import json
import logging
import re
import unicodedata
from datetime import date, timedelta
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from pypdf import PdfReader

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


def _source_key_with_schedule(
    source_key: str | None, start_date: str, start_time: str | None
) -> str | None:
    key = str(source_key or "").strip()
    if not key:
        return None
    if start_time:
        return f"{key}#d={start_date}#t={start_time}"
    return f"{key}#d={start_date}"


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
                    venue.venue_id,
                    source_key,
                    title,
                    start_date,
                    start_time=start_time,
                    url=event_url,
                )
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)
        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []

        for li in soup.select("li.eventInr"):
            link = li.find("a", href=True)
            if not link:
                continue

            right_cont = li.select_one(".rightCont")
            context = " ".join(
                (
                    right_cont.get_text(" ", strip=True)
                    if right_cont
                    else li.get_text(" ", strip=True)
                ).split()
            )
            if not context:
                continue

            date_text = ""
            date_node = li.find(class_=re.compile("date"))
            if date_node:
                date_text = " ".join(date_node.get_text(" ", strip=True).split())
            if not date_text:
                m_date = re.search(
                    r"\d{4}\.\d{1,2}\.\d{1,2}(?:\([^)]*\))?(?:\s*[〜~\-－]\s*\d{4}\.\d{1,2}\.\d{1,2}(?:\([^)]*\))?)?",
                    context,
                )
                if m_date:
                    date_text = m_date.group(0)
            if not date_text:
                continue

            date_parts = re.findall(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_text)
            if not date_parts:
                continue
            y, m, d = date_parts[0]
            start_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            end_date = None
            if len(date_parts) > 1:
                y2, m2, d2 = date_parts[-1]
                ed = f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
                if ed != start_date:
                    end_date = ed

            text_wo_date = context.replace(date_text, " ")
            text_wo_date = re.sub(r"\s*対象\s*.*$", "", text_wo_date)
            text_wo_date = re.sub(r"\s+", " ", text_wo_date).strip()
            if not text_wo_date:
                continue

            start_time = None
            tm = re.search(
                r"(?:開演|開始|OPEN|START)\s*[:：]?\s*(\d{1,2}:\d{2})",
                context,
                re.IGNORECASE,
            )
            if tm:
                start_time = _normalise_time(tm.group(1))

            event_url = link["href"]
            if not event_url.startswith("http"):
                event_url = f"https://www.m-messe.co.jp{event_url}"
            source_key = link["href"]

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                text_wo_date,
                start_date,
                start_time=start_time,
                url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)

            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=text_wo_date,
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
                    current_date = (
                        f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    )
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
                    venue.venue_id,
                    source_key,
                    title,
                    current_date,
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
        months_ahead = int(config.get("months_ahead", 6))
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        today = date.today()
        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            url = venue.source_url
            if not url.endswith("/"):
                url += "/"
            month_url = f"{url}?_y={d.year}&_m={d.month}"
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
            events.extend(self._parse_page(venue, soup, month_url, seen_uids))
        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
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
                venue.venue_id,
                source_key,
                title,
                date_str,
                start_time=start_time,
                url=event_url,
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

    _CATEGORY_LABEL_BY_SLUG = {
        "concert-show": "コンサート・ショー",
        "sports": "スポーツ",
        "meeting-ceremony": "集会・式典・セミナー",
        "shopping-exhibition": "物販・展示会",
        "other": "その他",
    }

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        allowed_categories = {
            str(v).strip()
            for v in config.get("allowed_categories", [])
            if str(v).strip()
        }
        allowed_place_keywords = [
            str(v).strip()
            for v in config.get("allowed_place_keywords", [])
            if str(v).strip()
        ]

        month_urls = self._collect_month_urls(venue, session)
        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for month_url in month_urls:
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "saitama_arena: %s returned %s", month_url, resp.status_code
                    )
                    continue
            except Exception:
                logger.warning("saitama_arena: failed to fetch %s", month_url)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(
                self._parse_page(
                    venue=venue,
                    soup=soup,
                    source_url=month_url,
                    seen_uids=seen_uids,
                    allowed_categories=allowed_categories,
                    allowed_place_keywords=allowed_place_keywords,
                )
            )
        return events

    def _collect_month_urls(self, venue: VenueRecord, session) -> list[str]:
        try:
            resp = session.get(venue.source_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "saitama_arena: %s returned %s", venue.source_url, resp.status_code
                )
                return [venue.source_url]
        except Exception:
            logger.warning("saitama_arena: failed to fetch %s", venue.source_url)
            return [venue.source_url]

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        urls: list[str] = [venue.source_url]
        seen: set[str] = set()
        for tag in soup.select("a[href], option[value]"):
            href = ""
            if tag.name == "a":
                href = str(tag.get("href", "")).strip()
            else:
                href = str(tag.get("value", "")).strip()
            if not href:
                continue
            if not re.search(r"/schedule/\d{4}/\d{2}/$", href):
                continue
            if href.startswith("http"):
                full = href
            elif href.startswith("/"):
                full = f"https://www.saitama-arena.co.jp{href}"
            else:
                full = f"https://www.saitama-arena.co.jp/{href}"
            if full in seen:
                continue
            seen.add(full)
            urls.append(full)
        return urls

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
        allowed_categories: set[str],
        allowed_place_keywords: list[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []

        for li in soup.select('li[id^="event"]'):
            class_names = [str(v).strip() for v in li.get("class", []) if str(v).strip()]
            category_slug = next(
                (
                    slug
                    for slug in self._CATEGORY_LABEL_BY_SLUG
                    if slug in class_names
                ),
                "",
            )
            if allowed_categories and category_slug not in allowed_categories:
                continue

            title_tag = li.select_one("h3 a")
            if title_tag is None:
                continue
            title = " ".join(title_tag.get_text(" ", strip=True).split())
            if not title:
                continue

            date_node = li.select_one("dl.date dd")
            date_text = (
                " ".join(date_node.get_text(" ", strip=True).split())
                if date_node is not None
                else ""
            )
            date_parts = re.findall(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_text)
            if not date_parts:
                continue
            y, m, d = date_parts[0]
            start_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            end_date = None
            if len(date_parts) > 1:
                y2, m2, d2 = date_parts[-1]
                ed = f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
                if ed != start_date:
                    end_date = ed

            place_type = ""
            for dl_tag in li.select("div.place dl"):
                dt_tag = dl_tag.find("dt")
                dd_tag = dl_tag.find("dd")
                if dt_tag is None or dd_tag is None:
                    continue
                dt_text = " ".join(dt_tag.get_text(" ", strip=True).split())
                if "会場タイプ" in dt_text:
                    place_type = " ".join(dd_tag.get_text(" ", strip=True).split())
                    break
            if allowed_place_keywords and not any(
                keyword in place_type for keyword in allowed_place_keywords
            ):
                continue

            content_text = " ".join(li.get_text(" ", strip=True).split())
            start_time = None
            for pattern in [
                r"(?:開演|開始|START)\s*[:：]?\s*(\d{1,2}:\d{2})",
                r"(?:開場|OPEN)\s*[:：]?\s*(\d{1,2}:\d{2})",
            ]:
                tm = re.search(pattern, content_text, re.IGNORECASE)
                if tm:
                    start_time = _normalise_time(tm.group(1))
                    if start_time:
                        break

            href = str(title_tag.get("href", "")).strip()
            if not href:
                continue
            event_url = href
            if not event_url.startswith("http"):
                if event_url.startswith("/"):
                    event_url = f"https://www.saitama-arena.co.jp{href}"
                else:
                    event_url = f"https://www.saitama-arena.co.jp/{href}"
            source_key = href

            details: list[str] = []
            category_label = self._CATEGORY_LABEL_BY_SLUG.get(category_slug, "")
            if category_label:
                details.append(f"カテゴリ:{category_label}")
            if place_type:
                details.append(f"会場タイプ:{place_type}")
            description = " / ".join(details) if details else None

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
                start_time=start_time,
                end_date=end_date,
                end_time=None,
                all_day=not bool(start_time),
                status="scheduled",
                url=event_url,
                description=description,
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
# Tokyo Dome calendar
# ---------------------------------------------------------------------------
@_register("tokyo_dome_calendar")
class _TokyoDomeCalendar(_BaseStrategy):
    """Parse Tokyo Dome event schedule (calendar table, all months on single page)."""

    _NOISE_TITLE_TERMS = (
        "お問い合わせ",
        "お問合せ",
        "お問合わせ",
        "よくあるご質問",
        "faq",
        "help",
        "チケットぴあ",
        "ticket board",
        "チケプラ",
        "sogo tokyo",
        "disk garage",
    )
    _NOISE_URL_TERMS = (
        "/help",
        "/faq",
        "/contact",
        "faq.",
        "help.",
        "support.",
        "sogotokyo.com",
        "pia.jp/help",
        "tixplus.jp",
        "tickebo.jp",
        "diskgarage.com",
        "msgs.jp/webapp/form",
    )

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
            if elem.name == "p" and "c-ttl-set-calender" in " ".join(
                elem.get("class", [])
            ):
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
                    if self._is_noise_link(title, href):
                        continue
                    event_url = href
                    if not event_url.startswith("http"):
                        event_url = f"https://www.tokyo-dome.co.jp{href}"
                    event_url = self._prefer_venue_official_url(event_url, venue.source_url)
                    # Extract times from surrounding text
                    row_text = detail_td.get_text(" ", strip=True)
                    start_time = self._extract_time(row_text)
                    source_key = _source_key_with_schedule(
                        href, start_date, start_time
                    )
                    uid = compute_event_uid(
                        venue.venue_id,
                        source_key,
                        title,
                        start_date,
                        start_time=start_time,
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
                    venue.venue_id,
                    None,
                    title,
                    start_date,
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
                    url=venue.source_url,
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
    def _prefer_venue_official_url(event_url: str, venue_source_url: str) -> str:
        url = str(event_url or "").strip()
        venue_url = str(venue_source_url or "").strip()
        if not url:
            return venue_url
        if not venue_url:
            return url
        parsed = urlparse(url)
        venue_parsed = urlparse(venue_url)
        event_host = parsed.netloc.lower()
        venue_host = venue_parsed.netloc.lower()
        if not event_host or not venue_host:
            return url
        if event_host != venue_host:
            return venue_url
        return url

    def _is_noise_link(self, title: str, href: str) -> bool:
        title_l = " ".join(title.split()).strip().lower()
        href_l = str(href or "").strip().lower()
        if not title_l:
            return True
        if any(term in title_l for term in self._NOISE_TITLE_TERMS):
            return True
        if any(term in href_l for term in self._NOISE_URL_TERMS):
            return True
        return False

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
                    source_key = _source_key_with_schedule(
                        href, start_date, start_time
                    )
                uid = compute_event_uid(
                    venue.venue_id,
                    source_key,
                    title,
                    start_date,
                    start_time=start_time,
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
            month_url = f"{venue.source_url}?monthId={d.month:02d}&yearId={d.year}"
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
            events.extend(self._parse_page(venue, soup, month_url, seen_uids))

        if not events:
            logger.warning(
                "kyocera_dome: 0 events from %s (months 0..%d). "
                "HTML structure may have changed.",
                venue.source_url,
                months_ahead,
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
            raw_source_key = None
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
                raw_source_key = href
                # Use heading text for title (not link text from 詳細を見る)
                if heading.find("a"):
                    title = heading.find("a").get_text(strip=True) or title
            performer = None
            artist_tag = section.select_one("div.top > h1") or section.find("h1")
            if artist_tag:
                candidate = " ".join(artist_tag.get_text(" ", strip=True).split())
                if candidate and candidate not in self._SKIP_TITLES:
                    performer = candidate
            # Times: 開始時間：17:00 or 開場時間：15:00
            start_time = None
            tm = re.search(r"(?:開始時間|開演)[：:]\s*(\d{1,2}:\d{2})", section_text)
            if tm:
                start_time = _normalise_time(tm.group(1))
            if not start_time:
                tm = re.search(
                    r"(?:開場時間|開場)[：:]\s*(\d{1,2}:\d{2})", section_text
                )
                if tm:
                    start_time = _normalise_time(tm.group(1))
            source_key = _source_key_with_schedule(
                raw_source_key, start_date, start_time
            )
            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
                start_time=start_time,
                end_date=end_date,
                end_time=None,
                all_day=not bool(start_time),
                status="scheduled",
                url=event_url,
                description=None,
                performers=performer,
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
        months_ahead = int(config.get("months_ahead", 8))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            month_date = today.replace(day=1) + timedelta(days=32 * offset)
            month_date = month_date.replace(day=1)
            ym = month_date.strftime("%Y%m")
            month_url = (
                f"https://bellunadome.seibulions.co.jp/schedule/{ym}/all/index.html"
            )

            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "belluna_dome: %s returned %s", month_url, resp.status_code
                    )
                    continue
            except Exception:
                logger.warning("belluna_dome: failed to fetch %s", month_url)
                continue

            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            for item in soup.select("div.event-item"):
                context = " ".join(item.get_text(" ", strip=True).split())
                if not context:
                    continue

                m = re.search(
                    r"^[A-Z]{3}\s+(\d{2})\.(\d{2})\s+(\d{4})\s+(.+)$", context
                )
                if not m:
                    continue

                month = int(m.group(1))
                day = int(m.group(2))
                year = int(m.group(3))
                body = m.group(4).strip()
                if not body:
                    continue
                if body in {"調整中", "メンテナンス", "貸切", "貸し切り"}:
                    continue

                start_date = f"{year:04d}-{month:02d}-{day:02d}"

                tm = re.search(r"[\(（]\s*(\d{1,2}:\d{2})\s*[\)）]", body)
                start_time = None
                if tm:
                    start_time = _normalise_time(tm.group(1))
                    body = re.sub(r"[\(（]\s*\d{1,2}:\d{2}\s*[\)）]", "", body).strip()

                start_time_inline = re.search(
                    r"(?:開演|試合開始|START|開始)\s*(\d{1,2}:\d{2})",
                    body,
                    re.IGNORECASE,
                )
                if start_time is None and start_time_inline:
                    start_time = _normalise_time(start_time_inline.group(1))

                title = re.sub(r"\s+", " ", body).strip()
                if not title:
                    continue

                label_node = item.select_one(".news-label")
                label_text = ""
                if label_node is not None:
                    label_text = " ".join(label_node.get_text(" ", strip=True).split())
                description = f"カテゴリ:{label_text}" if label_text else None

                detail_link = item.find("a", href=True)
                event_url = month_url
                source_key = f"{ym}:{start_date}:{title}"
                if detail_link:
                    href = detail_link["href"]
                    if href:
                        source_key = _source_key_with_schedule(
                            href, start_date, start_time
                        )
                        event_url = href
                        if not event_url.startswith("http"):
                            event_url = f"https://bellunadome.seibulions.co.jp{href}"

                uid = compute_event_uid(
                    venue.venue_id,
                    source_key,
                    title,
                    start_date,
                    start_time=start_time,
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
                    start_time=start_time,
                    end_date=None,
                    end_time=None,
                    all_day=not bool(start_time),
                    status="scheduled",
                    url=event_url,
                    description=description,
                    performers=None,
                    capacity=None,
                    source_type=venue.source_type,
                    source_url=month_url,
                    source_event_key=source_key,
                )
                rec.data_hash = compute_data_hash(rec)
                events.append(rec)

        return events


# ---------------------------------------------------------------------------
# Makuhari Messe schedule
# ---------------------------------------------------------------------------
@_register("makuhari_messe_schedule")
class _MakuhariMesseSchedule(_BaseStrategy):
    """Parse Makuhari Messe event calendar pages."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 6))
        max_pages = int(config.get("max_pages", 8))
        allowed_categories = {
            str(v).strip()
            for v in config.get("allowed_categories", [])
            if str(v).strip()
        }
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            month_date = today.replace(day=1) + timedelta(days=32 * offset)
            month_date = month_date.replace(day=1)
            ym = month_date.strftime("%Y%m")

            for page in range(1, max_pages + 1):
                month_url = f"{venue.source_url}?month={ym}&page={page}"
                try:
                    resp = session.get(month_url, timeout=30)
                    if resp.status_code != 200:
                        logger.warning(
                            "makuhari_messe: %s returned %s",
                            month_url,
                            resp.status_code,
                        )
                        break
                except Exception:
                    logger.warning("makuhari_messe: failed to fetch %s", month_url)
                    break

                resp.encoding = resp.apparent_encoding or "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")
                page_events = self._parse_page(
                    venue=venue,
                    soup=soup,
                    source_url=month_url,
                    seen_uids=seen_uids,
                    allowed_categories=allowed_categories,
                )
                if not page_events:
                    break
                events.extend(page_events)

                pagination = soup.find("div", class_=re.compile("pager|pagination"))
                if pagination is None or str(page + 1) not in pagination.get_text(
                    " ", strip=True
                ):
                    break

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
        allowed_categories: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []

        for li in soup.select("li.eventInr"):
            link = li.find("a", href=True)
            if not link:
                continue

            category_label = ""
            category_node = li.select_one(".category, .cate")
            if category_node is not None:
                category_label = " ".join(category_node.get_text(" ", strip=True).split())
            if allowed_categories and category_label not in allowed_categories:
                continue

            right_cont = li.select_one(".rightCont")
            context = " ".join(
                (
                    right_cont.get_text(" ", strip=True)
                    if right_cont
                    else li.get_text(" ", strip=True)
                ).split()
            )
            if not context:
                continue

            date_text = ""
            date_node = li.find(class_=re.compile("date"))
            if date_node:
                date_text = " ".join(date_node.get_text(" ", strip=True).split())
            if not date_text:
                m_date = re.search(
                    r"\d{4}\.\d{1,2}\.\d{1,2}(?:\([^)]*\))?(?:\s*[〜~\-－]\s*\d{4}\.\d{1,2}\.\d{1,2}(?:\([^)]*\))?)?",
                    context,
                )
                if m_date:
                    date_text = m_date.group(0)
            if not date_text:
                continue

            date_parts = re.findall(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_text)
            if not date_parts:
                continue
            y, m, d = date_parts[0]
            start_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            end_date = None
            if len(date_parts) > 1:
                y2, m2, d2 = date_parts[-1]
                ed = f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
                if ed != start_date:
                    end_date = ed

            text_wo_date = context.replace(date_text, " ")
            text_wo_date = re.sub(r"\s*対象\s*.*$", "", text_wo_date)
            text_wo_date = re.sub(r"\s+", " ", text_wo_date).strip()
            if category_label and text_wo_date.startswith(category_label):
                text_wo_date = text_wo_date[len(category_label) :].strip()
            text_wo_date = re.sub(r"^(イベント|音楽イベント)\s*", "", text_wo_date)
            if not text_wo_date:
                continue

            start_time = None
            tm = re.search(
                r"(?:開演|開始|OPEN|START)\s*[:：]?\s*(\d{1,2}:\d{2})",
                context,
                re.IGNORECASE,
            )
            if tm:
                start_time = _normalise_time(tm.group(1))

            event_url = link["href"]
            if not event_url.startswith("http"):
                event_url = f"https://www.m-messe.co.jp{event_url}"
            source_key = link["href"]

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                text_wo_date,
                start_date,
                start_time=start_time,
                url=event_url,
            )
            if uid in seen_uids:
                continue
            seen_uids.add(uid)

            rec = EventRecord(
                event_uid=uid,
                venue_id=venue.venue_id,
                title=text_wo_date,
                start_date=start_date,
                start_time=start_time,
                end_date=end_date,
                end_time=None,
                all_day=not bool(start_time),
                status="scheduled",
                url=event_url,
                description=f"カテゴリ:{category_label}" if category_label else None,
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
# K-Arena Yokohama schedule
# ---------------------------------------------------------------------------
@_register("k_arena_yokohama_schedule")
class _KArenaYokohamaSchedule(_BaseStrategy):
    """Parse K-Arena Yokohama schedule pages."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        max_pages = int(config.get("max_pages", 4))
        base = venue.source_url.rstrip("/") + "/"
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for page in range(1, max_pages + 1):
            page_url = base if page == 1 else f"{base}page/{page}/"
            try:
                resp = session.get(page_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "k_arena_yokohama: %s returned %s", page_url, resp.status_code
                    )
                    break
            except Exception:
                logger.warning("k_arena_yokohama: failed to fetch %s", page_url)
                break

            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            before_count = len(seen_uids)
            page_events = self._parse_page(venue, soup, page_url, seen_uids)
            if not page_events:
                break
            events.extend(page_events)
            if len(seen_uids) == before_count:
                break

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []

        for li in soup.select("li.schedule-list-item"):
            date_node = li.select_one("p.schedule-list-item__date")
            if not date_node:
                continue
            date_text = " ".join(date_node.get_text(" ", strip=True).split())
            dm = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_text)
            if not dm:
                continue
            start_date = (
                f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
            )

            link_tag = li.find("a", href=True)
            content_text = " ".join(li.get_text(" ", strip=True).split())
            if link_tag is not None:
                content_text = " ".join(link_tag.get_text(" ", strip=True).split())

            title = re.sub(
                r"^\d{4}\.\d{1,2}\.\d{1,2}\.[A-Za-z]{3}\.\s*", "", content_text
            )
            title = re.sub(r"^取扱公演\s*", "", title)
            title = re.sub(
                r"\s+(?:OPEN|開場)\s*\d{1,2}:\d{2}.*$", "", title, flags=re.IGNORECASE
            )
            title = re.sub(
                r"\s+(?:START|開演|開始)\s*\d{1,2}:\d{2}.*$",
                "",
                title,
                flags=re.IGNORECASE,
            )
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue

            start_time = None
            for pattern in [
                r"(?:START|開演|開始)\s*(\d{1,2}:\d{2})",
                r"(?:OPEN|開場)\s*(\d{1,2}:\d{2})",
            ]:
                tm = re.search(pattern, content_text, re.IGNORECASE)
                if tm:
                    start_time = _normalise_time(tm.group(1))
                    if start_time:
                        break

            event_url = source_url
            source_key = f"{start_date}:{title}"
            if link_tag is not None:
                href = link_tag["href"]
                if href:
                    source_key = href
                    event_url = href
                    if not event_url.startswith("http"):
                        event_url = f"https://k-arena.com{href}"

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
# Sapporo Dome schedule
# ---------------------------------------------------------------------------
@_register("sapporo_dome_schedule")
class _SapporoDomeSchedule(_BaseStrategy):
    """Parse Sapporo Dome (Daiwa House PREMIST DOME) schedule page."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        page_url = venue.source_url
        try:
            resp = session.get(page_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "sapporo_dome: %s returned %s", page_url, resp.status_code
                )
                return []
        except Exception:
            logger.warning("sapporo_dome: failed to fetch %s", page_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for item in soup.select("li.un_pickupEvent_item"):
            detail = item.select_one("div.un_pickupEvent_detailInner")
            detail_text = " ".join(
                (
                    detail.get_text(" ", strip=True)
                    if detail
                    else item.get_text(" ", strip=True)
                ).split()
            )
            if not detail_text:
                continue

            dm = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", detail_text)
            if not dm:
                continue
            start_date = (
                f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
            )

            title_node = item.select_one(".un_pickupEvent_ttl")
            if title_node is not None:
                title = " ".join(title_node.get_text(" ", strip=True).split())
            else:
                title = detail_text
                title = re.sub(r"^.*?(?=\d{4}/\d{1,2}/\d{1,2})", "", title)
                title = re.sub(r"^\d{4}/\d{1,2}/\d{1,2}\([^)]*\)\s*", "", title)
                title = re.sub(
                    r"\s*(開場時刻|開始時刻|終了時刻|駐車場|お問い合わせ)[:：].*$",
                    "",
                    title,
                )
                title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue

            start_time = None
            for pattern in [
                r"開始時刻\s*(\d{1,2}:\d{2})",
                r"開演\s*(\d{1,2}:\d{2})",
                r"開場\s*(\d{1,2}:\d{2})",
            ]:
                tm = re.search(pattern, detail_text)
                if tm:
                    start_time = _normalise_time(tm.group(1))
                    if start_time:
                        break

            event_url = page_url
            source_key = f"{start_date}:{title}"
            link_tag = item.find("a", href=True)
            if link_tag is not None:
                href = link_tag["href"]
                if href:
                    source_key = href
                    event_url = href
                    if not event_url.startswith("http"):
                        event_url = f"https://www.sapporo-dome.co.jp{href}"

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
                source_url=page_url,
                source_event_key=source_key,
            )
            rec.data_hash = compute_data_hash(rec)
            events.append(rec)

        return events


# ---------------------------------------------------------------------------
# Fukuoka PayPay Dome schedule
# ---------------------------------------------------------------------------
@_register("fukuoka_paypay_dome_schedule")
class _FukuokaPayPayDomeSchedule(_BaseStrategy):
    """Parse Fukuoka PayPay Dome yearly event schedule pages."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        years_ahead = int(config.get("years_ahead", 1))
        base_url = str(
            config.get(
                "yearly_base_url",
                "https://www.softbankhawks.co.jp/stadium/event_schedule/{year}/",
            )
        )
        current_year = date.today().year

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for year in range(current_year, current_year + years_ahead + 1):
            page_url = base_url.format(year=year)
            try:
                resp = session.get(page_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "fukuoka_paypay_dome: %s returned %s",
                        page_url,
                        resp.status_code,
                    )
                    continue
            except Exception:
                logger.warning("fukuoka_paypay_dome: failed to fetch %s", page_url)
                continue

            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(self._parse_page(venue, soup, page_url, seen_uids))

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        schedule_panels = soup.find_all("div", class_=re.compile("temp_tabPanel"))
        if not schedule_panels:
            return events

        for panel in schedule_panels:
            for dt_tag in panel.find_all("dt"):
                date_text = " ".join(dt_tag.get_text(" ", strip=True).split())
                dm = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_text)
                if not dm:
                    continue
                start_date = f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

                dd_tag = dt_tag.find_next_sibling("dd")
                if dd_tag is None:
                    continue
                dd_text = " ".join(dd_tag.get_text(" ", strip=True).split())
                if not dd_text or "決定次第掲載" in dd_text:
                    continue

                title = self._extract_title(dd_text)
                if not title:
                    continue

                start_time = None
                time_patterns = [
                    r"(?:開演|試合開始|開始)\s*[:：]?\s*(\d{1,2}:\d{2})",
                    r"(?:開場)\s*[:：]?\s*(\d{1,2}:\d{2})",
                    r"(?:開催時間)\s*(\d{1,2}:\d{2})",
                ]
                for pattern in time_patterns:
                    tm = re.search(pattern, dd_text, re.IGNORECASE)
                    if tm:
                        start_time = _normalise_time(tm.group(1))
                        if start_time:
                            break

                link_tag = dd_tag.find("a", href=True)
                event_url = source_url
                source_key = f"{start_date}:{title}"
                if link_tag is not None:
                    href = link_tag["href"]
                    if href:
                        source_key = _source_key_with_schedule(
                            href, start_date, start_time
                        )
                        event_url = href
                        if not event_url.startswith("http"):
                            event_url = f"https://www.softbankhawks.co.jp{href}"

                uid = compute_event_uid(
                    venue.venue_id,
                    source_key,
                    title,
                    start_date,
                    start_time=start_time,
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
    def _extract_title(dd_text: str) -> str:
        text = re.sub(r"\s+", " ", dd_text).strip()
        if not text:
            return ""

        text = re.sub(r"^(イベント|野球|コンサート)\s*", "", text)
        for marker in ["開演時間", "開催時間", "開場", "お問い合わせ"]:
            if marker in text:
                text = text.split(marker, 1)[0].strip()
                break

        text = re.sub(r"\s*TEL[:：].*$", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


# ---------------------------------------------------------------------------
# ZOZO Marine Stadium schedule
# ---------------------------------------------------------------------------
@_register("zozo_marine_stadium_schedule")
class _ZozoMarineStadiumSchedule(_BaseStrategy):
    """Parse ZOZO Marine Stadium event schedule and daily pages."""

    _BASE_URL = "https://www.marines.co.jp"

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        page_url = venue.source_url
        try:
            resp = session.get(page_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "zozo_marine_stadium: %s returned %s", page_url, resp.status_code
                )
                return []
        except Exception:
            logger.warning("zozo_marine_stadium: failed to fetch %s", page_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        daily_paths: list[str] = []
        seen_paths: set[str] = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if not re.search(r"/event/daily/\d{8}\.html$", href):
                continue
            if href in seen_paths:
                continue
            seen_paths.add(href)
            daily_paths.append(href)

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for daily_path in daily_paths:
            event_url = (
                daily_path
                if daily_path.startswith("http")
                else f"{self._BASE_URL}{daily_path}"
            )
            rec = self._parse_daily_page(
                venue,
                session,
                event_url,
                daily_path,
                page_url,
                seen_uids,
            )
            if rec is not None:
                events.append(rec)

        return events

    def _parse_daily_page(
        self,
        venue: VenueRecord,
        session,
        event_url: str,
        source_key: str,
        source_url: str,
        seen_uids: set[str],
    ) -> EventRecord | None:
        dm = re.search(r"(\d{4})(\d{2})(\d{2})\.html$", source_key)
        if not dm:
            return None
        start_date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"

        try:
            resp = session.get(event_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "zozo_marine_stadium: %s returned %s", event_url, resp.status_code
                )
                return None
        except Exception:
            logger.warning("zozo_marine_stadium: failed to fetch %s", event_url)
            return None

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            title = "千葉ロッテマリーンズ公式戦"

        start_time = self._extract_start_time(soup)

        uid = compute_event_uid(
            venue.venue_id,
            source_key,
            title,
            start_date,
            start_time=start_time,
            url=event_url,
        )
        if uid in seen_uids:
            return None
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
        return rec

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        for dt_tag in soup.select(".c-dailyevent-content dt"):
            text = " ".join(dt_tag.get_text(" ", strip=True).split())
            m = re.search(r"vs\s*(.+)$", text, re.IGNORECASE)
            if m:
                opponent = re.sub(r"\s+", " ", m.group(1)).strip()
                if opponent:
                    return f"千葉ロッテマリーンズ公式戦 vs {opponent}"
        return ""

    @staticmethod
    def _extract_start_time(soup: BeautifulSoup) -> str | None:
        time_text = ""
        node = soup.select_one(".c-dailyevent-kv .time") or soup.select_one(".time")
        if node is not None:
            time_text = " ".join(node.get_text(" ", strip=True).split())
        if not time_text:
            return None

        matches = re.findall(r"(\d{1,2}:\d{2})", time_text)
        if not matches:
            return None
        if len(matches) >= 2:
            return _normalise_time(matches[1])
        return _normalise_time(matches[0])


# ---------------------------------------------------------------------------
# Pia Arena MM event schedule
# ---------------------------------------------------------------------------
@_register("pia_arena_mm_schedule")
class _PiaArenaMmSchedule(_BaseStrategy):
    """Parse Pia Arena MM event listing pages."""

    _BASE_URL = "https://pia-arena-mm.jp"

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 3))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            month_url = f"{self._BASE_URL}/event@p1={d.year}&p2={d.month:02d}.html"
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "pia_arena_mm: %s returned %s", month_url, resp.status_code
                    )
                    continue
            except Exception:
                logger.warning("pia_arena_mm: failed to fetch %s", month_url)
                continue

            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(
                self._parse_page(venue, session, soup, month_url, d.year, seen_uids)
            )

        return events

    def _parse_page(
        self,
        venue: VenueRecord,
        session,
        soup: BeautifulSoup,
        source_url: str,
        year: int,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []

        for a_tag in soup.select("a.event-list[href]"):
            date_node = a_tag.select_one(".event-list__date")
            detail_node = a_tag.select_one(".event-list__detail")
            if date_node is None or detail_node is None:
                continue

            date_text = " ".join(date_node.get_text(" ", strip=True).split())
            dm = re.search(r"(\d{1,2})\.(\d{1,2})", date_text)
            if not dm:
                continue
            month = int(dm.group(1))
            day = int(dm.group(2))
            start_date = f"{year:04d}-{month:02d}-{day:02d}"

            title = " ".join(detail_node.get_text(" ", strip=True).split())
            title = re.sub(r"\s+", " ", title).strip()
            if not title or title.upper() == "PRIVATE":
                continue

            href = a_tag["href"]
            event_url = href
            if not event_url.startswith("http"):
                if event_url.startswith("../"):
                    event_url = f"{self._BASE_URL}/{event_url[3:]}"
                elif event_url.startswith("./"):
                    event_url = f"{self._BASE_URL}/event/{event_url[2:]}"
                elif event_url.startswith("event/"):
                    event_url = f"{self._BASE_URL}/{event_url}"
                elif event_url.startswith("/"):
                    event_url = f"{self._BASE_URL}{event_url}"
                else:
                    event_url = f"{self._BASE_URL}/event/{event_url}"

            start_time = self._extract_start_time(session, event_url)
            source_key = href

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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

    def _extract_start_time(self, session, event_url: str) -> str | None:
        try:
            resp = session.get(event_url, timeout=30)
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for dl_tag in soup.find_all("dl"):
            dt_tag = dl_tag.find("dt")
            dd_tag = dl_tag.find("dd")
            if dt_tag is None or dd_tag is None:
                continue
            dt_text = " ".join(dt_tag.get_text(" ", strip=True).split())
            if "公演時間" not in dt_text:
                continue
            dd_text = " ".join(dd_tag.get_text(" ", strip=True).split())
            for pattern in [
                r"(?:開演|START)\s*/?\s*(\d{1,2}:\d{2})",
                r"(?:開場|OPEN)\s*/?\s*(\d{1,2}:\d{2})",
            ]:
                tm = re.search(pattern, dd_text, re.IGNORECASE)
                if tm:
                    normalized = _normalise_time(tm.group(1))
                    if normalized:
                        return normalized

        return None


# ---------------------------------------------------------------------------
# Port Messe Nagoya events
# ---------------------------------------------------------------------------
@_register("portmesse_nagoya_events")
class _PortMesseNagoyaEvents(_BaseStrategy):
    """Parse Port Messe Nagoya event listing page."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        page_url = venue.source_url
        try:
            resp = session.get(page_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "portmesse_nagoya: %s returned %s", page_url, resp.status_code
                )
                return []
        except Exception:
            logger.warning("portmesse_nagoya: failed to fetch %s", page_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for li_tag in soup.select("li.mc-events"):
            event = self._parse_item(venue, li_tag, page_url, seen_uids)
            if event is not None:
                events.append(event)

        return events

    def _parse_item(
        self,
        venue: VenueRecord,
        li_tag,
        source_url: str,
        seen_uids: set[str],
    ) -> EventRecord | None:
        text = " ".join(li_tag.get_text(" ", strip=True).split())
        if not text:
            return None

        date_text = ""
        date_node = li_tag.select_one(".event-dp, .event-date")
        if date_node is not None:
            date_text = " ".join(date_node.get_text(" ", strip=True).split())
        if not date_text:
            return None

        date_parts = re.findall(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_text)
        if not date_parts:
            return None

        y, m, d = date_parts[0]
        start_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        end_date = None
        if len(date_parts) > 1:
            y2, m2, d2 = date_parts[-1]
            ed = f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
            if ed != start_date:
                end_date = ed

        title = self._extract_title(text, date_text)
        if not title:
            return None

        start_time = None
        for pattern in [
            r"(?:開演|開始|OPEN|START)\s*[:：/]?\s*(\d{1,2}:\d{2})",
            r"(\d{1,2}:\d{2})",
        ]:
            tm = re.search(pattern, text, re.IGNORECASE)
            if tm:
                start_time = _normalise_time(tm.group(1))
                if start_time:
                    break

        link = li_tag.find("a", href=True)
        event_url = source_url
        source_key = f"{start_date}:{title}"
        if link is not None:
            href = link["href"]
            if href:
                source_key = href
                event_url = href
                if not event_url.startswith("http"):
                    if event_url.startswith("/"):
                        event_url = f"https://portmesse.com{event_url}"
                    else:
                        event_url = f"https://portmesse.com/{event_url}"

        uid = compute_event_uid(
            venue.venue_id,
            source_key,
            title,
            start_date,
            start_time=start_time,
            url=event_url,
        )
        if uid in seen_uids:
            return None
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
        return rec

    @staticmethod
    def _extract_title(full_text: str, date_text: str) -> str:
        title = full_text.replace(date_text, " ")
        title = re.sub(r"会場[:：].*?\s", " ", title)
        for marker in ["お問い合わせ", "お問合せ", "連絡先"]:
            if marker in title:
                title = title.split(marker, 1)[0]
                break
        title = re.sub(r"(無料|招待)\s+https?://\S+", "", title)
        title = re.sub(r"https?://\S+", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        return title


# ---------------------------------------------------------------------------
# Asue Arena Osaka events
# ---------------------------------------------------------------------------
@_register("asue_arena_osaka_events")
class _AsueArenaOsakaEvents(_BaseStrategy):
    """Parse Asue Arena Osaka event pages."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        page_url = venue.source_url
        max_links = int(config.get("max_links", 40))

        try:
            resp = session.get(page_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "asue_arena_osaka: %s returned %s", page_url, resp.status_code
                )
                return []
        except Exception:
            logger.warning("asue_arena_osaka: failed to fetch %s", page_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        detail_urls: list[str] = []
        seen_urls: set[str] = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/arena_events/" not in href:
                continue
            event_url = href
            if not event_url.startswith("http"):
                if event_url.startswith("/"):
                    event_url = f"https://www.yahataya-park.jp{event_url}"
                else:
                    event_url = f"https://www.yahataya-park.jp/{event_url}"
            if event_url in seen_urls:
                continue
            seen_urls.add(event_url)
            detail_urls.append(event_url)
            if len(detail_urls) >= max_links:
                break

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for detail_url in detail_urls:
            event = self._parse_detail(venue, session, detail_url, page_url, seen_uids)
            if event is not None:
                events.append(event)

        return events

    def _parse_detail(
        self,
        venue: VenueRecord,
        session,
        detail_url: str,
        source_url: str,
        seen_uids: set[str],
    ) -> EventRecord | None:
        try:
            resp = session.get(detail_url, timeout=30)
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = " ".join(soup.get_text(" ", strip=True).split())

        title = self._extract_title(soup)
        if not title:
            return None

        date_parts = re.findall(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", page_text)
        if not date_parts:
            return None
        y, m, d = date_parts[0]
        start_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        end_date = None
        if len(date_parts) > 1:
            y2, m2, d2 = date_parts[-1]
            ed = f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
            if ed != start_date:
                end_date = ed

        start_time = None
        for pattern in [
            r"(?:開演|開始|OPEN|START)\s*[:：/]?\s*(\d{1,2}:\d{2})",
        ]:
            tm = re.search(pattern, page_text, re.IGNORECASE)
            if tm:
                start_time = _normalise_time(tm.group(1))
                if start_time:
                    break

        source_key = detail_url
        uid = compute_event_uid(
            venue.venue_id,
            source_key,
            title,
            start_date,
            start_time=start_time,
            url=detail_url,
        )
        if uid in seen_uids:
            return None
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
            url=detail_url,
            description=None,
            performers=None,
            capacity=None,
            source_type=venue.source_type,
            source_url=source_url,
            source_event_key=source_key,
        )
        rec.data_hash = compute_data_hash(rec)
        return rec

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        title = ""
        title_tag = soup.find("title")
        if title_tag is not None:
            title = " ".join(title_tag.get_text(" ", strip=True).split())
            title = title.split("–", 1)[0].strip()
            title = title.split("-", 1)[0].strip()
        if not title:
            h1 = soup.find("h1")
            if h1 is not None:
                title = " ".join(h1.get_text(" ", strip=True).split())

        title = re.sub(r"^【[^】]*】\s*", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or title in {"イベント", "Asue アリーナ大阪"}:
            return ""
        return title


# ---------------------------------------------------------------------------
# Nissan Stadium calendar
# ---------------------------------------------------------------------------
@_register("nissan_stadium_calendar")
class _NissanStadiumCalendar(_BaseStrategy):
    """Parse Nissan Stadium event calendar detail pages."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        page_url = venue.source_url
        try:
            resp = session.get(page_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "nissan_stadium: %s returned %s", page_url, resp.status_code
                )
                return []
        except Exception:
            logger.warning("nissan_stadium: failed to fetch %s", page_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        detail_urls: list[str] = []
        seen_urls: set[str] = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "detail.php" not in href:
                continue
            event_url = href
            if not event_url.startswith("http"):
                event_url = f"https://www.nissan-stadium.jp/calendar/{href}"
            if event_url in seen_urls:
                continue
            seen_urls.add(event_url)
            detail_urls.append(event_url)

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for detail_url in detail_urls:
            event = self._parse_detail(venue, session, detail_url, page_url, seen_uids)
            if event is not None:
                events.append(event)

        return events

    def _parse_detail(
        self,
        venue: VenueRecord,
        session,
        detail_url: str,
        source_url: str,
        seen_uids: set[str],
    ) -> EventRecord | None:
        try:
            resp = session.get(detail_url, timeout=30)
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        fields: dict[str, str] = {}
        for tr in soup.select("table tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th is None or td is None:
                continue
            key = " ".join(th.get_text(" ", strip=True).split())
            value = " ".join(td.get_text(" ", strip=True).split())
            if key and value:
                fields[key] = value

        title = fields.get("行事名", "").strip()
        if not title:
            return None

        date_text = fields.get("期日", "")
        dm = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", date_text)
        if not dm:
            dm = re.search(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", date_text)
        if not dm:
            return None
        start_date = (
            f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
        )

        start_time = None
        time_text = fields.get("開始", "")
        tm = re.search(r"(\d{1,2}):(\d{2})", time_text)
        if tm:
            start_time = _normalise_time(f"{tm.group(1)}:{tm.group(2)}")
        if not start_time:
            tm2 = re.search(r"(\d{1,2})\s*時", time_text)
            if tm2:
                start_time = _normalise_time(f"{int(tm2.group(1)):02d}:00")

        source_key = detail_url
        uid = compute_event_uid(
            venue.venue_id,
            source_key,
            title,
            start_date,
            start_time=start_time,
            url=detail_url,
        )
        if uid in seen_uids:
            return None
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
            url=detail_url,
            description=None,
            performers=None,
            capacity=None,
            source_type=venue.source_type,
            source_url=source_url,
            source_event_key=source_key,
        )
        rec.data_hash = compute_data_hash(rec)
        return rec


# ---------------------------------------------------------------------------
# MUFG Stadium (Ajinomoto Stadium) schedule
# ---------------------------------------------------------------------------
@_register("mufg_stadium_schedule")
class _MufgStadiumSchedule(_BaseStrategy):
    """Parse Ajinomoto Stadium schedule monthly pages."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 4))
        today = date.today()
        base = venue.source_url.rstrip("/")
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            month_url = f"{base}/{d.year}/{d.month:02d}/"
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "mufg_stadium: %s returned %s", month_url, resp.status_code
                    )
                    continue
            except Exception:
                logger.warning("mufg_stadium: failed to fetch %s", month_url)
                continue

            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(
                self._parse_month_page(venue, session, soup, month_url, seen_uids)
            )

        return events

    def _parse_month_page(
        self,
        venue: VenueRecord,
        session,
        soup: BeautifulSoup,
        source_url: str,
        seen_uids: set[str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            hm = re.search(r"/schedule/(\d{4})/(\d{2})(\d{2})_\d+\.php$", href)
            if not hm:
                continue

            year = int(hm.group(1))
            month = int(hm.group(2))
            day = int(hm.group(3))
            start_date = f"{year:04d}-{month:02d}-{day:02d}"

            raw_text = " ".join(a_tag.get_text(" ", strip=True).split())

            event_url = href
            if not event_url.startswith("http"):
                if event_url.startswith("/"):
                    event_url = f"https://www.ajinomotostadium.com{href}"
                else:
                    event_url = f"https://www.ajinomotostadium.com/{href}"

            detail_title, detail_start_time = self._extract_detail_fields(
                session, event_url
            )

            title = (
                detail_title
                or re.sub(r"^\d{1,2}\.\d{1,2}\s*\S*\s*", "", raw_text).strip()
            )
            if not title or title == "詳細はこちら":
                continue

            start_time = detail_start_time
            if not start_time:
                tm = re.search(r"(\d{1,2}:\d{2})", raw_text)
                if tm:
                    start_time = _normalise_time(tm.group(1))

            source_key = href
            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
    def _extract_detail_fields(
        session, event_url: str
    ) -> tuple[str | None, str | None]:
        try:
            resp = session.get(event_url, timeout=30)
            if resp.status_code != 200:
                return None, None
        except Exception:
            return None, None

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        text = " ".join(soup.get_text(" ", strip=True).split())

        title = None
        heading_nodes = soup.find_all("h2")
        for node in heading_nodes:
            candidate = " ".join(node.get_text(" ", strip=True).split())
            if (
                candidate
                and "施設から選ぶ" not in candidate
                and "用途から選ぶ" not in candidate
                and "LANGUAGE" not in candidate
                and "来場者の方へ" not in candidate
                and "施設利用の方へ" not in candidate
            ):
                title = candidate
                break

        if not title:
            article = soup.find("article")
            if article is not None:
                article_text = " ".join(article.get_text(" ", strip=True).split())
                mt = re.search(r"\d{4}\.\d{2}\.\d{2}\s*\S+\s*(.+)", article_text)
                if mt:
                    title = mt.group(1).strip()

        start_time = None
        for pattern in [
            r"(?:キックオフ|開演|開始|OPEN|START)\s*[:：]?\s*(\d{1,2}:\d{2})",
            r"(\d{1,2}:\d{2})",
        ]:
            tm = re.search(pattern, text, re.IGNORECASE)
            if tm:
                normalized = _normalise_time(tm.group(1))
                if normalized:
                    start_time = normalized
                    break
        return title, start_time


# ---------------------------------------------------------------------------
# Marine Messe Fukuoka events
# ---------------------------------------------------------------------------
@_register("marine_messe_fukuoka_event")
class _MarineMesseFukuokaEvent(_BaseStrategy):
    """Parse Marine Messe Fukuoka A hall event table."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        page_url = venue.source_url
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9",
        }
        try:
            resp = session.get(page_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "marine_messe_fukuoka: %s returned %s",
                    page_url,
                    resp.status_code,
                )
                return []
        except Exception:
            logger.warning("marine_messe_fukuoka: failed to fetch %s", page_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        page_year = date.today().year
        ym = re.search(r"(\d{4})年\s*(\d{1,2})月", soup.get_text(" ", strip=True))
        if ym:
            page_year = int(ym.group(1))

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for tr in soup.select("table tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue

            date_text = " ".join(cells[0].get_text(" ", strip=True).split())
            title = " ".join(cells[1].get_text(" ", strip=True).split())
            if not date_text or not title:
                continue

            date_parts = re.findall(r"(\d{1,2})\.(\d{1,2})", date_text)
            if not date_parts:
                continue

            month, day = map(int, date_parts[0])
            start_date = f"{page_year:04d}-{month:02d}-{day:02d}"
            end_date = None
            if len(date_parts) > 1:
                month2, day2 = map(int, date_parts[-1])
                end_year = page_year + 1 if month2 < month else page_year
                ed = f"{end_year:04d}-{month2:02d}-{day2:02d}"
                if ed != start_date:
                    end_date = ed

            start_time = None
            tm = re.search(r"(\d{1,2}:\d{2})", date_text)
            if tm:
                start_time = _normalise_time(tm.group(1))

            link = tr.find("a", href=True)
            event_url = page_url
            source_key = f"{start_date}:{title}"
            if link is not None:
                href = link["href"]
                if href:
                    source_key = href
                    event_url = href
                    if not event_url.startswith("http"):
                        if event_url.startswith("/"):
                            event_url = f"https://www.marinemesse.or.jp{event_url}"
                        else:
                            event_url = f"https://www.marinemesse.or.jp/{event_url}"

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
                source_url=page_url,
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
                    logger.warning(
                        "osaka_jo_hall: %s returned %s", month_url, resp.status_code
                    )
                    continue
            except Exception:
                logger.warning("osaka_jo_hall: failed to fetch %s", month_url)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(
                self._parse_page(venue, soup, month_url, d.year, d.month, seen_uids)
            )

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
                source_key = _source_key_with_schedule(
                    event_url, start_date, start_time=None
                )
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

            if event_url:
                source_key = _source_key_with_schedule(event_url, start_date, start_time)
            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
            month_url = (
                f"https://www.festivalhall.jp/events/list/{d.year}/{d.month:02d}/"
            )
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "festival_hall: %s returned %s", month_url, resp.status_code
                    )
                    continue
            except Exception:
                logger.warning("festival_hall: failed to fetch %s", month_url)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(
                self._parse_page(venue, soup, month_url, d.year, d.month, seen_uids)
            )

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
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
            if not year or not month:
                continue

            events.extend(
                self._parse_page(venue, soup, page_url, year, month, seen_uids)
            )

        return events

    @staticmethod
    def _detect_year_month(
        soup: BeautifulSoup, slug: str
    ) -> tuple[int | None, int | None]:
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
                    return int(year_span.get_text(strip=True)), int(
                        month_span.get_text(strip=True)
                    )
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
                        return int(year_span.get_text(strip=True)), int(
                            month_span.get_text(strip=True)
                        )
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
                venue.venue_id,
                source_key,
                title,
                start_date,
                start_time=start_time,
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
                start_date = (
                    f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                )

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
                    venue.venue_id,
                    source_key,
                    title,
                    start_date,
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
                        end_m, end_d = (
                            int(em.get_text(strip=True)),
                            int(ed.get_text(strip=True)),
                        )
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
            display_title = (
                f"{performer} {title}".strip()
                if performer and title
                else (title or performer)
            )

            event_url = a_tag["href"]
            source_key = event_url

            uid = compute_event_uid(
                venue.venue_id,
                source_key,
                display_title,
                start_date,
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
            if elem.name == "p" and "c-ttl-set-calender" in " ".join(
                elem.get("class", [])
            ):
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

                source_key = _source_key_with_schedule(
                    event_url, start_date, start_time
                )
                uid = compute_event_uid(
                    venue.venue_id,
                    source_key,
                    title,
                    start_date,
                    start_time=start_time,
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
            title = (
                f"{artist} {subtitle}".strip()
                if artist and subtitle
                else (artist or subtitle)
            )
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
                venue.venue_id,
                source_key,
                title,
                start_date,
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
# Panasonic Stadium Suita schedule
# ---------------------------------------------------------------------------
@_register("panasonic_stadium_suita_schedule")
class _PanasonicStadiumSuitaSchedule(_BaseStrategy):
    """Parse Panasonic Stadium Suita monthly schedule table."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        months_ahead = int(config.get("months_ahead", 6))
        today = date.today()
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for offset in range(months_ahead + 1):
            d = today.replace(day=1) + timedelta(days=32 * offset)
            d = d.replace(day=1)
            month_url = (
                f"https://suitacityfootballstadium.jp/schedule/index/year/"
                f"{d.year}/month/{d.month:02d}/"
            )
            try:
                resp = session.get(month_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(
                        "panasonic_stadium_suita: %s returned %s",
                        month_url,
                        resp.status_code,
                    )
                    continue
            except Exception:
                logger.warning("panasonic_stadium_suita: failed to fetch %s", month_url)
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            events.extend(
                self._parse_page(venue, soup, month_url, d.year, d.month, seen_uids)
            )
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
        schedule_table = soup.select_one("table")
        if not schedule_table:
            return events

        for row in schedule_table.select("tr"):
            date_cell = row.find("th")
            body_cell = row.find("td")
            if not date_cell or not body_cell:
                continue
            day_match = re.match(r"(\d{1,2})", date_cell.get_text(" ", strip=True))
            if not day_match:
                continue
            day = int(day_match.group(1))
            start_date = f"{year:04d}-{month:02d}-{day:02d}"

            for item in body_cell.select("li"):
                raw_text = " ".join(item.get_text(" ", strip=True).split())
                if not raw_text:
                    continue
                title = raw_text
                start_time = None
                event_url = None

                link = item.find("a", href=True)
                if link:
                    href = link["href"].strip()
                    if href.startswith("http"):
                        event_url = href

                time_match = re.match(r"(\d{1,2}:\d{2})\s*[~～]\s*(.+)$", raw_text)
                if time_match:
                    start_time = _normalise_time(time_match.group(1))
                    title = time_match.group(2).strip()

                title = re.sub(r"\[お問い合わせ先\].*$", "", title).strip()
                if not title or title in {"試合前準備", "スタジアムツアー 締切"}:
                    continue

                source_key = _source_key_with_schedule(
                    event_url or title, start_date, start_time
                )
                uid = compute_event_uid(
                    venue.venue_id,
                    source_key,
                    title,
                    start_date,
                    start_time=start_time,
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
# Edion Arena Osaka monthly PDF guidance
# ---------------------------------------------------------------------------
@_register("edion_arena_osaka_pdf_schedule")
class _EdionArenaOsakaPdfSchedule(_BaseStrategy):
    """Parse Edion Arena Osaka monthly PDF guidance."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        home_url = str(config.get("home_url") or venue.source_url or venue.official_url)
        home_url = home_url.strip()
        if not home_url:
            return []

        try:
            resp = session.get(home_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "edion_arena_osaka: %s returned %s", home_url, resp.status_code
                )
                return []
        except Exception:
            logger.warning("edion_arena_osaka: failed to fetch %s", home_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        min_year_month = _to_year_month(date.today())
        pdf_entries = _extract_edion_monthly_pdf_entries(
            resp.text,
            home_url,
            min_year_month=min_year_month,
        )
        events: list[EventRecord] = []
        seen_uids: set[str] = set()

        for pdf_url, year, month in pdf_entries:
            try:
                pdf_resp = session.get(pdf_url, timeout=30)
                if pdf_resp.status_code != 200:
                    logger.warning(
                        "edion_arena_osaka: %s returned %s",
                        pdf_url,
                        pdf_resp.status_code,
                    )
                    continue
            except Exception:
                logger.warning("edion_arena_osaka: failed to fetch %s", pdf_url)
                continue

            try:
                reader = PdfReader(io.BytesIO(pdf_resp.content))
            except Exception:
                logger.warning("edion_arena_osaka: failed to parse PDF %s", pdf_url)
                continue

            for page in reader.pages:
                layout_text = _extract_pdf_layout_text(page)
                if not layout_text:
                    continue
                events.extend(
                    _parse_edion_main_arena_layout_text(
                        venue=venue,
                        layout_text=layout_text,
                        source_url=pdf_url,
                        year=year,
                        month=month,
                        seen_uids=seen_uids,
                    )
                )

        return events


# ---------------------------------------------------------------------------
# Nagai Park monthly event calendar PDF
# ---------------------------------------------------------------------------
@_register("nagai_park_event_calendar_pdf")
class _NagaiParkEventCalendarPdf(_BaseStrategy):
    """Parse Nagai Park monthly event calendar PDFs for one target venue."""

    def parse(self, venue: VenueRecord, session, config: dict) -> list[EventRecord]:
        home_url = str(config.get("home_url") or venue.source_url or venue.official_url)
        home_url = home_url.strip()
        if not home_url:
            return []

        try:
            resp = session.get(home_url, timeout=30)
            if resp.status_code != 200:
                logger.warning("nagai_park: %s returned %s", home_url, resp.status_code)
                return []
        except Exception:
            logger.warning("nagai_park: failed to fetch %s", home_url)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        today = date.today()
        min_year_month = _to_year_month(today)
        months_ahead = int(config.get("months_ahead", 3) or 3)
        max_month_date = today.replace(day=1) + timedelta(days=32 * months_ahead)
        max_year_month = _to_year_month(max_month_date.replace(day=1))
        pdf_entries = _extract_nagai_event_calendar_pdf_entries(
            resp.text,
            home_url,
            min_year_month=min_year_month,
            max_year_month=max_year_month,
        )

        events: list[EventRecord] = []
        seen_uids: set[str] = set()
        for pdf_url, year, month in pdf_entries:
            try:
                pdf_resp = session.get(pdf_url, timeout=30)
                if pdf_resp.status_code != 200:
                    logger.warning("nagai_park: %s returned %s", pdf_url, pdf_resp.status_code)
                    continue
            except Exception:
                logger.warning("nagai_park: failed to fetch %s", pdf_url)
                continue

            try:
                reader = PdfReader(io.BytesIO(pdf_resp.content))
            except Exception:
                logger.warning("nagai_park: failed to parse PDF %s", pdf_url)
                continue

            for page in reader.pages:
                layout_text = _extract_pdf_layout_text(page)
                if not layout_text:
                    continue
                events.extend(
                    _parse_nagai_event_calendar_layout_text(
                        venue=venue,
                        layout_text=layout_text,
                        source_url=pdf_url,
                        year=year,
                        month=month,
                        seen_uids=seen_uids,
                    )
                )

        return events


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


def _to_year_month(d: date) -> int:
    return d.year * 100 + d.month


def _extract_pdf_layout_text(page) -> str:
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except TypeError:
        return page.extract_text() or ""


def _extract_edion_monthly_pdf_entries(
    html: str,
    base_url: str,
    min_year_month: int,
) -> list[tuple[str, int, int]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, tuple[int, int]] = {}
    for link in soup.select("a[href]"):
        href = str(link.get("href") or "").strip()
        if not href:
            continue
        match = re.search(r"monthly(\d{2})(\d{2})\.pdf\b", href, flags=re.IGNORECASE)
        if not match:
            continue
        year = 2000 + int(match.group(1))
        month = int(match.group(2))
        if year * 100 + month < min_year_month:
            continue
        found[urljoin(base_url, href)] = (year, month)
    return sorted(
        ((url, year, month) for url, (year, month) in found.items()),
        key=lambda item: (item[1], item[2], item[0]),
    )


def _extract_nagai_event_calendar_pdf_entries(
    html: str,
    base_url: str,
    min_year_month: int,
    max_year_month: int | None = None,
) -> list[tuple[str, int, int]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, tuple[int, int]] = {}
    for link in soup.select("a[href]"):
        href = str(link.get("href") or "").strip()
        if not href or ".pdf" not in href.lower():
            continue
        text_blob = " ".join(
            part
            for part in [
                link.get_text(" ", strip=True),
                unquote(href),
            ]
            if part
        )
        if "イベントカレンダー" not in text_blob:
            continue
        match = re.search(r"(20\d{2})年度?\s*(\d{1,2})月度", text_blob)
        if not match:
            match = re.search(r"(20\d{2})年\s*(\d{1,2})月", text_blob)
        if not match:
            continue
        year = int(match.group(1))
        month = int(match.group(2))
        year_month = year * 100 + month
        if year_month < min_year_month:
            continue
        if max_year_month is not None and year_month > max_year_month:
            continue
        found[urljoin(base_url, href)] = (year, month)
    return sorted(
        ((url, year, month) for url, (year, month) in found.items()),
        key=lambda item: (item[1], item[2], item[0]),
    )


def _parse_nagai_event_calendar_layout_text(
    venue: VenueRecord,
    layout_text: str,
    source_url: str,
    year: int,
    month: int,
    seen_uids: set[str],
) -> list[EventRecord]:
    events: list[EventRecord] = []
    current_day: int | None = None
    current_time: str | None = None
    current_parts: list[str] = []
    target_venue = venue.venue_name

    def flush_current() -> None:
        nonlocal current_time, current_parts
        if current_day is None or not current_time:
            current_time = None
            current_parts = []
            return
        text = _clean_nagai_calendar_text(" ".join(current_parts))
        current_time_value = current_time
        current_time = None
        current_parts = []
        if target_venue not in text:
            return
        title = _clean_nagai_calendar_title(text, target_venue)
        if not title or title in {"ー", "-"}:
            return
        start_date = f"{year:04d}-{month:02d}-{current_day:02d}"
        source_key = _source_key_with_schedule(title, start_date, current_time_value)
        uid = compute_event_uid(
            venue.venue_id,
            source_key,
            title,
            start_date,
            start_time=current_time_value,
            url=source_url,
        )
        if uid in seen_uids:
            return
        seen_uids.add(uid)
        rec = EventRecord(
            event_uid=uid,
            venue_id=venue.venue_id,
            title=title,
            start_date=start_date,
            start_time=current_time_value,
            end_date=None,
            end_time=None,
            all_day=False,
            status="scheduled",
            url=source_url,
            description=None,
            performers=None,
            capacity=None,
            source_type=venue.source_type,
            source_url=source_url,
            source_event_key=source_key,
        )
        rec.data_hash = compute_data_hash(rec)
        events.append(rec)

    for raw_line in layout_text.splitlines():
        line = _clean_nagai_calendar_text(raw_line)
        if not line:
            continue
        day_match = re.match(r"^(\d{1,2})\s+[月火水木金土日]\s*(.*)$", line)
        if day_match:
            flush_current()
            current_day = int(day_match.group(1))
            line = day_match.group(2).strip()
            if not line:
                continue
        if current_day is None:
            continue
        time_match = re.match(r"^(\d{1,2}[:：]\d{2})\s+(.+)$", line)
        if time_match:
            flush_current()
            current_time = _normalise_time(time_match.group(1).replace("：", ":"))
            current_parts = [time_match.group(2)]
            continue
        if current_time:
            if _is_nagai_calendar_location_only(line):
                continue
            current_parts.append(line)

    flush_current()
    return events


def _clean_nagai_calendar_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    return " ".join(text.split())


def _clean_nagai_calendar_title(value: str, venue_name: str) -> str:
    title = value.replace("関連リンク", " ")
    title = title.replace(venue_name, " ")
    title = re.sub(r"\s+", " ", title).strip(" -/|　")
    return title.strip()


def _is_nagai_calendar_location_only(value: str) -> bool:
    text = _clean_nagai_calendar_text(value)
    return text in {
        "ヤンマーフィールド長居",
        "ヤンマーハナサカスタジアム",
        "自由広場",
        "長居公園",
        "長居植物園",
    }


def _parse_edion_main_arena_layout_text(
    venue: VenueRecord,
    layout_text: str,
    source_url: str,
    year: int,
    month: int,
    seen_uids: set[str],
) -> list[EventRecord]:
    events: list[EventRecord] = []
    current_day: int | None = None
    current_parts: list[str] = []

    def flush_current() -> None:
        nonlocal current_day, current_parts
        if current_day is None:
            return
        day_value = current_day
        title = _clean_edion_title(" ".join(part for part in current_parts if part))
        current_day = None
        current_parts = []
        if _should_skip_edion_title(title):
            return
        start_date = f"{year:04d}-{month:02d}-{day_value:02d}"
        source_key = _source_key_with_schedule(title, start_date, None)
        uid = compute_event_uid(
            venue.venue_id,
            source_key,
            title,
            start_date,
            start_time=None,
            url=source_url,
        )
        if uid in seen_uids:
            return
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
            url=source_url,
            description=None,
            performers=None,
            capacity=None,
            source_type=venue.source_type,
            source_url=source_url,
            source_event_key=source_key,
        )
        rec.data_hash = compute_data_hash(rec)
        events.append(rec)

    for raw_line in layout_text.splitlines():
        left_segment, day = _extract_edion_left_column(raw_line)
        if day is not None:
            flush_current()
            current_day = day
            body = re.sub(
                r"^\s*\d{1,2}\s+[月火水木金土日]\s*",
                "",
                left_segment,
                count=1,
            ).strip()
            current_parts = [body] if body else []
            continue
        if current_day is None:
            continue
        continuation = left_segment.strip()
        if continuation:
            current_parts.append(continuation)
    flush_current()
    return events


def _extract_edion_left_column(line: str) -> tuple[str, int | None]:
    normalized = unicodedata.normalize("NFKC", line or "").replace("\u3000", " ")
    if not normalized.strip():
        return "", None
    day_matches = list(
        re.finditer(r"(?<!\d)(\d{1,2})\s+[月火水木金土日]\b", normalized)
    )
    day = None
    if day_matches and day_matches[0].start() <= 4:
        day = int(day_matches[0].group(1))
    split_at = None
    for match in day_matches[1:]:
        if match.start() >= 100:
            split_at = match.start()
            break
    if split_at is not None:
        return normalized[:split_at].rstrip(), day
    return normalized[:130].rstrip(), day


def _clean_edion_title(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", text or "").replace("\u3000", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(
        r"(?<=[一-龯ぁ-ゖァ-ヺー々〆ヶ])\s+(?=[一-龯ぁ-ゖァ-ヺー々〆ヶ])",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?<=[一-龯ぁ-ゖァ-ヺー々〆ヶ])\s+(?=[()（）・])",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?<=[()（）・])\s+(?=[一-龯ぁ-ゖァ-ヺー々〆ヶ])",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\(\s+", "(", cleaned)
    cleaned = re.sub(r"\s+\)", ")", cleaned)
    return cleaned.strip(" ・")


def _should_skip_edion_title(title: str) -> bool:
    if not title:
        return True
    if any(
        term in title
        for term in (
            "会場準備",
            "会場後始末",
            "保守点検",
            "は有料行事",
            "(注)",
            "主催者の都合により",
        )
    ):
        return True
    if title in {"公益財団法人日本相撲協会"}:
        return True
    return False
