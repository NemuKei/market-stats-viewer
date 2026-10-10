"""Bounded published-ID migration using only fictional files and occurrences."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from types import ModuleType

import pytest

from scripts import event_identity_registry as ids
from scripts import preserve_published_event_ids as migration


STAMP = "2026-10-06T11:28:46Z"
EVIDENCE = {"url": "https://example.com/published.json", "reviewed_at_utc": "2026-10-07T06:00:00Z",
            "reason": "Fictional published IDs verified against the same-generation source LP."}


def row(name):
    return {"event_key": "old-public-" + name, "event_date": "2026-11-01", "event_end_date": "2026-11-01",
            "event_start_time": "18:00", "venue_name": "Fictional venue " + name,
            "artist_name": "Fictional artist " + name, "title": "Fictional concert " + name,
            "supporting_sources": [{"source_id": "official_events", "record_id": "record-" + name}]}


def public_row(source):
    # Twenty-three fictional public fields, including fields absent from the
    # registry identity. The consumer fixture returns these independently from
    # the public snapshot, so equality must cover more than occurrence identity.
    return {"event_uid": source["event_key"], "source_record_id": source["supporting_sources"][0]["record_id"][:128],
            "source_policy_rule_id": "fictional-policy", "source_policy_status": "approved",
            "source_policy_reviewed_at": "2026-10-06", "source_domain": "example.com",
            "source_id": "official_events", "source_name": "Fictional official schedule",
            "title": source["title"], "start_date": source["event_date"], "end_date": source["event_end_date"],
            "start_time": source["event_start_time"], "published_at_utc": STAMP,
            "url": "https://example.com/" + source["event_key"], "updated_at_utc": STAMP,
            "venue_name": source["venue_name"], "pref_name": "東京都", "artist_name": source["artist_name"],
            "artist_confidence": "lp_canonical", "event_category": "コンサート", "source_type": "venue_official",
            "source_url": "https://example.com/schedule", "capacity": 10000}


def policy_metadata(count):
    return {"status": "enforced", "defaultDeny": True, "publishedCount": count, "policyId": "fictional-policy"}


def lp_payload(rows):
    result = {"schema_version": 1, "as_of_date": "2026-10-06", "generated_at_utc": STAMP, "events": deepcopy(rows)}
    for source in result["events"]:
        source["public_projection"] = public_row(source)
    return result


def snapshot_payload(lp):
    return {"metadata": {"asOfDate": lp["as_of_date"], "eventSourceGeneratedAtUtc": lp["generated_at_utc"]},
            "events": {"items": [deepcopy(source["public_projection"]) for source in lp["events"]],
                       "publicationPolicy": policy_metadata(len(lp["events"]))}}


def write_json(path, payload):
    path.write_bytes(ids.canonical_bytes(payload))


class FictionalMigration:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.registry = tmp_path / "registry.json"
        self.backup = tmp_path / "origin.backup.json"
        self.snapshot_path = tmp_path / "published.json"
        self.lp_path = tmp_path / "lp.json"
        self.policy_path = tmp_path / "policy.json"
        self.request_path = tmp_path / "request.json"
        self.scripts_dir = tmp_path / "consumer"
        self.scripts_dir.mkdir()
        # Small fictional consumer modules exercise the actual external-module
        # loading contract. They do not reproduce the production projection.
        modules = {
            "event_source_policy.py": '''from copy import deepcopy
import json
def load_source_policy(path):
    return json.loads(path.read_text())
def project_public_events(rows, policy):
    return deepcopy(rows), deepcopy(policy["publicationPolicy"])
''',
            "refresh_content_freshness.py": "def refresh_content_freshness(*args, **kwargs):\n    raise AssertionError('refresh must not run')\n",
            "verify_external_events_asset.py": "def require_timestamp(*args, **kwargs):\n    raise AssertionError('asset verification must not run')\n",
            "refresh_market_portal_data.py": '''import json
from event_source_policy import load_source_policy, project_public_events
from refresh_content_freshness import refresh_content_freshness
from verify_external_events_asset import require_timestamp
def export_lp_events(data_dir, as_of_date, lp_events_path=None):
    payload = json.loads(lp_events_path.read_text())
    assert payload["as_of_date"] == as_of_date
    return [row["public_projection"] for row in payload["events"] if not row.get("private")]
''',
        }
        for filename, text in modules.items():
            (self.scripts_dir / filename).write_text(text)
        # The seed has a historical ID that is absent from the latest public LP.
        seed_lp = lp_payload([row("A"), row("history")])
        seed_snapshot = ids.canonical_bytes(snapshot_payload(seed_lp))
        seed_lp_bytes = ids.canonical_bytes(seed_lp)
        origin = ids.seed_registry(seed_snapshot, expected_sha256=ids.digest(seed_snapshot), expected_count=2,
                                   lp_baseline_bytes=seed_lp_bytes, expected_lp_sha256=ids.digest(seed_lp_bytes))
        write_json(self.registry, origin)
        self.original_bytes = self.registry.read_bytes()
        self.origin = deepcopy(origin)
        self.lp = lp_payload([row("A"), row("B")])
        self.snapshot = snapshot_payload(self.lp)
        self.policy = {"publicationPolicy": deepcopy(self.snapshot["events"]["publicationPolicy"])}
        self.request = {
            "schema_version": 1, "kind": "preserve_published",
            "origin_registry_sha256": ids.digest(self.original_bytes), "origin_registry_revision": origin["revision"],
            "snapshot_sha256": "", "lp_sha256": "", "policy_sha256": "",
            "consumer_scripts_sha256": {filename: ids.digest((self.scripts_dir / filename).read_bytes())
                                        for filename in migration.CONSUMER_FILES},
            "added_ids": ["old-public-B"], "added_count": 1, "evidence": deepcopy(EVIDENCE),
        }
        self.freeze_inputs()

    def freeze_inputs(self):
        write_json(self.snapshot_path, self.snapshot)
        write_json(self.lp_path, self.lp)
        write_json(self.policy_path, self.policy)
        for path, key in ((self.snapshot_path, "snapshot_sha256"), (self.lp_path, "lp_sha256"),
                          (self.policy_path, "policy_sha256")):
            self.request[key] = ids.digest(path.read_bytes())
        self.write_request()

    def write_request(self):
        write_json(self.request_path, self.request)

    def run(self, **kwargs):
        arguments = dict(registry_path=self.registry, request_path=self.request_path,
                         expected_request_sha256=ids.digest(self.request_path.read_bytes()),
                         snapshot_path=self.snapshot_path, lp_path=self.lp_path, scripts_dir=self.scripts_dir,
                         policy_path=self.policy_path, backup_path=self.backup, apply=True)
        arguments.update(kwargs)
        return migration.preserve_published(**arguments)

    def assert_unchanged(self, *, backup=False):
        assert self.registry.read_bytes() == self.original_bytes
        assert self.backup.exists() is backup
        assert not (self.root / ".registry.json.lock").exists()


@pytest.fixture
def case(tmp_path):
    return FictionalMigration(tmp_path)


def test_dry_run_does_not_write_registry_backup_or_inputs(case):
    before = {path: path.read_bytes() for path in case.root.rglob("*") if path.is_file()}
    result = case.run(apply=False)
    assert result["would_change"] and not result["changed"] and result["added_count"] == 1
    assert before == {path: path.read_bytes() for path in case.root.rglob("*") if path.is_file()}
    case.assert_unchanged()


def test_apply_retains_history_ids_original_entries_and_published_id_without_uuid(case, monkeypatch):
    monkeypatch.setattr(ids, "uuid4", lambda: pytest.fail("migration must never allocate an ID"))
    result = case.run()
    current, _ = ids.load_registry(case.registry)
    assert result["changed"] and result["ids"] == 3 and result["revision"] == 2
    assert current["events"][:2] == case.origin["events"]
    assert {event["event_uid"] for event in current["events"]} == {"old-public-A", "old-public-history", "old-public-B"}
    assert case.backup.read_bytes() == case.original_bytes
    assert case.backup.stat().st_mode & 0o777 == 0o600
    before = case.registry.read_bytes(), case.backup.stat().st_ino, case.registry.stat().st_mtime_ns
    assert case.run()["replay"]
    assert before == (case.registry.read_bytes(), case.backup.stat().st_ino, case.registry.stat().st_mtime_ns)


def test_replay_after_correction_keeps_inactive_origin_and_added_observations(case):
    case.run()
    current, current_sha = ids.load_registry(case.registry)
    corrected = deepcopy(case.lp["events"][1])
    corrected["event_start_time"] = "19:00"
    review = {"schema_version": 1, "expected_revision": current["revision"], "kind": "correction",
              "previous_ids": ["old-public-B"],
              "candidates": [{"event_uid": "old-public-B", "observation": ids.observation_from_row(corrected)}],
              "evidence": {**EVIDENCE, "reason": "Fictional later official time correction."}}
    ids.write_registry(ids.apply_review(current, review), case.registry, expected_sha256=current_sha)
    before = case.registry.read_bytes()
    backup_inode = case.backup.stat().st_ino
    assert case.run()["replay"]
    assert case.registry.read_bytes() == before and case.backup.stat().st_ino == backup_inode
    loaded, _ = ids.load_registry(case.registry)
    assert loaded["events"][-1]["observations"][0]["active"] is False


@pytest.mark.parametrize("field", ["snapshot_sha256", "lp_sha256", "policy_sha256", "origin_registry_sha256"])
def test_hash_mismatch_fails_without_registry_or_backup_changes(case, field):
    case.request[field] = "0" * 64
    case.write_request()
    with pytest.raises(ValueError, match="hash mismatch"):
        case.run()
    case.assert_unchanged()


def test_request_hash_is_required_and_pins_raw_reviewed_bytes(case):
    with pytest.raises(ValueError, match="request hash mismatch"):
        case.run(expected_request_sha256="0" * 64)
    case.assert_unchanged()


@pytest.mark.parametrize("filename", migration.CONSUMER_FILES)
def test_every_consumer_script_is_hash_pinned(case, filename):
    with (case.scripts_dir / filename).open("a") as stream:
        stream.write("\n# source changed after review\n")
    with pytest.raises(ValueError, match="consumer script hash mismatch"):
        case.run()
    case.assert_unchanged()


@pytest.mark.parametrize("mutation,message", [
    (lambda c: c.request.update(origin_registry_revision=2), "revision mismatch"),
    (lambda c: c.request.update(added_count=2), "count mismatch"),
    (lambda c: c.request.update(added_ids=["never-published"]), "published ID set mismatch"),
    (lambda c: c.request.update(added_ids=["old-public-B", "old-public-B"], added_count=2), "unique and sorted"),
    (lambda c: c.request.update(schema_version=True), "version/kind"),
    (lambda c: c.request.update(extra_unreviewed="value"), "request schema"),
    (lambda c: c.request["evidence"].update(url="http://localhost/evidence"), "must not be local"),
])
def test_exact_request_scope_and_evidence_are_required(case, mutation, message):
    mutation(case)
    case.write_request()
    with pytest.raises(ValueError, match=message):
        case.run()
    case.assert_unchanged()


@pytest.mark.parametrize("field", ["capacity", "source_policy_reviewed_at", "updated_at_utc", "pref_name", "source_url", "title"])
def test_all_public_fields_must_match_actual_consumer_projection(case, field):
    case.snapshot["events"]["items"][1][field] = "different published value"
    case.freeze_inputs()
    with pytest.raises(ValueError, match="IDs/fields"):
        case.run()
    case.assert_unchanged()


def test_projection_numeric_type_change_is_not_silently_equal(case):
    case.snapshot["events"]["items"][1]["capacity"] = 10000.0
    case.freeze_inputs()
    with pytest.raises(ValueError, match="IDs/fields"):
        case.run()
    case.assert_unchanged()


@pytest.mark.parametrize("part", ["published", "source LP"])
def test_duplicate_row_ids_are_rejected_before_dict_conversion(case, part):
    if part == "published":
        case.snapshot["events"]["items"].append(deepcopy(case.snapshot["events"]["items"][1]))
    else:
        case.lp["events"].append(deepcopy(case.lp["events"][1]))
    case.freeze_inputs()
    with pytest.raises(ValueError, match="duplicate or invalid " + part):
        case.run()
    case.assert_unchanged()


@pytest.mark.parametrize("value,message", [(b'{"x":1,"x":2}', "duplicate JSON key"),
                                           (b'{"x":NaN}', "non-finite JSON number"),
                                           (b'{"x":Infinity}', "non-finite JSON number"),
                                           (b'{"x":1e9999}', "non-finite JSON number")])
def test_input_parser_rejects_duplicate_json_keys_and_nonfinite_values(value, message):
    with pytest.raises(ValueError, match=message):
        migration.parse_input(value)


def test_public_envelope_can_exceed_registry_limit(case):
    case.snapshot["unrelated_market_padding"] = "x" * (ids.MAX_REGISTRY_BYTES + 1)
    case.freeze_inputs()
    assert case.snapshot_path.stat().st_size > ids.MAX_REGISTRY_BYTES
    assert case.run()["changed"]


@pytest.mark.parametrize("mutation,message", [
    (lambda c: c.snapshot["metadata"].update(asOfDate="2026-10-07"), "basis mismatch"),
    (lambda c: c.snapshot["metadata"].update(eventSourceGeneratedAtUtc="2026-10-06T12:28:46Z"), "generation mismatch"),
    (lambda c: c.snapshot["metadata"].update(eventSourceGeneratedAtUtc="2026-10-06T11:28:46"), "explicit UTC"),
    (lambda c: c.snapshot["events"]["publicationPolicy"].update(defaultDeny=False), "policy/count required"),
    (lambda c: c.snapshot["events"]["publicationPolicy"].update(publishedCount=3), "policy/count required"),
    (lambda c: c.snapshot["events"]["publicationPolicy"].update(policyId="another-policy"), "policy mismatch"),
])
def test_same_generation_and_publication_policy_required(case, mutation, message):
    mutation(case)
    case.freeze_inputs()
    with pytest.raises(ValueError, match=message):
        case.run()
    case.assert_unchanged()


def test_unreviewed_source_collision_with_original_id_fails(case):
    case.lp["events"][1]["supporting_sources"] = deepcopy(case.lp["events"][0]["supporting_sources"])
    case.lp["events"][1]["public_projection"] = public_row(case.lp["events"][1])
    case.snapshot = snapshot_payload(case.lp)
    case.freeze_inputs()
    with pytest.raises(ValueError, match="source collision"):
        case.run()
    case.assert_unchanged()


def test_source_collision_between_two_additions_is_not_implicitly_reviewed(case):
    other = row("C")
    other["supporting_sources"] = deepcopy(case.lp["events"][1]["supporting_sources"])
    other["public_projection"] = public_row(other)
    case.lp["events"].append(other)
    case.snapshot = snapshot_payload(case.lp)
    case.policy["publicationPolicy"] = deepcopy(case.snapshot["events"]["publicationPolicy"])
    case.request.update(added_ids=["old-public-B", "old-public-C"], added_count=2)
    case.freeze_inputs()
    with pytest.raises(ValueError, match="source collision"):
        case.run()
    case.assert_unchanged()


def test_unique_truncated_public_record_preserves_full_namespace_id(case):
    full_record_id = "r" * 128 + "-original-long-record"
    case.lp["events"][1]["supporting_sources"][0]["record_id"] = full_record_id
    case.lp["events"][1]["public_projection"] = public_row(case.lp["events"][1])
    case.snapshot = snapshot_payload(case.lp)
    case.freeze_inputs()
    case.run()
    current, _ = ids.load_registry(case.registry)
    assert current["events"][-1]["observations"][0]["source_records"][0]["record_id"] == full_record_id


def test_ambiguous_truncated_record_is_rejected(case):
    sources = [{"source_id": "official_events", "record_id": "r" * 128 + suffix} for suffix in ("-one", "-two")]
    case.lp["events"][1]["supporting_sources"] = sources
    case.lp["events"][1]["public_projection"] = public_row(case.lp["events"][1])
    case.snapshot = snapshot_payload(case.lp)
    case.freeze_inputs()
    with pytest.raises(ValueError, match="missing or ambiguous"):
        case.run()
    case.assert_unchanged()


def test_existing_lock_is_respected_and_not_deleted(case):
    lock = case.root / ".registry.json.lock"
    lock.write_text("other writer owns this lock")
    with pytest.raises(FileExistsError):
        case.run()
    assert lock.read_text() == "other writer owns this lock"
    assert case.registry.read_bytes() == case.original_bytes and not case.backup.exists()


def test_registry_cas_rejects_a_writer_that_does_not_use_lock(case, monkeypatch):
    construct = migration.construct_migration
    other_writer_bytes = case.original_bytes + b"\n"

    def concurrent_edit(*args):
        result = construct(*args)
        case.registry.write_bytes(other_writer_bytes)
        return result

    monkeypatch.setattr(migration, "construct_migration", concurrent_edit)
    with pytest.raises(ValueError, match="registry changed before write"):
        case.run()
    assert case.registry.read_bytes() == other_writer_bytes
    assert not case.backup.exists() and not (case.root / ".registry.json.lock").exists()


def test_input_modified_during_projection_is_rejected(case, monkeypatch):
    project = migration.project_snapshot

    def concurrent_input_edit(*args):
        result = project(*args)
        case.lp_path.write_bytes(case.lp_path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(migration, "project_snapshot", concurrent_input_edit)
    with pytest.raises(ValueError, match="input changed before write"):
        case.run()
    case.assert_unchanged()


def test_atomic_replace_failure_keeps_original_and_retry_reuses_exact_backup(case, monkeypatch):
    replace = os.replace
    monkeypatch.setattr(os, "replace", lambda *args: (_ for _ in ()).throw(OSError("fictional disk failure")))
    with pytest.raises(OSError, match="disk failure"):
        case.run()
    case.assert_unchanged(backup=True)
    assert case.backup.read_bytes() == case.original_bytes
    assert sorted(path.name for path in case.root.iterdir() if path.name.startswith(".")) == []
    backup_inode = case.backup.stat().st_ino
    monkeypatch.setattr(os, "replace", replace)
    assert case.run()["changed"] and case.backup.stat().st_ino == backup_inode


def test_backup_write_failure_prevents_registry_replacement(case, monkeypatch):
    atomic = ids.atomic_write

    def fail_backup(path, data, **kwargs):
        if path == case.backup:
            raise OSError("fictional backup failure")
        return atomic(path, data, **kwargs)

    monkeypatch.setattr(ids, "atomic_write", fail_backup)
    with pytest.raises(OSError, match="backup failure"):
        case.run()
    case.assert_unchanged()


def test_registry_size_limit_is_checked_before_creating_backup(case, monkeypatch):
    # Origin is below this limit, but the supplemented serialization is above it.
    monkeypatch.setattr(ids, "MAX_REGISTRY_BYTES", len(case.original_bytes) + 100)
    with pytest.raises(ValueError, match="registry exceeds byte limit"):
        case.run()
    case.assert_unchanged()


def test_oversized_registry_read_is_bounded_before_parsing(case, monkeypatch):
    case.registry.write_bytes(b" " * (ids.MAX_REGISTRY_BYTES + 100))
    open_file = Path.open
    read_sizes = []

    class BoundedReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size=-1):
            read_sizes.append(size)
            assert size == ids.MAX_REGISTRY_BYTES + 1
            return self.stream.read(size)

    def checked_open(path, *args, **kwargs):
        stream = open_file(path, *args, **kwargs)
        return BoundedReader(stream) if path == case.registry else stream

    monkeypatch.setattr(Path, "open", checked_open)
    with pytest.raises(ValueError, match="registry exceeds byte limit"):
        case.run()
    assert read_sizes == [ids.MAX_REGISTRY_BYTES + 1]
    assert case.registry.stat().st_size == ids.MAX_REGISTRY_BYTES + 100
    assert not case.backup.exists() and not (case.root / ".registry.json.lock").exists()


def test_fifo_registry_is_rejected_before_any_open(case, monkeypatch):
    case.registry.unlink()
    os.mkfifo(case.registry)
    open_file = Path.open

    def refuse_fifo_open(path, *args, **kwargs):
        if path == case.registry:
            pytest.fail("FIFO registry must be rejected before opening")
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refuse_fifo_open)
    with pytest.raises(ValueError, match="registry must be a regular nonsymlink file"):
        case.run()
    assert not case.backup.exists() and not (case.root / ".registry.json.lock").exists()


def test_replay_without_origin_backup_fails_closed(case):
    case.run()
    before = case.registry.read_bytes()
    case.backup.unlink()
    with pytest.raises(ValueError, match="origin registry hash mismatch"):
        case.run()
    assert case.registry.read_bytes() == before and not case.backup.exists()


def test_replay_rejects_rewritten_evidence_even_when_registry_is_internally_valid(case):
    case.run()
    current, _ = ids.load_registry(case.registry)
    evidence = {**EVIDENCE, "reason": "Rewritten fictional evidence."}
    current["relations"][-1]["evidence"] = evidence
    current["events"][-1]["observations"][0]["evidence"] = evidence
    ids.validate_registry(current)
    write_json(case.registry, current)
    before = case.registry.read_bytes()
    with pytest.raises(ValueError, match="origin/journal history changed"):
        case.run()
    assert case.registry.read_bytes() == before


def test_cached_consumer_module_is_replaced_by_pinned_bytes_then_restored(case, monkeypatch):
    cached = ModuleType("event_source_policy")
    cached.load_source_policy = lambda _: pytest.fail("unverified cached module was used")
    monkeypatch.setitem(sys.modules, "event_source_policy", cached)
    assert case.run()["changed"]
    assert sys.modules["event_source_policy"] is cached


@pytest.mark.parametrize("field", ["registry", "snapshot_path", "lp_path", "policy_path", "request_path"])
def test_symlink_input_paths_are_rejected(case, field):
    path = getattr(case, field)
    original = path.with_suffix(".original")
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        case.run()
    assert case.registry.read_bytes() == case.original_bytes and not case.backup.exists()


def test_symlink_consumer_directory_and_script_are_rejected(case):
    alias = case.root / "consumer-link"
    alias.symlink_to(case.scripts_dir, target_is_directory=True)
    with pytest.raises(ValueError, match="nonsymlink directory"):
        case.run(scripts_dir=alias)
    path = case.scripts_dir / migration.CONSUMER_FILES[0]
    original = path.with_suffix(".original")
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(ValueError, match="nonsymlink file"):
        case.run()
    case.assert_unchanged()


@pytest.mark.parametrize("field", ["registry", "snapshot_path", "lp_path", "policy_path", "request_path"])
def test_backup_cannot_overwrite_any_registry_or_input_path(case, field):
    with pytest.raises(ValueError, match="overwrite a source/registry"):
        case.run(backup_path=getattr(case, field))
    case.assert_unchanged()


def test_backup_hardlink_alias_is_rejected(case):
    os.link(case.registry, case.backup)
    with pytest.raises(ValueError, match="aliases a source/registry"):
        case.run()
    assert case.registry.read_bytes() == case.original_bytes


def test_unpublished_unregistered_candidate_is_held_and_never_supplemented(case):
    private_row = row("unregistered")
    private_row.update(private=True, public_projection=public_row(private_row))
    case.lp["events"].append(private_row)
    case.freeze_inputs()
    case.run()
    current, _ = ids.load_registry(case.registry)
    _, held = ids.resolve_rows(case.lp["events"], current)
    assert len(current["events"]) == 3
    assert len(held) == 1 and held[0]["candidate_key"] == private_row["event_key"]
    assert held[0]["reason"] == "unregistered_candidate"


def test_changed_original_published_occurrence_cannot_be_silently_rebound(case):
    case.lp["events"][0]["event_start_time"] = "19:00"
    case.lp["events"][0]["public_projection"] = public_row(case.lp["events"][0])
    case.snapshot = snapshot_payload(case.lp)
    case.freeze_inputs()
    with pytest.raises(ValueError, match="occurrence is not bound"):
        case.run()
    case.assert_unchanged()


def test_registry_file_permissions_are_retained(case):
    case.registry.chmod(0o640)
    case.run()
    assert case.registry.stat().st_mode & 0o777 == 0o640
    assert case.backup.stat().st_mode & 0o777 == 0o600


def test_atomic_backup_creation_does_not_overwrite_a_competing_file(case, monkeypatch):
    atomic = ids.atomic_write

    def competing_backup(path, data, **kwargs):
        if path == case.backup:
            path.write_text("another process owns this backup")
        return atomic(path, data, **kwargs)

    monkeypatch.setattr(ids, "atomic_write", competing_backup)
    with pytest.raises(FileExistsError):
        case.run()
    assert case.registry.read_bytes() == case.original_bytes
    assert case.backup.read_text() == "another process owns this backup"
    assert not (case.root / ".registry.json.lock").exists()


def test_failed_consumer_import_restores_original_modules_and_writes_nothing(case, monkeypatch):
    original = ModuleType("event_source_policy")
    monkeypatch.setitem(sys.modules, "event_source_policy", original)
    path = case.scripts_dir / "refresh_market_portal_data.py"
    path.write_text("raise RuntimeError('fictional import failure')\n")
    case.request["consumer_scripts_sha256"][path.name] = ids.digest(path.read_bytes())
    case.write_request()
    with pytest.raises(RuntimeError, match="import failure"):
        case.run()
    assert sys.modules["event_source_policy"] is original
    case.assert_unchanged()


def test_different_existing_backup_is_never_overwritten(case):
    case.backup.write_text("different backup")
    with pytest.raises(ValueError, match="origin registry hash mismatch"):
        case.run()
    assert case.backup.read_text() == "different backup"
    assert case.registry.read_bytes() == case.original_bytes


def test_cli_defaults_to_dry_run_and_requires_reviewed_request_hash(case, capsys):
    arguments = ["--registry", str(case.registry), "--request", str(case.request_path),
                 "--expected-request-sha256", ids.digest(case.request_path.read_bytes()),
                 "--snapshot", str(case.snapshot_path), "--lp-baseline", str(case.lp_path),
                 "--consumer-scripts", str(case.scripts_dir), "--source-policy", str(case.policy_path),
                 "--origin-backup", str(case.backup)]
    assert migration.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["would_change"] is True
    case.assert_unchanged()
