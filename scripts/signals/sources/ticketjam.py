"""Ticketjam event source plugin (secondary market reference feed)."""

from __future__ import annotations

import gzip
import json
import logging
import re
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from ..types import SignalRecord, SignalSourceRecord
from .base import (
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

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_config(source.config_json)
        timeout_sec = max(10, int(cfg.get("timeout_sec", 30)))
        max_sitemaps = max(1, int(cfg.get("max_sitemaps", 20)))
        max_event_urls = max(1, int(cfg.get("max_event_urls", 25)))

        sitemap_items = self._load_sitemap_index(source.source_url, timeout_sec)
        if not sitemap_items:
            logger.warning("ticketjam: no sitemap entries from %s", source.source_url)
            return []

        sitemap_urls = [loc for loc, _ in sitemap_items[:max_sitemaps] if loc]
        event_url_map: dict[str, str] = {}
        for sitemap_url in sitemap_urls:
            for event_url, lastmod in self._load_event_urls(sitemap_url, timeout_sec):
                if not self._EVENT_URL_RE.match(event_url):
                    continue
                prev_lastmod = event_url_map.get(event_url, "")
                if lastmod >= prev_lastmod:
                    event_url_map[event_url] = lastmod

        if not event_url_map:
            logger.warning("ticketjam: no event URLs after sitemap scan")
            return []

        event_urls = [
            url
            for url, _ in sorted(
                event_url_map.items(), key=lambda kv: kv[1] or "", reverse=True
            )[:max_event_urls]
        ]

        records: list[SignalRecord] = []
        for event_url in event_urls:
            rec = self._fetch_event_signal(source.source_id, event_url, timeout_sec)
            if rec:
                records.append(rec)

        records.sort(key=lambda row: row.published_at_utc, reverse=True)
        if not records:
            logger.warning("ticketjam: parsed 0 valid signals from %s", source.source_id)
        return records

    def _load_config(self, config_json: str | None) -> dict[str, object]:
        if not config_json:
            return {}
        try:
            obj = json.loads(config_json)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _load_sitemap_index(
        self, index_url: str, timeout_sec: int
    ) -> list[tuple[str, str]]:
        root = self._fetch_xml_root(index_url, timeout_sec)
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
        self, sitemap_url: str, timeout_sec: int
    ) -> list[tuple[str, str]]:
        root = self._fetch_xml_root(sitemap_url, timeout_sec)
        if root is None:
            return []
        items: list[tuple[str, str]] = []
        for node in root.findall(".//{*}url"):
            loc = (node.findtext("{*}loc") or "").strip()
            lastmod = (node.findtext("{*}lastmod") or "").strip()
            if loc:
                items.append((loc, lastmod))
        return items

    def _fetch_xml_root(self, url: str, timeout_sec: int) -> ET.Element | None:
        try:
            resp = self.session.get(url, timeout=timeout_sec)
        except Exception as exc:
            logger.warning("ticketjam: sitemap fetch failed %s (%s)", url, exc)
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
        self, source_id: str, event_url: str, timeout_sec: int
    ) -> SignalRecord | None:
        try:
            resp = self.session.get(event_url, timeout=timeout_sec)
        except Exception as exc:
            logger.warning("ticketjam: event fetch failed %s (%s)", event_url, exc)
            return None
        if resp.status_code != 200:
            logger.warning("ticketjam: event %s returned %s", event_url, resp.status_code)
            return None

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        event_payload = self._extract_event_payload(soup)
        if not event_payload:
            return None

        title = str(event_payload.get("name", "")).strip()
        if not title:
            return None

        start_date, start_time = self._parse_start(event_payload.get("startDate"))
        if not start_date:
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

    def _extract_event_payload(self, soup: BeautifulSoup) -> dict[str, object]:
        for script in soup.find_all("script", type="application/ld+json"):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            events = self._collect_event_nodes(data)
            if events:
                return events[0]
        return {}

    def _collect_event_nodes(self, node: object) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        if isinstance(node, list):
            for item in node:
                out.extend(self._collect_event_nodes(item))
            return out
        if not isinstance(node, dict):
            return out

        raw_type = node.get("@type")
        if isinstance(raw_type, list):
            types = [str(t) for t in raw_type]
        else:
            types = [str(raw_type or "")]
        if any(t in ("Event", "MusicEvent", "SportsEvent") for t in types):
            out.append(node)
        if "@graph" in node:
            out.extend(self._collect_event_nodes(node.get("@graph")))
        return out

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

    def _build_event_info(
        self, event_date: str, start_time: str | None, pref_name: str, venue_name: str
    ) -> str:
        dt_part = f"{event_date} {start_time}" if start_time else event_date
        place = " ".join(part for part in [pref_name, venue_name] if part)
        return f"{dt_part} / {place}".strip()

    def _canonicalize_url(self, value: str) -> str:
        parts = urlsplit(str(value or "").strip())
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
