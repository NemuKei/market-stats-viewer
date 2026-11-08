"""Synthetic raw observations: reviewed publication and private quarantine."""
import sqlite3

import pytest

from scripts import reviewed_events_db as gate
from scripts.update_events_data import init_db


def raw(uid, venue="gated", **changes):
    row = dict(event_uid=uid, venue_id=venue, title="Fixture match", start_date="2027-01-03",
        start_time="17:05", end_date=None, end_time=None, all_day=0, status="scheduled",
        url="https://official.example/game", description=None, performers=None,
        artist_name_resolved="Fixture team", artist_confidence="high", event_category="その他",
        capacity=None, source_type="html", source_url="https://official.example/calendar",
        source_event_key=uid, data_hash="a" * 64, first_seen_at_utc="2026-11-08T00:00:00Z",
        updated_at_utc="2026-11-08T00:00:00Z")
    return {**row, **changes}


def database(path, rows):
    conn = init_db(path)
    for row in rows:
        columns = list(row)
        conn.execute(f"INSERT INTO events ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(row.values()))
    conn.commit()
    conn.execute("pragma wal_checkpoint(TRUNCATE)")
    conn.close()
    return path


def read(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return {r["event_uid"]: dict(r) for r in conn.execute("select * from events")}


def publication(row):
    return dict(event_key="fixed-" + row["event_uid"], title=row["title"], event_date=row["start_date"],
        event_end_date=row["end_date"] or row["start_date"], event_start_time=row["start_time"], event_end_time=row["end_time"],
        artist_name=row["artist_name_resolved"], event_category=row["event_category"], url=row["url"], evidence_url=row["source_url"],
        first_seen_at_utc=row["first_seen_at_utc"], updated_at_utc=row["updated_at_utc"])


def options(tmp_path, monkeypatch, old, current, decisions=None):
    monkeypatch.setattr(gate, "reviewed_official_rows", lambda **kw: decisions or {})
    for name in ("registry.json", "map.json", "baseline.json", "signals.sqlite"):
        (tmp_path / name).write_bytes(b"{}")
    return dict(previous_db=database(tmp_path / "old.sqlite", old), candidate_db=database(tmp_path / "private.sqlite", current),
        output=tmp_path / "public.sqlite", reviewed_venues={"gated"}, registry_path=tmp_path / "registry.json",
        source_map_path=tmp_path / "map.json", baseline_path=tmp_path / "baseline.json", signals_db=tmp_path / "signals.sqlite")


def test_private_held_rows_do_not_block_unrelated_normal_updates(tmp_path, monkeypatch):
    old = raw("old", description="OLD LEGACY BODY")
    changed = {**old, "description": "UNREVIEWED https://private.example/body"}
    unseen = raw("held", url="https://unreviewed.example/detail")
    normal = raw("normal", venue="normal")
    kw = options(tmp_path, monkeypatch, [old], [changed, unseen, normal])
    report = gate.build_reviewed_events_db(**kw)
    assert read(kw["output"]) == {"old": old, "normal": normal}
    assert report["held_changed"] == 1 and report["held_new"] == 1


def test_reviewed_new_raw_row_uses_public_facts_without_body_or_capacity(tmp_path, monkeypatch):
    observed = raw("new", description="UNAPPROVED BODY https://private.example/body", performers="PRIVATE TEXT", capacity=99000)
    approved = publication(observed)
    decision = dict(row=approved, public_urls=[observed["url"], observed["source_url"]])
    kw = options(tmp_path, monkeypatch, [], [observed], {"new": decision})
    gate.build_reviewed_events_db(**kw)
    result = read(kw["output"])["new"]
    assert result["description"] is result["performers"] is result["capacity"] is None
    assert result["title"] == approved["title"] and result["start_time"] == approved["event_start_time"]
    assert "private.example" not in str(result)


def test_unreviewed_embedded_link_stops_before_replacing_old_output(tmp_path, monkeypatch):
    row = raw("new", source_event_key="https://unreviewed.example/key")
    decision = dict(row=publication(row), public_urls=[row["url"], row["source_url"]])
    kw = options(tmp_path, monkeypatch, [], [row], {"new": decision})
    kw["output"].write_bytes(b"PREVIOUS OUTPUT")
    with pytest.raises(ValueError, match="URL"):
        gate.build_reviewed_events_db(**kw)
    assert kw["output"].read_bytes() == b"PREVIOUS OUTPUT"


def test_explicit_withdrawal_keeps_old_body_and_changes_only_status_metadata(tmp_path, monkeypatch):
    old = raw("old", description="LEGACY BODY")
    cancelled = {**old, "status": "cancelled", "description": "UNREVIEWED BODY"}
    kw = options(tmp_path, monkeypatch, [old], [cancelled])
    report = gate.build_reviewed_events_db(**kw)
    result = read(kw["output"])["old"]
    assert result["status"] == "cancelled" and result["description"] == old["description"]
    assert {k for k in old if old[k] != result[k]} <= {"status", "data_hash", "updated_at_utc"}
    assert report["withdrawals"] == 1


@pytest.mark.parametrize("field,value", [("start_date", "2027-01-04"), ("artist_name_resolved", "Different team")])
def test_withdrawal_with_changed_identity_or_source_stops(tmp_path, monkeypatch, field, value):
    old = raw("old")
    cancelled = {**old, "status": "cancelled", field: value}
    kw = options(tmp_path, monkeypatch, [old], [cancelled])
    with pytest.raises(ValueError, match="withdrawal"):
        gate.build_reviewed_events_db(**kw)
    assert not kw["output"].exists()


def test_absent_source_is_not_a_cancellation_and_unchanged_output_keeps_bytes(tmp_path, monkeypatch):
    old = raw("old")
    kw = options(tmp_path, monkeypatch, [old], [])
    gate.build_reviewed_events_db(**kw)
    assert kw["output"].read_bytes() == kw["previous_db"].read_bytes()
    assert read(kw["output"])["old"]["status"] == "scheduled"


def test_invalid_review_does_not_replace_output(tmp_path, monkeypatch):
    kw = options(tmp_path, monkeypatch, [], [raw("new")])
    def invalid(**kw):
        raise ValueError("invalid source map")
    monkeypatch.setattr(gate, "reviewed_official_rows", invalid)
    with pytest.raises(ValueError, match="source map"):
        gate.build_reviewed_events_db(**kw)
    assert not kw["output"].exists()


def test_real_map_requires_publication_review_and_holds_stale_source(tmp_path):
    """Actual fixture pipeline and ID/map validation; decisions remain test-only."""
    import json
    from pathlib import Path
    import shutil
    from scripts.build_lp_events import _build_lp_event_candidates
    from scripts.event_identity_registry import load_registry, observation_from_row, resolve_rows
    from scripts.public_lp_projection import publication_preview
    from scripts.reviewed_source_map import apply_reviewed_source_map

    data = Path(__file__).resolve().parents[1] / "data"
    for name in ("events.sqlite", "event_signals.sqlite", "event_identity_registry.json", "reviewed_event_baseline.json"):
        shutil.copyfile(data / name, tmp_path / name)
    candidate = tmp_path / "events.sqlite"
    registry, _ = load_registry(tmp_path / "event_identity_registry.json")
    rows = _build_lp_event_candidates(events_db_path=candidate,
        event_signals_db_path=tmp_path / "event_signals.sqlite", include_past=True)["events"]
    fixed, _ = resolve_rows(rows, registry)
    selected = next(r for r in fixed if r["display_source_id"] == "official_events"
                    and len(r["supporting_sources"]) == 1)
    original = next(r for r in rows if r["event_key"] == observation_from_row(selected)["candidate_key"])
    uid = original["supporting_sources"][0]["record_id"]
    raw_row = read(candidate)[uid]
    rec = dict(event_uid=selected["event_key"], observation=observation_from_row(original),
        source=dict(source_id="official_events", record_id=uid, source_url=raw_row["source_url"], detail_url=raw_row["url"]),
        source_class="venue_official", fact_review="reviewed", public_urls=sorted({raw_row["source_url"], raw_row["url"]}))
    doc = {"schema_version": 1, "records": [rec]}
    mapped = apply_reviewed_source_map([original], registry, json.dumps(doc).encode(), candidate)[0]
    mapped["event_key"] = selected["event_key"]
    rec["publication"] = publication_preview(mapped)
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps(doc))
    options = dict(candidate_db=candidate, registry_path=tmp_path / "event_identity_registry.json",
        source_map_path=map_path, baseline_path=tmp_path / "reviewed_event_baseline.json", signals_db=tmp_path / "event_signals.sqlite")
    assert gate.reviewed_official_rows(**options) == {}
    rec["publication"]["status"] = "reviewed"  # TEST ONLY, no actual publication approval.
    map_path.write_text(json.dumps(doc))
    assert set(gate.reviewed_official_rows(**options)) == {uid}
    with sqlite3.connect(candidate) as conn:
        conn.execute("update events set source_url=source_url || '?drift' where event_uid=?", (uid,))
    assert gate.reviewed_official_rows(**options) == {}


def test_input_changes_during_projection_do_not_replace_public_output(tmp_path, monkeypatch):
    kw = options(tmp_path, monkeypatch, [raw("old")], [raw("old"), raw("new", venue="normal")])
    def drift(**ignored):
        kw["registry_path"].write_bytes(b"CHANGED INPUT")
        return {}
    monkeypatch.setattr(gate, "reviewed_official_rows", drift)
    with pytest.raises(ValueError, match="input changed"):
        gate.build_reviewed_events_db(**kw)
    assert not kw["output"].exists()


def test_old_publication_review_does_not_reactivate_cancelled_event(tmp_path, monkeypatch):
    cancelled = raw("old", status="cancelled")
    row = {**cancelled, "status": "scheduled"}
    decision = dict(row=publication(row), public_urls=[row["url"], row["source_url"]])
    kw = options(tmp_path, monkeypatch, [cancelled], [row], {"old": decision})
    gate.build_reviewed_events_db(**kw)
    assert read(kw["output"])["old"] == cancelled


def test_readonly_inference_preserves_reviewed_db_bytes(tmp_path):
    import hashlib
    from pathlib import Path
    import subprocess
    import sys
    path = database(tmp_path / "public.sqlite", [raw("old")])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, "-B", "-m", "scripts.build_events_artist_inferred",
        "--db-path", str(path), "--output", str(tmp_path / "artists.csv"), "--skip-events-sync"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("confidence", ["source", "source_normalized", "cross_venue_title"])
def test_existing_inference_confidence_values_are_compatible(tmp_path, monkeypatch, confidence):
    row = raw("new", artist_confidence=confidence)
    decision = dict(row=publication(row), public_urls=[row["url"], row["source_url"]])
    kw = options(tmp_path, monkeypatch, [], [row], {"new": decision})
    gate.build_reviewed_events_db(**kw)
    assert read(kw["output"])["new"]["artist_confidence"] == confidence


def test_misconfigured_dated_venue_cannot_escape_projection(tmp_path, monkeypatch):
    kw = options(tmp_path, monkeypatch, [], [raw("new", venue="not_gated")])
    with sqlite3.connect(kw["candidate_db"]) as conn:
        conn.execute("INSERT INTO venues (venue_id,venue_name,pref_code,pref_name,source_type,source_url,config_json,created_at_utc,updated_at_utc) VALUES ('not_gated','A','13','東京都','html','https://official.example/','{\"dated_sessions\":true}','2026-11-08T00:00:00Z','2026-11-08T00:00:00Z')")
        conn.commit()
        conn.execute("pragma wal_checkpoint(TRUNCATE)")
    conn.close()
    with pytest.raises(ValueError, match="dated venue"):
        gate.build_reviewed_events_db(**kw)
    assert not kw["output"].exists()


def test_other_public_inference_writer_respects_venue_opt_in(tmp_path, monkeypatch):
    import json
    from scripts import build_events_artist_inferred as infer
    from scripts.events.types import VenueRecord
    path = database(tmp_path / "public.sqlite", [raw("old"), raw("normal", venue="normal")])
    monkeypatch.setattr(infer, "EVENTS_DB_PATH", path)
    venue = VenueRecord("gated", "有明アリーナ", "13", "東京都", None, "https://official.example/",
        "html", "https://official.example/", json.dumps({"dated_sessions": True}), True)
    monkeypatch.setattr(infer, "load_venue_registry", lambda: [venue])
    infer.sync_resolved_artists_to_events(path, [])
    assert read(path)["old"] == raw("old")
    assert read(path)["normal"]["artist_name_resolved"] != raw("normal")["artist_name_resolved"]
    alias = tmp_path / "hardlink.sqlite"
    alias.hardlink_to(path)
    infer.sync_resolved_artists_to_events(alias, [])
    assert read(path)["old"] == raw("old")


def test_public_and_private_db_hardlinks_are_rejected(tmp_path, monkeypatch):
    kw = options(tmp_path, monkeypatch, [raw("old")], [])
    kw["candidate_db"].unlink()
    kw["candidate_db"].hardlink_to(kw["previous_db"])
    with pytest.raises(ValueError, match="separate"):
        gate.build_reviewed_events_db(**kw)


def test_exclusive_projection_lock_cannot_be_entered_twice(tmp_path, monkeypatch):
    from scripts.event_identity_registry import registry_lock
    kw = options(tmp_path, monkeypatch, [raw("old")], [])
    with registry_lock(kw["output"]):
        with pytest.raises(FileExistsError):
            gate.build_reviewed_events_db(**kw)
    assert not kw["output"].exists()
