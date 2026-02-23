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
    """Fetch Kstyle category list pages and score event-like signals."""

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
        records: list[SignalRecord] = []
        for a in soup.select('a[href*="article.ksn?articleNo="]'):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            title = " ".join(a.get_text(" ", strip=True).split())
            if not title:
                continue

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

            snippet = self._extract_snippet(container, title)
            abs_url = urljoin(page_url, href)
            score, labels = self._score_and_labels(title, snippet)

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
        score = 30
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
