"""Ticketjam event source plugin (secondary market reference feed)."""

from __future__ import annotations

import csv
import gzip
import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from ..types import SignalRecord, SignalSourceRecord
from .base import (
    JST,
    SignalSource,
    canonical_labels_json,
    compute_content_hash,
    compute_signal_uid,
    to_utc_z_from_jst_date,
    trim_snippet,
)

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]


class TicketjamEventsSource(SignalSource):
    """Fetch Ticketjam event pages via venue pages (preferred) or legacy sitemaps."""

    _START_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?")
    _EVENT_URL_RE = re.compile(r"^https://ticketjam\.jp/tickets/[^/]+/event/\d+$")
    _TITLE_OPTION_RE = re.compile(
        r"(\d{1,2})/(\d{1,2})\([^)]*\)\s+(\d{2}:\d{2})\s+(.+)$"
    )
    _VENUE_PAGE_EVENT_LINK_SELECTOR = "a.p-event-min__link[href]"
    _SKIP_EVENT_HINTS = ("駐車場券", "駐車券", "駐車場")

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        cfg = self._normalize_legacy_config(cfg)
        timeout_sec = max(10, int(cfg.get("timeout_sec", 30)))
        request_retries = max(1, int(cfg.get("request_retries", 3)))
        future_only = bool(cfg.get("future_only", True))
        lookback_days = max(0, int(cfg.get("lookback_days", 0)))
        min_event_date = (datetime.now(JST).date() - timedelta(days=lookback_days)).isoformat()
        allowed_event_types = self._resolve_allowed_types(cfg)
        discovery_mode = str(cfg.get("discovery_mode", "sitemap")).strip().lower()
        if discovery_mode == "venue_pages":
            event_urls = self._load_event_urls_from_venue_pages(
                cfg,
                timeout_sec=timeout_sec,
                request_retries=request_retries,
            )
        else:
            event_urls = self._load_event_urls_from_sitemaps(
                source.source_url,
                cfg,
                timeout_sec=timeout_sec,
                request_retries=request_retries,
                source=source,
            )
        if not event_urls:
            logger.warning("ticketjam: no event URLs after discovery")
            return []

        records: list[SignalRecord] = []
        for event_url in event_urls:
            rec = self._fetch_event_signal(
                source.source_id,
                event_url,
                timeout_sec,
                request_retries=request_retries,
                min_event_date=min_event_date,
                future_only=future_only,
                allowed_event_types=allowed_event_types,
            )
            if rec:
                records.append(rec)

        records = self._dedupe_records(records)
        records.sort(key=lambda row: row.published_at_utc, reverse=True)
        if not records:
            logger.warning("ticketjam: parsed 0 valid signals from %s", source.source_id)
        return records

    def _load_event_urls_from_venue_pages(
        self,
        cfg: dict[str, object],
        *,
        timeout_sec: int,
        request_retries: int,
    ) -> list[str]:
        venue_pages = self._load_ticketjam_venue_pages(cfg)
        if not venue_pages:
            logger.warning("ticketjam: no ticketjam venue pages configured")
            return []
        raw_skip_keywords = cfg.get("exclude_title_keywords") or list(self._SKIP_EVENT_HINTS)
        skip_keywords = tuple(
            str(value).strip() for value in raw_skip_keywords if str(value).strip()
        ) or self._SKIP_EVENT_HINTS

        event_url_map: dict[str, str] = {}
        scanned_venues = 0
        for venue in venue_pages:
            venue_url = str(venue.get("ticketjam_venue_url") or "").strip()
            if not venue_url:
                continue
            scanned_venues += 1
            event_links = self._load_event_urls_from_venue_page(
                venue_url,
                timeout_sec=timeout_sec,
                request_retries=request_retries,
                skip_keywords=skip_keywords,
            )
            for event_url in event_links:
                event_id = self._extract_event_id(event_url)
                event_key = event_id or event_url
                event_url_map[event_key] = event_url

        logger.info(
            "ticketjam: venue pages=%d urls=%d",
            scanned_venues,
            len(event_url_map),
        )
        return list(event_url_map.values())

    def _load_ticketjam_venue_pages(
        self, cfg: dict[str, object]
    ) -> list[dict[str, str]]:
        raw_path = str(
            cfg.get("venue_pages_csv") or "data/ticketjam_venue_pages.csv"
        ).strip()
        if not raw_path:
            return []
        csv_path = Path(raw_path)
        if not csv_path.is_absolute():
            csv_path = REPO_ROOT / csv_path
        if not csv_path.exists():
            logger.warning("ticketjam: venue pages CSV missing: %s", csv_path)
            return []

        rows: list[dict[str, str]] = []
        include_disabled = bool(cfg.get("include_disabled_venues", False))
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                is_enabled = str(row.get("is_enabled", "1")).strip() == "1"
                if not include_disabled and not is_enabled:
                    continue
                rows.append({str(k): str(v or "").strip() for k, v in row.items()})
        return rows

    def _load_event_urls_from_venue_page(
        self,
        venue_url: str,
        *,
        timeout_sec: int,
        request_retries: int,
        skip_keywords: tuple[str, ...],
    ) -> list[str]:
        resp = self._get_with_retry(
            venue_url,
            timeout_sec=timeout_sec,
            request_retries=request_retries,
            kind="venue",
        )
        if resp is None or resp.status_code != 200:
            status = getattr(resp, "status_code", "n/a")
            logger.warning("ticketjam: venue page %s returned %s", venue_url, status)
            return []

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        sections = self._find_venue_event_sections(soup)

        event_urls: list[str] = []
        for section in sections:
            for anchor in section.select(self._VENUE_PAGE_EVENT_LINK_SELECTOR):
                href = str(anchor.get("href") or "").strip()
                if not href:
                    continue
                url = self._canonicalize_url(urljoin("https://ticketjam.jp", href))
                if not self._EVENT_URL_RE.match(url):
                    continue
                label = " ".join(anchor.get_text(" ", strip=True).split())
                if self._should_skip_event_link(label, skip_keywords):
                    continue
                event_urls.append(url)
        if event_urls:
            return list(dict.fromkeys(event_urls))

        # Fallback: if section detection failed, scan the whole page.
        for anchor in soup.select(self._VENUE_PAGE_EVENT_LINK_SELECTOR):
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue
            url = self._canonicalize_url(urljoin("https://ticketjam.jp", href))
            label = " ".join(anchor.get_text(" ", strip=True).split())
            if self._EVENT_URL_RE.match(url) and not self._should_skip_event_link(
                label, skip_keywords
            ):
                event_urls.append(url)
        return list(dict.fromkeys(event_urls))

    def _find_venue_event_sections(self, soup: BeautifulSoup) -> list[BeautifulSoup]:
        sections: list[BeautifulSoup] = []
        for section in soup.select(".l-section"):
            header = " ".join(
                section.select_one(".l-box-header").get_text(" ", strip=True).split()
            ) if section.select_one(".l-box-header") else ""
            if "イベント一覧" in header:
                sections.append(section)
        return sections

    def _should_skip_event_link(self, text: str, skip_keywords: tuple[str, ...]) -> bool:
        compact = " ".join(str(text or "").split())
        if not compact:
            return False
        return any(hint in compact for hint in skip_keywords)

    def _load_event_urls_from_sitemaps(
        self,
        index_url: str,
        cfg: dict[str, object],
        *,
        timeout_sec: int,
        request_retries: int,
        source: SignalSourceRecord,
    ) -> list[str]:
        max_sitemaps, max_event_urls = self._resolve_limits(source, cfg)
        max_sitemap_attempts = max(
            max_sitemaps,
            int(cfg.get("max_sitemap_attempts", max_sitemaps * 5)),
        )
        sitemap_items = self._load_sitemap_index(index_url, timeout_sec, request_retries)
        if not sitemap_items:
            logger.warning("ticketjam: no sitemap entries from %s", index_url)
            return []

        event_url_map: dict[str, tuple[str, str]] = {}
        sitemap_attempts = 0
        sitemap_successes = 0
        for sitemap_url, _ in sitemap_items:
            if sitemap_successes >= max_sitemaps:
                break
            if sitemap_attempts >= max_sitemap_attempts:
                break
            if not sitemap_url:
                continue

            sitemap_attempts += 1
            rows = self._load_event_urls(sitemap_url, timeout_sec, request_retries)
            if not rows:
                continue
            sitemap_successes += 1

            for event_url, lastmod in rows:
                if not self._EVENT_URL_RE.match(event_url):
                    continue
                event_id = self._extract_event_id(event_url)
                event_key = event_id or event_url
                prev = event_url_map.get(event_key)
                prev_lastmod = prev[1] if prev else ""
                if lastmod >= prev_lastmod:
                    event_url_map[event_key] = (event_url, lastmod)
            if len(event_url_map) >= max_event_urls:
                break

        logger.info(
            "ticketjam: sitemap attempts=%d successes=%d urls=%d",
            sitemap_attempts,
            sitemap_successes,
            len(event_url_map),
        )
        return [
            row[0]
            for _, row in sorted(
                event_url_map.items(), key=lambda kv: kv[1][1] or "", reverse=True
            )[:max_event_urls]
        ]

    def _dedupe_records(self, records: list[SignalRecord]) -> list[SignalRecord]:
        """Collapse duplicate listings for the same performance into one signal."""
        deduped: dict[tuple[str, str, str, str, str], SignalRecord] = {}
        for row in records:
            labels: dict[str, object] = {}
            if isinstance(row.labels_json, str) and row.labels_json.strip():
                try:
                    parsed = json.loads(row.labels_json)
                    if isinstance(parsed, dict):
                        labels = parsed
                except Exception:
                    labels = {}
            event_date = str(labels.get("event_start_date") or "").strip()
            event_time = str(labels.get("event_start_time") or "").strip()
            venue = str(labels.get("venue_name") or "").strip()
            artist = str(labels.get("artist_name") or "").strip()
            title = str(row.title or "").strip()
            key = (event_date, event_time, venue, artist, title)

            prev = deduped.get(key)
            if prev is None:
                deduped[key] = row
                continue
            # Deterministic tie-breaker: prefer lexicographically smaller canonical URL.
            if str(row.url or "") < str(prev.url or ""):
                deduped[key] = row
        return list(deduped.values())

    def _load_config(self, config_json: str | None) -> dict[str, object]:
        if not config_json:
            return {}
        try:
            obj = json.loads(config_json)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _normalize_legacy_config(self, cfg: dict[str, object]) -> dict[str, object]:
        """Upgrade old config variants to current safe defaults at runtime."""
        if not cfg:
            return cfg
        is_legacy = "discovery_mode" not in cfg and "venue_pages_csv" not in cfg
        if not is_legacy:
            return cfg

        upgraded = dict(cfg)
        upgraded["discovery_mode"] = "venue_pages"
        upgraded["venue_pages_csv"] = str(
            cfg.get("venue_pages_csv") or "data/ticketjam_venue_pages.csv"
        )
        upgraded["exclude_title_keywords"] = list(
            cfg.get("exclude_title_keywords") or list(self._SKIP_EVENT_HINTS)
        )
        upgraded["allowed_event_types"] = ["Event", "MusicEvent", "SportsEvent"]
        upgraded["future_only"] = True
        upgraded["lookback_days"] = int(cfg.get("lookback_days", 0))
        logger.info("ticketjam: upgraded legacy config to venue-page mode at runtime")
        return upgraded

    def _resolve_limits(
        self, source: SignalSourceRecord, cfg: dict[str, object]
    ) -> tuple[int, int]:
        if not source.last_signature:
            max_sitemaps = max(1, int(cfg.get("bootstrap_max_sitemaps", 8000)))
            max_event_urls = max(1, int(cfg.get("bootstrap_max_event_urls", 50000)))
            return max_sitemaps, max_event_urls
        max_sitemaps = max(1, int(cfg.get("max_sitemaps", 120)))
        max_event_urls = max(1, int(cfg.get("max_event_urls", 400)))
        return max_sitemaps, max_event_urls

    def _resolve_allowed_types(self, cfg: dict[str, object]) -> set[str]:
        raw = cfg.get("allowed_event_types", ["Event", "MusicEvent"])
        if isinstance(raw, list):
            values = {str(v).strip() for v in raw if str(v).strip()}
            if values:
                return values
        if isinstance(raw, str) and raw.strip():
            return {raw.strip()}
        return {"Event", "MusicEvent"}

    def _load_sitemap_index(
        self, index_url: str, timeout_sec: int, request_retries: int
    ) -> list[tuple[str, str]]:
        root = self._fetch_xml_root(index_url, timeout_sec, request_retries)
        if root is None:
            return []
        items: list[tuple[str, str]] = []
        for node in root.findall(".//{*}sitemap"):
            loc = (node.findtext("{*}loc") or "").strip()
            lastmod = (node.findtext("{*}lastmod") or "").strip()
            if loc:
                items.append((loc, lastmod))
        items.sort(key=lambda row: row[1] or "", reverse=True)
        return items

    def _load_event_urls(
        self, sitemap_url: str, timeout_sec: int, request_retries: int
    ) -> list[tuple[str, str]]:
        root = self._fetch_xml_root(sitemap_url, timeout_sec, request_retries)
        if root is None:
            return []
        items: list[tuple[str, str]] = []
        for node in root.findall(".//{*}url"):
            loc = (node.findtext("{*}loc") or "").strip()
            lastmod = (node.findtext("{*}lastmod") or "").strip()
            if loc:
                items.append((loc, lastmod))
        return items

    def _fetch_xml_root(
        self, url: str, timeout_sec: int, request_retries: int
    ) -> ET.Element | None:
        resp = self._get_with_retry(
            url,
            timeout_sec=timeout_sec,
            request_retries=request_retries,
            kind="sitemap",
        )
        if resp is None:
            return None
        if resp.status_code != 200:
            logger.warning("ticketjam: sitemap %s returned %s", url, resp.status_code)
            return None

        content = bytes(resp.content or b"")
        if not content:
            return None
        try:
            raw_xml = gzip.decompress(content)
        except OSError:
            raw_xml = content
        try:
            return ET.fromstring(raw_xml)
        except Exception:
            try:
                return ET.fromstring(raw_xml.decode("utf-8", errors="replace"))
            except Exception as exc:
                logger.warning("ticketjam: sitemap XML parse failed %s (%s)", url, exc)
                return None

    def _fetch_event_signal(
        self,
        source_id: str,
        event_url: str,
        timeout_sec: int,
        request_retries: int,
        *,
        min_event_date: str,
        future_only: bool,
        allowed_event_types: set[str],
    ) -> SignalRecord | None:
        resp = self._get_with_retry(
            event_url,
            timeout_sec=timeout_sec,
            request_retries=request_retries,
            kind="event",
        )
        if resp is None:
            return None
        if resp.status_code != 200:
            logger.warning("ticketjam: event %s returned %s", event_url, resp.status_code)
            return None

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        category_group = self._extract_category_group(soup)
        category_slug = self._extract_primary_category_slug(soup)
        event_payload = self._extract_event_payload(soup, allowed_event_types)
        if not event_payload:
            return None

        title = str(event_payload.get("name", "")).strip()
        if not title:
            return None

        payload_start_date, payload_start_time = self._parse_start(
            event_payload.get("startDate")
        )
        if not payload_start_date:
            return None

        end_date, _ = self._parse_start(event_payload.get("endDate"))
        if not end_date:
            end_date = payload_start_date

        artist_name = self._extract_artist_name(event_payload.get("performer"))
        if not artist_name:
            artist_name = self._extract_artist_fallback(soup)

        venue_name, pref_name = self._extract_location(event_payload.get("location"))
        if not venue_name:
            venue_name = self._extract_venue_fallback(soup)

        # Ticketjam pages can expose multiple performances in JSON-LD; prefer the
        # page headline performance for date/time/venue to avoid cross-venue mixups.
        page_start_date, page_start_time, page_venue_name = self._extract_page_performance(
            soup,
            default_year=payload_start_date[:4],
        )

        start_date = page_start_date or payload_start_date
        start_time = page_start_time or payload_start_time
        if page_venue_name:
            if venue_name and page_venue_name != venue_name:
                # Drop potentially stale region from JSON-LD if venue changed.
                pref_name = ""
            venue_name = page_venue_name
        if not pref_name:
            pref_name = self._extract_pref_from_page_text(soup, start_date, start_time, venue_name)
        if future_only and start_date < min_event_date:
            return None

        # Keep quality bar strict: require the 4 requested fields.
        if not (start_date and venue_name and artist_name and title):
            return None

        event_info = self._build_event_info(start_date, start_time, pref_name, venue_name)
        published_at_utc = to_utc_z_from_jst_date(start_date, "%Y-%m-%d")
        if not published_at_utc:
            return None

        labels: dict[str, object] = {
            "announce": True,
            "jp_show": True,
            "category": "ticket_market",
            "source_kind": "secondary_market",
            "artist_name": artist_name,
            "venue_name": venue_name,
            "raw_artist_name": artist_name,
            "raw_venue_name": venue_name,
            "event_info": event_info,
            "event_start_date": start_date,
            "event_end_date": end_date,
            "event_start_time": start_time or "",
        }
        if pref_name:
            labels["pref_name"] = pref_name
        if category_group:
            labels["ticketjam_category_group"] = category_group
        if category_slug:
            labels["ticketjam_category_slug"] = category_slug

        extra_key = f"{start_date}|{venue_name}|{artist_name}"
        canonical_url = self._canonicalize_url(event_url)
        rec = SignalRecord(
            signal_uid=compute_signal_uid(source_id, canonical_url, extra_key),
            source_id=source_id,
            published_at_utc=published_at_utc,
            title=title,
            url=canonical_url,
            snippet=trim_snippet(event_info),
            score=68,
            labels_json=canonical_labels_json(labels),
        )
        rec.content_hash = compute_content_hash(rec)
        return rec

    def _extract_event_payload(
        self, soup: BeautifulSoup, allowed_event_types: set[str]
    ) -> dict[str, object]:
        for script in soup.find_all("script", type="application/ld+json"):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            events = self._collect_event_nodes(data, allowed_event_types)
            if events:
                return events[0]
        return {}

    def _collect_event_nodes(
        self, node: object, allowed_event_types: set[str] | None = None
    ) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        if isinstance(node, list):
            for item in node:
                out.extend(self._collect_event_nodes(item, allowed_event_types))
            return out
        if not isinstance(node, dict):
            return out

        types = self._parse_event_types(node.get("@type"))
        if self._is_allowed_event_types(types, allowed_event_types):
            out.append(node)
        if "@graph" in node:
            out.extend(self._collect_event_nodes(node.get("@graph"), allowed_event_types))
        return out

    def _parse_event_types(self, raw_type: object) -> set[str]:
        if isinstance(raw_type, list):
            raw_values = [str(t).strip() for t in raw_type if str(t).strip()]
        else:
            text = str(raw_type or "").strip()
            raw_values = [text] if text else []

        values: set[str] = set()
        for value in raw_values:
            values.add(value)
            values.add(value.rsplit("/", 1)[-1])
            values.add(value.rsplit("#", 1)[-1])
        return {v for v in values if v}

    def _is_allowed_event_types(
        self, types: set[str], allowed_event_types: set[str] | None
    ) -> bool:
        if not types:
            return False
        if not allowed_event_types:
            return any(t in {"Event", "MusicEvent", "SportsEvent"} for t in types)
        return bool(types.intersection(allowed_event_types))

    def _parse_start(self, value: object) -> tuple[str, str | None]:
        if value is None:
            return "", None
        text = str(value).strip()
        if not text:
            return "", None
        m = self._START_RE.search(text)
        if not m:
            return "", None
        return m.group(1), (m.group(2) or None)

    def _extract_artist_name(self, performer: object) -> str:
        if isinstance(performer, dict):
            return " ".join(str(performer.get("name", "")).split())
        if isinstance(performer, list):
            names: list[str] = []
            for item in performer:
                if isinstance(item, dict):
                    name = " ".join(str(item.get("name", "")).split())
                else:
                    name = " ".join(str(item).split())
                if name:
                    names.append(name)
            return " / ".join(names)
        return " ".join(str(performer or "").split())

    def _extract_artist_fallback(self, soup: BeautifulSoup) -> str:
        for anchor in soup.select('a[href^="/tickets/"]'):
            href = str(anchor.get("href") or "").strip()
            if re.match(r"^/tickets/[^/]+$", href):
                text = " ".join(anchor.get_text(" ", strip=True).split())
                text = re.sub(r"\s*チケット$", "", text)
                if text:
                    return text
        return ""

    def _extract_location(self, location: object) -> tuple[str, str]:
        node: dict[str, object] | None = None
        if isinstance(location, dict):
            node = location
        elif isinstance(location, list):
            for item in location:
                if isinstance(item, dict):
                    node = item
                    break

        if not node:
            return "", ""

        venue_name = " ".join(str(node.get("name", "")).split())
        pref_name = ""
        address = node.get("address")
        if isinstance(address, dict):
            pref_name = " ".join(str(address.get("addressRegion", "")).split())
        return venue_name, pref_name

    def _extract_page_performance(
        self,
        soup: BeautifulSoup,
        *,
        default_year: str,
    ) -> tuple[str, str | None, str]:
        fallback_year = self._safe_int(default_year) or datetime.now(JST).year
        for text in self._iter_page_performance_texts(soup):
            match = self._TITLE_OPTION_RE.search(text)
            if not match:
                continue
            month = self._safe_int(match.group(1))
            day = self._safe_int(match.group(2))
            if not month or not day:
                continue
            event_date = f"{fallback_year:04d}-{month:02d}-{day:02d}"
            event_time = str(match.group(3) or "").strip() or None
            venue_name = " ".join(str(match.group(4) or "").split())
            if venue_name:
                return event_date, event_time, venue_name
        return "", None, ""

    def _iter_page_performance_texts(self, soup: BeautifulSoup) -> list[str]:
        out: list[str] = []
        for selector in [".title-option", "h1", "title"]:
            for node in soup.select(selector):
                text = " ".join(node.get_text(" ", strip=True).split())
                if text:
                    out.append(text)
        return out

    def _extract_pref_from_page_text(
        self,
        soup: BeautifulSoup,
        event_date: str,
        start_time: str | None,
        venue_name: str,
    ) -> str:
        if not event_date or not start_time or not venue_name:
            return ""
        event_date_slash = event_date.replace("-", "/")
        full_text = " ".join(soup.get_text(" ", strip=True).split())
        pref_pattern = re.compile(
            rf"{re.escape(event_date_slash)}\([^)]*\)\s+{re.escape(start_time)}\s+([^\s]+)\s+{re.escape(venue_name)}"
        )
        match = pref_pattern.search(full_text)
        if not match:
            return ""
        return self._normalize_pref_name(match.group(1))

    def _normalize_pref_name(self, value: str) -> str:
        raw = "".join(str(value or "").split())
        if not raw:
            return ""
        if raw.endswith(("都", "道", "府", "県")):
            return raw
        if raw.endswith(("市", "区", "町", "村")):
            return ""
        if raw == "東京":
            return "東京都"
        if raw == "大阪":
            return "大阪府"
        if raw == "京都":
            return "京都府"
        if raw == "北海道":
            return "北海道"
        return f"{raw}県"

    def _safe_int(self, value: object) -> int:
        try:
            return int(str(value).strip())
        except Exception:
            return 0

    def _extract_venue_fallback(self, soup: BeautifulSoup) -> str:
        node = soup.select_one(".title-option a")
        if not node:
            return ""
        return " ".join(node.get_text(" ", strip=True).split())

    def _extract_category_group(self, soup: BeautifulSoup) -> str:
        node = soup.select_one('.breadcrumbs a[href*="/categorie_groups/"]')
        if not node:
            return ""
        href = str(node.get("href") or "").strip().lower()
        m = re.search(r"/categorie_groups/([^/?#]+)", href)
        if not m:
            return ""
        return m.group(1).strip()

    def _extract_primary_category_slug(self, soup: BeautifulSoup) -> str:
        node = soup.select_one('.breadcrumbs a[href*="/categories/"]')
        if not node:
            return ""
        href = str(node.get("href") or "").strip().lower()
        m = re.search(r"/categories/([^/?#]+)", href)
        if not m:
            return ""
        return m.group(1).strip()

    def _extract_event_id(self, url: str) -> str:
        m = re.search(r"/event/(\d+)$", str(url or "").strip())
        if not m:
            return ""
        return m.group(1)

    def _build_event_info(
        self, event_date: str, start_time: str | None, pref_name: str, venue_name: str
    ) -> str:
        dt_part = f"{event_date} {start_time}" if start_time else event_date
        place = " ".join(part for part in [pref_name, venue_name] if part)
        return f"{dt_part} / {place}".strip()

    def _canonicalize_url(self, value: str) -> str:
        parts = urlsplit(str(value or "").strip())
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def _get_with_retry(
        self,
        url: str,
        *,
        timeout_sec: int,
        request_retries: int,
        kind: str,
    ):
        last_exc: Exception | None = None
        for attempt in range(1, request_retries + 1):
            try:
                return self.session.get(url, timeout=timeout_sec)
            except Exception as exc:
                last_exc = exc
                if attempt < request_retries:
                    time.sleep(min(2.0, 0.4 * attempt))
                    continue
        logger.warning("ticketjam: %s fetch failed %s (%s)", kind, url, last_exc)
        return None
