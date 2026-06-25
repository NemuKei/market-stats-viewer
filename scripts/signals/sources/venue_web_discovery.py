"""Venue web discovery source plugin.

This source turns Codex-verified official/semi-official event evidence into
event_signals rows. Discovery itself happens in Codex Automation; this plugin
only persists confirmed events from data/venue_web_discovery_config.json.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

from ...events.category import classify_event_category
from ..types import SignalRecord, SignalSourceRecord
from .base import (
    SignalSource,
    canonical_labels_json,
    compute_content_hash,
    compute_signal_uid,
    to_utc_z,
    trim_snippet,
)

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "data" / "venue_web_discovery_config.json"
ACCEPTED_SOURCE_CLASSES = {
    "venue_official",
    "artist_official",
    "promoter_official",
    "ticket_official",
}
CONTENT_EXTRACTORS = {"requests_bs4", "crawl4ai"}
CONFIDENCE_SCORES = {
    "high": 95,
    "medium": 75,
    "low": 50,
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class VenueWebDiscoverySource(SignalSource):
    """Load Codex-confirmed official/semi-official event signals from config."""

    def fetch_signals(self, source: SignalSourceRecord) -> list[SignalRecord]:
        cfg = self._load_runtime_config(source.config_json)
        source_classes = self._accepted_source_classes(cfg)
        rejected_source_classes = {
            str(value).strip()
            for value in cfg.get("rejected_source_classes", [])
            if str(value).strip()
        }
        future_only = bool(cfg.get("future_only", True))
        today_iso = date.today().isoformat()

        records: list[SignalRecord] = []
        for event in cfg.get("confirmed_events", []):
            if not isinstance(event, dict):
                continue
            rec = self._event_to_signal(
                source_id=source.source_id,
                event=event,
                accepted_source_classes=source_classes,
                rejected_source_classes=rejected_source_classes,
                future_only=future_only,
                today_iso=today_iso,
            )
            if rec is not None:
                records.append(rec)

        records.sort(key=lambda row: (row.published_at_utc, row.title, row.signal_uid), reverse=True)
        logger.info("venue_web_discovery: loaded %d confirmed event signal(s)", len(records))
        return records

    def _load_runtime_config(self, config_json: str | None) -> dict[str, object]:
        source_cfg: dict[str, object] = {}
        if isinstance(config_json, str) and config_json.strip():
            try:
                parsed = json.loads(config_json)
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                source_cfg = parsed

        config_path_text = str(source_cfg.get("config_path") or "").strip()
        config_path = Path(config_path_text) if config_path_text else DEFAULT_CONFIG_PATH
        if not config_path.is_absolute():
            config_path = REPO_ROOT / config_path
        if not config_path.exists():
            logger.warning("venue_web_discovery: config not found: %s", config_path)
            return source_cfg

        with config_path.open("r", encoding="utf-8") as handle:
            file_cfg = json.load(handle)
        if not isinstance(file_cfg, dict):
            raise ValueError(f"venue web discovery config must be an object: {config_path}")
        merged = dict(file_cfg)
        for key, value in source_cfg.items():
            if key != "config_path":
                merged[key] = value
        return merged

    def _accepted_source_classes(self, cfg: dict[str, object]) -> set[str]:
        raw = cfg.get("accepted_source_classes") or sorted(ACCEPTED_SOURCE_CLASSES)
        accepted = {str(value).strip() for value in raw if str(value).strip()}
        return accepted & ACCEPTED_SOURCE_CLASSES or set(ACCEPTED_SOURCE_CLASSES)

    def _event_to_signal(
        self,
        *,
        source_id: str,
        event: dict[str, object],
        accepted_source_classes: set[str],
        rejected_source_classes: set[str],
        future_only: bool,
        today_iso: str,
    ) -> SignalRecord | None:
        if event.get("enabled") is False:
            return None

        source_class = str(event.get("source_class") or "").strip()
        if source_class not in accepted_source_classes or source_class in rejected_source_classes:
            return None

        event_start_date = str(event.get("event_start_date") or "").strip()
        event_end_date = str(event.get("event_end_date") or event_start_date).strip()
        if not DATE_RE.match(event_start_date) or not DATE_RE.match(event_end_date):
            logger.warning("venue_web_discovery: skip invalid date event_id=%s", event.get("event_id"))
            return None
        if future_only and event_end_date < today_iso:
            return None

        title = str(event.get("title") or "").strip()
        url = str(event.get("url") or event.get("evidence_url") or "").strip()
        venue_name = str(event.get("venue_name") or "").strip()
        artist_name = str(event.get("artist_name") or "").strip()
        evidence_url = str(event.get("evidence_url") or url).strip()
        evidence_snippet = trim_snippet(str(event.get("evidence_snippet") or ""))
        if not title or not url or not venue_name or not artist_name or not evidence_url or not evidence_snippet:
            logger.warning("venue_web_discovery: skip incomplete event_id=%s", event.get("event_id"))
            return None

        description = str(event.get("event_info") or evidence_snippet or "").strip()
        event_category = str(event.get("event_category") or "").strip() or classify_event_category(
            title,
            artist_name,
            description,
        )
        content_extractor = str(event.get("content_extractor") or "requests_bs4").strip()
        if content_extractor not in CONTENT_EXTRACTORS:
            content_extractor = "requests_bs4"
        confidence = str(event.get("confidence") or "medium").strip().lower()
        score = int(event.get("score") or CONFIDENCE_SCORES.get(confidence, 75))
        event_id = str(event.get("event_id") or "").strip()
        published_at_utc = self._published_at(event)
        labels = {
            "event_start_date": event_start_date,
            "event_end_date": event_end_date,
            "venue_name": venue_name,
            "raw_venue_name": str(event.get("raw_venue_name") or venue_name).strip(),
            "artist_name": artist_name,
            "raw_artist_name": str(event.get("raw_artist_name") or artist_name).strip(),
            "event_category": event_category,
            "source_class": source_class,
            "confidence": confidence,
            "content_extractor": content_extractor,
            "evidence_url": evidence_url,
            "evidence_snippet": evidence_snippet,
        }
        for key in (
            "event_start_time",
            "event_end_time",
            "event_info",
            "pref_name",
            "discovery_query",
            "verified_at_utc",
            "announced_at_utc",
        ):
            value = str(event.get(key) or "").strip()
            if value:
                labels[key] = value

        rec = SignalRecord(
            signal_uid=compute_signal_uid(
                source_id,
                url,
                extra_key=event_id or f"{event_start_date}|{venue_name}|{artist_name}|{title}",
            ),
            source_id=source_id,
            published_at_utc=published_at_utc,
            title=title,
            url=url,
            snippet=evidence_snippet,
            score=score,
            labels_json=canonical_labels_json(labels),
        )
        rec.content_hash = compute_content_hash(rec)
        return rec

    def _published_at(self, event: dict[str, object]) -> str:
        raw = str(
            event.get("published_at_utc")
            or event.get("announced_at_utc")
            or event.get("verified_at_utc")
            or ""
        ).strip()
        if raw.endswith("Z") and "T" in raw:
            return raw
        if DATE_RE.match(raw):
            return f"{raw}T00:00:00Z"
        return to_utc_z(datetime.now(timezone.utc))
