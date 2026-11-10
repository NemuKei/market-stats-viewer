"""Synthetic pinned legacy corrections; no production DB writes."""

from copy import deepcopy
import sqlite3
import pytest
from scripts import event_identity_registry as ids
from scripts.reviewed_artist_correction import MODE, split_records, validate_correction
from scripts.reviewed_source_map import (
    baseline_from_asset,
    source_signature,
    reviewed_rows_for_publication,
    guard_new_ids,
)
from scripts.public_lp_projection import attach_public_row_checks, project_payload
from test_event_identity_registry import record, payload, registry_for, request


@pytest.fixture
def case(tmp_path):
    original = payload([record()])
    old = original["events"][0]
    old.update(
        capacity=17000,
        raw_artist_name="historical raw artist",
        raw_venue_name="historical raw venue",
    )
    uid = old["event_key"]
    reg = registry_for([old])
    current = payload([record(artist_name="Corrected artist")])["events"][0]
    req = request(reg, "correction", [uid], [(uid, current)])
    req["evidence"]["url"] = old["url"]
    changed = ids.apply_review(reg, req)
    sources = {"source-A": ("https://example.com/schedule.json", old["url"])}
    asset = ids.canonical_bytes(dict(original, history_scope="all_verified_retained"))
    baseline = baseline_from_asset(
        asset, ids.digest(asset), sources, retain_published_rows=True
    )
    rec = dict(
        mode=MODE,
        event_uid=uid,
        observation=ids.observation_from_row(current),
        source_signature=source_signature(current, sources),
        previous_row_sha256=ids.digest(ids.canonical_bytes(old)),
        correction_request_sha256=ids.digest(ids.canonical_bytes(req)),
        evidence=req["evidence"],
    )
    db = tmp_path / "events.sqlite"
    with sqlite3.connect(db) as c:
        c.execute("create table events(event_uid text,source_url text,url text)")
        c.execute(
            "insert into events values(?,?,?)", ("source-A", *sources["source-A"])
        )
    return old, current, reg, changed, sources, baseline, rec, original, req, db


def test_exact_single_field_preservation_and_idempotency(case):
    old, current, reg, changed, sources, base, rec, _, req, _ = case
    result = validate_correction(rec, base, changed, sources, current)
    assert result == dict(old, artist_name="Corrected artist")
    assert ids.apply_review(changed, req) == changed
    assert changed["events"][0]["observations"][0] == dict(
        reg["events"][0]["observations"][0], active=False
    )
    assert split_records({"schema_version": 1, "records": [rec]})[1] == [rec]


@pytest.mark.parametrize(
    "field,value",
    [
        ("capacity", 18000),
        ("updated_at_utc", "2026-10-07T00:00:00Z"),
        ("raw_artist_name", "changed"),
        ("url", "https://example.com/other"),
    ],
)
def test_full_previous_row_hash_includes_all_fields(case, field, value):
    _, cur, _, reg, src, base, rec, *_ = case
    base["published_rows"][rec["event_uid"]][field] = value
    with pytest.raises(ValueError):
        validate_correction(rec, base, reg, src, cur)


@pytest.mark.parametrize(
    "change",
    [
        "date",
        "venue",
        "title",
        "source",
        "unknown",
        "blank",
        "same",
        "new_id",
        "wrong_relation",
        "active_old",
        "evidence",
        "signature",
        "current_title",
        "current_url",
        "missing_official",
        "acquisition",
    ],
)
def test_fail_closed(case, change):
    old, cur, _, reg, src, base, rec, *_ = case
    if change in ("date", "venue", "title"):
        field = {"date": "event_date", "venue": "venue_name", "title": "title"}[change]
        rec["observation"]["identity"][field] = "different"
    elif change == "source":
        rec["observation"]["source_records"][0]["record_id"] = "different"
    elif change == "unknown":
        rec["extra"] = "not permitted"
    elif change == "blank":
        rec["observation"]["identity"]["artist_name"] = ""
    elif change == "same":
        rec["observation"]["identity"]["artist_name"] = old["artist_name"]
    elif change == "new_id":
        rec["event_uid"] = "missing"
    elif change == "wrong_relation":
        reg["relations"][0]["kind"] = "new"
    elif change == "active_old":
        reg["events"][0]["observations"][0]["active"] = True
    elif change == "evidence":
        rec["evidence"]["url"] = "https://evil.example/unrelated"
    elif change == "signature":
        rec["source_signature"] = "0" * 64
    elif change == "current_title":
        cur["title"] = "different"
    elif change == "current_url":
        cur["url"] = "https://example.com/other"
    elif change == "missing_official":
        src.clear()
    elif change == "acquisition":
        src["source-A"] = ("https://example.com/other.json", old["url"])
    with pytest.raises(ValueError):
        split_records({"schema_version": 1, "records": [rec]})
        validate_correction(rec, base, reg, src, cur)


def test_build_guard_writer_path_retains_metadata(case):
    old, cur, _, reg, src, base, rec, original, _, db = case
    map_raw = ids.canonical_bytes({"schema_version": 1, "records": [rec]})
    base_raw = ids.canonical_bytes(base)
    rows, failed = reviewed_rows_for_publication(
        [cur], reg, map_raw, base_raw, db, None
    )
    p = ids.apply_to_payload(
        dict(original, events=rows), reg, ids.digest(ids.canonical_bytes(reg))
    )
    reviewed = set()
    assert (
        guard_new_ids(
            p["events"],
            map_raw,
            base_raw,
            {cur["event_key"]},
            src,
            registry=reg,
            retained_changes=[],
            reviewed_event_uids=reviewed,
            failed_source_uids=failed,
        )
        == set()
    )
    assert not reviewed
    attach_public_row_checks(p, reviewed_ids=reviewed)
    out = project_payload(p)
    assert out["events"] == [dict(old, artist_name="Corrected artist")]
    ids.validate_resolved_rows(out["events"], reg)


def test_missing_ambiguous_and_expired_candidates(case):
    _, cur, _, reg, _, base, rec, _, _, db = case
    m = ids.canonical_bytes({"schema_version": 1, "records": [rec]})
    b = ids.canonical_bytes(base)
    for rows in ([], [cur, cur]):
        with pytest.raises(ValueError):
            reviewed_rows_for_publication(rows, reg, m, b, db, None)
    assert reviewed_rows_for_publication(
        [], reg, m, b, db, None, history_start_date="2027-01-01"
    ) == ([], set())


def test_duplicate_review_and_v4_rejected(case):
    _, cur, _, reg, src, base, rec, *_ = case
    with pytest.raises(ValueError):
        split_records({"schema_version": 1, "records": [rec, deepcopy(rec)]})
    base["schema_version"] = 4
    with pytest.raises(ValueError):
        validate_correction(rec, base, reg, src, cur)


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_strict_schema_type(case, version):
    with pytest.raises(ValueError):
        split_records({"schema_version": version, "records": [case[6]]})


def test_stale_baseline_cannot_skip_an_intermediate_correction(case):
    old, current, _, reg, sources, base, rec, *_ = case
    newest = payload([record(artist_name="Third artist")])["events"][0]
    req = request(reg, "correction", [old["event_key"]], [(old["event_key"], newest)])
    req["evidence"]["url"] = old["url"]
    updated = ids.apply_review(reg, req)
    second = dict(
        rec,
        observation=ids.observation_from_row(newest),
        source_signature=source_signature(newest, sources),
        correction_request_sha256=ids.digest(ids.canonical_bytes(req)),
        evidence=req["evidence"],
    )
    with pytest.raises(ValueError, match="directly follow"):
        validate_correction(second, base, updated, sources, newest)
    with pytest.raises(ValueError):
        validate_correction(rec, base, updated, sources, current)
