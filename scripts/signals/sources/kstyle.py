"""Kstyle category news source plugin."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..artist_registry import (
    build_artist_index,
    choose_primary_match,
    load_registry,
    match_artists_in_title,
)
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
    PREFECTURE_TERMS = [
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
    ]
    MAJOR_CITY_TERMS = [
        "東京",
        "大阪",
        "名古屋",
        "福岡",
        "札幌",
        "横浜",
        "神戸",
        "仙台",
    ]
    VENUE_RE = re.compile(
        r"【(?:会場|開催場所|場所)】\s*[:：]?\s*(.+?)(?=【|■|$)", re.S
    )
    VENUE_FALLBACK_RE = re.compile(
        r"(?:会場|開催場所|場所)\s*[:：]\s*(.+?)(?=【|■|$)", re.S
    )
    DATE_LINE_RE = re.compile(r"(?:日時|日程|公演日|開催日|開演|DAY\d)")
    DATE_TOKEN_RE = re.compile(r"(?:(\d{4})[./年-]\s*(\d{1,2})[./月-]\s*(\d{1,2})日?)")
    PREF_VENUE_LINE_RE = re.compile(
        r"^[\[［]\s*(?P<pref>[^\]］]+?)\s*[\]］]\s*(?P<venue>.+)$"
    )
    _ARTIST_INDEX_CACHE: dict[str, object] | None = None

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
            detail = self._fetch_article_detail(abs_url, title)
            if detail is None:
                continue
            section_lines, title_raw = detail
            occurrences = self._extract_occurrences(section_lines)
            if not occurrences:
                continue

            section_text = " ".join(section_lines)
            score, base_labels = self._score_and_labels(title, section_text)
            artist_name, artist_labels = self._resolve_artist_from_title(title_raw)
            for event_date, venue_name, event_info, pref_name in occurrences:
                labels = dict(base_labels)
                labels["artist_name"] = artist_name
                labels.update(artist_labels)
                labels["venue_name"] = venue_name
                labels["event_info"] = event_info
                labels["event_start_date"] = event_date
                labels["event_end_date"] = event_date
                if pref_name:
                    labels["pref_name"] = pref_name

                snippet = trim_snippet(
                    " / ".join(
                        [
                            f"会場: {venue_name}",
                            f"日時: {event_date}",
                            event_info,
                        ]
                    )
                )
                venue_key = self._normalize_venue_name(venue_name)
                extra_key = f"{event_date}|{venue_key}"
                rec = SignalRecord(
                    signal_uid=compute_signal_uid(source_id, abs_url, extra_key),
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
        self, article_url: str, fallback_title: str
    ) -> tuple[list[str], str] | None:
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

        section_lines = self._extract_concert_info_section(lines)
        if not section_lines:
            return None
        if not self._is_japan_show(" ".join(section_lines)):
            return None
        title_raw = self._extract_article_title(soup, fallback_title)
        return section_lines, title_raw

    def _extract_article_title(self, soup: BeautifulSoup, fallback_title: str) -> str:
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title is not None:
            content = str(og_title.get("content", "")).strip()
            if content:
                return self._strip_title_decorations(content)

        h1 = soup.select_one("h1")
        if h1 is not None:
            text = " ".join(h1.get_text(" ", strip=True).split())
            if text:
                return self._strip_title_decorations(text)

        return self._strip_title_decorations(fallback_title)

    def _strip_title_decorations(self, text: str) -> str:
        out = " ".join(text.split())
        for _ in range(6):
            next_out = re.sub(
                r"^\s*(?:【[^】]*】|\[[^\]]*\]|［[^］]*］|＜[^＞]*＞|<[^>]*>)\s*",
                "",
                out,
            )
            if next_out == out:
                break
            out = next_out
        return out.strip()

    def _resolve_artist_from_title(
        self, title_raw: str
    ) -> tuple[str, dict[str, object]]:
        index = self._get_artist_index()
        matches = match_artists_in_title(title_raw, index)
        primary, confidence = choose_primary_match(matches)
        if primary is not None:
            return str(primary.get("canonical_name", "")), {
                "artist_id": str(primary.get("artist_id", "")),
                "artist_confidence": confidence,
                "artist_matched_alias": str(primary.get("matched_alias", "")),
                "artist_raw": title_raw,
            }

        fallback = self._infer_artist_name(title_raw)
        return fallback, {
            "artist_confidence": "low",
            "artist_raw": title_raw,
        }

    @classmethod
    def _get_artist_index(cls) -> dict[str, object]:
        if cls._ARTIST_INDEX_CACHE is None:
            cls._ARTIST_INDEX_CACHE = build_artist_index(load_registry())
        return cls._ARTIST_INDEX_CACHE

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

    def _extract_concert_info_section(self, lines: list[str]) -> list[str] | None:
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
        return section_lines

    def _extract_venue(self, text: str) -> str | None:
        match = self.VENUE_RE.search(text)
        if not match:
            match = self.VENUE_FALLBACK_RE.search(text)
        if not match:
            return None
        return " ".join(match.group(1).split())

    def _extract_date_line(self, text: str) -> str | None:
        tokens = re.split(r"(?=【)|(?=■)", text)
        for token in tokens:
            if self.DATE_LINE_RE.search(token):
                return " ".join(token.split())
        return None

    def _extract_occurrences(
        self, section_lines: list[str]
    ) -> list[tuple[str, str, str, str]]:
        occurrences: list[tuple[str, str, str, str]] = []
        current_venue = ""
        current_pref = ""
        for line in section_lines:
            normalized_line = " ".join(line.split())
            pref_venue_match = self.PREF_VENUE_LINE_RE.match(normalized_line)
            if pref_venue_match:
                current_venue = self._normalize_venue_name(
                    pref_venue_match.group("venue")
                )
                current_pref = self._normalize_pref_name(pref_venue_match.group("pref"))

            venue_on_line = self._extract_venue(normalized_line)
            if venue_on_line:
                current_venue = venue_on_line
                if not pref_venue_match:
                    current_pref = ""

            event_dates = self._extract_event_dates_from_line(normalized_line)
            if not event_dates:
                continue
            if not current_venue:
                continue

            event_info = normalized_line
            venue_name = self._normalize_venue_name(current_venue)
            for event_date in event_dates:
                occurrences.append((event_date, venue_name, event_info, current_pref))

        deduped: dict[tuple[str, str], tuple[str, str, str, str]] = {}
        for event_date, venue_name, event_info, pref_name in occurrences:
            deduped[(event_date, venue_name)] = (
                event_date,
                venue_name,
                event_info,
                pref_name,
            )
        return sorted(deduped.values(), key=lambda row: (row[0], row[1]))

    def _extract_event_dates_from_line(self, line: str) -> list[str]:
        matches = list(self.DATE_TOKEN_RE.finditer(line))
        if not matches:
            return []

        if len(matches) >= 2 and re.search(r"[〜～\-−ー]", line):
            start = self._match_to_date(matches[0])
            end = self._match_to_date(matches[1])
            if start and end and start <= end:
                return self._expand_date_range(start, end)

        out: list[str] = []
        for match in matches:
            date_text = self._match_to_date(match)
            if date_text:
                out.append(date_text)
        return sorted(set(out))

    def _match_to_date(self, match: re.Match[str]) -> str | None:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _expand_date_range(self, start: str, end: str) -> list[str]:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            return []
        if end_dt < start_dt:
            return []
        days = (end_dt - start_dt).days
        return [
            (start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days + 1)
        ]

    def _normalize_venue_name(self, venue_name: str) -> str:
        return " ".join(str(venue_name).split())

    @staticmethod
    def _normalize_pref_name(value: str | None) -> str:
        pref = str(value or "").strip()
        if not pref:
            return ""
        if pref in ("東京", "東京都"):
            return "東京都"
        if pref in ("大阪", "大阪府"):
            return "大阪府"
        if pref in ("京都", "京都府"):
            return "京都府"
        if pref == "北海道":
            return "北海道"
        if pref.endswith(("都", "道", "府", "県")):
            return pref
        return f"{pref}県"

    def _is_japan_show(self, text: str) -> bool:
        has_japan_word = "日本" in text
        has_prefecture = any(term in text for term in self.PREFECTURE_TERMS)
        has_major_city = any(term in text for term in self.MAJOR_CITY_TERMS)
        return has_japan_word or has_prefecture or has_major_city

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
