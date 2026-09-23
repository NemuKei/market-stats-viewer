"""Select records that may enter LP publication grouping."""

from __future__ import annotations

from typing import Any

from .events.types import JAPAN_PREFECTURES
from .signals.sources.venue_web_discovery import ACCEPTED_SOURCE_CLASSES

PUBLISHABLE_SOURCE_IDS = frozenset(
    {"official_events", "venue_web_discovery", "starto_concert", "kstyle_music"}
)


def select_publishable_records(
    records: list[dict[str, Any]], *, venue_prefectures: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trusted: list[dict[str, Any]] = []
    location_held: list[dict[str, Any]] = []
    for row in records:
        if row["source_id"] not in PUBLISHABLE_SOURCE_IDS:
            continue
        if row["source_id"] == "venue_web_discovery" and (
            row.get("source_class") not in ACCEPTED_SOURCE_CLASSES
            or not row.get("evidence_url")
            or not row.get("evidence_snippet")
        ):
            raise ValueError("unverified venue_web_discovery record cannot be published")
        row = dict(row)
        known_pref = venue_prefectures.get(row["venue_name"])
        if known_pref and row.get("pref_name") and row["pref_name"] != known_pref:
            location_held.append({"source_id": row["source_id"], "record_id": row["record_id"],
                                  "reason": "venue_prefecture_conflict"})
            continue
        row["pref_name"] = row.get("pref_name") or known_pref
        if row["pref_name"] not in JAPAN_PREFECTURES:
            location_held.append({"source_id": row["source_id"], "record_id": row["record_id"],
                                  "reason": "unresolved_domestic_location"})
            continue
        trusted.append(row)
    return trusted, location_held
