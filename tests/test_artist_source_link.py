"""Four real candidates with in-memory hypothetical IDs and policy only."""

import json
import sqlite3
from datetime import date
import pytest
from test_reviewed_source_map import setup_case, ROOT
from scripts.build_lp_events import build_lp_events, write_lp_events
from scripts.event_identity_registry import digest, resolve_rows
from scripts.reviewed_source_map import (
    source_signature,
    read_official_sources,
    embedded_urls,
    SourceMapError,
)
from scripts.validate_external_events import validate_payload
from scripts.public_lp_projection import publication_preview


def case(tmp_path, *, publication_reviewed=True):
    args = setup_case()
    candidates, old, _, new, _, _, _, _ = args
    targets = [
        r
        for r in candidates
        if r["title"] == "Hey! Say! JUMP DOME TOUR 2026-2027 Juliet"
        and r["event_date"] in {"2026-12-12", "2026-12-13", "2026-12-19", "2026-12-20"}
    ]
    db = sqlite3.connect(
        (ROOT / "data/event_signals.sqlite").as_uri() + "?mode=ro", uri=True
    )
    records = []
    for row in targets:
        member = next(
            x for x in row["supporting_sources"] if x["source_id"] == "starto_concert"
        )
        uid, source_url = db.execute(
            "select signal_uid,url from signals where signal_uid=?",
            (member["record_id"],),
        ).fetchone()
        from scripts.event_identity_registry import observation_from_row

        obs = observation_from_row(row)
        event = next(
            e
            for e in new["events"]
            if any(
                o["active"] and o["fingerprint"] == obs["fingerprint"]
                for o in e["observations"]
            )
        )
        records.append(
            {
                "mode": "artist_source_link",
                "event_uid": event["event_uid"],
                "candidate_key": obs["candidate_key"],
                "fingerprint": obs["fingerprint"],
                "source_id": "starto_concert",
                "record_id": uid,
                "evidence_url_sha256": digest(source_url.encode()),
                "fact_review": "reviewed",
            }
        )
    db.close()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(new, ensure_ascii=False))
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"schema_version": 1, "records": records}))
    if publication_reviewed:
        from scripts.reviewed_source_map import apply_reviewed_source_map
        mapped = apply_reviewed_source_map(candidates, new, mapping.read_bytes(), ROOT / "data/events.sqlite", ROOT / "data/event_signals.sqlite")
        mapped, _ = resolve_rows(mapped, new)
        by_uid = {row["event_key"]: row for row in mapped}
        for rec in records:
            rec["publication"] = publication_preview(by_uid[rec["event_uid"]])
            rec["publication"]["status"] = "reviewed"  # Hypothetical Git publication decision.
        mapping.write_text(json.dumps({"schema_version": 1, "records": records}))
    full = __import__(
        "scripts.build_lp_events", fromlist=["_build_lp_event_candidates"]
    )._build_lp_event_candidates(as_of_date=date(2026, 11, 6), include_past=True)[
        "events"
    ]
    old_rows, _ = resolve_rows(full, old)
    official = read_official_sources(ROOT / "data/events.sqlite")
    baseline = tmp_path / "baseline"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "asset_sha256": "a" * 64,
                "event_sources": {
                    r["event_key"]: source_signature(r, official, legacy_row=True) for r in old_rows
                },
            }
        )
    )
    return args, records, registry, mapping, baseline


def test_four_source_link_rows_preserve_the_upstream_contract(tmp_path):
    args, records, registry, mapping, baseline = case(tmp_path)
    payload = build_lp_events(
        as_of_date=date(2026, 11, 6),
        identity_registry_path=registry,
        reviewed_source_map_path=mapping,
        reviewed_source_baseline_path=baseline,
    )
    rows = {r["event_key"]: r for r in payload["events"]}
    selected = [rows[r["event_uid"]] for r in records]
    before, _ = resolve_rows(args[0], args[1])
    assert all(rows[r["event_key"]] == r for r in before)
    assert len(selected) == 4 and all(
        r["display_source_class"] == "artist_official"
        and r["display_source_id"] == "starto_concert"
        for r in selected
    )
    assert all(
        r["url"] == r["evidence_url"] == "https://starto.jp/s/p/live/10602"
        for r in selected
    )
    assert all(
        set(embedded_urls(r)) == {"https://starto.jp/s/p/live/10602"} for r in selected
    )
    validate_payload(payload)
    output = tmp_path / "lp.json"
    write_lp_events(payload, output, identity_registry_path=registry)


def test_changed_or_misattributed_artist_source_fails(tmp_path):
    _, records, registry, mapping, baseline = case(tmp_path)
    records[0]["evidence_url_sha256"] = "a" * 64
    mapping.write_text(json.dumps({"schema_version": 1, "records": records}))
    with pytest.raises(SourceMapError, match="artist source changed"):
        build_lp_events(
            as_of_date=date(2026, 11, 6),
            identity_registry_path=registry,
            reviewed_source_map_path=mapping,
            reviewed_source_baseline_path=baseline,
        )


def test_four_fact_selections_without_publication_decision_stay_out_of_upstream_asset(tmp_path):
    args, records, registry, mapping, baseline = case(tmp_path, publication_reviewed=False)
    payload = build_lp_events(as_of_date=date(2026, 11, 6), identity_registry_path=registry,
        reviewed_source_map_path=mapping, reviewed_source_baseline_path=baseline)
    target_ids = {rec["event_uid"] for rec in records}
    assert not target_ids & {row["event_key"] for row in payload["events"]}
    holds = [row for row in payload["identity_held_records"] if row["reason"] == "source_review_required"]
    assert {row["related_event_uids"][0] for row in holds} == target_ids
    output = tmp_path / "lp.json"
    write_lp_events(payload, output, identity_registry_path=registry)
    public = json.loads(output.read_text())
    assert not target_ids & {row["event_key"] for row in public["events"]}
    assert all(row["event_key"] not in target_ids for row in public["events"])
    before, _ = resolve_rows(args[0], args[1])
    assert public["events"] == before


def test_selected_artist_observation_must_substantiate_start_time(tmp_path):
    import shutil
    from scripts.reviewed_source_map import apply_reviewed_source_map
    from scripts.event_identity_registry import load_registry

    args, records, registry, mapping, _ = case(tmp_path)
    signals = tmp_path / "signals.sqlite"
    shutil.copyfile(ROOT / "data/event_signals.sqlite", signals)
    db = sqlite3.connect(signals)
    raw = db.execute(
        "select labels_json from signals where signal_uid=?", (records[0]["record_id"],)
    ).fetchone()[0]
    labels = json.loads(raw)
    labels["event_info"] = labels["event_info"].replace("18:00", "19:00")
    db.execute(
        "update signals set labels_json=? where signal_uid=?",
        (json.dumps(labels), records[0]["record_id"]),
    )
    db.commit()
    db.close()
    current, _ = load_registry(registry)
    with pytest.raises(SourceMapError, match="does not substantiate candidate facts"):
        apply_reviewed_source_map(
            args[0], current, mapping.read_bytes(), ROOT / "data/events.sqlite", signals
        )
