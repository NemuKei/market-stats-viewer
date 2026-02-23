"""Kstyle article source plugin – filters on ■公演情報 in the body."""

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

# Article body candidate selectors (tried in order)
_BODY_SELECTORS = [
    "div#artBody",
    "div.article-body",
    "div.article_body",
    "div.read_text",
    "div.articleContent",
    "div.article_content",
    "article",
]


class KstyleMusicSource(SignalSource):
    """Fetch Kstyle articles whose body contains '■公演情報' (Japan concerts)."""

    CONCERT_MARKER = "■公演情報"
    PUBLISHED_RE = re.compile(r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})")
    JP_DATE_RE = re.compile(r"\d{4}年\s*\d{1,2}月\s*\d{1,2}日")
    MAX_CONCERT_SECTION_LEN = 800

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
    ]

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        pages = max(1, int(cfg.get("pages", 2)))
        max_articles = int(cfg.get("max_articles", 40))

        first_resp = self.session.get(source.source_url, timeout=30)
        first_resp.raise_for_status()
        first_resp.encoding = first_resp.apparent_encoding or "utf-8"

        page_urls = [first_resp.url]
        soup_first = BeautifulSoup(first_resp.text, "html.parser")
        page_urls.extend(
            self._extract_pagination_urls(soup_first, first_resp.url, pages - 1)
        )

        page_num = 2
        while len(page_urls) < pages:
            sep = "&" if "?" in source.source_url else "?"
            page_urls.append(f"{source.source_url}{sep}page={page_num}")
            page_num += 1

        # Collect article candidates from list pages
        candidates: dict[str, tuple[str, str]] = {}  # url -> (title, published_at)
        for page_url in page_urls[:pages]:
            resp = (
                first_resp
                if page_url == first_resp.url
                else self.session.get(page_url, timeout=30)
            )
            if resp.status_code != 200:
                logger.warning("kstyle: %s returned %s", page_url, resp.status_code)
                continue
            if resp is not first_resp:
                resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            for art_url, title, published_at in self._extract_article_links(
                soup, resp.url
            ):
                candidates[art_url] = (title, published_at)

        # Fetch each article body, keep only concert-info articles
        signals: dict[str, SignalRecord] = {}
        for art_url, (title, published_at) in list(candidates.items())[:max_articles]:
            try:
                rec = self._process_article(
                    art_url, title, published_at, source.source_id
                )
                if rec is not None:
                    signals[rec.signal_uid] = rec
            except Exception:
                logger.debug(
                    "kstyle: failed to process article %s", art_url, exc_info=True
                )

        return sorted(signals.values(), key=lambda r: r.published_at_utc, reverse=True)

    # ------------------------------------------------------------------
    # List-page helpers
    # ------------------------------------------------------------------

    def _extract_article_links(
        self, soup: BeautifulSoup, page_url: str
    ) -> list[tuple[str, str, str]]:
        """Return (article_url, title, published_at_utc) for each article on the list page."""
        results: list[tuple[str, str, str]] = []
        for a in soup.select('a[href*="article.ksn?articleNo="]'):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            title = " ".join(a.get_text(" ", strip=True).split())
            if not title:
                continue

            container = self._find_container_with_date(a)
            context = (
                " ".join(container.get_text(" ", strip=True).split())
                if container
                else ""
            )
            dt_match = self.PUBLISHED_RE.search(context)
            if not dt_match:
                continue
            published_at = self._to_utc_datetime(dt_match.group(1))
            if not published_at:
                continue

            abs_url = urljoin(page_url, href)
            results.append((abs_url, title, published_at))
        return results

    def _find_container_with_date(self, tag: Tag) -> Tag | None:
        node: Tag | None = tag
        for _ in range(6):
            if node is None:
                return None
            text = " ".join(node.get_text(" ", strip=True).split())
            if self.PUBLISHED_RE.search(text):
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

    # ------------------------------------------------------------------
    # Article body helpers
    # ------------------------------------------------------------------

    def _process_article(
        self, url: str, title: str, published_at: str, source_id: str
    ) -> SignalRecord | None:
        """Fetch article body; return SignalRecord only if Japan concert info found."""
        resp = self.session.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        body_text = self._get_body_text(soup)
        if self.CONCERT_MARKER not in body_text:
            return None

        snippet, labels = self._extract_concert_section(body_text)
        if not labels.get("jp_concert"):
            return None

        rec = SignalRecord(
            signal_uid=compute_signal_uid(source_id, url),
            source_id=source_id,
            published_at_utc=published_at,
            title=title,
            url=url,
            snippet=snippet,
            score=90,
            labels_json=canonical_labels_json(labels),
        )
        rec.content_hash = compute_content_hash(rec)
        return rec

    def _get_body_text(self, soup: BeautifulSoup) -> str:
        """Return article body text, trying known selectors then falling back to full page."""
        for selector in _BODY_SELECTORS:
            elem = soup.select_one(selector)
            if elem:
                return " ".join(elem.get_text(" ", strip=True).split())
        return " ".join(soup.get_text(" ", strip=True).split())

    def _extract_concert_section(
        self, text: str
    ) -> tuple[str | None, dict[str, object]]:
        """Extract the ■公演情報 section and analyse it for Japan concerts."""
        idx = text.find(self.CONCERT_MARKER)
        if idx == -1:
            return None, {"jp_concert": False, "concert_info": False}

        # Take text from the marker up to the next ■ section or MAX_CONCERT_SECTION_LEN chars
        section = text[idx:]
        next_marker = section.find("■", 1)
        if next_marker > 0:
            section = section[:next_marker]
        section = section[: self.MAX_CONCERT_SECTION_LEN]

        jp_concert = any(kw in section for kw in self.JAPAN_KEYWORDS)
        date_count = len(self.JP_DATE_RE.findall(section))

        labels: dict[str, object] = {
            "concert_info": True,
            "jp_concert": jp_concert,
            "date_count": date_count,
        }
        return trim_snippet(section), labels

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

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
    def _to_utc_datetime(value: str) -> str | None:
        try:
            dt_jst = datetime.strptime(value, "%Y/%m/%d %H:%M").replace(
                tzinfo=timezone(timedelta(hours=9))
            )
        except ValueError:
            return None
        return dt_jst.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
