"""STARTO CONCERT news source plugin."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from ..types import SignalRecord, SignalSourceRecord
from .base import (
    SignalSource,
    canonical_labels_json,
    compute_content_hash,
    compute_signal_uid,
    trim_snippet,
)

logger = logging.getLogger(__name__)


class StartoConcertSource(SignalSource):
    """Fetch STARTO CONCERT live list and parse SCHEDULE details."""

    DATE_RE = re.compile(r"(\d{4}\.\d{2}\.\d{2})")
    LIVE_DETAIL_HREF_RE = re.compile(r"/s/p/live/\d+")
    JAPAN_TERMS = [
        "北海道",
        "青森県",
        "岩手県",
        "宮城県",
        "秋田県",
        "山形県",
        "福島県",
        "茨城県",
        "栃木県",
        "群馬県",
        "埼玉県",
        "千葉県",
        "東京都",
        "神奈川県",
        "新潟県",
        "富山県",
        "石川県",
        "福井県",
        "山梨県",
        "長野県",
        "岐阜県",
        "静岡県",
        "愛知県",
        "三重県",
        "滋賀県",
        "京都府",
        "大阪府",
        "兵庫県",
        "奈良県",
        "和歌山県",
        "鳥取県",
        "島根県",
        "岡山県",
        "広島県",
        "山口県",
        "徳島県",
        "香川県",
        "愛媛県",
        "高知県",
        "福岡県",
        "佐賀県",
        "長崎県",
        "熊本県",
        "大分県",
        "宮崎県",
        "鹿児島県",
        "沖縄県",
    ]

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        pages = max(1, int(cfg.get("pages", 1)))
        if "live?ct=concert" in source.source_url:
            pages = 1

        first_resp = self.session.get(source.source_url, timeout=30)
        first_resp.raise_for_status()
        first_resp.encoding = first_resp.apparent_encoding or "utf-8"

        urls = [first_resp.url]
        soup_first = BeautifulSoup(first_resp.text, "html.parser")
        urls.extend(
            self._extract_pagination_urls(soup_first, first_resp.url, pages - 1)
        )

        fallback_page = 2
        while len(urls) < pages:
            sep = "&" if "?" in source.source_url else "?"
            urls.append(f"{source.source_url}{sep}page={fallback_page}")
            fallback_page += 1

        signals: dict[str, SignalRecord] = {}
        for page_url in urls[:pages]:
            resp = (
                first_resp
                if page_url == first_resp.url
                else self.session.get(page_url, timeout=30)
            )
            if resp.status_code != 200:
                logger.warning("starto: %s returned %s", page_url, resp.status_code)
                continue
            if resp is not first_resp:
                resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            for rec in self._parse_page(soup, resp.url, source.source_id):
                signals[rec.signal_uid] = rec

        out = sorted(signals.values(), key=lambda r: r.published_at_utc, reverse=True)
        if not out:
            logger.warning("starto: fetched 0 signals from %s", source.source_id)
        return out

    def _parse_page(
        self, soup: BeautifulSoup, page_url: str, source_id: str
    ) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        seen_urls: set[str] = set()

        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            if not self.LIVE_DETAIL_HREF_RE.search(href):
                continue

            title = " ".join(a.get_text(" ", strip=True).split())
            if not title or len(title) < 3:
                continue

            abs_url = urljoin(page_url, href)
            abs_url = self._canonicalize_detail_url(abs_url)
            if abs_url in seen_urls:
                continue
            seen_urls.add(abs_url)

            detail = self._fetch_live_detail(abs_url)
            if detail is None:
                continue

            detail_title, schedules = detail
            if not schedules:
                continue
            artist_name = self._infer_artist_name(detail_title or title)
            grouped = self._group_schedules_by_date_venue(schedules)
            for (event_date, venue_name), rows in grouped.items():
                published_at_utc = self._to_utc_date(event_date.replace("-", "."))
                if not published_at_utc:
                    continue
                event_info = self._build_occurrence_info(rows)
                snippet = trim_snippet(event_info)
                labels = {
                    "announce": True,
                    "jp_show": True,
                    "category": "concert",
                    "venue_count": 1,
                    "date_count": len(rows),
                    "artist_name": artist_name,
                    "venue_name": venue_name,
                    "event_info": event_info,
                    "event_start_date": event_date,
                    "event_end_date": event_date,
                }
                extra_key = f"{event_date}|{venue_name}"
                rec = SignalRecord(
                    signal_uid=compute_signal_uid(source_id, abs_url, extra_key),
                    source_id=source_id,
                    published_at_utc=published_at_utc,
                    title=detail_title or title,
                    url=abs_url,
                    snippet=snippet,
                    score=92,
                    labels_json=canonical_labels_json(labels),
                )
                rec.content_hash = compute_content_hash(rec)
                records.append(rec)

        return records

    def _fetch_live_detail(
        self, detail_url: str
    ) -> tuple[str, list[tuple[str, str | None, str, str | None]]] | None:
        try:
            resp = self.session.get(detail_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "starto: detail %s returned %s", detail_url, resp.status_code
                )
                return None
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as exc:
            logger.warning("starto: detail fetch failed %s (%s)", detail_url, exc)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        title_node = soup.select_one("h1")
        title = (
            " ".join(title_node.get_text(" ", strip=True).split()) if title_node else ""
        )

        schedules = self._extract_schedules(soup, resp.text)
        if not schedules:
            return None
        if not self._contains_japan_schedule(schedules):
            return None
        return title, schedules

    def _extract_schedules(
        self, soup: BeautifulSoup, raw_text: str
    ) -> list[tuple[str, str | None, str, str | None]]:
        schedules = self._extract_schedules_from_embedded_data(raw_text)
        if schedules:
            return schedules

        schedules = []
        for heading in soup.select("h3"):
            heading_text = " ".join(heading.get_text(" ", strip=True).split())
            if not heading_text:
                continue
            prefecture, venue = self._split_prefecture_venue(heading_text)

            table = heading.find_next("table")
            if table is None:
                continue

            for row in table.select("tr"):
                cells = [
                    " ".join(td.get_text(" ", strip=True).split())
                    for td in row.select("td")
                ]
                if len(cells) < 1:
                    continue
                date = self._extract_date(cells[0])
                if not date:
                    continue
                start_time = cells[1] if len(cells) > 1 and cells[1] else None
                schedules.append((date, start_time, venue, prefecture))

        schedules.sort(key=lambda row: row[0])
        return schedules

    def _extract_schedules_from_embedded_data(
        self, raw_text: str
    ) -> list[tuple[str, str | None, str, str | None]]:
        pattern = re.compile(
            r'"str_itemDate"\s*:\s*"(?P<date>\d{4}-\d{2}-\d{2})".*?'
            r'"str_itemPlacePref"\s*:\s*"(?P<pref>[^"]*)".*?'
            r'"str_itemPlace"\s*:\s*"(?P<venue>[^"]*)".*?'
            r'"str_itemTime"\s*:\s*`(?P<time>[^`]*)`',
            re.S,
        )
        schedules: list[tuple[str, str | None, str, str | None]] = []
        for match in pattern.finditer(raw_text):
            raw_date = match.group("date")
            venue = " ".join(match.group("venue").split())
            if not venue:
                continue
            date = raw_date.replace("-", ".")
            pref = " ".join(match.group("pref").split()) or None
            time_text = " ".join(match.group("time").split()) or None
            schedules.append((date, time_text, venue, pref))

        schedules.sort(key=lambda row: row[0])
        return schedules

    def _split_prefecture_venue(self, heading_text: str) -> tuple[str | None, str]:
        match = re.match(r"^\[(.+?)\]\s*(.+)$", heading_text)
        if match:
            return match.group(1), match.group(2)
        return None, heading_text

    def _canonicalize_detail_url(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def _extract_date(self, text: str) -> str | None:
        match = self.DATE_RE.search(text)
        if not match:
            return None
        return match.group(1)

    def _contains_japan_schedule(
        self, schedules: list[tuple[str, str | None, str, str | None]]
    ) -> bool:
        blob_parts: list[str] = []
        for _, _, venue, prefecture in schedules:
            blob_parts.append(venue)
            if prefecture:
                blob_parts.append(prefecture)
        blob = " ".join(blob_parts)
        return any(term in blob for term in self.JAPAN_TERMS)

    def _build_snippet(
        self, schedules: list[tuple[str, str | None, str, str | None]]
    ) -> str:
        preview = schedules[:5]
        lines: list[str] = []
        for date, start_time, venue, prefecture in preview:
            place = f"[{prefecture}] {venue}" if prefecture else venue
            if start_time:
                lines.append(f"{date} {start_time} / {place}")
            else:
                lines.append(f"{date} / {place}")
        if len(schedules) > len(preview):
            lines.append(f"ほか {len(schedules) - len(preview)} 件")
        return " | ".join(lines)

    def _group_schedules_by_date_venue(
        self, schedules: list[tuple[str, str | None, str, str | None]]
    ) -> dict[tuple[str, str], list[tuple[str, str | None, str, str | None]]]:
        grouped: dict[
            tuple[str, str], list[tuple[str, str | None, str, str | None]]
        ] = defaultdict(list)
        for date_raw, start_time, venue, prefecture in schedules:
            event_date = date_raw.replace(".", "-")
            venue_name = " ".join(venue.split())
            if not event_date or not venue_name:
                continue
            grouped[(event_date, venue_name)].append(
                (event_date, start_time, venue_name, prefecture)
            )
        return dict(grouped)

    def _build_occurrence_info(
        self, rows: list[tuple[str, str | None, str, str | None]]
    ) -> str:
        parts: list[str] = []
        for event_date, start_time, venue_name, prefecture in sorted(
            rows, key=lambda row: (row[0], row[1] or "")
        ):
            place = f"[{prefecture}] {venue_name}" if prefecture else venue_name
            if start_time:
                parts.append(f"{event_date} {start_time} / {place}")
            else:
                parts.append(f"{event_date} / {place}")
        return " | ".join(parts)

    def _extract_event_date_range(
        self, schedules: list[tuple[str, str | None, str, str | None]]
    ) -> tuple[str | None, str | None]:
        if not schedules:
            return None, None
        dates = sorted(row[0] for row in schedules if row[0])
        if not dates:
            return None, None
        start_date = dates[0].replace(".", "-")
        end_date = dates[-1].replace(".", "-")
        return start_date, end_date

    def _infer_artist_name(self, title: str) -> str:
        normalized = " ".join(title.split())
        for marker in [
            " LIVE TOUR",
            " CONCERT TOUR",
            " DOME TOUR",
            " ARENA TOUR",
            " STAGE",
            " CONCERT",
            " LIVE",
        ]:
            pos = normalized.find(marker)
            if pos > 0:
                return normalized[:pos].strip()
        return normalized

    def _find_context_node(self, tag: Tag) -> Tag | None:
        node: Tag | None = tag
        for _ in range(6):
            if node is None:
                return None
            text = " ".join(node.get_text(" ", strip=True).split())
            if self.DATE_RE.search(text):
                return node
            parent = node.parent
            node = parent if isinstance(parent, Tag) else None
        return None

    def _extract_pagination_urls(
        self, soup: BeautifulSoup, base_url: str, max_count: int
    ) -> list[str]:
        if max_count <= 0:
            return []
        urls: list[str] = []
        seen: set[str] = set()
        for a in soup.select("a[href]"):
            text = " ".join(a.get_text(" ", strip=True).split())
            if not text.isdigit():
                continue
            href = (a.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            urls.append(abs_url)
            if len(urls) >= max_count:
                break
        return urls

    @staticmethod
    def _load_config(config_json: str | None) -> dict:
        if not config_json:
            return {}
        try:
            parsed = json.loads(config_json)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _to_utc_date(value: str) -> str | None:
        try:
            dt_jst = datetime.strptime(value, "%Y.%m.%d").replace(
                tzinfo=timezone(timedelta(hours=9))
            )
        except ValueError:
            return None
        return dt_jst.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
