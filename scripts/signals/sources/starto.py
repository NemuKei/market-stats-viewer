"""STARTO live-concert listing source plugin."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

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
    """Fetch STARTO live-concert listing page (Japan concerts only)."""

    # YYYY.MM.DD or YYYY年MM月DD日
    DATE_RE = re.compile(
        r"(\d{4})\.(\d{2})\.(\d{2})|(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日"
    )

    JAPAN_KEYWORDS = [
        "東京",
        "大阪",
        "名古屋",
        "福岡",
        "札幌",
        "横浜",
        "神戸",
        "埼玉",
        "千葉",
        "京都",
        "仙台",
        "広島",
        "岡山",
        "新潟",
        "静岡",
        "宮城",
        "ドーム",
        "武道館",
        "アリーナ",
        "ホール",
        "スタジアム",
        "日本",
    ]
    OVERSEAS_KEYWORDS = [
        "ソウル",
        "釜山",
        "バンコク",
        "シンガポール",
        "ニューヨーク",
        "ロサンゼルス",
        "ロンドン",
        "パリ",
        "上海",
        "北京",
        "台北",
        "マニラ",
        "ジャカルタ",
        "バンクーバー",
    ]

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        pages = max(1, int(cfg.get("pages", 3)))

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

        # Target links to individual live event pages
        for a in soup.select('a[href*="/s/p/live/"]'):
            href = (a.get("href") or "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            title = " ".join(a.get_text(" ", strip=True).split())
            if not title or len(title) < 3:
                continue

            context_node = self._find_context_node(a)
            if context_node is None:
                continue
            context = " ".join(context_node.get_text(" ", strip=True).split())
            date_str = self._extract_date_str(context)
            if date_str is None:
                continue

            published_at_utc = self._to_utc_date(date_str)
            if not published_at_utc:
                continue

            # Japan-only filter
            if not self._is_japan_concert(context, title):
                continue

            abs_url = urljoin(page_url, href)
            venue_snippet = self._extract_venue_snippet(context)
            labels: dict[str, object] = {
                "category": "concert",
                "jp_concert": True,
                "venue_found": venue_snippet is not None,
            }
            rec = SignalRecord(
                signal_uid=compute_signal_uid(source_id, abs_url),
                source_id=source_id,
                published_at_utc=published_at_utc,
                title=title,
                url=abs_url,
                snippet=trim_snippet(venue_snippet),
                score=90,
                labels_json=canonical_labels_json(labels),
            )
            rec.content_hash = compute_content_hash(rec)
            records.append(rec)

        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_context_node(self, tag: Tag) -> Tag | None:
        """Walk up the DOM to find a node that contains a recognisable date."""
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

    def _extract_date_str(self, text: str) -> str | None:
        """Return the first date found in text as a canonical 'YYYY.MM.DD' string."""
        m = self.DATE_RE.search(text)
        if not m:
            return None
        if m.group(1):  # YYYY.MM.DD branch
            return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
        # YYYY年MM月DD日 branch
        try:
            return f"{m.group(4)}.{int(m.group(5)):02d}.{int(m.group(6)):02d}"
        except (TypeError, ValueError):
            return None

    def _is_japan_concert(self, context: str, title: str) -> bool:
        """Return True when the context/title looks like a Japan concert."""
        blob = f"{context} {title}"
        # Explicit overseas reference → exclude
        if any(kw in blob for kw in self.OVERSEAS_KEYWORDS):
            return False
        # Any Japan keyword → include
        if any(kw in blob for kw in self.JAPAN_KEYWORDS):
            return True
        # No location info at all → assume Japan (STARTO artists are Japan-based)
        return True

    def _extract_venue_snippet(self, context: str) -> str | None:
        """Extract a venue-relevant substring from the context text."""
        for kw in self.JAPAN_KEYWORDS:
            idx = context.find(kw)
            if idx == -1:
                continue
            start = max(0, idx - 5)
            end = min(len(context), idx + 30)
            return context[start:end].strip()
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
