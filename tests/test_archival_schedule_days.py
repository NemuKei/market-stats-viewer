"""Fictional day-schedule units, copied-registry identity and boundary checks."""

from copy import deepcopy
import pytest

from scripts import build_archival_schedule_days as days
from scripts import event_identity_registry as ids


def fixture():
    raw, inventory = [], []
    for i, (day, title, time, classification) in enumerate(
        [
            ("2026-03-04", "架空の同番組", "13:00", days.CANDIDATE),
            ("2026-03-04", "架空の同番組", "18:00", days.CANDIDATE),
            ("2026-03-04", "架空の別番組", "12:00", days.CANDIDATE),
            ("2026-03-05", "架空大会の日程", None, days.CANDIDATE),
            ("2026-03-06", "架空大会の日程", None, days.CANDIDATE),
            ("2026-03-07", "架空の矛盾候補", "13:00", "undecided"),
            (
                "2026-03-08",
                "【中止】架空予定",
                None,
                "cancellation_or_postponement_observation",
            ),
        ]
    ):
        r = {
            "venue_id": "fictional-hall",
            "venue_name": "架空ホール",
            "pref_name": "東京都",
            "title": title,
            "start_date": day,
            "end_date": None,
            "start_time": time,
            "status": "scheduled",
            "source_url": "https://venue.example.test/calendar",
            "updated_at_utc": "2026-02-01T00:00:00Z",
            "first_seen_at_utc": "2026-02-01T00:00:00Z",
        }
        uid = "fictional-source-" + str(i)
        ref = f"observation-{i:04d}"
        raw.append(
            {
                "source_uid": uid,
                "raw_observations": [
                    {"record": dict(r), "observed_at": "2026-02-02T09:00:00+09:00"}
                ],
            }
        )
        inventory.append(
            {
                "case_ref": f"case-{i:04d}",
                "classification": classification,
                "observation_refs": [ref],
                "source_uids": [uid],
                "reasons": [] if classification == days.CANDIDATE else ["held"],
                "cancellation_evidence": [],
                "proposed_schedule_fact": r,
                "proposed_canonical_venue": "架空ホール",
            }
        )
    return (
        inventory,
        raw,
        {
            "events": {
                "items": [
                    {"event_uid": "fictional-existing", "start_date": "2026-07-06"}
                ]
            }
        },
    )


def base_registry():
    row = {
        "event_uid": "fictional-existing",
        "source_id": "official_events",
        "source_record_id": "fictional-existing-source",
        "source_policy_status": "approved",
        "title": "架空既存公演",
        "venue_name": "架空ホール",
        "artist_name": "架空出演者",
        "start_date": "2026-07-06",
        "end_date": "2026-07-06",
        "start_time": "19:00",
    }
    b = ids.canonical_bytes(
        {
            "events": {
                "items": [row],
                "publicationPolicy": {
                    "status": "enforced",
                    "defaultDeny": True,
                    "publishedCount": 1,
                },
            }
        }
    )
    return ids.seed_registry(b, expected_sha256=ids.digest(b), expected_count=1)


def reviewed(registry, rows, *, kind="new", previous=None, version=2):
    return {
        "schema_version": version,
        "expected_revision": registry["revision"],
        "kind": kind,
        "previous_ids": previous or [],
        "candidates": [
            {
                "event_uid": (previous or [None])[0],
                "observation": ids.observation_from_row(r),
            }
            for r in rows
        ],
        "evidence": {
            "url": "https://venue.example.test/calendar",
            "reviewed_at_utc": "2026-10-11T06:45:00Z",
            "reason": "Fictional retained day observations, not confirmed performances.",
        },
    }


def test_day_grouping_keeps_all_sources_times_and_distinct_programs():
    inv, raw, baseline = fixture()
    rows, meta, plan = days.build_candidates(inv, raw, baseline)
    assert len(rows) == 4 and plan["retained_candidate_case_count"] == 5
    merged = next(r for r in rows if r["title"] == "架空の同番組")
    assert merged["event_start_time"] == "" and len(merged["supporting_sources"]) == 2
    assert meta[merged["event_key"]]["observedTimes"] == ["13:00", "18:00"]
    assert all(
        m["performanceCount"] is None and m["occurrenceCompleted"] == "unverified"
        for m in meta.values()
    )
    unknown = [r for r in rows if r["title"] == "架空大会の日程"]
    assert len(unknown) == 2  # Different observed days, not a claim about game count.
    assert all(meta[r["event_key"]]["hasUnknownTime"] for r in unknown)
    assert all(m["lastObservedAtUtc"].endswith("+00:00") for m in meta.values())
    reverse = days.build_candidates(list(reversed(inv)), raw, baseline)
    assert reverse[:2] == (rows, meta)
    assert (
        len({r["event_key"] for r in rows}) == 4
    )  # Shared calendar URL never merges another program.


@pytest.mark.parametrize(
    "change",
    [
        lambda inv, raw: inv[0]["proposed_schedule_fact"].update(end_date="2026-03-05"),
        lambda inv, raw: raw[0]["raw_observations"][0]["record"].update(
            title="【延期】架空の同番組"
        ),
        lambda inv, raw: inv[0]["reasons"].append("unresolved"),
        lambda inv, raw: inv.pop(),
        lambda inv, raw: inv[1]["observation_refs"].append("observation-0000"),
        lambda inv, raw: inv[0]["proposed_schedule_fact"].update(
            title="原本にない架空番組"
        ),
        lambda inv, raw: inv[0]["source_uids"].append("extra-invented-source"),
    ],
)
def test_unreviewed_ranges_cancellation_and_missing_provenance_stop(change):
    inv, raw, baseline = fixture()
    change(inv, raw)
    with pytest.raises(ValueError):
        days.build_candidates(inv, raw, baseline)


def test_typed_registry_preserves_legacy_fingerprints_and_allocates_once():
    inv, raw, baseline = fixture()
    rows, _, _ = days.build_candidates(inv, raw, baseline)
    registry = base_registry()
    before = deepcopy(registry)
    req = reviewed(registry, rows)
    updated = ids.apply_review(registry, req)
    assert registry == before
    assert updated["schema_version"] == 2
    assert updated["events"][0] == registry["events"][0]
    assert "record_kind" not in updated["events"][0]["observations"][0]["identity"]
    assert ids.apply_review(updated, req) == updated
    bound, held = ids.resolve_rows(rows, updated)
    again, held_again = ids.resolve_rows(list(reversed(rows)), updated)
    assert held == held_again == []
    assert {r["title"] + r["event_date"]: r["event_key"] for r in bound} == {
        r["title"] + r["event_date"]: r["event_key"] for r in again
    }


def test_cross_unit_id_inheritance_and_kind_downgrade_are_rejected():
    rows, _, _ = days.build_candidates(*fixture())
    base = base_registry()
    with pytest.raises(ValueError, match="cross-kind"):
        ids.apply_review(
            base,
            reviewed(
                base, rows[:1], kind="correction", previous=["fictional-existing"]
            ),
        )
    typed = ids.apply_review(base, reviewed(base, rows[:1]))
    uid = typed["events"][-1]["event_uid"]
    occurrence = dict(rows[0])
    occurrence.pop("record_kind")
    occurrence["event_key"] = "fictional-occurrence"
    with pytest.raises(ValueError, match="cross-kind"):
        ids.apply_review(
            typed, reviewed(typed, [occurrence], kind="correction", previous=[uid])
        )
    malformed = ids.observation_from_row(rows[0])
    malformed["identity"].pop("record_kind")
    malformed["fingerprint"] = ids.fingerprint(
        malformed["candidate_key"], malformed["identity"], malformed["source_records"]
    )
    with pytest.raises(ValueError, match="cannot be omitted"):
        ids.validate_observation(malformed)
    with pytest.raises(ValueError, match="schema v2"):
        ids.apply_review(base, reviewed(base, rows[:1], version=1))


def test_registered_source_requires_explicit_distinct_unit_acknowledgement():
    rows, _, _ = days.build_candidates(*fixture())
    rows[0]["supporting_sources"] = [
        {"source_id": "official_events", "record_id": "fictional-existing-source"}
    ]
    base = base_registry()
    req = reviewed(base, rows[:1])
    with pytest.raises(ValueError, match="shares registered sources"):
        ids.apply_review(base, req)
    req["acknowledged_related_event_uids"] = ["fictional-existing"]
    updated = ids.apply_review(base, req)
    assert updated["events"][0] == base["events"][0]


@pytest.mark.parametrize(
    "left,right",
    [
        ("AB C", "A BC"),
        ("昼公演", "夜公演"),
        ("第1回", "第2回"),
        ("①", "1"),
        ("Program A", "Program a"),
        ("A-B", "AB"),
    ],
)
def test_title_normalization_retains_meaningful_program_differences(left, right):
    assert days.normalized_title(left) != days.normalized_title(right)
    assert days.normalized_title("  AB\t C  ") == "AB C"


def test_legacy_candidate_key_collision_holds_distinct_programs():
    inv, raw, baseline = fixture()
    for i, title in enumerate(["AB C", "A BC"]):
        inv[i]["proposed_schedule_fact"]["title"] = title
        raw[i]["raw_observations"][0]["record"]["title"] = title
    with pytest.raises(ValueError, match="distinct program titles collide"):
        days.build_candidates(inv, raw, baseline)


def test_original_title_versions_and_venue_section_are_preserved():
    inv, raw, baseline = fixture()
    version = deepcopy(raw[0]["raw_observations"][0])
    version["record"].update(title="架空旧題名・別副題", description="会場タイプ:けやきひろば", venue_name="架空旧会場表記")
    raw[0]["raw_observations"].append(version)
    rows, meta, plan = days.build_candidates(inv, raw, baseline)
    row = next(r for r in rows if r["title"] == "架空の同番組")
    assert meta[row["event_key"]]["observedTitles"] == ["架空の同番組", "架空旧題名・別副題"]
    assert meta[row["event_key"]]["venueNotes"] == ["原本の会場区分: けやきひろば"]
    assert meta[row["event_key"]]["historicalVenueNames"] == ["架空ホール", "架空旧会場表記"]
    group = next(g for g in plan["private_groups"] if g["candidate_key"] == row["event_key"])
    assert version in group["original_observations"]


def test_registry_loader_rejects_cross_kind_history_even_if_inactive():
    rows, _, _ = days.build_candidates(*fixture())
    registry = ids.apply_review(base_registry(), reviewed(base_registry(), rows[:1]))
    day = deepcopy(registry["events"][-1]["observations"][0])
    day["active"] = False
    registry["events"][0]["observations"].append(day)
    with pytest.raises(ValueError, match="cross-kind"):
        ids.validate_registry(registry)


def test_registry_loader_rejects_cross_kind_split_with_new_ids():
    rows, _, _ = days.build_candidates(*fixture())
    base = base_registry()
    req = reviewed(base, rows[:2], kind="split", previous=["fictional-existing"])
    for candidate in req["candidates"]:
        candidate["event_uid"] = None
    with pytest.raises(ValueError, match="cross-kind"):
        ids.apply_review(base, req)
    edited = ids.apply_review(base, reviewed(base, rows[:2]))
    edited["relations"][-1].update(kind="split", previous_ids=["fictional-existing"])
    edited["events"][0]["observations"][0]["active"] = False
    with pytest.raises(ValueError, match="cross-kind"):
        ids.validate_registry(edited)


def test_asset_rejects_registry_mismatch_and_invalid_day_metadata():
    rows, meta, _ = days.build_candidates(*fixture())
    registry = ids.apply_review(base_registry(), reviewed(base_registry(), rows))
    bound, _ = ids.resolve_rows(rows, registry)
    mapped = {
        o["candidate_key"]: e["event_uid"]
        for e in registry["events"]
        for o in e["observations"]
        if o["active"]
    }
    asset = dict(
        schema_version=1,
        dataset="preserved_schedule_days",
        generated_at_utc="2026-10-11T06:00:00Z",
        baseline_sha256="a" * 64,
        input_sha256=dict(inventory="b" * 64, raw_observations="c" * 64),
        identity_registry=dict(
            schema_version=2, revision=registry["revision"], sha256="d" * 64
        ),
        events=bound,
        schedule_metadata={mapped[k]: v for k, v in meta.items()},
    )
    days.validate_asset(asset, registry, "d" * 64)
    uid = bound[0]["event_key"]
    for mutate in [
        lambda p: p["identity_registry"].update(revision=999),
        lambda p: p["identity_registry"].update(sha256="e" * 64),
        lambda p: p["schedule_metadata"][uid].update(observedTimes=["not-a-time"]),
        lambda p: p["schedule_metadata"][uid].update(hasUnknownTime="yes"),
        lambda p: p["schedule_metadata"][uid].update(
            evidenceBasis="confirmed_performance"
        ),
        lambda p: p["schedule_metadata"][uid].update(
            lastObservedAtUtc="2026-02-01T09:00:00+09:00"
        ),
    ]:
        malformed = deepcopy(asset)
        mutate(malformed)
        with pytest.raises(ValueError):
            days.validate_asset(malformed, registry, "d" * 64)


def test_private_output_guards_run_before_any_write(tmp_path):
    root = tmp_path.resolve()
    input_file = root / "baseline.json"
    input_file.write_text("original")
    output = root / "private-data"
    days.validate_preview_paths(root, output, [input_file])
    assert not output.exists()
    with pytest.raises(ValueError, match="private-data"):
        days.validate_preview_paths(root, root / "data", [input_file])
    output.mkdir()
    colliding = output / "lp_schedule_days.json"
    colliding.write_text("original")
    with pytest.raises(ValueError, match="collides"):
        days.validate_preview_paths(root, output, [colliding])
    link = output / "preview-identity-registry.json"
    link.symlink_to(input_file)
    with pytest.raises(ValueError, match="symlinks"):
        days.validate_preview_paths(root, output, [input_file])
    assert input_file.read_text() == colliding.read_text() == "original"


def test_original_repository_subdirectory_cannot_be_a_preview_root(tmp_path):
    root = tmp_path.resolve()
    (root / ".git").mkdir()
    data = root / "data"
    data.mkdir()
    source = data / "registry.json"
    source.write_text("original")
    with pytest.raises(ValueError, match="non-repository"):
        days.validate_preview_paths(data, data / "private-data", [source])


def test_cli_repeat_keeps_reviewed_bytes_and_refuses_changed_inputs(tmp_path, monkeypatch):
    import sys
    inventory, raw, baseline = fixture()
    root = tmp_path.resolve()
    values = {"inventory.json": inventory, "raw.json": raw, "baseline.json": baseline,
        "base-registry.json": base_registry(), "evidence.json": reviewed(base_registry(), [])["evidence"]}
    for name, value in values.items():
        (root / name).write_bytes(ids.canonical_bytes(value))
    args = ["build_archival_schedule_days", "--preview-root", str(root), "--output-dir", str(root / "private-data"),
        "--inventory", str(root / "inventory.json"), "--expected-inventory-sha256", ids.digest((root / "inventory.json").read_bytes()),
        "--raw-observations", str(root / "raw.json"), "--expected-raw-sha256", ids.digest((root / "raw.json").read_bytes()),
        "--baseline", str(root / "baseline.json"), "--base-registry", str(root / "base-registry.json"), "--review-evidence", str(root / "evidence.json")]
    monkeypatch.setattr(sys, "argv", args)
    assert days.main() == 0
    outputs = list((root / "private-data").glob("*.json"))
    assert len(outputs) == 4
    before = {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in outputs}
    assert days.main() == 0
    assert before == {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in outputs}
    baseline["events"]["items"][0]["start_date"] = "2026-07-07"
    (root / "baseline.json").write_bytes(ids.canonical_bytes(baseline))
    with pytest.raises(ValueError, match="reviewed preview outputs differ"):
        days.main()
    assert before == {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in outputs}


def test_source_timestamps_are_compared_as_instants_and_require_timezone():
    inventory, raw, baseline = fixture()
    version = deepcopy(raw[0]["raw_observations"][0])
    version["record"].update(first_seen_at_utc="2026-02-01T00:00:00.100000Z", updated_at_utc="2026-02-01T00:00:00.100000Z")
    raw[0]["raw_observations"].append(version)
    rows, metadata, _ = days.build_candidates(inventory, raw, baseline)
    same = next(r for r in rows if r["title"] == "架空の同番組")
    assert same["first_seen_at_utc"] == "2026-02-01T00:00:00Z"
    assert same["updated_at_utc"] == "2026-02-01T00:00:00.100000Z"
    assert metadata[same["event_key"]]["lastObservedAtUtc"] == "2026-02-02T00:00:00+00:00"
    version["observed_at"] = "2026-02-02T09:00:00"
    with pytest.raises(ValueError, match="timezone"):
        days.build_candidates(inventory, raw, baseline)


def test_metadata_retains_exact_space_variants_and_fullwidth_venue_note():
    inventory, raw, baseline = fixture()
    version = deepcopy(raw[0]["raw_observations"][0])
    version["record"].update(title=" 架空の同番組 ", description="会場タイプ：架空広場")
    raw[0]["raw_observations"].append(version)
    rows, metadata, _ = days.build_candidates(inventory, raw, baseline)
    row = next(r for r in rows if r["title"] == "架空の同番組")
    assert metadata[row["event_key"]]["observedTitles"] == [" 架空の同番組 ", "架空の同番組"]
    assert metadata[row["event_key"]]["venueNotes"] == ["原本の会場区分: 架空広場"]


def test_archival_categories_use_shared_rules_without_changing_units():
    inv, raw, baseline = fixture()
    rows, meta, _ = days.build_candidates(inv, raw, baseline)
    by_title = {r['title']: r for r in rows}
    assert by_title['架空の同番組']['event_category'] == '未分類'
    assert by_title['架空大会の日程']['event_category'] == 'その他'
    assert all(r['artist_name'] == '' and r['record_kind'] == 'schedule_day' for r in rows)
    assert all(m['performanceCount'] is None for m in meta.values())
