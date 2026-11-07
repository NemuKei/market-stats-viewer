"""The map and ID requests here are synthetic; no policy or approval changes."""

import json
from copy import deepcopy
from datetime import date
import pytest
from scripts.build_lp_events import build_lp_events
from scripts.reviewed_source_map import SourceMapError
from scripts.public_lp_projection import publication_preview
import sqlite3
from pathlib import Path
from scripts.build_lp_events import _build_lp_event_candidates
from scripts.event_identity_registry import (
    apply_review,
    load_registry,
    observation_from_row,
)

ROOT = Path(__file__).resolve().parents[1]


def setup_case():
    candidates = _build_lp_event_candidates(as_of_date=date(2026, 11, 6))["events"]
    current, _ = load_registry()
    targets = [
        r
        for r in candidates
        if r["title"] == "Hey! Say! JUMP DOME TOUR 2026-2027 Juliet"
        and r["event_date"] in {"2026-12-12", "2026-12-13", "2026-12-19", "2026-12-20"}
    ]
    assert len(targets) == 4
    # Build a test-only pre-registration state. It works both before and after
    # the real four IDs are adopted and never changes the production registry.
    from scripts.event_identity_registry import resolve_rows, identity_from_row, canonical_bytes, digest
    from test_event_identity_registry import registry_for
    full = _build_lp_event_candidates(as_of_date=date(2026, 11, 6), include_past=True)["events"]
    known, _ = resolve_rows(full, current)
    target_identities = [identity_from_row(row) for row in targets]
    old = registry_for([row for row in known if identity_from_row(row) not in target_identities])
    sha = digest(canonical_bytes(old))
    request = {
        "schema_version": 1,
        "expected_revision": old["revision"],
        "kind": "new",
        "previous_ids": [],
        "candidates": [
            {"event_uid": None, "observation": observation_from_row(r)} for r in targets
        ],
        "evidence": {
            "url": "https://example.test/hypothetical",
            "reviewed_at_utc": "2026-11-06T06:00:00Z",
            "reason": "TEST ONLY",
        },
    }
    new = apply_review(old, request)
    db = sqlite3.connect((ROOT / "data/events.sqlite").as_uri() + "?mode=ro", uri=True)
    records = []
    for row in targets:
        sid = next(
            x["record_id"]
            for x in row["supporting_sources"]
            if x["source_id"] == "official_events"
        )
        source_url, detail_url = db.execute(
            "select source_url,url from events where event_uid=?", (sid,)
        ).fetchone()
        records.append(
            {
                "observation": observation_from_row(row),
                "source": {
                    "source_id": "official_events",
                    "record_id": sid,
                    "source_url": source_url,
                    "detail_url": detail_url,
                },
            }
        )
    db.close()
    return candidates, old, sha, new, None, records, None, None


def map_record(rec, uid):
    return {
        "event_uid": uid,
        "observation": rec["observation"],
        "source": rec["source"],
        "source_class": "venue_official",
        "fact_review": "reviewed",
        "public_urls": [rec["source"]["source_url"], rec["source"]["detail_url"]],
    }


def setup_files(tmp_path):
    args = setup_case()
    candidates, old, sha, new, policy, records, read, project = args
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(new, ensure_ascii=False))
    record = records[0]
    fingerprint = record["observation"]["fingerprint"]
    uid = next(
        e["event_uid"]
        for e in new["events"]
        if any(
            o["active"] and o["fingerprint"] == fingerprint for o in e["observations"]
        )
    )
    source = map_record(record, uid)
    import re

    original = next(
        r
        for r in candidates
        if r["event_key"] == record["observation"]["candidate_key"]
    )
    source["public_urls"] = sorted(
        set(source["public_urls"])
        | {
            url
            for member in original["supporting_sources"]
            for value in member.values()
            if isinstance(value, str)
            for url in re.findall(r"https?://[^\s]+", value)
        }
    )
    map_path = tmp_path / "sources.json"
    map_path.write_text(
        json.dumps({"schema_version": 1, "records": [source]}, ensure_ascii=False)
    )
    from scripts.event_identity_registry import resolve_rows
    from scripts.build_lp_events import _build_lp_event_candidates
    from scripts.reviewed_source_map import apply_reviewed_source_map

    mapped = apply_reviewed_source_map(candidates, new, map_path.read_bytes(), ROOT / "data/events.sqlite")
    mapped, _ = resolve_rows(mapped, new)
    source["publication"] = publication_preview(next(row for row in mapped if row["event_key"] == uid))
    source["publication"]["status"] = "reviewed"  # Synthetic publication decision only.
    map_path.write_text(json.dumps({"schema_version": 1, "records": [source]}))
    full = _build_lp_event_candidates(as_of_date=date(2026, 11, 6), include_past=True)[
        "events"
    ]
    resolved, _ = resolve_rows(full, new)
    baseline = tmp_path / "baseline.json"
    from scripts.reviewed_source_map import source_signature, read_official_sources

    official = read_official_sources(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "data/events.sqlite"
    )
    baseline.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "asset_sha256": "a" * 64,
                "event_sources": {
                    r["event_key"]: source_signature(r, official, legacy_row=True)
                    for r in resolved
                    if r["event_key"] != uid
                },
            }
        )
    )
    return args, registry_path, map_path, baseline, source


def test_producer_opt_in_preserves_unselected_rows(tmp_path):
    args, registry, map_path, baseline, source = setup_files(tmp_path)
    initial = build_lp_events(
        as_of_date=date(2026, 11, 6), identity_registry_path=registry
    )
    selected = build_lp_events(
        as_of_date=date(2026, 11, 6),
        identity_registry_path=registry,
        reviewed_source_map_path=map_path,
        reviewed_source_baseline_path=baseline,
    )
    before = {r["event_key"]: r for r in initial["events"]}
    after = {r["event_key"]: r for r in selected["events"]}
    assert before.keys() == after.keys()
    assert all(before[k] == after[k] for k in before if k != source["event_uid"])
    row = after[source["event_uid"]]
    assert (
        row["url"] == source["source"]["detail_url"]
        and row["evidence_url"] == source["source"]["source_url"]
        and row["evidence_snippet"] == ""
    )
    target = next(
        s
        for s in row["supporting_sources"]
        if s["record_id"] == source["source"]["record_id"]
    )
    assert target["evidence_url"] == source["source"]["source_url"]


def test_unbound_and_stale_review_fail_without_writing(tmp_path):
    args, registry, map_path, baseline, source = setup_files(tmp_path)
    source["event_uid"] = "missing"
    map_path.write_text(json.dumps({"schema_version": 1, "records": [source]}))
    with pytest.raises(SourceMapError, match="active fixed ID"):
        build_lp_events(
            as_of_date=date(2026, 11, 6),
            identity_registry_path=registry,
            reviewed_source_map_path=map_path,
            reviewed_source_baseline_path=baseline,
        )
    args, registry, map_path, baseline, source = setup_files(tmp_path)
    source["source"]["source_url"] += "?changed"
    source["public_urls"].append(source["source"]["source_url"])
    map_path.write_text(json.dumps({"schema_version": 1, "records": [source]}))
    with pytest.raises(SourceMapError, match="stored source changed"):
        build_lp_events(
            as_of_date=date(2026, 11, 6),
            identity_registry_path=registry,
            reviewed_source_map_path=map_path,
            reviewed_source_baseline_path=baseline,
        )


def test_default_build_has_no_implicit_review_file(monkeypatch):
    from scripts import reviewed_source_map
    def unexpected_implicit_selection(*args, **kwargs):
        raise AssertionError("source selection must be explicitly enabled")
    monkeypatch.setattr(reviewed_source_map, "apply_reviewed_source_map", unexpected_implicit_selection)
    existing = json.loads(
        (
            __import__("pathlib").Path(__file__).resolve().parents[1]
            / "data/lp_events.json"
        ).read_text()
    )
    new = build_lp_events(as_of_date=date.fromisoformat(existing["as_of_date"]))
    _, sha = load_registry()
    assert new["events"] and new["identity_registry"]["sha256"] == sha


def test_reviewed_selection_survives_all_dates_generation(tmp_path):
    from scripts.build_all_dates_lp_events import (
        build_all_dates_payload,
        validate_all_dates_payload,
    )

    args, registry, map_path, baseline, source = setup_files(tmp_path)
    recent = build_lp_events(
        as_of_date=date(2026, 11, 6),
        identity_registry_path=registry,
        reviewed_source_map_path=map_path,
        reviewed_source_baseline_path=baseline,
    )
    recent.pop("identity_held_records")
    recent.pop("location_held_records")
    all_dates = build_all_dates_payload(
        recent,
        identity_registry_path=registry,
        reviewed_source_map_path=map_path,
        reviewed_source_baseline_path=baseline,
    )
    assert next(
        r for r in all_dates["events"] if r["event_key"] == source["event_uid"]
    ) == next(r for r in recent["events"] if r["event_key"] == source["event_uid"])
    validate_all_dates_payload(all_dates, recent, allow_internal_identity_records=True)


def test_all_scheduled_rebuilds_use_tracked_map_and_release_all_dates_matches():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in (
        "update_events_official.yml",
        "update_signals.yml",
        "update_signals_venue_web_discovery.yml",
    ):
        text = (root / ".github/workflows" / name).read_text()
        assert text.count("git cat-file -e HEAD:data/reviewed_event_sources.json") == 2
        assert text.count("--reviewed-source-map data/reviewed_event_sources.json") == 2
        assert (
            text.count(
                "git diff --quiet HEAD -- data/reviewed_event_sources.json data/reviewed_event_baseline.json"
            )
            == 2
        )
    publish = (
        root / ".github/workflows/publish_external_events_assets.yml"
    ).read_text()
    assert (
        "build_all_dates_lp_events --reviewed-source-map data/reviewed_event_sources.json"
        in publish
    )


def test_new_unreviewed_ids_are_held_without_stopping_generation(tmp_path):
    args, registry, map_path, baseline, source = setup_files(tmp_path)
    from scripts.event_identity_registry import resolve_rows

    old, _ = resolve_rows(args[0], args[1])
    from scripts.reviewed_source_map import source_signature, read_official_sources

    official = read_official_sources(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "data/events.sqlite"
    )
    baseline.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "asset_sha256": "a" * 64,
                "event_sources": {
                    r["event_key"]: source_signature(r, official, legacy_row=True) for r in old
                },
            }
        )
    )
    result = build_lp_events(
        as_of_date=date(2026, 11, 6),
        identity_registry_path=registry,
        reviewed_source_map_path=map_path,
        reviewed_source_baseline_path=baseline,
    )
    holds = [r for r in result["identity_held_records"] if r["reason"] == "source_review_required"]
    assert len(holds) == 3
    assert len(result["events"]) == len(old) + 1


def test_baseline_from_verified_asset_rejects_wrong_hash_and_invalid_scope():
    from scripts.reviewed_source_map import baseline_from_asset
    from scripts.event_identity_registry import digest

    asset = json.dumps(
        {
            "history_scope": "all_verified_retained",
            "events": [{"event_key": "old", "supporting_sources": []}],
        }
    ).encode()
    assert list(baseline_from_asset(asset, digest(asset), {})["event_sources"]) == [
        "old"
    ]
    with pytest.raises(SourceMapError, match="hash mismatch"):
        baseline_from_asset(asset, "a" * 64, {})
    with pytest.raises(SourceMapError, match="all-dates"):
        baseline_from_asset(b"{}", digest(b"{}"), {})


def test_existing_id_source_and_supporting_link_changes_stop():
    from scripts.reviewed_source_map import guard_new_ids, source_signature

    row = {
        "event_key": "old",
        "display_source_id": "official_events",
        "display_source_class": "venue_official",
        "url": "https://example.org/event",
        "evidence_url": "https://venue.example/schedule",
        "supporting_sources": [
            {
                "source_id": "official_events",
                "record_id": "r",
                "url": "https://example.org/event",
            }
        ],
    }
    baseline = json.dumps(
        {
            "schema_version": 4,
            "asset_sha256": "a" * 64,
            "event_sources": {
                "old": source_signature(
                    row,
                    {
                        "r": (
                            "https://venue.example/schedule",
                            "https://example.org/event",
                        )
                    },
                    legacy_row=True,
                )
            },
        }
    ).encode()
    selection = b'{"schema_version":1,"records":[]}'
    official = {"r": ("https://venue.example/schedule", "https://example.org/event")}
    guard_new_ids([row], selection, baseline, set(), official)
    for field, value in [
        ("display_source_id", "starto_concert"),
        ("display_source_class", "promoter_official"),
        ("url", "https://example.org/new"),
        ("evidence_url", "https://venue.example/new"),
    ]:
        changed = deepcopy(row)
        changed[field] = value
        with pytest.raises(
            SourceMapError, match="existing ID source or public link changed"
        ):
            guard_new_ids([changed], selection, baseline, set(), official)
    changed = deepcopy(row)
    changed["supporting_sources"][0]["url"] = "https://other.example/private"
    with pytest.raises(
        SourceMapError, match="existing ID source or public link changed"
    ):
        guard_new_ids([changed], selection, baseline, set(), official)


def test_each_selected_and_supporting_url_requires_decision(tmp_path):
    args, registry, map_path, baseline, source = setup_files(tmp_path)
    source["public_urls"].remove(source["source"]["detail_url"])
    map_path.write_text(json.dumps({"schema_version": 1, "records": [source]}))
    with pytest.raises(SourceMapError):
        build_lp_events(
            as_of_date=date(2026, 11, 6),
            identity_registry_path=registry,
            reviewed_source_map_path=map_path,
            reviewed_source_baseline_path=baseline,
        )
    args, registry, map_path, baseline, source = setup_files(tmp_path)
    extra = next(
        u
        for u in source["public_urls"]
        if u not in (source["source"]["source_url"], source["source"]["detail_url"])
    )
    source["public_urls"].remove(extra)
    map_path.write_text(json.dumps({"schema_version": 1, "records": [source]}))
    with pytest.raises(SourceMapError, match="unreviewed supporting source URL"):
        build_lp_events(
            as_of_date=date(2026, 11, 6),
            identity_registry_path=registry,
            reviewed_source_map_path=map_path,
            reviewed_source_baseline_path=baseline,
        )


def test_hidden_db_source_change_is_detected():
    from scripts.reviewed_source_map import guard_new_ids, source_signature

    row = {
        "event_key": "old",
        "display_source_id": "official_events",
        "display_source_class": "venue_official",
        "url": "https://tickets.example/event",
        "evidence_url": "https://tickets.example/event",
        "supporting_sources": [{"source_id": "official_events", "record_id": "r"}],
    }
    before = {"r": ("https://venue.example/old", "https://tickets.example/event")}
    after = {"r": ("https://venue.example/new", "https://tickets.example/event")}
    baseline = json.dumps(
        {
            "schema_version": 4,
            "asset_sha256": "a" * 64,
            "event_sources": {"old": source_signature(row, before, legacy_row=True)},
        }
    ).encode()
    guard_new_ids([row], b'{"schema_version":1,"records":[]}', baseline, set(), before)
    with pytest.raises(
        SourceMapError, match="existing ID source or public link changed"
    ):
        guard_new_ids(
            [row], b'{"schema_version":1,"records":[]}', baseline, set(), after
        )


def test_baseline_cli_requires_snapshot_hashes_and_never_overwrites(tmp_path):
    import subprocess
    from scripts.event_identity_registry import digest
    import sys

    db = tmp_path / "events.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("create table events(event_uid text, source_url text, url text)")
    connection.execute(
        "insert into events values(?,?,?)",
        ("r", "https://venue.example/show", "https://show.example/event"),
    )
    connection.commit()
    connection.close()
    asset = tmp_path / "all.json"
    asset.write_text(
        json.dumps(
            {
                "history_scope": "all_verified_retained",
                "events": [
                    {
                        "event_key": "old",
                        "supporting_sources": [
                            {"source_id": "official_events", "record_id": "r"}
                        ],
                    }
                ],
            }
        )
    )
    out = tmp_path / "baseline.json"
    command = [
        sys.executable,
        "-m",
        "scripts.reviewed_source_map",
        "--asset",
        str(asset),
        "--asset-sha256",
        digest(asset.read_bytes()),
        "--events-db",
        str(db),
        "--events-db-sha256",
        digest(db.read_bytes()),
        "--output",
        str(out),
    ]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0 and list(
        json.loads(out.read_text())["event_sources"]
    ) == ["old"]
    before = out.read_bytes()
    assert (
        subprocess.run(command, capture_output=True).returncode != 0
        and out.read_bytes() == before
    )
