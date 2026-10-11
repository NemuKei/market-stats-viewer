from copy import deepcopy
from datetime import date
import json
import sqlite3

import pytest

from scripts import build_all_dates_lp_events as builder
from scripts.build_external_events_manifest import _build_manifest
from scripts import build_lp_events as canonical
from scripts import event_identity_registry as identities


def recent_payload():
    return {
        "schema_version": 1, "as_of_date": "2026-10-11", "generated_at_utc": "2026-10-10T15:51:14Z",
        "history_window_days": 90, "history_start_date": "2026-07-13", "include_past": True,
        "source_priority": ["official_events"],
        "identity_registry": {"schema_version": 1, "revision": 1, "sha256": "a" * 64},
        "summary": {"event_count": 1, "counts_by_display_source": {"official_events": 1},
                    "identity_held_record_count": 0},
        "events": [{"event_key": "fictional-current", "display_source_id": "official_events",
            "title": "架空の演奏会", "artist_name": "架空の演奏者", "venue_name": "架空東ホール",
            "pref_name": "東京都", "event_date": "2026-10-11", "event_start_time": "19:00",
            "url": "https://venue.example.test/current", "first_seen_at_utc": "2026-07-01T00:00:00Z"}],
    }


def all_payload():
    p = deepcopy(recent_payload())
    p.update(history_window_days=None, history_start_date=None)
    p["events"].insert(0, dict(p["events"][0], event_key="fictional-past", event_date="2026-01-30"))
    p["summary"].update(event_count=2, counts_by_display_source={"official_events": 2})
    p["identity_held_records"] = []
    p["summary"]["identity_held_record_count"] = 0
    p["location_held_records"] = [{"record_id": "fictional-unreviewed"}]
    return p


def test_additive_all_dates_preserves_current_fields_and_source_freshness(monkeypatch):
    full = all_payload()
    full["generated_at_utc"] = "2026-10-11T03:00:00Z"
    monkeypatch.setattr(builder, "build_lp_events", lambda **kwargs: deepcopy(full))
    recent = recent_payload()
    before = deepcopy(recent)
    p = builder.build_all_dates_payload(recent)
    assert recent == before
    assert p["events"][1] == recent["events"][0]
    assert p["generated_at_utc"] == recent["generated_at_utc"]
    assert p["retained_from_date"] == "2026-01-30"
    assert "location_held_records" not in p


@pytest.mark.parametrize("changed", ["title", "first_seen_at_utc", "event_key", "event_date"])
def test_current_row_changes_are_rejected(monkeypatch, changed):
    p = all_payload()
    p["events"][1][changed] = "fictional-change" if changed != "event_date" else "2026-10-12"
    monkeypatch.setattr(builder, "build_lp_events", lambda **kwargs: p)
    with pytest.raises(ValueError):
        builder.build_all_dates_payload(recent_payload())


@pytest.mark.parametrize("start,end", [("2026-10-20", "2026-10-20"), ("2026-07-06", "2026-07-13")])
def test_extra_rows_inside_recent_window_are_rejected(monkeypatch, start, end):
    p = all_payload()
    p["events"].append(dict(p["events"][1], event_key="fictional-extra", event_date=start, event_end_date=end))
    p["summary"].update(event_count=3, counts_by_display_source={"official_events": 3})
    monkeypatch.setattr(builder, "build_lp_events", lambda **kwargs: p)
    with pytest.raises(ValueError, match="recent window"):
        builder.build_all_dates_payload(recent_payload())


def test_manifest_is_additive_and_binds_all_dates_bytes(tmp_path):
    for name in ("events.sqlite", "event_signals.sqlite", "lp_events.json"):
        (tmp_path / name).write_bytes(b"fictional")
    original = _build_manifest(tmp_path, "external-events-latest")
    assert set(original["assets"]) == {"events.sqlite", "event_signals.sqlite", "lp_events.json"}
    (tmp_path / builder.ALL_DATES_ASSET).write_text(json.dumps(all_payload()))
    new = _build_manifest(tmp_path, "external-events-latest")
    assert all(new["assets"][key] == value for key, value in original["assets"].items())
    assert new["assets"][builder.ALL_DATES_ASSET]["size_bytes"] > 0


@pytest.mark.parametrize("missing", ["history_window_days", "history_start_date"])
def test_all_dates_requires_explicit_null_window_fields(missing):
    p = all_payload()
    p.update(history_scope=builder.ALL_DATES_SCOPE, retained_from_date="2026-01-30", retained_through_date="2026-10-11")
    p.pop(missing)
    with pytest.raises(ValueError, match="explicit unbounded"):
        builder.validate_all_dates_payload(p)


@pytest.mark.parametrize("field", ["identity_held_records", "location_held_records"])
def test_public_all_dates_validation_rejects_private_candidate_details(field):
    p = all_payload()
    for name in ["identity_held_records", "location_held_records"]:
        p.pop(name)
    p.update(history_scope=builder.ALL_DATES_SCOPE, retained_from_date="2026-01-30", retained_through_date="2026-10-11")
    p[field] = []
    with pytest.raises(ValueError, match="private candidate details"):
        builder.validate_all_dates_payload(p)


def test_real_sqlite_build_and_protected_write_are_unbounded_private_and_read_only(tmp_path):
    events, signals, registry_path = [tmp_path / name for name in ["events.sqlite", "signals.sqlite", "registry.json"]]
    with sqlite3.connect(events) as connection:
        connection.execute("CREATE TABLE venues (venue_id TEXT, venue_name TEXT, pref_name TEXT, capacity INTEGER)")
        connection.execute("INSERT INTO venues VALUES ('fictional-hall', '架空東ホール', '東京都', NULL)")
        connection.execute("CREATE TABLE events (event_uid TEXT, venue_id TEXT, title TEXT, start_date TEXT, start_time TEXT, end_date TEXT, end_time TEXT, status TEXT, url TEXT, description TEXT, performers TEXT, artist_name_resolved TEXT, event_category TEXT, source_type TEXT, source_url TEXT, first_seen_at_utc TEXT, updated_at_utc TEXT)")
        for index, day in enumerate(["2026-01-30", "2026-10-11", "2026-11-20"]):
            connection.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                f"fictional-record-{index}", "fictional-hall", f"架空の演奏会{index}", day, "19:00", day,
                None, "scheduled", f"https://venue.example.test/{index}", "fictional", "架空出演者",
                "架空出演者", "コンサート", "venue_official", f"https://venue.example.test/{index}",
                "2026-07-01T00:00:00Z", "2026-10-10T15:51:14Z"))
    with sqlite3.connect(signals) as connection:
        connection.execute("CREATE TABLE signal_sources (source_id TEXT, source_name TEXT)")
        connection.execute("CREATE TABLE signals (signal_uid TEXT, source_id TEXT, published_at_utc TEXT, title TEXT, url TEXT, snippet TEXT, score INTEGER, labels_json TEXT, first_seen_at_utc TEXT, updated_at_utc TEXT)")
    paths = dict(events_db_path=events, event_signals_db_path=signals)
    candidates = canonical._build_lp_event_candidates(include_past=True, as_of_date=date(2026, 10, 11), **paths)
    assert len(candidates["events"]) == 3
    public = [dict(event_uid=row["event_key"], source_id=row["display_source_id"],
        source_record_id=row["supporting_sources"][0]["record_id"], source_policy_status="approved",
        title=row["title"], start_date=row["event_date"], end_date=row["event_end_date"],
        start_time=row["event_start_time"], venue_name=row["venue_name"], artist_name=row["artist_name"])
        for row in candidates["events"][:2]]
    seed = identities.canonical_bytes({"events": {"items": public, "publicationPolicy": {
        "status": "enforced", "defaultDeny": True, "publishedCount": 2}}})
    registry = identities.seed_registry(seed, expected_sha256=identities.digest(seed), expected_count=2)
    registry_path.write_bytes(identities.canonical_bytes(registry))
    before = {path: path.read_bytes() for path in [events, signals, registry_path]}
    recent = canonical.build_lp_events(as_of_date=date(2026, 10, 11), identity_registry_path=registry_path, **paths)
    recent.pop("identity_held_records")
    assert len(recent["events"]) == 1
    full = builder.build_all_dates_payload(recent, identity_registry_path=registry_path, **paths)
    assert len(full["events"]) == 2 and full["events"][0]["event_date"] == "2026-01-30"
    assert full["summary"]["identity_held_record_count"] == 1
    output = tmp_path / "all.json"
    canonical.write_lp_events(full, output, identity_registry_path=registry_path)
    published = json.loads(output.read_bytes())
    builder.validate_all_dates_payload(published, recent)
    assert "identity_held_records" not in published and "location_held_records" not in published
    assert published["summary"]["identity_held_record_count"] == 1
    assert published["generated_at_utc"] == recent["generated_at_utc"]
    assert all(path.read_bytes() == raw for path, raw in before.items())
