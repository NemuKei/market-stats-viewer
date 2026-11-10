"""Reviewed ticket facts, distributed separately from the event snapshot.

No network or database writes. Caller must supply reviewed official evidence;
this validator does not establish the truth or licensing of a source.
"""

from copy import deepcopy
from datetime import date, datetime
import hashlib
import re
from urllib.parse import urlsplit

ROOT = {
    "schema_version",
    "generated_at_utc",
    "event_generation_sha256",
    "rounds",
    "links",
}
ROUND = {
    "ticket_round_id",
    "title",
    "sale_method",
    "round_type",
    "eligibility_label",
    "status",
    "revision",
    "first_seen_at_utc",
    "last_verified_at_utc",
    "milestones",
}
MILESTONE = {
    "kind",
    "knowledge_status",
    "precision",
    "date",
    "time",
    "end_date",
    "end_time",
    "timezone",
    "source",
}
SOURCE = {"url", "name", "source_class", "checked_at_utc"}
OFFICIAL = {"venue_official", "artist_official", "promoter_official", "ticket_official"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def shape(value, keys):
    require(isinstance(value, dict) and set(value) == keys, "unexpected fields")


def text(value):
    require(
        isinstance(value, str)
        and 0 < len(value) <= 500
        and value == value.strip()
        and not any(ord(c) < 32 or c == "\ufffd" for c in value),
        "invalid text",
    )


def utc(value):
    require(
        isinstance(value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value),
        "UTC timestamp required",
    )
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def day(value):
    require(
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
        "invalid date",
    )
    date.fromisoformat(value)


def clock(value):
    require(
        isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value),
        "invalid time",
    )


def source(value):
    shape(value, SOURCE)
    text(value["name"])
    text(value["url"])
    u = urlsplit(value["url"])
    require(
        u.scheme == "https" and bool(u.hostname) and not u.username and not u.password,
        "HTTPS official source required",
    )
    require(value["source_class"] in OFFICIAL, "official source required")
    utc(value["checked_at_utc"])


def validate(payload, *, event_generation_sha256, event_uids):
    shape(payload, ROOT)
    require(
        type(payload["schema_version"]) is int and payload["schema_version"] == 1,
        "unsupported schema",
    )
    utc(payload["generated_at_utc"])
    digest = payload["event_generation_sha256"]
    require(
        isinstance(digest, str)
        and re.fullmatch("[a-f0-9]{64}", digest)
        and digest == event_generation_sha256,
        "event generation mismatch",
    )
    require(
        isinstance(payload["rounds"], list) and isinstance(payload["links"], list),
        "lists required",
    )
    ids = set()
    for r in payload["rounds"]:
        shape(r, ROUND)
        for k in ("ticket_round_id", "title", "eligibility_label"):
            text(r[k])
        require(r["ticket_round_id"] not in ids, "duplicate round")
        ids.add(r["ticket_round_id"])
        require(r["sale_method"] in {"lottery", "first_come", "unknown"}, "sale method")
        require(
            r["round_type"] in {"fan_club", "general", "upgrade", "other"}, "round type"
        )
        require(r["status"] in {"active", "postponed", "cancelled"}, "round status")
        require(type(r["revision"]) is int and r["revision"] > 0, "revision")
        utc(r["first_seen_at_utc"])
        utc(r["last_verified_at_utc"])
        require(
            r["first_seen_at_utc"]
            <= r["last_verified_at_utc"]
            <= payload["generated_at_utc"],
            "timestamp order",
        )
        require(
            isinstance(r["milestones"], list) and len(r["milestones"]) > 0,
            "milestones required",
        )
        kinds = set()
        for m in r["milestones"]:
            shape(m, MILESTONE)
            require(
                m["kind"]
                in {
                    "application_open",
                    "application_close",
                    "results",
                    "payment_deadline",
                }
                and m["kind"] not in kinds,
                "duplicate or invalid milestone",
            )
            kinds.add(m["kind"])
            require(m["timezone"] == "Asia/Tokyo", "timezone")
            require(
                m["knowledge_status"]
                in {
                    "confirmed",
                    "unannounced",
                    "unverified",
                    "not_applicable",
                    "conflict",
                },
                "knowledge status",
            )
            if m["source"] is not None:
                source(m["source"])
                require(
                    m["source"]["checked_at_utc"] <= r["last_verified_at_utc"],
                    "source check after verification",
                )
            if m["knowledge_status"] in {"confirmed", "unannounced"}:
                require(m["source"] is not None, "source required")
            if r["sale_method"] == "first_come" and m["kind"] == "results":
                require(
                    m["knowledge_status"] == "not_applicable",
                    "first come has no lottery result",
                )
            if m["knowledge_status"] != "confirmed":
                require(
                    all(
                        m[k] is None
                        for k in ("precision", "date", "time", "end_date", "end_time")
                    ),
                    "unknown date must stay null",
                )
                continue
            day(m["date"])
            require(m["precision"] in {"date", "time", "range"}, "precision")
            if m["precision"] == "date":
                require(m["time"] is None, "date only cannot imply midnight")
            elif m["time"] is not None:
                clock(m["time"])
            if m["precision"] == "time":
                clock(m["time"])
            if m["precision"] == "range":
                day(m["end_date"])
                require(
                    (m["time"] is None) == (m["end_time"] is None),
                    "range precision mismatch",
                )
                if m["end_time"] is not None:
                    clock(m["end_time"])
                require(
                    (m["date"], m["time"] or "")
                    <= (m["end_date"], m["end_time"] or ""),
                    "reversed range",
                )
            else:
                require(
                    m["end_date"] is None and m["end_time"] is None, "unexpected range"
                )
        boundaries = {
            m["kind"]: m
            for m in r["milestones"]
            if m["knowledge_status"] == "confirmed" and m["precision"] != "range"
        }
        if {"application_open", "application_close"} <= boundaries.keys():
            a, b = boundaries["application_open"], boundaries["application_close"]
            require(a["date"] <= b["date"], "application closes before opening")
            if a["date"] == b["date"] and a["time"] and b["time"]:
                require(a["time"] <= b["time"], "application closes before opening")
    links = set()
    for link in payload["links"]:
        shape(link, {"ticket_round_id", "event_uid"})
        text(link["ticket_round_id"])
        text(link["event_uid"])
        pair = (link["ticket_round_id"], link["event_uid"])
        require(
            pair not in links and pair[0] in ids and pair[1] in event_uids,
            "invalid or duplicate event link",
        )
        links.add(pair)
    require({r for r, _ in links} == ids, "unlinked round")
    return deepcopy(payload)


def build(ledger, event_bytes, *, generated_at_utc):
    """Project a reviewed ledger. Never modify the ledger or event generation."""
    import json

    shape(ledger, {"schema_version", "rounds", "links", "review", "history"})
    from .ticket_review_history import validate_history

    validate_history(ledger)
    require(
        type(ledger["schema_version"]) is int and ledger["schema_version"] == 1,
        "ledger schema",
    )
    shape(ledger["review"], {"status", "facts_sha256", "reviewed_at_utc"})
    require(ledger["review"]["status"] == "reviewed", "review required")
    utc(ledger["review"]["reviewed_at_utc"])
    require(
        ledger["review"]["reviewed_at_utc"] <= generated_at_utc, "review from future"
    )
    facts = {"rounds": ledger["rounds"], "links": ledger["links"]}
    raw = json.dumps(
        facts, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    require(
        hashlib.sha256(raw).hexdigest() == ledger["review"]["facts_sha256"],
        "facts changed after review",
    )
    events = json.loads(event_bytes)
    uids = {
        e["event_key"]
        for e in events["events"]
        if e.get("record_kind", "event") == "event"
    }
    require(len(uids) == len(events["events"]), "ambiguous or non-event IDs")
    digest = hashlib.sha256(event_bytes).hexdigest()
    return validate(
        {
            "schema_version": 1,
            "generated_at_utc": generated_at_utc,
            "event_generation_sha256": digest,
            **deepcopy(facts),
        },
        event_generation_sha256=digest,
        event_uids=uids,
    )
