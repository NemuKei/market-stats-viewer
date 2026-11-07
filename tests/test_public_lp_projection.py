"""The public LP writer itself must exclude unselected fields and links."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts import build_lp_events as builder
from scripts import event_identity_registry as ids
from scripts.public_lp_projection import (
    attach_public_row_checks, embedded_urls, project_event, project_payload, public_row_sha256, publication_is_reviewed, publication_preview,
)
from scripts.reviewed_source_map import source_signature, guard_new_ids, SourceMapError
from test_event_identity_registry import record, payload, registry_for


def test_public_writer_drops_prose_unknown_fields_and_unselected_support_urls(tmp_path):
    candidate = payload([record()])
    row = candidate["events"][0]
    registry = registry_for([row])
    registry_path = tmp_path / "registry.json"
    ids.write_registry(registry, registry_path, expected_sha256=None)
    _, sha = ids.load_registry(registry_path)
    candidate = ids.apply_to_payload(candidate, registry, sha)
    row = candidate["events"][0]
    row.update(evidence_snippet="PRIVATE_BODY https://unapproved.example/body",
               raw_artist_name="PRIVATE_RAW_ARTIST", raw_venue_name="PRIVATE_RAW_VENUE",
               body="PRIVATE_BODY", html="PRIVATE_HTML", future_field="PRIVATE_FUTURE",
               image_url="https://unapproved.example/image")
    row["supporting_sources"][0].update(title="PRIVATE_SUPPORT_TITLE",
        url="https://unapproved.example/support", snippet="PRIVATE_SUPPORT_BODY")
    candidate["private_future"] = "PRIVATE_TOP"
    candidate["summary"]["private_future"] = "PRIVATE_SUMMARY"
    candidate["location_held_records"] = [{"record_id": "https://unapproved.example/held"}]
    attach_public_row_checks(candidate, reviewed_ids={row["event_key"]})
    output = tmp_path / "lp.json"
    builder.write_lp_events(candidate, output, identity_registry_path=registry_path)
    text = output.read_text()
    assert "PRIVATE_" not in text and "unapproved.example" not in text
    assert json.loads(text)["events"] == [project_event(row)]
    assert json.loads(text)["events"][0]["capacity"] is None
    assert json.loads(text)["events"][0]["evidence_snippet"] == ""
    # Previously unhandled changes to private text cannot change or enter the LP.
    row["evidence_snippet"] = "ANOTHER_PRIVATE_BODY https://unapproved.example/new"
    builder.write_lp_events(candidate, output, identity_registry_path=registry_path)
    assert output.read_text() == text


def test_provenance_signature_covers_public_metadata_but_not_private_body():
    row = payload([record()])["events"][0]
    official = {"source-A": (row["evidence_url"], row["url"])}
    signature = source_signature(row, official)
    body_changed = deepcopy(row)
    body_changed["evidence_snippet"] = "PRIVATE_CHANGED_BODY https://unapproved.example/body"
    body_changed["supporting_sources"][0]["title"] = "PRIVATE_CHANGED_TITLE"
    assert source_signature(body_changed, official) == signature
    assert project_event(body_changed) == project_event(row)
    for key, value in [("display_source_label", "Changed attribution"),
                       ("event_end_time", "22:00"), ("event_category", "その他")]:
        changed = deepcopy(row)
        changed[key] = value
        assert source_signature(changed, official) != signature


def test_publication_requires_separate_pending_to_reviewed_decision_and_exact_public_row():
    row = payload([record()])["events"][0]
    rec = {"mode": "preserve_source", "fact_review": "reviewed"}
    assert not publication_is_reviewed(rec, row)
    rec["publication"] = publication_preview(row)
    assert not publication_is_reviewed(rec, row)
    rec["publication"]["status"] = "reviewed"
    assert publication_is_reviewed(rec, row)
    changed = deepcopy(row)
    changed["display_source_label"] = "Unreviewed public attribution"
    with pytest.raises(ValueError, match="public fields or URLs changed"):
        publication_is_reviewed(rec, changed)
    rec["publication"]["public_urls"] = []
    with pytest.raises(ValueError, match="public fields or URLs changed"):
        publication_is_reviewed(rec, row)


@pytest.mark.parametrize("scheme", ["https", "HTTPS"])
def test_allowed_identifier_cannot_hide_a_new_public_url(scheme):
    row = payload([record()])["events"][0]
    rec = {"mode": "preserve_source", "publication": publication_preview(row)}
    rec["publication"]["status"] = "reviewed"
    changed = deepcopy(row)
    changed["supporting_sources"][0]["record_id"] = f"{scheme}://unapproved.example/identifier"
    # Even if a reviewer recomputed the field hash, the separate URL decision
    # must include every exposed URL, including one embedded in an identifier.
    rec["publication"]["row_sha256"] = public_row_sha256(changed)
    with pytest.raises(ValueError, match="public fields or URLs changed"):
        publication_is_reviewed(rec, changed)


@pytest.mark.parametrize("target", ["updated_at_utc", "event_end_time"])
def test_volatile_or_time_field_cannot_carry_prose(target):
    row = payload([record()])["events"][0]
    row[target] = "PRIVATE_BODY https://unapproved.example/body"
    with pytest.raises(ValueError):
        project_event(row)


def test_old_baseline_version_is_not_silently_reused():
    baseline = {"schema_version": 2, "asset_sha256": "a" * 64, "event_sources": {}}
    with pytest.raises(SourceMapError, match="invalid verified publication baseline"):
        guard_new_ids([], b'{"schema_version":1,"records":[]}', json.dumps(baseline).encode(), set(), {})


@pytest.mark.parametrize("source_id", ["starto_concert", "kstyle_music"])
def test_public_writer_rejects_news_only_row_even_when_identity_is_registered(tmp_path, source_id):
    candidate = payload([record(source_id=source_id, source_class="")])
    registry = registry_for(candidate["events"])
    registry_path = tmp_path / "registry.json"
    ids.write_registry(registry, registry_path, expected_sha256=None)
    _, sha = ids.load_registry(registry_path)
    resolved = ids.apply_to_payload(candidate, registry, sha)
    output = tmp_path / "lp.json"
    output.write_bytes(b"previous approved snapshot")
    with pytest.raises(ValueError, match="news-only source cannot enter"):
        builder.write_lp_events(resolved, output, identity_registry_path=registry_path)
    assert output.read_bytes() == b"previous approved snapshot"


def test_writer_detects_public_url_change_after_producer_checks(tmp_path, monkeypatch):
    raw = record()
    row = payload([raw])["events"][0]
    registry = registry_for([row])
    registry_path = tmp_path / "registry.json"
    ids.write_registry(registry, registry_path, expected_sha256=None)
    monkeypatch.setattr(builder, "load_lp_records", lambda **kwargs: [deepcopy(raw)])
    result = builder.build_lp_events(identity_registry_path=registry_path)
    output = tmp_path / "lp.json"
    builder.write_lp_events(result, output, identity_registry_path=registry_path)
    before = output.read_bytes()
    assert "_public_row_checks" not in json.loads(before)
    result["events"][0]["url"] = "https://unapproved.example/after-build"
    with pytest.raises(ValueError, match="public row changed after source/publication checks"):
        builder.write_lp_events(result, output, identity_registry_path=registry_path)
    assert output.read_bytes() == before


def test_existing_996_rows_keep_all_v1_fields_and_urls():
    original = json.loads((Path(__file__).resolve().parents[1] / "data/lp_events.json").read_text())
    candidate = deepcopy(original)
    attach_public_row_checks(candidate)  # Simulate the verified legacy-row path.
    result = project_payload(candidate)
    assert len(result["events"]) == 996
    assert result == original
    assert set(embedded_urls(result)) == set(embedded_urls(original))


def test_mixed_legacy_and_reviewed_rows_preserve_v1_keys_and_limit_only_target():
    candidate = payload([record("old"), record("new")])
    old = next(row for row in candidate["events"] if row["artist_name"].endswith("old"))
    new = next(row for row in candidate["events"] if row["artist_name"].endswith("new"))
    old["evidence_snippet"] = "legacy public description"
    new["evidence_snippet"] = "PRIVATE_NEW_BODY"
    old_before = deepcopy(old)
    attach_public_row_checks(candidate, reviewed_ids={new["event_key"]})
    result = project_payload(candidate)
    by_id = {row["event_key"]: row for row in result["events"]}
    assert by_id[old["event_key"]] == old_before
    target = by_id[new["event_key"]]
    assert set(target) == set(new)
    assert set(target["supporting_sources"][0]) == set(new["supporting_sources"][0])
    assert target["evidence_snippet"] == "" and target["capacity"] is None
    assert "PRIVATE_NEW_BODY" not in json.dumps(result)


def test_legacy_body_or_capacity_drift_is_not_hidden_by_redaction():
    row = payload([record()])["events"][0]
    official = {"source-A": (row["evidence_url"], row["url"])}
    baseline = json.dumps({"schema_version": 4, "asset_sha256": "a" * 64,
        "event_sources": {row["event_key"]: source_signature(row, official, legacy_row=True)}}).encode()
    refreshed = deepcopy(row)
    refreshed["updated_at_utc"] = "2026-11-06T12:00:00Z"
    refreshed["supporting_sources"][0]["updated_at_utc"] = "2026-11-06T12:00:00Z"
    guard_new_ids([refreshed], b'{"schema_version":1,"records":[]}', baseline, set(), official)
    for key, value in [("evidence_snippet", "unreviewed body"), ("capacity", 12345)]:
        changed = deepcopy(row)
        changed[key] = value
        with pytest.raises(SourceMapError, match="existing ID source or public link changed"):
            guard_new_ids([changed], b'{"schema_version":1,"records":[]}', baseline, set(), official)


def test_writer_cannot_omit_row_mode_checks(tmp_path):
    candidate = payload([record()])
    registry = registry_for(candidate["events"])
    registry_path = tmp_path / "registry.json"
    ids.write_registry(registry, registry_path, expected_sha256=None)
    _, sha = ids.load_registry(registry_path)
    resolved = ids.apply_to_payload(candidate, registry, sha)
    with pytest.raises(ValueError, match="public row modes and checks required"):
        builder.write_lp_events(resolved, tmp_path / "lp.json", identity_registry_path=registry_path)
