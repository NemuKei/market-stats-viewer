"""Fictional observations only: export approval, privacy and distribution gates."""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

from scripts import build_public_schedule_days as public
from scripts import event_identity_registry as ids
from scripts.build_external_events_manifest import _build_manifest
from scripts.validate_external_events import validate_package
from test_archival_schedule_days import base_registry, fixture as original_fixture, reviewed
from test_validate_external_events import payload as recent_fixture


def public_row(row):
    return dict(event_uid=row["event_key"], source_record_id="fictional-public-source",
        source_policy_rule_id="fictional-official-rule", source_policy_status="approved",
        source_policy_reviewed_at="2026-10-11", source_domain="venue.example.test", kind="official",
        kindLabel="会場公式", source_id="official_events", source_name="架空ホール",
        title=row["title"], start_date=row["event_date"], end_date=row["event_end_date"],
        published_at_utc="2026-02-01T00:00:00Z", updated_at_utc="2026-02-01T00:00:00Z",
        url="https://venue.example.test/calendar", venue_name=row["venue_name"], pref_name="東京都",
        event_category="未分類", source_type="venue_official")


def policy(count, excluded=0):
    return dict(status="enforced", policyId="fictional-public-policy", policySchemaVersion=1,
        reviewedAt="2026-10-11", defaultDeny=True, inputCount=count + excluded, publishedCount=count,
        excludedCount=excluded, excludedByStatus={"blocked": 0, "unknown": excluded, "invalid": 0},
        allowedFields=sorted(public.ROW_FIELDS))


def summary(rows):
    return {"byKind": {"official": len(rows)}, "categories": {"未分類": len(rows)},
            "topPrefectures": [["東京都", len(rows)]]}


def fixture():
    inv, raw, old = original_fixture()
    rows, metadata, _ = public_source_rows(inv, raw, old)
    registry = ids.apply_review(base_registry(), reviewed(base_registry(), rows))
    bound, held = ids.resolve_rows(rows, registry)
    assert not held
    registry_sha = ids.digest(ids.canonical_bytes(registry))
    ordinary = public_row(dict(bound[0], event_key="fictional-existing", event_date="2026-07-06", event_end_date="2026-07-06"))
    ordinary.update(artist_name="架空出演者", start_time="19:00")
    baseline = dict(schemaVersion=1, metadata=dict(generatedAtUtc="2026-10-11T06:00:00Z",
        eventSourceGeneratedAtUtc="2026-10-11T06:00:00Z", asOfDate="2026-10-11", eventHistoryWindowDays=None,
        eventHistoryStartDate="2026-07-06", sourceRepository="market-stats-viewer", sourceOwner="market-stats-viewer",
        displayOwner="SideBiz_HotelRM", sourceCommit="c" * 40, sourceAssetSha256="b" * 64),
        coverage=dict(scope="all_verified_retained", availableFrom="2026-07-06", availableThrough="2026-07-06",
        publicCount=1, completeArchive=False), events=dict(items=[ordinary], publicationPolicy=policy(1), summary=summary([ordinary])))
    baseline["generation"] = ids.digest(ids.canonical_bytes(baseline))
    source = dict(schema_version=1, dataset="preserved_schedule_days", generated_at_utc="2026-10-11T06:00:00Z",
        baseline_sha256=ids.digest(ids.canonical_bytes(baseline)), input_sha256={"inventory": "d" * 64, "raw_observations": "e" * 64},
        identity_registry=dict(schema_version=2, revision=registry["revision"], sha256=registry_sha), events=bound,
        schedule_metadata={b["event_key"]: metadata[r["event_key"]] for b, r in zip(bound, rows)})
    approved = [public_row(r) for r in bound[:-1]]
    snapshot = deepcopy(baseline)
    snapshot["schemaVersion"] = 2
    snapshot["metadata"].update(scheduleSourceAssetSha256=ids.digest(ids.canonical_bytes(source)),
        scheduleSourceGeneratedAtUtc=source["generated_at_utc"])
    snapshot["events"].update(items=approved + [ordinary], publicationPolicy=policy(len(approved) + 1, 1),
        summary=summary(approved + [ordinary]), recordUnits={ordinary["event_uid"]: "occurrence"} | {r["event_uid"]: "schedule_day" for r in approved},
        scheduleDays={r["event_uid"]: source["schedule_metadata"][r["event_uid"]] for r in approved})
    snapshot["metadata"]["eventHistoryStartDate"] = min(row["start_date"] for row in snapshot["events"]["items"])
    snapshot["coverage"].update(publicCount=len(approved) + 1,
        availableFrom=snapshot["metadata"]["eventHistoryStartDate"],
        availableThrough=max(row["end_date"] for row in snapshot["events"]["items"]),
        unitCounts={"occurrence": 1, "schedule_day": len(approved)})
    snapshot["generation"] = ids.digest(ids.canonical_bytes({k: v for k, v in snapshot.items() if k != "generation"}))
    # The injection is an independent approved projection witness, not policy code.
    def projector(input_rows, approved_snapshot):
        return [public_row(r) for r in input_rows[:-1]], policy(len(input_rows) - 1, 1)
    return source, registry, snapshot, baseline, projector


def public_source_rows(inv, raw, old):
    from scripts.build_archival_schedule_days import build_candidates
    return build_candidates(inv, raw, old)


def build(source, registry, snapshot, projector):
    return public.build_public_asset(source, registry, snapshot,
        source_sha256=ids.digest(ids.canonical_bytes(source)), registry_sha256=ids.digest(ids.canonical_bytes(registry)),
        expected_approval_sha256=public.approval_set_digest(snapshot["events"]["scheduleDays"]), projector=projector)


def write_cli_fixture(root, *, consumer_scripts=None, source_policy=None):
    """Write only fictional inputs; optional actual helpers enable a cross-repo smoke.

    With no helpers, the caller injects the independent projection witness via
    pinned_consumer. With helpers, the supplied synthetic policy and the exact
    four captured scripts generate the rows, aggregate and summary themselves.
    """
    root.mkdir(parents=True, exist_ok=True)
    s, r, snap, baseline, projector = fixture()
    ordinary = deepcopy(s["events"][0])
    ordinary.update(event_key="fictional-existing", event_date="2026-07-06",
        event_end_date="2026-07-06", event_start_time="19:00", artist_name="架空出演者",
        url="https://venue.example.test/ordinary-old", evidence_url="https://venue.example.test/ordinary-old")
    ordinary.pop("record_kind")
    for index, support in enumerate(ordinary["supporting_sources"]):
        support.update(record_id=f"fictional-existing-record-{index}", url=ordinary["url"], evidence_url=ordinary["url"])
    if consumer_scripts is None:
        consumer_scripts = root / "fictional-code"
        consumer_scripts.mkdir()
        for name in public.CONSUMER_FILES:
            (consumer_scripts / name).write_text("# Fictional captured-code witness.\n")
        source_policy = {"fixture": "fictional"}
    else:
        assert source_policy is not None
        # A held row remains outside the permitted fictional domain.
        held = s["events"][-1]
        held["url"] = held["evidence_url"] = "https://unregistered.example.test/calendar"
        for support in held["supporting_sources"]:
            support["url"] = support["evidence_url"] = held["url"]
        script_bytes = {name: (consumer_scripts / name).read_bytes() for name in public.CONSUMER_FILES}
        with public.pinned_consumer(consumer_scripts, script_bytes) as (portal, policy_module):
            policy_path = root / "source-policy.json"
            policy_path.write_bytes(ids.canonical_bytes(source_policy))
            verified_policy = policy_module.load_source_policy(policy_path)
            ordinary_rows, ordinary_policy = policy_module.project_public_events(
                portal.export_lp_event_rows([ordinary], history_start_date=None), verified_policy)
            day_rows, day_policy = policy_module.project_public_events(
                portal.export_lp_event_rows(s["events"], history_start_date=None), verified_policy)
            baseline["events"] = dict(items=ordinary_rows, publicationPolicy=ordinary_policy,
                                      summary=policy_module.summarize_public_events(ordinary_rows))
            snap["events"].update(items=day_rows + ordinary_rows,
                recordUnits={row["event_uid"]: "schedule_day" for row in day_rows} | {"fictional-existing": "occurrence"},
                scheduleDays={row["event_uid"]: s["schedule_metadata"][row["event_uid"]] for row in day_rows},
                publicationPolicy=deepcopy(day_policy), summary=policy_module.summarize_public_events(day_rows + ordinary_rows))
            snap["events"]["publicationPolicy"]["inputCount"] += len(ordinary_rows)
            snap["events"]["publicationPolicy"]["publishedCount"] += len(ordinary_rows)
    baseline["generation"] = ids.digest(ids.canonical_bytes({k: v for k, v in baseline.items() if k != "generation"}))
    # Pretty original bytes intentionally differ from canonical encoding.
    baseline_bytes = json.dumps(baseline, ensure_ascii=False, indent=2).encode() + b"\n"
    s["baseline_sha256"] = ids.digest(baseline_bytes)
    source_bytes = ids.canonical_bytes(s)
    snap["metadata"]["scheduleSourceAssetSha256"] = ids.digest(source_bytes)
    snap["generation"] = ids.digest(ids.canonical_bytes({k: v for k, v in snap.items() if k != "generation"}))
    hashes = {name: ids.digest((consumer_scripts / name).read_bytes()) for name in public.CONSUMER_FILES}
    paths = {name: root / (name + ".json") for name in ("private-asset", "registry", "approved-snapshot", "consumer-hashes", "source-policy", "baseline")}
    contents = [source_bytes, ids.canonical_bytes(r), ids.canonical_bytes(snap), ids.canonical_bytes(hashes),
                ids.canonical_bytes(source_policy), baseline_bytes]
    for path, raw in zip(paths.values(), contents):
        path.write_bytes(raw)
    out = root / "distribution"
    out.mkdir()
    paths.update(output=out / public.PUBLIC_ASSET_FILENAME, **{"baseline-output": out / public.PUBLIC_BASELINE_FILENAME,
        "consumer-scripts": consumer_scripts})
    argv = [word for name, path in paths.items() for word in ("--" + name, str(path))]
    for name, raw in zip(("asset", "registry", "snapshot", "consumer-hashes", "policy"), contents):
        argv += ["--expected-" + name + "-sha256", ids.digest(raw)]
    argv += ["--expected-approval-sha256", public.approval_set_digest(snap["events"]["scheduleDays"])]
    return argv, dict(paths=paths, source=s, registry=r, snapshot=snap, baseline=baseline,
                      baseline_bytes=baseline_bytes, projector=projector, ordinary_source_rows=[ordinary])


def inject_cli_witness(monkeypatch, bundle):
    @contextmanager
    def captured_consumer(*_):
        portal = SimpleNamespace(export_lp_event_rows=lambda rows, **_: rows)
        policy_module = SimpleNamespace(load_source_policy=lambda _: {}, verify_public_event_payload=lambda *_: None,
            project_public_events=lambda rows, _: bundle["projector"](rows, bundle["snapshot"]))
        yield portal, policy_module
    monkeypatch.setattr(public, "pinned_consumer", captured_consumer)


def test_export_retains_public_fields_times_and_private_exclusion_aggregates():
    s, r, snapshot, baseline, projector = fixture()
    before = deepcopy((s, r, snapshot, baseline))
    asset = build(s, r, snapshot, projector)
    assert (s, r, snapshot, baseline) == before
    assert asset["events"] == snapshot["events"]["items"][:-1]
    assert asset["schedule_metadata"] == snapshot["events"]["scheduleDays"]
    assert asset["publication_policy"] == policy(3, 1)
    assert asset["generated_at_utc"] == s["generated_at_utc"]
    assert all("supporting_sources" not in row for row in asset["events"])
    assert s["events"][-1]["event_key"] not in asset["schedule_metadata"]
    for row in s["events"][:-1]:
        expected = sorted(hashlib.sha256(json.dumps([q["source_id"], q["record_id"]], ensure_ascii=False,
            separators=(",", ":")).encode()).hexdigest() for q in row["supporting_sources"])
        assert asset["source_record_digests"][row["event_key"]] == expected
    assert public.source_record_digest("official_events", "架空source") == hashlib.sha256(
        '["official_events","架空source"]'.encode()).hexdigest()
    public.validate_public_baseline(baseline)


@pytest.mark.parametrize("change", [
    lambda a: a.update(raw_observations=[]),
    lambda a: a["events"][0].update(supporting_sources=[]),
    lambda a: a["events"][0].update(source_policy_status="unknown"),
    lambda a: a["events"][0].update(start_time="13:00"),
    lambda a: a["events"][0].update(artist_name="未確認出演者"),
    lambda a: a["schedule_metadata"][a["events"][0]["event_uid"]].update(performanceCount=2),
    lambda a: a["schedule_metadata"][a["events"][0]["event_uid"]].update(occurrenceCompleted="confirmed"),
    lambda a: a["schedule_metadata"].clear(),
    lambda a: a["source_record_digests"][a["events"][0]["event_uid"]].append("private-source-id"),
    lambda a: a["publication_policy"].update(publishedCount=True),
    lambda a: a["publication_policy"]["excludedByStatus"].update(unknown=2),
    lambda a: a["provenance"]["identity_registry"].update(schema_version=1),
    lambda a: a.update(schema_version=True),
    lambda a: a["events"][0].update(event_uid=a["events"][1]["event_uid"]),
])
def test_public_validator_rejects_private_fields_false_predicates_and_count_drift(change):
    s, r, snap, _, projection = fixture()
    asset = build(s, r, snap, projection)
    change(asset)
    with pytest.raises(ValueError):
        public.validate_public_asset(asset)


@pytest.mark.parametrize("change", [
    lambda snap: snap["events"]["items"][0].update(title="未確認の別番組"),
    lambda snap: snap["events"]["scheduleDays"][next(iter(snap["events"]["scheduleDays"]))].update(observedTimes=["22:00"]),
    lambda snap: snap["metadata"].update(scheduleSourceAssetSha256="0" * 64),
])
def test_snapshot_must_exactly_match_private_projection(change):
    s, r, snap, _, projection = fixture()
    snap = deepcopy(snap)
    change(snap)
    with pytest.raises(ValueError):
        build(s, r, snap, projection)


def test_policy_expansion_cannot_promote_held_day_with_old_approval_pin():
    s, r, snap, _, projection = fixture()
    pin = public.approval_set_digest(snap["events"]["scheduleDays"])
    snap = deepcopy(snap)
    extra = public_row(s["events"][-1])
    snap["events"]["items"].insert(-1, extra)
    snap["events"]["recordUnits"][extra["event_uid"]] = "schedule_day"
    snap["events"]["scheduleDays"][extra["event_uid"]] = s["schedule_metadata"][extra["event_uid"]]
    with pytest.raises(ValueError, match="approval set"):
        public.build_public_asset(s, r, snap, source_sha256=ids.digest(ids.canonical_bytes(s)),
            registry_sha256=ids.digest(ids.canonical_bytes(r)), expected_approval_sha256=pin,
            projector=lambda rows, _: ([public_row(v) for v in rows], policy(4)))


def selected_asset(source, registry, snapshot, projector, approved_ids, **changes):
    selection = {"schema_version": 1, "approved_ids": approved_ids}
    selection.update(changes)
    return public.build_public_asset(source, registry, snapshot,
        source_sha256=ids.digest(ids.canonical_bytes(source)),
        registry_sha256=ids.digest(ids.canonical_bytes(registry)),
        expected_approval_sha256=public.approval_set_digest(approved_ids), projector=projector,
        publication_selection=selection)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_explicit_selection_preserves_full_review_and_changes_only_public_membership(count):
    source, registry, snapshot, baseline, projector = fixture()
    before = deepcopy((source, registry, snapshot, baseline))
    full = build(source, registry, snapshot, projector)
    approved_ids = sorted(snapshot["events"]["scheduleDays"])[:count]
    asset = selected_asset(source, registry, snapshot, projector, approved_ids)
    assert (source, registry, snapshot, baseline) == before
    assert asset["events"] == [r for r in full["events"] if r["event_uid"] in approved_ids]
    assert asset["schedule_metadata"] == {uid: value for uid, value in full["schedule_metadata"].items() if uid in approved_ids}
    assert asset["source_record_digests"] == {uid: value for uid, value in full["source_record_digests"].items() if uid in approved_ids}
    assert asset["generated_at_utc"] == full["generated_at_utc"]
    assert asset["provenance"]["schedule_asset_sha256"] == full["provenance"]["schedule_asset_sha256"]
    assert asset["provenance"]["identity_registry"] == full["provenance"]["identity_registry"]
    publication = asset["publication_policy"]
    assert publication["inputCount"] == 4 and publication["publishedCount"] == count
    assert publication["excludedCount"] == 4 - count
    assert publication["excludedByStatus"] == {"blocked": 3 - count, "unknown": 1, "invalid": 0}
    if count == 3:
        assert asset == full


@pytest.mark.parametrize("case", ["unknown", "held", "duplicate", "unsorted", "false-version", "extra-field", "non-list", "pin"])
def test_publication_selection_rejects_unreviewed_or_malformed_membership(case):
    source, registry, snapshot, _, projector = fixture()
    approved_ids = sorted(snapshot["events"]["scheduleDays"])
    selection = {"schema_version": 1, "approved_ids": approved_ids}
    pin = public.approval_set_digest(approved_ids)
    if case == "unknown":
        selection["approved_ids"] = ["fictional-unreviewed-id"]
        pin = public.approval_set_digest(selection["approved_ids"])
    elif case == "held":
        selection["approved_ids"] = [source["events"][-1]["event_key"]]
        pin = public.approval_set_digest(selection["approved_ids"])
    elif case == "duplicate":
        selection["approved_ids"] = [approved_ids[0], approved_ids[0]]
    elif case == "unsorted":
        selection["approved_ids"] = list(reversed(approved_ids))
    elif case == "false-version":
        selection["schema_version"] = True
    elif case == "extra-field":
        selection["private_notes"] = "fictional"
    elif case == "non-list":
        selection["approved_ids"] = {approved_ids[0]: True}
    else:
        pin = "0" * 64
    before = deepcopy((source, registry, snapshot))
    with pytest.raises(ValueError):
        public.build_public_asset(source, registry, snapshot,
            source_sha256=ids.digest(ids.canonical_bytes(source)),
            registry_sha256=ids.digest(ids.canonical_bytes(registry)),
            expected_approval_sha256=pin, projector=projector, publication_selection=selection)
    assert (source, registry, snapshot) == before


def test_selection_does_not_hide_changed_full_projection_or_invalid_aggregates():
    source, registry, snapshot, _, projector = fixture()
    selected = sorted(snapshot["events"]["scheduleDays"])[:1]
    omitted = next(r for r in snapshot["events"]["items"] if r["event_uid"] in snapshot["events"]["scheduleDays"] and r["event_uid"] not in selected)
    omitted["title"] = "unreviewed fictional title"
    with pytest.raises(ValueError, match="projection changed"):
        selected_asset(source, registry, snapshot, projector, selected)
    source, registry, snapshot, _, projector = fixture()
    def broken_projection(rows, approved):
        projected, publication = projector(rows, approved)
        publication["inputCount"] += 1
        return projected, publication
    with pytest.raises(ValueError, match="counts differ"):
        selected_asset(source, registry, snapshot, broken_projection, [])


def test_empty_public_asset_requires_external_approval_and_empty_metadata():
    source, registry, snapshot, _, projector = fixture()
    asset = selected_asset(source, registry, snapshot, projector, [])
    pin = public.approval_set_digest([])
    with pytest.raises(ValueError, match="external approval"):
        public.validate_public_asset(asset)
    assert public.validate_public_asset(asset, expected_approval_sha256=pin)["day_count"] == 0
    for mutate in [lambda a: a["schedule_metadata"].update(unreviewed={}),
                   lambda a: a["source_record_digests"].update(unreviewed=[]),
                   lambda a: a["publication_policy"].update(publishedCount=1)]:
        malformed = deepcopy(asset)
        mutate(malformed)
        with pytest.raises(ValueError):
            public.validate_public_asset(malformed, expected_approval_sha256=pin)


def package(tmp_path):
    s, r, snap, baseline, projector = fixture()
    public_asset = build(s, r, snap, projector)
    for name in ("events.sqlite", "event_signals.sqlite"):
        with sqlite3.connect(tmp_path / name) as db:
            db.execute("create table fictional (id integer)")
    (tmp_path / "lp_events.json").write_text(json.dumps(recent_fixture()))
    (tmp_path / public.PUBLIC_ASSET_FILENAME).write_bytes(ids.canonical_bytes(public_asset))
    (tmp_path / public.PUBLIC_BASELINE_FILENAME).write_bytes(ids.canonical_bytes(baseline))
    pins = dict(expected_public_sha256=ids.digest((tmp_path / public.PUBLIC_ASSET_FILENAME).read_bytes()),
        expected_baseline_sha256=public_asset["baseline_sha256"], expected_approval_sha256=public_asset["provenance"]["approval_set_sha256"])
    return public_asset, pins


def test_manifest_is_disabled_by_default_and_enabled_pair_is_hash_verified(tmp_path):
    asset, pins = package(tmp_path)
    old = _build_manifest(tmp_path, "external-events-latest")
    assert set(old["assets"]) == {"events.sqlite", "event_signals.sqlite", "lp_events.json"}
    new = _build_manifest(tmp_path, "external-events-latest", include_public_schedule_days=True, **pins)
    assert all(new["assets"][k] == v for k, v in old["assets"].items())
    assert new["schema_version"] == old["schema_version"] and new["dataset"] == old["dataset"]
    (tmp_path / "manifest.json").write_text(json.dumps(new))
    assert validate_package(tmp_path, require_public_schedule_days=True, **pins)["day_count"] == len(asset["events"])
    (tmp_path / public.PUBLIC_BASELINE_FILENAME).unlink()
    with pytest.raises(ValueError, match="regular"):
        _build_manifest(tmp_path, "external-events-latest", include_public_schedule_days=True, **pins)


def test_distribution_rejects_missing_pins_asset_mutation_and_manifest_half_pair(tmp_path):
    _, pins = package(tmp_path)
    with pytest.raises(ValueError, match="three reviewed pins"):
        _build_manifest(tmp_path, "external-events-latest", include_public_schedule_days=True)
    manifest = _build_manifest(tmp_path, "external-events-latest", include_public_schedule_days=True, **pins)
    manifest["assets"].pop(public.PUBLIC_BASELINE_FILENAME)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="pair"):
        validate_package(tmp_path)
    path = tmp_path / public.PUBLIC_ASSET_FILENAME
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="bytes differ"):
        _build_manifest(tmp_path, "external-events-latest", include_public_schedule_days=True, **pins)


@pytest.mark.parametrize("change", [
    lambda b: b["metadata"].update(private_plan=[]),
    lambda b: b["events"]["items"][0].update(source_records=[]),
    lambda b: b.update(schemaVersion=2),
    lambda b: b["coverage"].update(completeArchive=True),
])
def test_public_baseline_forbids_private_fields_and_false_completeness(change):
    _, _, _, baseline, _ = fixture()
    change(baseline)
    baseline["generation"] = ids.digest(ids.canonical_bytes({k: v for k, v in baseline.items() if k != "generation"}))
    with pytest.raises(ValueError):
        public.validate_public_baseline(baseline)


def test_existing_public_optional_empty_fields_remain_valid():
    s, r, snap, baseline, projector = fixture()
    baseline["events"]["items"][0].update(start_time="", source_url="", artist_name="")
    baseline["generation"] = ids.digest(ids.canonical_bytes({k: v for k, v in baseline.items() if k != "generation"}))
    public.validate_public_baseline(baseline)
    asset = build(s, r, snap, projector)
    asset["events"][0].update(start_time="", source_url="", artist_name="")
    public.validate_public_asset(asset)


def test_duplicate_private_support_is_not_silently_collapsed():
    s, r, snap, _, projection = fixture()
    s["events"][0]["supporting_sources"].append(deepcopy(s["events"][0]["supporting_sources"][0]))
    snap["metadata"]["scheduleSourceAssetSha256"] = ids.digest(ids.canonical_bytes(s))
    with pytest.raises(ValueError, match="duplicate private source"):
        build(s, r, snap, projection)


def test_cli_copy_is_exact_noop_is_idempotent_and_inputs_stay_unchanged(tmp_path, monkeypatch):
    argv, bundle = write_cli_fixture(tmp_path)
    inject_cli_witness(monkeypatch, bundle)
    paths = bundle["paths"]
    inputs = {name: path.read_bytes() for name, path in paths.items() if name not in {"consumer-scripts", "output", "baseline-output"}}
    assert public.main(argv) == 0
    assert paths["baseline-output"].read_bytes() == bundle["baseline_bytes"]
    assert ids.canonical_bytes(bundle["baseline"]) != bundle["baseline_bytes"]
    public.validate_public_package(paths["output"].parent)
    before = {name: (paths[name].read_bytes(), paths[name].stat().st_mtime_ns) for name in ("output", "baseline-output")}
    assert public.main(argv) == 0
    assert before == {name: (paths[name].read_bytes(), paths[name].stat().st_mtime_ns) for name in before}
    assert inputs == {name: paths[name].read_bytes() for name in inputs}


@pytest.mark.parametrize("count", [0, 1])
def test_cli_publication_selection_is_immutable_and_keeps_private_inputs(tmp_path, monkeypatch, count):
    argv, bundle = write_cli_fixture(tmp_path)
    inject_cli_witness(monkeypatch, bundle)
    paths = bundle["paths"]
    approved_ids = sorted(bundle["snapshot"]["events"]["scheduleDays"])[:count]
    selection_path = tmp_path / "fictional-publication-selection.json"
    selection_path.write_bytes(ids.canonical_bytes({"schema_version": 1, "approved_ids": approved_ids}))
    argv += ["--publication-selection", str(selection_path)]
    argv[argv.index("--expected-approval-sha256") + 1] = public.approval_set_digest(approved_ids)
    inputs = {name: path.read_bytes() for name, path in paths.items() if name not in {"consumer-scripts", "output", "baseline-output"}}
    assert public.main(argv) == 0
    asset = json.loads(paths["output"].read_bytes())
    assert len(asset["events"]) == count
    assert paths["baseline-output"].read_bytes() == bundle["baseline_bytes"]
    assert public.validate_public_package(paths["output"].parent,
        expected_approval_sha256=public.approval_set_digest(approved_ids))["day_count"] == count
    before = {name: (paths[name].read_bytes(), paths[name].stat().st_mtime_ns) for name in ("output", "baseline-output")}
    assert public.main(argv) == 0
    assert before == {name: (paths[name].read_bytes(), paths[name].stat().st_mtime_ns) for name in before}
    changed = sorted(bundle["snapshot"]["events"]["scheduleDays"])
    selection_path.write_bytes(ids.canonical_bytes({"schema_version": 1, "approved_ids": changed}))
    argv[argv.index("--expected-approval-sha256") + 1] = public.approval_set_digest(changed)
    with pytest.raises(ValueError, match="new reviewed output"):
        public.main(argv)
    assert before == {name: (paths[name].read_bytes(), paths[name].stat().st_mtime_ns) for name in before}
    assert inputs == {name: paths[name].read_bytes() for name in inputs}


def test_public_bytes_are_stable_across_process_hash_seeds(tmp_path, monkeypatch):
    next_id = iter(range(1, 10))
    monkeypatch.setattr(ids, "uuid4", lambda: UUID(int=next(next_id), version=4))
    source, registry, snapshot, _, _ = fixture()
    captured = tmp_path / "fictional-reviewed-inputs.json"
    captured.write_text(json.dumps(dict(source=source, registry=registry, snapshot=snapshot)))
    child = """
import json, sys
from test_public_schedule_days import build, public_row, policy
data = json.load(open(sys.argv[1]))
def project(rows, _):
    return [public_row(row) for row in rows[:-1]], policy(len(rows) - 1, 1)
result = build(data['source'], data['registry'], data['snapshot'], project)
print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
"""
    root = Path(__file__).resolve().parents[1]
    outputs = []
    for seed in (1, 2, 37):
        env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPATH=os.pathsep.join((str(root), str(root / "tests"))))
        outputs.append(subprocess.check_output([sys.executable, "-c", child, str(captured)], cwd=root, env=env))
    assert outputs[0] == outputs[1] == outputs[2]


@pytest.mark.parametrize("original", ["架空　題名\t Cafe\u0301", "架空😀公演" * 60])
def test_public_title_projection_keeps_the_complete_original_metadata(original):
    source, registry, snapshot, _, projector = fixture()
    asset = build(source, registry, snapshot, projector)
    row = asset["events"][0]
    metadata = asset["schedule_metadata"][row["event_uid"]]
    metadata["observedTitles"] = [original]
    row["title"] = public.normalized_title(original)[:180]
    before = deepcopy(asset)
    public.validate_public_asset(asset)
    assert asset == before
    assert metadata["observedTitles"] == [original]
    row["title"] = "未確認の別番組"
    with pytest.raises(ValueError, match="original observation"):
        public.validate_public_asset(asset)


@pytest.mark.parametrize("change", ["source", "consumer-hashes", "script", "baseline", "old-output", "old-baseline", "symlink", "in-place", "traversal"])
def test_cli_failure_never_changes_previous_output_or_input(tmp_path, monkeypatch, change):
    argv, bundle = write_cli_fixture(tmp_path)
    inject_cli_witness(monkeypatch, bundle)
    paths = bundle["paths"]
    public.main(argv)
    if change in {"source", "consumer-hashes", "baseline"}:
        target = paths[{"source": "private-asset", "consumer-hashes": "consumer-hashes", "baseline": "baseline"}[change]]
        target.write_bytes(target.read_bytes() + b" ")
    elif change == "script":
        (paths["consumer-scripts"] / public.CONSUMER_FILES[0]).write_text("# Unexpected captured code.\n")
    elif change in {"old-output", "old-baseline"}:
        paths[{"old-output": "output", "old-baseline": "baseline-output"}[change]].write_bytes(b"previous reviewed bytes")
    elif change == "symlink":
        paths["baseline-output"].unlink()
        paths["baseline-output"].symlink_to(paths["baseline"])
    elif change == "in-place":
        alias = paths["baseline"].parent / public.PUBLIC_BASELINE_FILENAME
        alias.hardlink_to(paths["baseline"])
        argv[argv.index("--baseline") + 1] = str(alias)
        argv[argv.index("--output") + 1] = str(alias.parent / public.PUBLIC_ASSET_FILENAME)
        argv[argv.index("--baseline-output") + 1] = str(alias)
    elif change == "traversal":
        argv[argv.index("--output") + 1] = str(paths["output"].parent / ".." / "distribution" / public.PUBLIC_ASSET_FILENAME)
    before = {name: path.read_bytes() for name, path in paths.items() if path.is_file()}
    with pytest.raises(ValueError):
        public.main(argv)
    assert before == {name: paths[name].read_bytes() for name in before}


def test_cli_pair_preflight_prevents_creation_when_second_output_differs(tmp_path, monkeypatch):
    argv, bundle = write_cli_fixture(tmp_path)
    inject_cli_witness(monkeypatch, bundle)
    bundle["paths"]["baseline-output"].write_bytes(b"previous reviewed baseline")
    with pytest.raises(ValueError, match="new reviewed output"):
        public.main(argv)
    assert not bundle["paths"]["output"].exists()
    assert bundle["paths"]["baseline-output"].read_bytes() == b"previous reviewed baseline"


def test_workflow_disabled_gate_keeps_explicit_assets_and_manifest_last():
    workflow = Path(".github/workflows/publish_external_events_assets.yml").read_text()
    assert "vars.PUBLIC_SCHEDULE_DAYS_ENABLED == 'true' && 'true' || 'false'" in workflow
    assert "--include-public-schedule-days" in workflow and "--require-public-schedule-days" in workflow
    upload = workflow.split("      - name: Upload release assets", 1)[1]
    assert upload.index("data/public_schedule_days.json") < upload.index("assets+=(data/manifest.json)")
    assert "private-data" not in upload and "identity_registry.json" not in upload
