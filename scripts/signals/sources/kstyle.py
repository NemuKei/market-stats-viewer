"""Kstyle category news source plugin."""

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


class KstyleMusicSource(SignalSource):
    """Fetch Kstyle category pages and keep JP concert announcement articles."""

    DATETIME_RE = re.compile(r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})")
    INCLUDE_TERMS = [
        "日本公演",
        "来日",
        "ジャパンツアー",
        "追加公演",
        "アンコール公演",
        "ドーム",
        "アリーナ",
        "開催決定",
        "先行",
        "チケット",
        "公演",
        "ファンミ",
        "ライブ",
        "ツアー",
        "公演情報",
    ]
    EXCLUDE_TERMS = [
        "カムバック",
        "リリース",
        "MV",
        "ドラマ",
        "映画",
        "熱愛",
        "ファッション",
        "PHOTO",
        "コスメ",
    ]
    LOCATION_TERMS = [
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
    ]
    ARTICLE_TEXT_SELECTORS = [
        "div#articleBody",
        "div.articleBody",
        "div.newsView",
        "div.article_view",
        "article",
    ]
    CONCERT_INFO_MARKERS = ("■公演情報", "■ 公演情報", "■開催概要", "■ 開催概要")
    SECTION_STOP_MARKERS = ("■", "【関連", "元記事配信日時", "記者")
    JAPAN_TERMS = [
        "日本",
        "北海道",
        "青森",
        "岩手",
        "宮城",
        "秋田",
        "山形",
        "福島",
        "茨城",
        "栃木",
        "群馬",
        "埼玉",
        "千葉",
        "東京",
        "神奈川",
        "新潟",
        "富山",
        "石川",
        "福井",
        "山梨",
        "長野",
        "岐阜",
        "静岡",
        "愛知",
        "三重",
        "滋賀",
        "京都",
        "大阪",
        "兵庫",
        "奈良",
        "和歌山",
        "鳥取",
        "島根",
        "岡山",
        "広島",
        "山口",
        "徳島",
        "香川",
        "愛媛",
        "高知",
        "福岡",
        "佐賀",
        "長崎",
        "熊本",
        "大分",
        "宮崎",
        "鹿児島",
        "沖縄",
        "ドーム",
        "アリーナ",
        "ホール",
        "会場",
    ]
    VENUE_RE = re.compile(r"(?:会場|開催場所|場所)】?[:：]\s*([^\n]+)")
    DATE_LINE_RE = re.compile(r"(?:日時|日程|公演日|開催日|開演|DAY\d)")
    DATE_TOKEN_RE = re.compile(r"(?:(\d{4})[./年-]\s*(\d{1,2})[./月-]\s*(\d{1,2})日?)")

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        pages = max(1, int(cfg.get("pages", 2)))

        first_resp = self.session.get(source.source_url, timeout=30)
        first_resp.raise_for_status()
        first_resp.encoding = first_resp.apparent_encoding or "utf-8"

        urls = [first_resp.url]
        soup_first = BeautifulSoup(first_resp.text, "html.parser")
        urls.extend(
            self._extract_pagination_urls(soup_first, first_resp.url, pages - 1)
        )

        page_num = 2
        while len(urls) < pages:
            sep = "&" if "?" in source.source_url else "?"
            urls.append(f"{source.source_url}{sep}page={page_num}")
            page_num += 1

        signals: dict[str, SignalRecord] = {}
        for page_url in urls[:pages]:
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
            for rec in self._parse_page(soup, resp.url, source.source_id):
                signals[rec.signal_uid] = rec

        return sorted(signals.values(), key=lambda r: r.published_at_utc, reverse=True)

    def _parse_page(
        self, soup: BeautifulSoup, page_url: str, source_id: str
    ) -> list[SignalRecord]:
        candidates: list[tuple[str, str, str]] = []
        seen_urls: set[str] = set()
        for a in soup.select('a[href*="article.ksn?articleNo="]'):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            title = " ".join(a.get_text(" ", strip=True).split())
            if not title:
                continue
            abs_url = urljoin(page_url, href)
            if abs_url in seen_urls:
                continue
            seen_urls.add(abs_url)

            container = self._find_container(a)
            context = (
                " ".join(container.get_text(" ", strip=True).split())
                if container
                else ""
            )
            dt_match = self.DATETIME_RE.search(context)
            if not dt_match:
                continue
            published_at_utc = self._to_utc_datetime(dt_match.group(1))
            if not published_at_utc:
                continue

            candidates.append((title, abs_url, published_at_utc))

        records: list[SignalRecord] = []
        for title, abs_url, published_at_utc in candidates:
            detail = self._fetch_article_detail(abs_url)
            if detail is None:
                continue
            section_text, venue_text, date_text = detail
            event_start_date, event_end_date = self._extract_event_date_range(
                section_text
            )
            score, labels = self._score_and_labels(title, section_text)
            labels["artist_name"] = self._infer_artist_name(title)
            labels["venue_name"] = venue_text or ""
            labels["event_info"] = date_text or ""
            if event_start_date:
                labels["event_start_date"] = event_start_date
            if event_end_date:
                labels["event_end_date"] = event_end_date

            snippet_parts: list[str] = []
            if venue_text:
                snippet_parts.append(f"会場: {venue_text}")
            if date_text:
                snippet_parts.append(f"日時: {date_text}")
            snippet_parts.append(section_text)
            snippet = trim_snippet(" / ".join(part for part in snippet_parts if part))

            rec = SignalRecord(
                signal_uid=compute_signal_uid(source_id, abs_url),
                source_id=source_id,
                published_at_utc=published_at_utc,
                title=title,
                url=abs_url,
                snippet=snippet,
                score=score,
                labels_json=canonical_labels_json(labels),
            )
            rec.content_hash = compute_content_hash(rec)
            records.append(rec)

        return records

    def _fetch_article_detail(
        self, article_url: str
    ) -> tuple[str, str | None, str | None] | None:
        try:
            resp = self.session.get(article_url, timeout=30)
            if resp.status_code != 200:
                logger.warning(
                    "kstyle: detail %s returned %s", article_url, resp.status_code
                )
                return None
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as exc:
            logger.warning("kstyle: detail fetch failed %s (%s)", article_url, exc)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        lines = self._extract_article_lines(soup)
        if not lines:
            return None

        section_text = self._extract_concert_info_section(lines)
        if not section_text:
            return None
        if not self._is_japan_show(section_text):
            return None

        venue_text = self._extract_venue(section_text)
        date_text = self._extract_date_line(section_text)
        return section_text, venue_text, date_text

    def _extract_article_lines(self, soup: BeautifulSoup) -> list[str]:
        for selector in self.ARTICLE_TEXT_SELECTORS:
            node = soup.select_one(selector)
            if node is None:
                continue
            lines = [
                " ".join(text.split())
                for text in node.stripped_strings
                if text and " ".join(text.split())
            ]
            if lines:
                return lines
        return []

    def _extract_concert_info_section(self, lines: list[str]) -> str | None:
        start_idx: int | None = None
        for idx, line in enumerate(lines):
            if any(marker in line for marker in self.CONCERT_INFO_MARKERS):
                start_idx = idx
                break
        if start_idx is None:
            return None

        section_lines: list[str] = []
        for idx in range(start_idx, len(lines)):
            line = lines[idx].strip()
            if not line:
                continue
            if idx > start_idx and any(
                line.startswith(marker) for marker in self.SECTION_STOP_MARKERS
            ):
                break
            section_lines.append(line)

        if not section_lines:
            return None
        return " ".join(section_lines)

    def _extract_venue(self, text: str) -> str | None:
        match = self.VENUE_RE.search(text)
        if not match:
            return None
        return " ".join(match.group(1).split())

    def _extract_date_line(self, text: str) -> str | None:
        tokens = re.split(r"(?=【)|(?=■)", text)
        for token in tokens:
            if self.DATE_LINE_RE.search(token):
                return " ".join(token.split())
        return None

    def _is_japan_show(self, text: str) -> bool:
        return any(term in text for term in self.JAPAN_TERMS)

    def _extract_event_date_range(self, text: str) -> tuple[str | None, str | None]:
        dates: list[str] = []
        for match in self.DATE_TOKEN_RE.finditer(text):
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            try:
                date_text = datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                continue
            dates.append(date_text)

        if not dates:
            return None, None
        dates_sorted = sorted(set(dates))
        return dates_sorted[0], dates_sorted[-1]

    def _infer_artist_name(self, title: str) -> str:
        normalized = " ".join(title.split())
        for splitter in ["、", "「", "（", "("]:
            if splitter in normalized:
                head = normalized.split(splitter, 1)[0].strip()
                if head:
                    return head
        return normalized

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

    def _find_container(self, tag: Tag) -> Tag | None:
        node: Tag | None = tag
        for _ in range(6):
            if node is None:
                return None
            text = " ".join(node.get_text(" ", strip=True).split())
            if self.DATETIME_RE.search(text):
                return node
            parent = node.parent
            node = parent if isinstance(parent, Tag) else None
        return None

    def _extract_snippet(self, container: Tag | None, title: str) -> str | None:
        if container is None:
            return None
        for p in container.find_all("p"):
            text = " ".join(p.get_text(" ", strip=True).split())
            if not text or text == title:
                continue
            if self.DATETIME_RE.search(text):
                continue
            if len(text) < 20:
                continue
            return trim_snippet(text)
        return None

    def _score_and_labels(
        self, title: str, snippet: str | None
    ) -> tuple[int, dict[str, object]]:
        blob = f"{title} {snippet or ''}"
        score = 70
        include_hits = sum(1 for t in self.INCLUDE_TERMS if t in blob)
        exclude_hits = sum(1 for t in self.EXCLUDE_TERMS if t.lower() in blob.lower())
        location_hits = sum(1 for t in self.LOCATION_TERMS if t in blob)

        score += include_hits * 8
        score += location_hits * 6
        score -= exclude_hits * 10
        score = max(0, min(score, 100))

        labels = {
            "jp_show": include_hits > 0,
            "announce": any(
                term in blob for term in ["決定", "開催", "公演", "チケット", "先行"]
            ),
            "location_hit": location_hits > 0,
            "noise_penalty": exclude_hits > 0,
            "include_hits": include_hits,
            "exclude_hits": exclude_hits,
            "has_concert_info": any(
                marker in blob for marker in self.CONCERT_INFO_MARKERS
            ),
        }
        return score, labels

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
