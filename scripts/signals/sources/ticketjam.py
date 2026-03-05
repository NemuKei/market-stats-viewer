"""Ticketjam event source plugin (secondary market reference feed)."""

from __future__ import annotations

import gzip
import json
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
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


class TicketjamEventsSource(SignalSource):
    """Fetch Ticketjam event pages via public sitemaps and extract event basics."""

    _START_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?")
    _EVENT_URL_RE = re.compile(r"^https://ticketjam\.jp/tickets/[^/]+/event/\d+$")
    _DEFAULT_ALLOWED_CATEGORY_SLUGS = {
        "idol-music",
        "band-music",
        "foreign-band-music",
        "classical-music",
        "foreign-classical-music",
        "jazz-and-fusion",
        "foreign-jazz-and-fusion",
        "anime-music",
        "music-event-and-festival",
        "male-artist",
        "female-artist",
        "foreign-male-artist",
        "foreign-female-artist",
    }
    _DEFAULT_AMBIGUOUS_CATEGORY_SLUGS = {
        "male-artist",
        "female-artist",
        "foreign-male-artist",
        "foreign-female-artist",
    }
    _DEFAULT_MUSIC_INCLUDE_KEYWORDS = {
        "ライブ",
        "コンサート",
        "公演",
        "ツアー",
        "フェス",
        "festival",
        "tour",
        "live",
        "concert",
        "oneman",
        "one man",
        "showcase",
        "band",
        "リサイタル",
        "オーケストラ",
        "音楽",
    }
    _DEFAULT_NON_LIVE_EXCLUDE_KEYWORDS = {
        "お笑い",
        "漫才",
        "舞台挨拶",
        "試写会",
        "トークショー",
        "講演会",
        "朗読劇",
        "演劇",
        "ミュージカル",
        "歌劇",
        "宝塚",
        "落語",
        "展示",
        "展覧",
        "博覧",
        "コレクション",
        "ファッション",
        "花火",
        "サッカー",
        "football",
        "dream match",
        "格闘技",
        "プロレス",
        "野球",
        "baseball",
        "試合",
        "対戦",
        "グランプリ",
    }

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        cfg = self._normalize_legacy_config(cfg)
        timeout_sec = max(10, int(cfg.get("timeout_sec", 30)))
        request_retries = max(1, int(cfg.get("request_retries", 3)))
        max_sitemaps, max_event_urls = self._resolve_limits(source, cfg)
        max_sitemap_attempts = max(
            max_sitemaps,
            int(cfg.get("max_sitemap_attempts", max_sitemaps * 5)),
        )
        future_only = bool(cfg.get("future_only", True))
        lookback_days = max(0, int(cfg.get("lookback_days", 0)))
        min_event_date = (datetime.now(JST).date() - timedelta(days=lookback_days)).isoformat()
        allowed_event_types = self._resolve_allowed_types(cfg)
        allowed_category_groups = self._resolve_allowed_category_groups(cfg)
        allowed_category_slugs = self._resolve_allowed_category_slugs(cfg)
        ambiguous_category_slugs = self._resolve_ambiguous_category_slugs(cfg)
        music_include_keywords = self._resolve_music_include_keywords(cfg)
        non_live_exclude_keywords = self._resolve_non_live_exclude_keywords(cfg)

        sitemap_items = self._load_sitemap_index(
            source.source_url, timeout_sec, request_retries
        )
        if not sitemap_items:
            logger.warning("ticketjam: no sitemap entries from %s", source.source_url)
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

        if not event_url_map:
            logger.warning("ticketjam: no event URLs after sitemap scan")
            return []

        event_urls = [
            row[0]
            for _, row in sorted(
                event_url_map.items(), key=lambda kv: kv[1][1] or "", reverse=True
            )[:max_event_urls]
        ]

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
                allowed_category_groups=allowed_category_groups,
                allowed_category_slugs=allowed_category_slugs,
                ambiguous_category_slugs=ambiguous_category_slugs,
                music_include_keywords=music_include_keywords,
                non_live_exclude_keywords=non_live_exclude_keywords,
            )
            if rec:
                records.append(rec)

        records = self._dedupe_records(records)
        records.sort(key=lambda row: row.published_at_utc, reverse=True)
        if not records:
            logger.warning("ticketjam: parsed 0 valid signals from %s", source.source_id)
        return records

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
        is_legacy = (
            "bootstrap_max_sitemaps" not in cfg
            and "bootstrap_max_event_urls" not in cfg
            and "allowed_event_types" not in cfg
            and "future_only" not in cfg
        )
        if not is_legacy and (
            "allowed_category_groups" not in cfg
            or "allowed_category_slugs" not in cfg
            or "ambiguous_category_slugs" not in cfg
            or "music_include_keywords" not in cfg
            or "non_live_exclude_keywords" not in cfg
        ):
            is_legacy = True
        if not is_legacy:
            return cfg

        upgraded = dict(cfg)
        upgraded["bootstrap_max_sitemaps"] = int(cfg.get("bootstrap_max_sitemaps", 8000))
        upgraded["bootstrap_max_event_urls"] = int(
            cfg.get("bootstrap_max_event_urls", 50000)
        )
        upgraded["max_sitemaps"] = max(120, int(cfg.get("max_sitemaps", 120)))
        upgraded["max_event_urls"] = max(400, int(cfg.get("max_event_urls", 400)))
        upgraded["allowed_event_types"] = ["Event", "MusicEvent"]
        upgraded["allowed_category_groups"] = ["live_domestic", "live_international"]
        upgraded["allowed_category_slugs"] = sorted(self._DEFAULT_ALLOWED_CATEGORY_SLUGS)
        upgraded["ambiguous_category_slugs"] = sorted(
            self._DEFAULT_AMBIGUOUS_CATEGORY_SLUGS
        )
        upgraded["music_include_keywords"] = sorted(
            self._DEFAULT_MUSIC_INCLUDE_KEYWORDS
        )
        upgraded["non_live_exclude_keywords"] = sorted(
            self._DEFAULT_NON_LIVE_EXCLUDE_KEYWORDS
        )
        upgraded["future_only"] = True
        upgraded["lookback_days"] = int(cfg.get("lookback_days", 0))
        logger.info("ticketjam: upgraded legacy config at runtime")
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

    def _resolve_allowed_category_groups(self, cfg: dict[str, object]) -> set[str]:
        raw = cfg.get("allowed_category_groups", ["live_domestic", "live_international"])
        values: set[str] = set()
        if isinstance(raw, list):
            values = {str(v).strip().lower() for v in raw if str(v).strip()}
        elif isinstance(raw, str) and raw.strip():
            values = {raw.strip().lower()}
        return values

    def _resolve_allowed_category_slugs(self, cfg: dict[str, object]) -> set[str]:
        raw = cfg.get("allowed_category_slugs", sorted(self._DEFAULT_ALLOWED_CATEGORY_SLUGS))
        values: set[str] = set()
        if isinstance(raw, list):
            values = {str(v).strip().lower() for v in raw if str(v).strip()}
        elif isinstance(raw, str) and raw.strip():
            values = {raw.strip().lower()}
        return values or set(self._DEFAULT_ALLOWED_CATEGORY_SLUGS)

    def _resolve_ambiguous_category_slugs(self, cfg: dict[str, object]) -> set[str]:
        raw = cfg.get(
            "ambiguous_category_slugs", sorted(self._DEFAULT_AMBIGUOUS_CATEGORY_SLUGS)
        )
        values: set[str] = set()
        if isinstance(raw, list):
            values = {str(v).strip().lower() for v in raw if str(v).strip()}
        elif isinstance(raw, str) and raw.strip():
            values = {raw.strip().lower()}
        return values or set(self._DEFAULT_AMBIGUOUS_CATEGORY_SLUGS)

    def _resolve_music_include_keywords(self, cfg: dict[str, object]) -> set[str]:
        raw = cfg.get(
            "music_include_keywords", sorted(self._DEFAULT_MUSIC_INCLUDE_KEYWORDS)
        )
        values: set[str] = set()
        if isinstance(raw, list):
            values = {str(v).strip().lower() for v in raw if str(v).strip()}
        elif isinstance(raw, str) and raw.strip():
            values = {raw.strip().lower()}
        return values or {k.lower() for k in self._DEFAULT_MUSIC_INCLUDE_KEYWORDS}

    def _resolve_non_live_exclude_keywords(self, cfg: dict[str, object]) -> set[str]:
        raw = cfg.get(
            "non_live_exclude_keywords", sorted(self._DEFAULT_NON_LIVE_EXCLUDE_KEYWORDS)
        )
        values: set[str] = set()
        if isinstance(raw, list):
            values = {str(v).strip().lower() for v in raw if str(v).strip()}
        elif isinstance(raw, str) and raw.strip():
            values = {raw.strip().lower()}
        return values or {k.lower() for k in self._DEFAULT_NON_LIVE_EXCLUDE_KEYWORDS}

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
        allowed_category_groups: set[str],
        allowed_category_slugs: set[str],
        ambiguous_category_slugs: set[str],
        music_include_keywords: set[str],
        non_live_exclude_keywords: set[str],
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
        if allowed_category_groups and category_group not in allowed_category_groups:
            return None
        category_slug = self._extract_primary_category_slug(soup)
        if allowed_category_slugs and category_slug not in allowed_category_slugs:
            return None
        event_payload = self._extract_event_payload(soup, allowed_event_types)
        if not event_payload:
            return None

        title = str(event_payload.get("name", "")).strip()
        if not title:
            return None

        start_date, start_time = self._parse_start(event_payload.get("startDate"))
        if not start_date:
            return None
        if future_only and start_date < min_event_date:
            return None

        end_date, _ = self._parse_start(event_payload.get("endDate"))
        if not end_date:
            end_date = start_date

        artist_name = self._extract_artist_name(event_payload.get("performer"))
        if not artist_name:
            artist_name = self._extract_artist_fallback(soup)

        venue_name, pref_name = self._extract_location(event_payload.get("location"))
        if not venue_name:
            venue_name = self._extract_venue_fallback(soup)

        # Keep quality bar strict: require the 4 requested fields.
        if not (start_date and venue_name and artist_name and title):
            return None
        if self._contains_any_keyword(
            f"{title} {artist_name}",
            non_live_exclude_keywords,
        ):
            return None
        if (
            category_slug in ambiguous_category_slugs
            and not self._contains_any_keyword(
                f"{title} {artist_name}",
                music_include_keywords,
            )
        ):
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

    def _contains_any_keyword(self, text: str, keywords: set[str]) -> bool:
        normalized = str(text or "").lower()
        return any(keyword in normalized for keyword in keywords if keyword)

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
