"""Schema-v1 publication: preserve legacy rows, constrain reviewed changes.

This is a projection and exact-event publication gate, not a terms/licence
engine. Human publication decisions belong in the existing Git review.
"""

from copy import deepcopy
from datetime import date, datetime, time, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit


EVENT_FIELDS = frozenset({
    "event_key", "event_date", "event_end_date", "event_start_time", "event_end_time",
    "venue_name", "artist_name", "title", "event_category", "pref_name",
    "url", "evidence_url", "display_source_id", "display_source_class",
    "display_source_label", "source_domain", "first_seen_at_utc", "updated_at_utc",
})
TOP_FIELDS = frozenset({
    "schema_version", "generated_at_utc", "as_of_date", "include_past",
    "history_window_days", "history_start_date", "source_priority", "identity_registry",
    "history_scope", "retained_from_date", "retained_through_date",
})
COUNT_FIELDS = frozenset({
    "record_count_before_grouping", "event_count", "identity_held_record_count",
    "location_held_record_count", "suppressed_event_count", "start_time_split_group_count",
    "start_time_split_event_count", "supplemental_merged_group_count", "supplemental_merged_record_count",
})
SOURCES = frozenset({"official_events", "venue_web_discovery", "starto_concert", "kstyle_music"})
OFFICIAL_CLASSES = frozenset({"venue_official", "artist_official", "promoter_official", "ticket_official"})
SOURCE_PRIORITY = {"official_events": 10, "venue_web_discovery": 20, "starto_concert": 30, "kstyle_music": 30}


def host(url):
    try:
        parts = urlsplit(url)
        return parts.hostname if parts.scheme in {"http", "https"} and not parts.username and not parts.password else None
    except (TypeError, ValueError):
        return None


def embedded_urls(value):
    if isinstance(value, str):
        yield from re.findall(r"https?://[^\s]+", value, flags=re.IGNORECASE)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from embedded_urls(key)
            yield from embedded_urls(item)
    elif isinstance(value, list):
        for item in value:
            yield from embedded_urls(item)


def check_timestamp(value):
    if value in (None, ""):
        return
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value):
        raise ValueError("invalid public source timestamp")
    if datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("public source timestamp must be UTC")


def project_event(row):
    """Constrain one explicitly reviewed row without deleting v1 field names."""
    result = {key: deepcopy(value) for key, value in row.items() if key in EVENT_FIELDS}
    result.update(raw_artist_name="", raw_venue_name="", capacity=None, evidence_snippet="",
                  source_priority=SOURCE_PRIORITY.get(row.get("display_source_id"), 999))
    for field in ("first_seen_at_utc", "updated_at_utc"):
        check_timestamp(result.get(field))
    for field in ("event_start_time", "event_end_time"):
        if result.get(field):
            time.fromisoformat(result[field])
    links = {result.get("url"), result.get("evidence_url")} - {None, ""}
    members = row.get("supporting_sources", [])
    if not isinstance(members, list) or any(not isinstance(item, dict) for item in members):
        raise ValueError("invalid public supporting sources")
    result["supporting_sources"] = []
    for member in members:
        item = {key: deepcopy(member[key]) for key in ("source_id", "record_id", "updated_at_utc") if key in member}
        item.setdefault("updated_at_utc", None)
        item.update(source_class="", source_label="",
                    title="", url="", evidence_url="", content_extractor=None,
                    priority=SOURCE_PRIORITY.get(member.get("source_id"), 999))
        check_timestamp(item.get("updated_at_utc"))
        # Keep matching display links so existing consumers choose the same
        # source record. Unselected supporting links and prose stay private.
        item.update({key: member[key] for key in ("url", "evidence_url") if member.get(key) in links})
        result["supporting_sources"].append(item)
    return result


def project_payload(payload):
    result = {key: deepcopy(value) for key, value in payload.items() if key in TOP_FIELDS}
    check_timestamp(result.get("generated_at_utc"))
    for key in ("as_of_date", "history_start_date", "retained_from_date", "retained_through_date"):
        if result.get(key) is not None:
            date.fromisoformat(result[key])
    if "history_scope" in result and result["history_scope"] != "all_verified_retained":
        raise ValueError("invalid public history scope")
    if "include_past" in result and type(result["include_past"]) is not bool:
        raise ValueError("invalid public history flag")
    window = result.get("history_window_days")
    if window is not None and (type(window) is not int or window < 0):
        raise ValueError("invalid public history window")
    if any(source not in SOURCES for source in result.get("source_priority", [])):
        raise ValueError("invalid public source priority")
    result["summary"] = {key: value for key, value in payload["summary"].items() if key in COUNT_FIELDS}
    if any(type(value) is not int or value < 0 for value in result["summary"].values()):
        raise ValueError("invalid public summary count")
    counts = payload["summary"]["counts_by_display_source"]
    if any(key not in SOURCES or type(value) is not int or value < 0 for key, value in counts.items()):
        raise ValueError("invalid public source counts")
    result["summary"]["counts_by_display_source"] = dict(counts)
    if any(not official_public_source(row, allow_artist_selection=True) for row in payload["events"]):
        raise ValueError("news-only source cannot enter the public LP")
    checks = payload.get("_public_row_checks", {} if not payload["events"] else None)
    ids = {row["event_key"] for row in payload["events"]}
    if not isinstance(checks, dict) or set(checks) != ids:
        raise ValueError("public row modes and checks required")
    result["events"] = []
    for row in payload["events"]:
        check = checks[row["event_key"]]
        if (not isinstance(check, dict) or set(check) != {"mode", "sha256"}
                or check["mode"] not in {"legacy", "reviewed"}):
            raise ValueError("invalid public row mode")
        if public_row_sha256(row, mode=check["mode"]) != check["sha256"]:
            raise ValueError("public row changed after source/publication checks")
        result["events"].append(legacy_event(row) if check["mode"] == "legacy" else project_event(row))
    # Preserve the existing v1 diagnostic shape. Novel prose/URLs do not become
    # public merely because they occur on a withheld-location record.
    if "location_held_records" in payload:
        result["location_held_records"] = [deepcopy(item) for item in payload["location_held_records"]
            if isinstance(item, dict) and set(item) == {"source_id", "record_id", "reason"}
            and item["source_id"] in SOURCES
            and item["reason"] in {"unresolved_domestic_location", "venue_prefecture_conflict"}
            and isinstance(item["record_id"], str)
            and re.fullmatch(r"[A-Za-z0-9_:.\-]{1,256}", item["record_id"])]
    return result


def legacy_event(row):
    """Preserve every field of a row accepted under the existing v1 contract."""
    for field in ("first_seen_at_utc", "updated_at_utc"):
        check_timestamp(row.get(field))
    for member in row.get("supporting_sources", []):
        check_timestamp(member.get("updated_at_utc"))
    return deepcopy(row)


def attach_public_row_checks(payload, *, reviewed_ids=frozenset()):
    """Bind per-call row modes after the caller's publication decisions."""
    payload["_public_row_checks"] = {
        row["event_key"]: {"mode": mode, "sha256": public_row_sha256(row, mode=mode)}
        for row in payload["events"]
        for mode in ["reviewed" if row["event_key"] in reviewed_ids else "legacy"]
    }


def public_row_sha256(row, *, include_event_key=True, mode="reviewed"):
    public = legacy_event(row) if mode == "legacy" else project_event(row)
    for key in ("first_seen_at_utc", "updated_at_utc"):
        public.pop(key, None)
    if not include_event_key:
        public.pop("event_key", None)
    for member in public["supporting_sources"]:
        member.pop("updated_at_utc", None)
    data = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def publication_preview(row):
    return {"status": "pending", "row_sha256": public_row_sha256(row),
            "public_urls": sorted(set(embedded_urls(project_event(row))))}


def validate_publication(decision):
    if (not isinstance(decision, dict) or set(decision) != {"status", "row_sha256", "public_urls"}
            or decision["status"] not in {"pending", "reviewed"}
            or not isinstance(decision["row_sha256"], str)
            or not re.fullmatch("[0-9a-f]{64}", decision["row_sha256"])
            or not isinstance(decision["public_urls"], list)
            or any(not isinstance(url, str) or not host(url) for url in decision["public_urls"])
            or len(decision["public_urls"]) != len(set(decision["public_urls"]))):
        raise ValueError("invalid event publication decision")


def publication_is_reviewed(record, row):
    decision = record.get("publication")
    if decision is None:
        return False
    validate_publication(decision)
    if decision["status"] != "reviewed":
        return False
    official = official_public_source(row, allow_artist_selection=record.get("mode") == "artist_source_link")
    if not official:
        return False  # A news-only record is not an official factual basis.
    if (public_row_sha256(row) != decision["row_sha256"]
            or set(embedded_urls(project_event(row))) != set(decision["public_urls"])):
        raise ValueError("public fields or URLs changed since publication review")
    return True


def official_public_source(row, *, allow_artist_selection=False):
    source, source_class = row.get("display_source_id"), row.get("display_source_class")
    return (source == "official_events" and source_class == "venue_official"
            or source == "venue_web_discovery" and source_class in OFFICIAL_CLASSES
            or allow_artist_selection and source == "starto_concert" and source_class == "artist_official")
