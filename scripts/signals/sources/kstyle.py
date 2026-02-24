"""Kstyle category news source plugin."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

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

    SEARCH_WORD = "■公演情報"
    SEARCH_BASE_URL = "https://kstyle.com/search.ksn"
    EVENTS_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "events.sqlite"
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
    CONCERT_INFO_MARKERS = ("■公演情報", "■ 公演情報")
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
    JP_PREF_MAP = {
        "北海道": "北海道",
        "青森": "青森県",
        "青森県": "青森県",
        "岩手": "岩手県",
        "岩手県": "岩手県",
        "宮城": "宮城県",
        "宮城県": "宮城県",
        "秋田": "秋田県",
        "秋田県": "秋田県",
        "山形": "山形県",
        "山形県": "山形県",
        "福島": "福島県",
        "福島県": "福島県",
        "茨城": "茨城県",
        "茨城県": "茨城県",
        "栃木": "栃木県",
        "栃木県": "栃木県",
        "群馬": "群馬県",
        "群馬県": "群馬県",
        "埼玉": "埼玉県",
        "埼玉県": "埼玉県",
        "千葉": "千葉県",
        "千葉県": "千葉県",
        "東京": "東京都",
        "東京都": "東京都",
        "神奈川": "神奈川県",
        "神奈川県": "神奈川県",
        "新潟": "新潟県",
        "新潟県": "新潟県",
        "富山": "富山県",
        "富山県": "富山県",
        "石川": "石川県",
        "石川県": "石川県",
        "福井": "福井県",
        "福井県": "福井県",
        "山梨": "山梨県",
        "山梨県": "山梨県",
        "長野": "長野県",
        "長野県": "長野県",
        "岐阜": "岐阜県",
        "岐阜県": "岐阜県",
        "静岡": "静岡県",
        "静岡県": "静岡県",
        "愛知": "愛知県",
        "愛知県": "愛知県",
        "三重": "三重県",
        "三重県": "三重県",
        "滋賀": "滋賀県",
        "滋賀県": "滋賀県",
        "京都": "京都府",
        "京都府": "京都府",
        "大阪": "大阪府",
        "大阪府": "大阪府",
        "兵庫": "兵庫県",
        "兵庫県": "兵庫県",
        "奈良": "奈良県",
        "奈良県": "奈良県",
        "和歌山": "和歌山県",
        "和歌山県": "和歌山県",
        "鳥取": "鳥取県",
        "鳥取県": "鳥取県",
        "島根": "島根県",
        "島根県": "島根県",
        "岡山": "岡山県",
        "岡山県": "岡山県",
        "広島": "広島県",
        "広島県": "広島県",
        "山口": "山口県",
        "山口県": "山口県",
        "徳島": "徳島県",
        "徳島県": "徳島県",
        "香川": "香川県",
        "香川県": "香川県",
        "愛媛": "愛媛県",
        "愛媛県": "愛媛県",
        "高知": "高知県",
        "高知県": "高知県",
        "福岡": "福岡県",
        "福岡県": "福岡県",
        "佐賀": "佐賀県",
        "佐賀県": "佐賀県",
        "長崎": "長崎県",
        "長崎県": "長崎県",
        "熊本": "熊本県",
        "熊本県": "熊本県",
        "大分": "大分県",
        "大分県": "大分県",
        "宮崎": "宮崎県",
        "宮崎県": "宮崎県",
        "鹿児島": "鹿児島県",
        "鹿児島県": "鹿児島県",
        "沖縄": "沖縄県",
        "沖縄県": "沖縄県",
    }
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
    DATE_TOKEN_RE = re.compile(
        r"(?:(?P<year>\d{4})\s*[./年-]\s*)?"
        r"(?P<month>\d{1,2})\s*[./月-]\s*(?P<day>\d{1,2})\s*日?"
    )
    DAY_ONLY_RE = re.compile(r"(?<!\d)(?P<day>\d{1,2})\s*日")
    PREF_VENUE_LINE_RE = re.compile(
        r"^[\[［]\s*(?P<pref>[^\]］]+?)\s*[\]］]\s*(?P<venue>.+)$"
    )
    NON_EVENT_DATE_TERMS = (
        "申込期間",
        "受付期間",
        "受付中",
        "当選発表",
        "入金期限",
        "先着受付",
        "先行",
        "販売期間",
        "発売",
        "実施期間",
        "締切",
        "終演まで",
        "インバウンド受付",
        "会員先行",
        "オフィシャル先行",
        "先行受付",
        "当日引換券",
    )
    _ARTIST_INDEX_CACHE: dict[str, object] | None = None
    _OFFICIAL_VENUE_PREF_CACHE: dict[str, str] | None = None
    OFFICIAL_VENUE_PREF_ALIASES = {
        "MUFG STADIUM": "東京都",
        "MUFG STADIUM（国立競技場）": "東京都",
        "国立競技場": "東京都",
    }

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        # Keep enough lookback while avoiding timeout-prone deep pagination.
        pages = max(1, int(cfg.get("pages", 8)))
        pages = max(pages, 8)
        search_url = self._resolve_search_url(source.source_url, cfg)
        first_page_url = self._with_page_param(search_url, 1)
        first_resp = self._get_with_retry(first_page_url, timeout=30)
        first_resp.raise_for_status()
        first_resp.encoding = first_resp.apparent_encoding or "utf-8"

        urls = [first_resp.url] + [
            self._with_page_param(search_url, page_num)
            for page_num in range(2, pages + 1)
        ]

        signals: dict[str, SignalRecord] = {}
        seen_article_urls: set[str] = set()
        for page_url in urls[:pages]:
            resp = (
                first_resp
                if page_url == first_resp.url
                else self._get_with_retry(page_url, timeout=30)
            )
            if resp.status_code != 200:
                logger.warning("kstyle: %s returned %s", page_url, resp.status_code)
                continue
            if resp is not first_resp:
                resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            if not soup.select('a[href*="article.ksn?articleNo="]'):
                logger.info("kstyle: no article cards on %s; stop paging", page_url)
                break
            for rec in self._parse_page(
                soup, resp.url, source.source_id, seen_article_urls
            ):
                signals[rec.signal_uid] = rec

        return sorted(signals.values(), key=lambda r: r.published_at_utc, reverse=True)

    def _parse_page(
        self,
        soup: BeautifulSoup,
        page_url: str,
        source_id: str,
        seen_article_urls: set[str] | None = None,
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
            if seen_article_urls is not None and abs_url in seen_article_urls:
                continue
            seen_urls.add(abs_url)

            container = self._find_container(a)
            context = (
                " ".join(container.get_text(" ", strip=True).split())
                if container
                else ""
            )
            if not self._is_event_candidate(title, context):
                continue
            dt_match = self.DATETIME_RE.search(context)
            if not dt_match:
                continue
            published_at_utc = self._to_utc_datetime(dt_match.group(1))
            if not published_at_utc:
                continue

            candidates.append((title, abs_url, published_at_utc))
            if seen_article_urls is not None:
                seen_article_urls.add(abs_url)

        records: list[SignalRecord] = []
        for title, abs_url, published_at_utc in candidates:
            detail = self._fetch_article_detail(abs_url, title)
            if detail is None:
                continue
            section_lines, title_raw, concert_title = detail
            default_year = self._default_year_from_utc(published_at_utc)
            occurrences = self._extract_occurrences(
                section_lines, default_year=default_year
            )
            if not occurrences:
                continue
            if not self._is_japan_occurrence(section_lines, occurrences):
                continue

            display_title = concert_title or title
            section_text = " ".join(section_lines)
            score, base_labels = self._score_and_labels(display_title, section_text)
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
                    title=display_title,
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
    ) -> tuple[list[str], str, str] | None:
        try:
            resp = self._get_with_retry(article_url, timeout=30)
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
        title_raw = self._extract_article_title(soup, fallback_title)
        concert_title = self._extract_concert_title_from_section(section_lines)
        return section_lines, title_raw, concert_title

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

    def _extract_concert_title_from_section(self, section_lines: list[str]) -> str:
        if len(section_lines) <= 1:
            return ""
        for line in section_lines[1:]:
            text = self._normalize_concert_title(line)
            if not text:
                continue
            if text.startswith("【") and text.endswith("】"):
                continue
            if text.startswith("[") and text.endswith("]"):
                continue
            if "日程" in text and "会場" in text:
                continue
            return text
        return ""

    @staticmethod
    def _normalize_concert_title(value: str) -> str:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            return ""
        if len(text) >= 2 and (
            (text.startswith("「") and text.endswith("」"))
            or (text.startswith("『") and text.endswith("』"))
            or (text.startswith('"') and text.endswith('"'))
        ):
            text = text[1:-1].strip()
        return text

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
        self, section_lines: list[str], default_year: int | None = None
    ) -> list[tuple[str, str, str, str]]:
        occurrences: list[tuple[str, str, str, str]] = []
        current_venue = self._extract_default_venue(section_lines)
        current_pref = self._pref_from_official_venue(
            current_venue
        ) or self._pref_from_text(current_venue)
        expect_venue_next = False
        for line in section_lines:
            normalized_line = " ".join(line.split())
            if any(marker in normalized_line for marker in ("元記事配信日時", "記者")):
                continue
            if re.fullmatch(r"\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}", normalized_line):
                continue
            if normalized_line in ("【会場】", "【開催場所】", "【場所】"):
                expect_venue_next = True
                continue

            if expect_venue_next:
                venue_candidate = self._normalize_venue_name(normalized_line)
                if venue_candidate and not any(
                    marker in venue_candidate for marker in ["【", "■", "DAY", "日時"]
                ):
                    current_venue = venue_candidate
                    current_pref = self._pref_from_official_venue(
                        current_venue
                    ) or self._pref_from_text(current_venue)
                expect_venue_next = False

            pref_venue_match = self.PREF_VENUE_LINE_RE.match(normalized_line)
            if pref_venue_match and not self._is_pref_token(
                pref_venue_match.group("pref")
            ):
                pref_venue_match = None
            if pref_venue_match:
                current_venue = self._normalize_venue_name(
                    pref_venue_match.group("venue")
                )
                current_pref = self._normalize_pref_name(
                    pref_venue_match.group("pref")
                ) or self._pref_from_official_venue(
                    current_venue
                ) or self._pref_from_text(current_venue)

            venue_on_line = self._extract_venue(normalized_line)
            if venue_on_line:
                current_venue = venue_on_line
                if not pref_venue_match:
                    current_pref = self._pref_from_official_venue(
                        current_venue
                    ) or self._pref_from_text(current_venue)

            event_dates = self._extract_event_dates_from_line(
                normalized_line, default_year=default_year
            )
            if not event_dates:
                continue
            if any(term in normalized_line for term in self.NON_EVENT_DATE_TERMS):
                continue

            inline_pref, inline_venue = self._extract_pref_venue_from_date_line(
                normalized_line
            )
            if inline_venue:
                current_venue = inline_venue
                current_pref = (
                    inline_pref
                    or self._pref_from_official_venue(current_venue)
                    or self._pref_from_text(current_venue)
                )
            if not current_venue:
                continue

            event_info = normalized_line
            venue_name = self._normalize_venue_name(current_venue)
            pref_name = (
                current_pref
                or self._pref_from_official_venue(venue_name)
                or self._pref_from_text(venue_name)
            )
            for event_date in event_dates:
                occurrences.append((event_date, venue_name, event_info, pref_name))

        deduped: dict[tuple[str, str], tuple[str, str, str, str]] = {}
        for event_date, venue_name, event_info, pref_name in occurrences:
            deduped[(event_date, venue_name)] = (
                event_date,
                venue_name,
                event_info,
                pref_name,
            )
        return sorted(deduped.values(), key=lambda row: (row[0], row[1]))

    def _extract_pref_venue_from_date_line(self, line: str) -> tuple[str, str]:
        date_match = self.DATE_TOKEN_RE.search(line)
        if date_match is None:
            return "", ""

        rest = line[date_match.end() :].strip()
        rest = re.sub(r"^[（(][^）)]{1,8}[）)]\s*", "", rest)
        if not rest:
            return "", ""

        rest = re.split(
            r"(?:開場|開演|START|DOOR|チケット|問い合わせ|お問合せ|※)",
            rest,
            maxsplit=1,
        )[0].strip()
        if not rest:
            return "", ""
        rest_nfkc = unicodedata.normalize("NFKC", rest)
        if re.match(r"^\d{1,2}:\d{2}", rest_nfkc):
            return "", ""

        pref_venue_match = self.PREF_VENUE_LINE_RE.match(rest)
        if pref_venue_match:
            pref_name = self._normalize_pref_name(pref_venue_match.group("pref"))
            venue_name = self._normalize_venue_name(pref_venue_match.group("venue"))
            return pref_name, venue_name
        return "", self._normalize_venue_name(rest)

    def _is_pref_token(self, value: str) -> bool:
        token = str(value or "").strip()
        if not token:
            return False
        token_nfkc = unicodedata.normalize("NFKC", token)
        if re.search(r"\d", token_nfkc):
            return False
        if token_nfkc.endswith("部") or token_nfkc.startswith("DAY"):
            return False
        if token_nfkc in self.JP_PREF_MAP:
            return True
        return bool(re.fullmatch(r"[A-Z][A-Z\s\-]{2,20}", token_nfkc))

    def _extract_default_venue(self, section_lines: list[str]) -> str:
        for idx, line in enumerate(section_lines):
            normalized = " ".join(line.split())
            venue_on_line = self._extract_venue(normalized)
            if venue_on_line:
                return self._normalize_venue_name(venue_on_line)
            if normalized in ("【会場】", "【開催場所】", "【場所】"):
                for next_line in section_lines[idx + 1 :]:
                    candidate = self._normalize_venue_name(" ".join(next_line.split()))
                    if not candidate:
                        continue
                    if any(marker in candidate for marker in ["【", "■", "DAY", "日時"]):
                        continue
                    return candidate
        return ""

    def _extract_event_dates_from_line(
        self, line: str, default_year: int | None = None
    ) -> list[str]:
        matches = list(self.DATE_TOKEN_RE.finditer(line))
        if not matches:
            return []

        out: list[str] = []
        last_year = default_year
        last_month: int | None = None
        spans = [(m.start(), m.end()) for m in matches]

        for match in matches:
            year_text = match.group("year")
            month = int(match.group("month"))
            day = int(match.group("day"))
            if year_text:
                last_year = int(year_text)
            if last_year is None:
                continue
            date_text = self._to_date_text(last_year, month, day)
            if date_text:
                out.append(date_text)
                last_month = month

        if out and last_month is not None:
            for day_match in self.DAY_ONLY_RE.finditer(line):
                span = (day_match.start(), day_match.end())
                if any(span[0] >= s and span[1] <= e for s, e in spans):
                    continue
                if last_year is None:
                    break
                day = int(day_match.group("day"))
                date_text = self._to_date_text(last_year, last_month, day)
                if date_text:
                    out.append(date_text)

        return sorted(set(out))

    def _to_date_text(self, year: int, month: int, day: int) -> str | None:
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _default_year_from_utc(value: str) -> int | None:
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").year
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
    def _normalize_venue_lookup_key(value: str | None) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).lower()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[()（）\[\]［］{}【】「」『』\"'`~^!?,.:：;／/\\|+-]", "", text)
        return text

    @classmethod
    def _load_official_venue_pref_cache(cls) -> dict[str, str]:
        if cls._OFFICIAL_VENUE_PREF_CACHE is not None:
            return cls._OFFICIAL_VENUE_PREF_CACHE

        lookup: dict[str, str] = {}
        if cls.EVENTS_DB_PATH.exists():
            conn = sqlite3.connect(str(cls.EVENTS_DB_PATH))
            try:
                cur = conn.execute(
                    """
                    SELECT venue_name, pref_name
                    FROM venues
                    WHERE venue_name IS NOT NULL
                      AND pref_name IS NOT NULL
                    """
                )
                for venue_name, pref_name in cur.fetchall():
                    key = cls._normalize_venue_lookup_key(str(venue_name))
                    pref = cls._normalize_pref_name(str(pref_name))
                    if key and pref and key not in lookup:
                        lookup[key] = pref
            except sqlite3.Error as exc:
                logger.warning("kstyle: failed to load events.sqlite venues (%s)", exc)
            finally:
                conn.close()

        for alias, pref_name in cls.OFFICIAL_VENUE_PREF_ALIASES.items():
            key = cls._normalize_venue_lookup_key(alias)
            pref = cls._normalize_pref_name(pref_name)
            if key and pref:
                lookup[key] = pref

        cls._OFFICIAL_VENUE_PREF_CACHE = lookup
        return lookup

    def _pref_from_official_venue(self, venue_name: str | None) -> str:
        key = self._normalize_venue_lookup_key(venue_name)
        if not key:
            return ""

        lookup = self._load_official_venue_pref_cache()
        direct = lookup.get(key)
        if direct:
            return direct

        best_pref = ""
        best_score = 0
        for venue_key, pref_name in lookup.items():
            if len(venue_key) < 4:
                continue
            if key in venue_key or venue_key in key:
                score = min(len(key), len(venue_key))
                if score > best_score:
                    best_score = score
                    best_pref = pref_name
        return best_pref

    @staticmethod
    def _normalize_pref_name(value: str | None) -> str:
        pref = str(value or "").strip()
        if not pref:
            return ""
        return KstyleMusicSource.JP_PREF_MAP.get(pref, "")

    def _pref_from_text(self, value: str | None) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        for key in sorted(self.JP_PREF_MAP.keys(), key=len, reverse=True):
            if key and key in text:
                pref_name = self.JP_PREF_MAP.get(key, "")
                if pref_name:
                    return pref_name
        return ""

    def _is_japan_occurrence(
        self,
        section_lines: list[str],
        occurrences: list[tuple[str, str, str, str]],
    ) -> bool:
        if self._is_japan_show(" ".join(section_lines)):
            return True
        for _, venue_name, _, pref_name in occurrences:
            if self._normalize_pref_name(pref_name):
                return True
            if self._pref_from_official_venue(venue_name):
                return True
            if self._pref_from_text(venue_name):
                return True
            if any(term in venue_name for term in self.PREFECTURE_TERMS):
                return True
            if any(term in venue_name for term in self.MAJOR_CITY_TERMS):
                return True
        return False

    def _is_japan_show(self, text: str) -> bool:
        has_japan_word = "日本" in text
        has_prefecture = any(term in text for term in self.PREFECTURE_TERMS)
        has_major_city = any(term in text for term in self.MAJOR_CITY_TERMS)
        return has_japan_word or has_prefecture or has_major_city

    def _extract_event_date_range(self, text: str) -> tuple[str | None, str | None]:
        dates: list[str] = []
        for match in self.DATE_TOKEN_RE.finditer(text):
            year_text = match.group("year")
            if not year_text:
                continue
            year = int(year_text)
            month = int(match.group("month"))
            day = int(match.group("day"))
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

    def _is_event_candidate(self, title: str, context: str) -> bool:
        blob = f"{title} {context}"
        include_hits = sum(1 for t in self.INCLUDE_TERMS if t in blob)
        if include_hits == 0:
            return False
        exclude_hits = sum(1 for t in self.EXCLUDE_TERMS if t.lower() in blob.lower())
        return include_hits > exclude_hits

    @staticmethod
    def _load_config(config_json: str | None) -> dict:
        if not config_json:
            return {}
        try:
            parsed = json.loads(config_json)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _resolve_search_url(self, source_url: str, cfg: dict) -> str:
        search_word = str(cfg.get("search_word") or self.SEARCH_WORD).strip()
        if not search_word:
            search_word = self.SEARCH_WORD

        source = source_url.strip()
        if "search.ksn" in source:
            parts = urlsplit(source)
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query["searchWord"] = search_word
            return urlunsplit(
                (
                    parts.scheme or "https",
                    parts.netloc or "kstyle.com",
                    parts.path or "/search.ksn",
                    urlencode(query),
                    "",
                )
            )

        return urlunsplit(
            (
                "https",
                "kstyle.com",
                "/search.ksn",
                urlencode({"searchWord": search_word}),
                "",
            )
        )

    @staticmethod
    def _with_page_param(url: str, page_num: int) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["page"] = str(page_num)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    @staticmethod
    def _to_utc_datetime(value: str) -> str | None:
        try:
            dt_jst = datetime.strptime(value, "%Y/%m/%d %H:%M").replace(
                tzinfo=timezone(timedelta(hours=9))
            )
        except ValueError:
            return None
        return dt_jst.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _get_with_retry(self, url: str, timeout: int = 30, retries: int = 3):
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                return self.session.get(url, timeout=timeout)
            except Exception as exc:  # requests/urllib exceptions
                last_exc = exc
                if attempt >= retries:
                    break
                wait_sec = 1.5 * attempt
                logger.warning(
                    "kstyle: request retry %d/%d for %s after %s",
                    attempt,
                    retries,
                    url,
                    exc.__class__.__name__,
                )
                time.sleep(wait_sec)
        assert last_exc is not None
        raise last_exc
