"""Fixed identity and atomic-publication checks using fictional occurrences."""
from copy import deepcopy
from datetime import date
import json

import pytest

from scripts import build_lp_events as builder
from scripts import event_identity_registry as ids
from scripts.validate_external_events import validate_payload


def record(name="A", **changes):
    row = dict(source_id="official_events", record_id="source-" + name,
               source_class="venue_official", source_label="Fictional venue",
               event_date="2026-11-01", event_end_date="2026-11-01",
               event_start_time="18:00", venue_name="架空会場A", pref_name="東京都",
               artist_name="架空出演者" + name, title="架空の公演" + name,
               url="https://example.com/event/" + name,
               evidence_url="https://example.com/event/" + name,
               evidence_snippet="fictional official schedule",
               updated_at_utc="2026-10-06T00:00:00Z", event_status="scheduled")
    row.update(changes)
    return row


def payload(records):
    return builder.assemble_lp_payload(records, as_of_date=date(2026, 10, 6))


def seed_bytes(rows):
    public = []
    for row in rows:
        public.append(dict(event_uid=row["event_key"], source_id=row["display_source_id"],
                           source_record_id=row["supporting_sources"][0]["record_id"],
                           source_policy_status="approved", title=row["title"],
                           start_date=row["event_date"], end_date=row["event_end_date"],
                           start_time=row["event_start_time"], venue_name=row["venue_name"],
                           artist_name=row["artist_name"]))
    return ids.canonical_bytes({"events": {"items": public, "publicationPolicy": {"status": "enforced", "defaultDeny": True, "publishedCount": len(public)}}})


def registry_for(rows):
    raw = seed_bytes(rows)
    return ids.seed_registry(raw, expected_sha256=ids.digest(raw), expected_count=len(rows))


def request(registry, kind, previous, candidates):
    return dict(schema_version=1, expected_revision=registry["revision"], kind=kind,
                previous_ids=previous,
                candidates=[{"event_uid": uid, "observation": ids.observation_from_row(row)} for uid, row in candidates],
                evidence={"url": "https://example.com/confirmed-correction", "reviewed_at_utc": "2026-10-06T14:00:00Z", "reason": "Fictional official evidence confirms the stated occurrence relationship."})


def write_fixture_registry(tmp_path, rows):
    path = tmp_path / "identity.json"
    ids.write_registry(registry_for(rows), path, expected_sha256=None)
    return path


def test_seed_and_repeat_keep_ids_order_rows_and_unrelated_notes(tmp_path):
    original = payload([record("A"), record("B")])
    before = deepcopy(original)
    registry = registry_for(original["events"])
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({original["events"][0]["event_key"]: "own history"}))
    before_notes = notes.read_bytes()
    for _ in range(2):
        published, held = ids.resolve_rows(original["events"], registry)
        assert published == original["events"] and held == []
    assert original == before
    assert notes.read_bytes() == before_notes


@pytest.mark.parametrize("changes", [
    {"event_date": "2026-11-02", "event_end_date": "2026-11-02", "record_id": "date-key-changed"},
    {"venue_name": "改称後の架空会場"},
    {"artist_name": "訂正後の架空出演者"},
    {"title": "訂正後の架空公演名"},
    {"event_end_date": "2026-11-03"},
    {"event_start_time": "19:00"},
])
def test_only_reviewed_one_to_one_correction_retains_old_id(changes):
    old = payload([record()])["events"][0]
    changed = payload([record(**changes)])["events"][0]
    registry = registry_for([old])
    published, held = ids.resolve_rows([changed], registry)
    assert published == [] and len(held) == 1
    revision_before = deepcopy(registry)
    review = request(registry, "correction", [old["event_key"]], [(old["event_key"], changed)])
    reviewed = ids.apply_review(registry, review)
    assert registry == revision_before
    published, held = ids.resolve_rows([changed], reviewed)
    assert held == [] and published[0]["event_key"] == old["event_key"]
    assert published[0]["venue_name"] == changed["venue_name"]
    assert ids.apply_review(reviewed, review) == reviewed
    # Old source rows can remain in the DB, but superseded observations do not
    # reappear alongside the corrected row with the same fixed ID.
    published, held = ids.resolve_rows([old], reviewed)
    assert published == [] and held[0]["reason"] == "superseded_observation"
    assert reviewed["events"][0]["observations"][0]["active"] is False


def test_source_record_id_alone_never_rebinds_date_or_venue():
    old = payload([record()])["events"][0]
    changed = payload([record(event_date="2026-11-03", event_end_date="2026-11-03", venue_name="別の架空会場")])["events"][0]
    published, held = ids.resolve_rows([changed], registry_for([old]))
    assert published == []
    assert held[0]["related_event_uids"] == [old["event_key"]]
    assert held[0]["reason"] == "changed_or_unbound_observation"


def test_identical_identity_with_unbound_source_is_held_not_guessed():
    old = payload([record()])["events"][0]
    changed = deepcopy(old)
    changed["supporting_sources"][0]["record_id"] = "another-source-row"
    assert ids.resolve_rows([changed], registry_for([old]))[0] == []


def test_additional_source_keeps_unchanged_registered_occurrence_without_editing_registry():
    old = payload([record()])["events"][0]
    with_support = deepcopy(old)
    with_support["supporting_sources"].append({**with_support["supporting_sources"][0], "source_id": "venue_web_discovery", "record_id": "additional-record"})
    registry = registry_for([old])
    before = deepcopy(registry)
    rows, held = ids.resolve_rows([with_support], registry)
    assert rows[0]["event_key"] == old["event_key"] and held == [] and registry == before


def test_split_blank_time_aggregate_requires_review_and_reuses_only_confirmed_child():
    old = payload([record(event_start_time="")])["events"][0]
    # Blank-time source is shared by both performances in the current grouping
    # implementation; that shared source is not a child identity proof.
    split = payload([record(event_start_time=""), record(event_start_time="14:00", record_id="matinee"), record(event_start_time="19:00", record_id="evening")])["events"]
    registry = registry_for([old])
    assert ids.resolve_rows(split, registry)[0] == []
    revised = ids.apply_review(registry, request(registry, "split", [old["event_key"]], [(old["event_key"], split[0]), (None, split[1])]))
    published, held = ids.resolve_rows(split, revised)
    assert held == [] and len(published) == 2
    assert published[0]["event_key"] == old["event_key"]
    assert published[1]["event_key"].startswith("evt_")
    assert published[1]["event_key"] != old["event_key"]
    assert ids.resolve_rows([old], revised)[0] == []


def test_ambiguous_split_keeps_old_history_without_cloning_its_id():
    old = payload([record(event_start_time="")])["events"][0]
    split = payload([record(event_start_time="14:00", record_id="matinee"), record(event_start_time="19:00", record_id="evening")])["events"]
    registry = registry_for([old])
    bad = request(registry, "split", [old["event_key"]], [(old["event_key"], row) for row in split])
    with pytest.raises(ValueError, match="multiple children"):
        ids.apply_review(registry, bad)
    assert registry["events"][0]["observations"][0]["active"]
    assert ids.resolve_rows(split, registry)[0] == []


@pytest.mark.parametrize("continue_old", [True, False])
def test_confirmed_merge_keeps_all_old_ids_and_does_not_move_notes(continue_old):
    old = payload([record("A"), record("B")])["events"]
    registry = registry_for(old)
    merged = payload([record("C", artist_name="架空統合公演")])["events"][0]
    old_ids = [row["event_key"] for row in old]
    notes = {uid: "own note " + str(i) for i, uid in enumerate(old_ids)}
    before_notes = deepcopy(notes)
    review = request(registry, "merge", old_ids, [(old_ids[0] if continue_old else None, merged)])
    revised = ids.apply_review(registry, review)
    published, held = ids.resolve_rows([merged], revised)
    assert held == [] and len(published) == 1
    assert published[0]["event_key"] == old_ids[0] if continue_old else published[0]["event_key"] not in old_ids
    assert set(old_ids) <= {entry["event_uid"] for entry in revised["events"]}
    assert ids.resolve_rows(old, revised)[0] == []
    assert notes == before_notes


def test_ambiguous_candidate_is_held_while_other_confirmed_rows_publish():
    original = payload([record("A"), record("B")])["events"]
    revised_candidate = payload([record("A", venue_name="別の架空会場")])["events"][0]
    registry = registry_for(original)
    rows, held = ids.resolve_rows([revised_candidate, original[1]], registry)
    assert [row["event_key"] for row in rows] == [original[1]["event_key"]]
    assert held[0]["related_event_uids"] == [original[0]["event_key"]]
    assert len(registry["events"]) == 2


def test_new_id_allocated_once_by_review_not_by_generation():
    old = payload([record()])["events"][0]
    new = payload([record("Z")])["events"][0]
    registry = registry_for([old])
    assert ids.resolve_rows([new], registry)[1][0]["reason"] == "unregistered_candidate"
    review = request(registry, "new", [], [(None, new)])
    revised = ids.apply_review(registry, review)
    assert ids.apply_review(revised, review) == revised
    fixed = ids.resolve_rows([new], revised)[0][0]["event_key"]
    assert fixed.startswith("evt_") and fixed != new["event_key"]
    assert ids.resolve_rows([], revised) == ([], [])
    assert ids.resolve_rows([new], revised)[0][0]["event_key"] == fixed


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(schema_version=True),
    lambda r: r.update(schema_version=2),
    lambda r: r.update(revision=True),
    lambda r: r.update(revision=2),
    lambda r: r["events"].append(deepcopy(r["events"][0])),
    lambda r: r["events"].clear(),
    lambda r: r["events"][0].update(event_uid="changed-old-ID"),
    lambda r: r["events"][0]["observations"][0]["identity"].update(event_date="2026-11-02"),
    lambda r: r["events"][0]["observations"][0]["source_records"][0].update(record_id="changed-source"),
    lambda r: r["events"][0]["observations"][0].update(active="yes"),
    lambda r: r["events"][0]["observations"][0].update(fingerprint="0" * 64),
])
def test_malformed_or_lost_registry_fails_without_writing(mutate, tmp_path):
    row = payload([record()])["events"][0]
    path = write_fixture_registry(tmp_path, [row])
    original = path.read_bytes()
    bad = registry_for([row])
    mutate(bad)
    with pytest.raises(ValueError):
        ids.write_registry(bad, path, expected_sha256=ids.digest(original))
    assert path.read_bytes() == original


def test_edited_seed_fields_cannot_be_hidden_by_recomputing_observation_hash():
    registry = registry_for(payload([record()])["events"])
    obs = registry["events"][0]["observations"][0]
    obs["identity"]["title"] = "unreviewed edit"
    obs["fingerprint"] = ids.fingerprint(obs["candidate_key"], obs["identity"], obs["source_records"])
    with pytest.raises(ValueError, match="changed seed observations"):
        ids.validate_registry(registry)


def test_duplicate_json_keys_and_nonfinite_values_fail():
    for data in [b'{"schema_version":1,"schema_version":2}', b'{"value":NaN}']:
        with pytest.raises(ValueError):
            ids.parse_json(data)


def test_unreviewed_activity_edit_and_reactivation_fail():
    old = payload([record()])["events"][0]
    registry = registry_for([old])
    bad = deepcopy(registry)
    bad["events"][0]["observations"][0]["active"] = False
    with pytest.raises(ValueError, match="reviewed history"):
        ids.validate_registry(bad)
    changed = payload([record(title="訂正")])["events"][0]
    reviewed = ids.apply_review(registry, request(registry, "correction", [old["event_key"]], [(old["event_key"], changed)]))
    reviewed["events"][0]["observations"][0]["active"] = True
    reviewed["events"][0]["observations"][1]["active"] = False
    with pytest.raises(ValueError, match="reviewed history"):
        ids.validate_registry(reviewed)


def test_stale_or_unreviewed_transaction_fails_without_mutating_registry():
    row = payload([record()])["events"][0]
    registry = registry_for([row])
    before = deepcopy(registry)
    changed = payload([record(title="訂正")])["events"][0]
    for mutate in [lambda r: r.update(expected_revision=0), lambda r: r.update(evidence={}), lambda r: r["evidence"].update(url="file:///private"), lambda r: r["evidence"].update(url="https://user:password@example.com/")]:
        review = request(registry, "correction", [row["event_key"]], [(row["event_key"], changed)])
        mutate(review)
        with pytest.raises(ValueError):
            ids.apply_review(registry, review)
        assert registry == before


def test_retired_id_and_unrelated_old_id_cannot_be_reused():
    old = payload([record("A"), record("B")])["events"]
    registry = registry_for(old)
    new = payload([record("C")])["events"][0]
    with pytest.raises(ValueError, match="outside confirmed predecessors"):
        ids.apply_review(registry, request(registry, "new", [], [(old[0]["event_key"], new)]))
    merged = ids.apply_review(registry, request(registry, "merge", [r["event_key"] for r in old], [(None, new)]))
    with pytest.raises(ValueError, match="retired ID"):
        ids.apply_review(merged, request(merged, "correction", [old[0]["event_key"]], [(old[0]["event_key"], new)]))


def test_seed_cli_is_idempotent_after_review_and_never_replaces_another_seed(tmp_path):
    old = payload([record()])["events"][0]
    raw = seed_bytes([old])
    snapshot = tmp_path / "published.json"
    snapshot.write_bytes(raw)
    path = write_fixture_registry(tmp_path, [old])
    changed = payload([record(title="訂正")])["events"][0]
    registry, sha = ids.load_registry(path)
    revised = ids.apply_review(registry, request(registry, "correction", [old["event_key"]], [(old["event_key"], changed)]))
    ids.write_registry(revised, path, expected_sha256=sha)
    before = path.read_bytes()
    args = ["--registry", str(path), "seed", "--snapshot", str(snapshot), "--expected-sha256", ids.digest(raw), "--expected-count", "1"]
    assert ids.main(args) == 0 and path.read_bytes() == before
    snapshot.write_bytes(seed_bytes(payload([record("X")])["events"]))
    args[args.index("--expected-sha256") + 1] = ids.digest(snapshot.read_bytes())
    with pytest.raises(ValueError, match="different seed"):
        ids.main(args)
    assert path.read_bytes() == before


def test_registry_write_conflicts_locks_and_replace_failure_keep_old_bytes(tmp_path, monkeypatch):
    row = payload([record()])["events"][0]
    path = write_fixture_registry(tmp_path, [row])
    registry, sha = ids.load_registry(path)
    changed = payload([record(title="訂正")])["events"][0]
    revised = ids.apply_review(registry, request(registry, "correction", [row["event_key"]], [(row["event_key"], changed)]))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="changed before write"):
        ids.write_registry(revised, path, expected_sha256="0" * 64)
    lock = path.with_name("." + path.name + ".lock")
    lock.write_bytes(b"another owner")
    with pytest.raises(FileExistsError):
        ids.write_registry(revised, path, expected_sha256=sha)
    assert lock.read_bytes() == b"another owner"
    lock.unlink()
    monkeypatch.setattr(ids.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("synthetic replace failed")))
    with pytest.raises(OSError):
        ids.write_registry(revised, path, expected_sha256=sha)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".identity.json.*"))


def test_missing_registry_stops_before_source_loading_and_preserves_output(tmp_path, monkeypatch):
    output = tmp_path / "lp.json"
    output.write_bytes(b"existing verified snapshot")
    called = []
    monkeypatch.setattr(builder, "load_lp_records", lambda **_: called.append(True))
    with pytest.raises(FileNotFoundError):
        builder.build_lp_events(identity_registry_path=tmp_path / "missing.json")
    assert called == [] and output.read_bytes() == b"existing verified snapshot"


def test_generator_filters_pending_updates_counts_and_validates_before_replace(tmp_path, monkeypatch):
    original = payload([record("A"), record("B")])
    path = write_fixture_registry(tmp_path, original["events"])
    monkeypatch.setattr(builder, "load_lp_records", lambda **_: [record("A", venue_name="改称後の架空会場"), record("B")])
    result = builder.build_lp_events(identity_registry_path=path, as_of_date=date(2026, 10, 6))
    assert result["summary"]["event_count"] == 1
    assert result["summary"]["identity_held_record_count"] == 1
    assert validate_payload(result)["event_count"] == 1
    output = tmp_path / "lp.json"
    output.write_bytes(b"previous")
    builder.write_lp_events(result, output, identity_registry_path=path)
    saved = output.read_bytes()
    assert json.loads(saved)["identity_registry"]["revision"] == 1
    assert "identity_held_records" not in json.loads(saved)
    assert json.loads(saved)["summary"]["identity_held_record_count"] == 1
    assert validate_payload(json.loads(saved))["event_count"] == 1
    bad = deepcopy(result)
    bad["events"][0]["venue_name"] = "unreviewed alteration"
    with pytest.raises(ValueError, match="not bound"):
        builder.write_lp_events(bad, output, identity_registry_path=path)
    bad = deepcopy(result)
    bad["events"].append(deepcopy(bad["events"][0]))
    with pytest.raises(ValueError):
        builder.write_lp_events(bad, output, identity_registry_path=path)
    assert output.read_bytes() == saved


def test_registry_drift_all_held_and_output_write_failure_preserve_snapshot(tmp_path, monkeypatch):
    initial = payload([record()])
    path = write_fixture_registry(tmp_path, initial["events"])
    registry, sha = ids.load_registry(path)
    output = tmp_path / "lp.json"
    output.write_bytes(b"last verified snapshot")
    resolved = ids.apply_to_payload(initial, registry, sha)
    changed = payload([record(title="訂正")])
    all_held = ids.apply_to_payload(changed, registry, sha)
    with pytest.raises(ValueError, match="all candidates held"):
        builder.write_lp_events(all_held, output, identity_registry_path=path)
    revised = ids.apply_review(registry, request(registry, "correction", [initial["events"][0]["event_key"]], [(initial["events"][0]["event_key"], changed["events"][0])]))
    ids.write_registry(revised, path, expected_sha256=sha)
    with pytest.raises(ValueError, match="changed during generation"):
        builder.write_lp_events(resolved, output, identity_registry_path=path)
    registry, sha = ids.load_registry(path)
    resolved = ids.apply_to_payload(changed, registry, sha)
    monkeypatch.setattr(ids.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("synthetic replace failed")))
    with pytest.raises(OSError):
        builder.write_lp_events(resolved, output, identity_registry_path=path)
    assert output.read_bytes() == b"last verified snapshot"
    assert not list(tmp_path.glob(".lp.json.*")) and not list(tmp_path.glob(".identity.json.*"))


def test_valid_zero_candidates_do_not_delete_registry_or_notes(tmp_path):
    path = write_fixture_registry(tmp_path, payload([record()])["events"])
    registry, sha = ids.load_registry(path)
    before = path.read_bytes()
    empty = ids.apply_to_payload(payload([]), registry, sha)
    output = tmp_path / "lp.json"
    builder.write_lp_events(empty, output, identity_registry_path=path)
    assert json.loads(output.read_bytes())["events"] == [] and path.read_bytes() == before


def test_publication_validator_rejects_mixed_held_count_and_registry_metadata(tmp_path):
    original = payload([record()])
    path = write_fixture_registry(tmp_path, original["events"])
    registry, sha = ids.load_registry(path)
    result = ids.apply_to_payload(original, registry, sha)
    for mutate in [lambda p: p["summary"].update(identity_held_record_count=1), lambda p: p["identity_registry"].update(revision=True), lambda p: p["identity_registry"].update(sha256="invalid")]:
        bad = deepcopy(result)
        mutate(bad)
        with pytest.raises(ValueError):
            validate_payload(bad)


def test_seed_uses_exact_source_occurrence_when_public_projection_changes_display_text():
    original = payload([record(title="原表記の架空公演")])
    public = json.loads(seed_bytes(original["events"]))
    public["events"]["items"][0]["title"] = "公開用に調整された架空公演"
    public["metadata"] = {"asOfDate": original["as_of_date"], "eventSourceGeneratedAtUtc": original["generated_at_utc"]}
    snapshot, raw_lp = ids.canonical_bytes(public), ids.canonical_bytes(original)
    registry = ids.seed_registry(snapshot, expected_sha256=ids.digest(snapshot), expected_count=1, lp_baseline_bytes=raw_lp, expected_lp_sha256=ids.digest(raw_lp))
    resolved, held = ids.resolve_rows(original["events"], registry)
    assert held == [] and resolved == original["events"]
    assert registry["events"][0]["event_uid"] == public["events"]["items"][0]["event_uid"]


def test_seed_truncated_display_source_id_is_not_used_as_a_future_binding():
    source_id = "source-" + "a" * 180
    original = payload([record(record_id=source_id)])
    public = json.loads(seed_bytes(original["events"]))
    public["events"]["items"][0]["source_record_id"] = source_id[:128]
    public["metadata"] = {"asOfDate": original["as_of_date"], "eventSourceGeneratedAtUtc": original["generated_at_utc"]}
    snapshot, raw = ids.canonical_bytes(public), ids.canonical_bytes(original)
    registry = ids.seed_registry(snapshot, expected_sha256=ids.digest(snapshot), expected_count=1, lp_baseline_bytes=raw, expected_lp_sha256=ids.digest(raw))
    assert ids.resolve_rows(original["events"], registry)[1] == []
    changed = deepcopy(original["events"][0])
    changed["supporting_sources"][0]["record_id"] = source_id[:128] + "different-tail"
    assert ids.resolve_rows([changed], registry)[0] == []


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(as_of_date="2026-10-05"),
    lambda p: p.update(generated_at_utc="2026-10-05T00:00:00Z"),
    lambda p: p["events"][0].update(event_key="wrong-key"),
    lambda p: p["events"][0]["supporting_sources"][0].update(record_id="wrong-source"),
    lambda p: p["events"].append(deepcopy(p["events"][0])),
])
def test_wrong_or_mixed_source_baseline_cannot_seed_ids(mutate):
    original = payload([record()])
    public = json.loads(seed_bytes(original["events"]))
    public["metadata"] = {"asOfDate": original["as_of_date"], "eventSourceGeneratedAtUtc": original["generated_at_utc"]}
    snapshot = ids.canonical_bytes(public)
    mutate(original)
    raw = ids.canonical_bytes(original)
    with pytest.raises(ValueError):
        ids.seed_registry(snapshot, expected_sha256=ids.digest(snapshot), expected_count=1, lp_baseline_bytes=raw, expected_lp_sha256=ids.digest(raw))


def test_reviewed_batch_new_allocates_distinct_ids_once_without_old_aliases():
    old = payload([record()])["events"][0]
    candidates = payload([record("B"), record("C")])["events"]
    registry = registry_for([old])
    review = request(registry, "new", [], [(None, row) for row in candidates])
    reviewed = ids.apply_review(registry, review)
    rows, held = ids.resolve_rows([old, *candidates], reviewed)
    assert held == [] and len({row["event_key"] for row in rows}) == 3
    assert rows[0]["event_key"] == old["event_key"]
    assert all(row["event_key"].startswith("evt_") for row in rows[1:])
    assert ids.apply_review(reviewed, review) == reviewed
    assert reviewed["revision"] == 2 and registry["revision"] == 1


def test_pending_cli_exposes_all_held_without_overwriting_registry_input_or_output(tmp_path):
    old = payload([record()])["events"]
    registry_path = write_fixture_registry(tmp_path, old)
    source = tmp_path / "candidate.json"
    source.write_bytes(ids.canonical_bytes(payload([record(title="確認前の訂正")])))
    preview_path = tmp_path / "pending.json"
    before = (registry_path.read_bytes(), source.read_bytes())
    argv = ["--registry", str(registry_path), "pending", "--lp-events", str(source), "--output", str(preview_path)]
    assert ids.main(argv) == 0
    preview = json.loads(preview_path.read_bytes())
    assert preview["resolved_count"] == 0 and len(preview["held_records"]) == 1
    assert preview["input_sha256"] == ids.digest(before[1])
    saved = preview_path.read_bytes()
    with pytest.raises(FileExistsError):
        ids.main(argv)
    assert preview_path.read_bytes() == saved
    assert before == (registry_path.read_bytes(), source.read_bytes())
    assert not list(tmp_path.glob(".pending.json.*"))


def test_registry_serialized_limit_preserves_readable_old_bytes_at_boundary(tmp_path, monkeypatch):
    old = payload([record()])["events"][0]
    path = write_fixture_registry(tmp_path, [old])
    registry, sha = ids.load_registry(path)
    before = path.read_bytes()
    changed = payload([record(title="訂正された架空公演")])["events"][0]
    revised = ids.apply_review(registry, request(registry, "correction", [old["event_key"]], [(old["event_key"], changed)]))
    monkeypatch.setattr(ids, "MAX_REGISTRY_BYTES", len(before))
    assert ids.write_registry(registry, path, expected_sha256=sha) is False
    with pytest.raises(ValueError, match="registry exceeds byte limit"):
        ids.write_registry(revised, path, expected_sha256=sha)
    assert path.read_bytes() == before
    assert ids.load_registry(path) == (registry, sha)
    assert not list(tmp_path.glob(".identity.json.*"))


def test_pending_from_current_candidates_works_when_all_held(tmp_path, monkeypatch):
    original = payload([record()])
    path = write_fixture_registry(tmp_path, original["events"])
    before = path.read_bytes()
    monkeypatch.setattr(builder, "_build_lp_event_candidates", lambda: payload([record(title="未確認の訂正")]))
    output = tmp_path / "private-preview.json"
    assert ids.main(["--registry", str(path), "pending", "--output", str(output)]) == 0
    preview = json.loads(output.read_bytes())
    assert preview["resolved_count"] == 0 and len(preview["held_records"]) == 1
    assert path.read_bytes() == before


def test_pending_reads_internal_resolved_payload_but_rejects_published_or_stale_copy(tmp_path):
    initial = payload([record("A"), record("B")])
    path = write_fixture_registry(tmp_path, initial["events"])
    registry, sha = ids.load_registry(path)
    resolved = ids.apply_to_payload(payload([record("A", title="確認待ち"), record("B")]), registry, sha)
    copied = tmp_path / "internal.json"
    copied.write_bytes(ids.canonical_bytes(resolved))
    argv = ["--registry", str(path), "pending", "--lp-events", str(copied), "--output", str(tmp_path / "preview.json")]
    assert ids.main(argv) == 0
    saved = (tmp_path / "preview.json").read_bytes()
    resolved.pop("identity_held_records")
    copied.write_bytes(ids.canonical_bytes(resolved))
    with pytest.raises(ValueError, match="published LP omits"):
        ids.main(argv)
    assert (tmp_path / "preview.json").read_bytes() == saved
    resolved["identity_registry"]["sha256"] = "0" * 64
    copied.write_bytes(ids.canonical_bytes(resolved))
    with pytest.raises(ValueError, match="preview registry changed"):
        ids.main(argv)


def test_related_source_new_registration_requires_explicit_distinct_occurrence_acknowledgement():
    old = payload([record()])["events"][0]
    registry = registry_for([old])
    changed = payload([record(title="同sourceの別開催か訂正か未確認", event_date="2026-11-02", event_end_date="2026-11-02")])["events"][0]
    review = request(registry, "new", [], [(None, changed)])
    with pytest.raises(ValueError, match="shares registered sources"):
        ids.apply_review(registry, review)
    review["acknowledged_related_event_uids"] = [old["event_key"]]
    review["evidence"]["reason"] = "Fictional official evidence confirms a distinct new occurrence, not a correction."
    revised = ids.apply_review(registry, review)
    assert revised["relations"][-1]["acknowledged_related_event_uids"] == [old["event_key"]]
    rows, held = ids.resolve_rows([old, changed], revised)
    assert held == [] and len({row["event_key"] for row in rows}) == 2
    assert ids.apply_review(revised, review) == revised


def test_source_priority_change_is_held_until_reviewed_correction():
    lower = record(source_id="starto_concert", source_class="general_news", title="架空公演の速報表記")
    old = payload([lower])["events"][0]
    candidate = payload([lower, record(title="架空公演の公式表記", record_id="new-official")])["events"][0]
    assert candidate["display_source_id"] == "official_events"
    registry = registry_for([old])
    assert ids.resolve_rows([candidate], registry)[0] == []
    corrected = ids.apply_review(registry, request(registry, "correction", [old["event_key"]], [(old["event_key"], candidate)]))
    rows, held = ids.resolve_rows([candidate], corrected)
    assert held == [] and rows[0]["event_key"] == old["event_key"]


@pytest.mark.parametrize("url", ["https://localhost/", "https://127.0.0.1/", "https://10.0.0.1/", "https://[::1]/"])
def test_review_evidence_rejects_known_local_addresses(url):
    old = payload([record()])["events"][0]
    registry = registry_for([old])
    review = request(registry, "correction", [old["event_key"]], [(old["event_key"], old)])
    review["evidence"]["url"] = url
    with pytest.raises(ValueError, match="review URL must not"):
        ids.apply_review(registry, review)


def test_lock_metadata_and_cleanup_do_not_unlink_a_replacement_lock(tmp_path):
    path = tmp_path / "identity.json"
    lock = path.with_name("." + path.name + ".lock")
    with ids.registry_lock(path):
        owner = json.loads(lock.read_bytes())
        assert owner["pid"] > 0 and owner["started_at_utc"].endswith("+00:00")
        lock.rename(tmp_path / "first-owner.lock")
        lock.write_bytes(b"replacement owner")
    assert lock.read_bytes() == b"replacement owner"


def test_atomic_replace_preserves_existing_file_permissions(tmp_path):
    path = tmp_path / "published.json"
    path.write_bytes(b"old")
    path.chmod(0o644)
    ids.atomic_write(path, b"new")
    assert path.read_bytes() == b"new" and path.stat().st_mode & 0o777 == 0o644
