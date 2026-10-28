"""CLI bundle integrity checks using local Git repos and fictional official pages."""
from copy import deepcopy
from datetime import date
import json
import shutil
import subprocess

import pytest

from scripts import build_lp_events as builder
from scripts import event_identity_registry as ids
from scripts import review_new_events as review
from test_review_new_events import NOW, baseline, evidence_for, page, payload, row, seed


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")


def command(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root, *paths):
    command(root, "add", *paths)
    command(root, "-c", "user.name=Fictional test", "-c", "user.email=fixture@users.noreply.github.com", "commit", "-qm", "fictional fixture")


@pytest.fixture
def cli(tmp_path, monkeypatch):
    source, consumer, private = [tmp_path / p for p in ("source", "consumer", "private")]
    source.mkdir()
    consumer.mkdir()
    private.mkdir()
    for root in (source, consumer):
        command(root, "init", "-q", "-b", "main")
        command(root, "remote", "add", "origin", str(root))
    registry = seed()
    original = payload([row("SEED"), row("A")])
    state = review.initial_state(original, registry, now="2026-10-28T10:00:00Z", source_sha="a" * 40)
    current = payload([row("SEED"), row("A"), row("B", first_seen_at_utc="2026-10-28T10:30:00Z")])
    data = {"payload": current, "fetches": 0, "now": NOW, "evidence_at": NOW,
        "on_fetch": None, "on_ingestion": None}
    for path, value in {"data/event_identity_registry.json": registry, "data/lp_events.json": baseline(current, registry),
            "data/new_event_review_state.json": state}.items():
        put(source / path, value)
    (source / "scripts").mkdir()
    (source / "scripts/review_new_events.py").write_text("# fictional entrypoint\n")
    (source / "data/events.sqlite").write_bytes(b"fictional database pin")
    commit(source, "data/event_identity_registry.json", "data/lp_events.json", "data/new_event_review_state.json", "data/events.sqlite", "scripts/review_new_events.py")
    for name in review.CONSUMER_FILES:
        target = consumer / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}" if name.endswith(".json") else "# fictional helper\n")
    put(consumer / "02_Service/web_lp/data/events.json", {})
    commit(consumer, *review.CONSUMER_FILES, "02_Service/web_lp/data/events.json")
    real_load = ids.load_registry
    monkeypatch.setattr(ids, "load_registry", lambda path=source / "data/event_identity_registry.json": real_load(path))
    monkeypatch.setattr(review, "ROOT", source)
    monkeypatch.setattr(review, "now_z", lambda: data["now"])
    monkeypatch.setattr(builder, "_build_lp_event_candidates", lambda **_: deepcopy(data["payload"]))
    monkeypatch.setattr(review, "consumer_context", lambda p, _: ({r["event_key"] for r in p["events"]}, []))
    receipt = {"run_id": 123, "head_sha": "a" * 40, "completed_at_utc": NOW, "inbox_sha256": "b" * 64}
    def fake_ingestion(*_):
        if data["on_ingestion"]:
            data["on_ingestion"]()
        return receipt
    monkeypatch.setattr(review, "read_ingestion", fake_ingestion)
    live_pages = {}
    def add_pages(p):
        for r in p["events"]:
            h = ids.observation_from_row(r)
            e = evidence_for(h)
            live_pages[e["url"]] = page(e)
    add_pages(current)
    real_verify = review.verify_evidence
    def fake_fetch(url):
        data["fetches"] += 1
        if data["on_fetch"]:
            data["on_fetch"]()
        return live_pages[url]
    monkeypatch.setattr(review, "verify_evidence", lambda r, h, e, *, now, fetch=None: real_verify(r, h, e, now=now, fetch=fake_fetch))

    def prepare(name, cohort="backlog"):
        target = private / name
        review.main(["prepare", "--state", str(source / "data/new_event_review_state.json"), "--consumer-repo", str(consumer),
            "--cohort", cohort, "--ingestion-run-id", "123", "--output", str(target)])
        return target

    def stage(target):
        plan = json.loads((target / "plan.json").read_bytes())
        evidence = [evidence_for(h) for h in plan["eligible"]]
        for e in evidence:
            e["reviewed_at_utc"] = data["evidence_at"]
        epath = private / (target.name + "-evidence.json")
        put(epath, evidence)
        review.main(["stage", "--prepared", str(target), "--evidence", str(epath)])

    def approval(target):
        plan = json.loads((target / "plan.json").read_bytes())
        root = target / "staged"
        requests = json.loads((root / "requests.json").read_bytes())["requests"]
        value = {"schema_version": 1, "reviewer_role": "independent_reviewer", "plan_sha256": ids.digest(ids.canonical_bytes(plan)),
            "bundle_sha256": review.bundle_hashes(root), "reviewed_at_utc": data["now"],
            "findings": [{"fingerprint": q["candidates"][0]["observation"]["fingerprint"], "url": q["evidence"]["url"],
                "same_occurrence_confirmed": True, "not_existing_identity_change_confirmed": True,
                "cancellation_status": "not_cancelled_or_postponed", "reason": "Fictional independent occurrence, existing identity and cancellation check."} for q in requests]}
        path = private / (target.name + "-independent.json")
        put(path, value)
        return path

    def audit(target, approval_path=None):
        return review.main(["audit", "--prepared", str(target), "--independent-review", str(approval_path or approval(target))])

    def install_history():
        old = builder.assemble_lp_payload([row("SEED"), row("P")], as_of_date=date(2026, 10, 27))
        past = "2026-10-27T11:00:00Z"
        state0 = review.initial_state(old, registry, now="2026-10-27T10:00:00Z", source_sha="a" * 40)
        plan = review.prepare(old, registry, state0, now=past)
        evidence = [evidence_for(h) for h in plan["eligible"]]
        for e in evidence:
            e["reviewed_at_utc"] = past
        add_pages(old)
        result = review.stage(old, registry, plan, evidence, public_baseline=baseline(old, registry), now=past)
        data["payload"] = payload([row("SEED"), row("P"), row("A"), row("B", first_seen_at_utc="2026-10-28T10:30:00Z")])
        add_pages(data["payload"])
        put(source / "data/event_identity_registry.json", result["registry"])
        put(source / "data/lp_events.json", baseline(data["payload"], result["registry"]))
        put(source / "data/new_event_review_state.json", result["state"])
        commit(source, "data/event_identity_registry.json", "data/lp_events.json", "data/new_event_review_state.json")

    return dict(source=source, consumer=consumer, private=private, data=data, prepare=prepare, stage=stage,
        approval=approval, audit=audit, install_history=install_history)


def test_cli_prepare_stage_audit_reloads_evidence_and_replays_requests(cli):
    target = cli["prepare"]("valid")
    cli["stage"](target)
    assert cli["data"]["fetches"] == 1
    assert cli["audit"](target) == 0
    assert cli["data"]["fetches"] == 2
    assert command(cli["source"], "status", "--porcelain") == ""
    assert command(cli["consumer"], "status", "--porcelain") == ""


def test_cli_rejects_another_cohort_even_if_report_plan_hash_is_rebound(cli):
    backlog, daily = cli["prepare"]("backlog"), cli["prepare"]("daily", "daily")
    cli["stage"](backlog)
    cli["stage"](daily)
    for name in review.BUNDLE_FILES:
        shutil.copyfile(daily / "staged" / name, backlog / "staged" / name)
    report_path = backlog / "staged/report.json"
    report = json.loads(report_path.read_bytes())
    report["plan_sha256"] = ids.digest(ids.canonical_bytes(json.loads((backlog / "plan.json").read_bytes())))
    put(report_path, report)
    with pytest.raises(ValueError, match="other-cohort|prepared eligible"):
        cli["audit"](backlog)


def test_cli_rejects_self_consistent_retiming_of_past_quota(cli):
    cli["install_history"]()
    target = cli["prepare"]("history")
    cli["stage"](target)
    path = target / "staged/new_event_review_state.json"
    state = json.loads(path.read_bytes())
    state["batches"][0]["day_jst"] = "2026-10-26"
    state["batches"][0]["staged_at_utc"] = "2026-10-26T11:00:00Z"
    registry = ids.parse_json((target / "staged/event_identity_registry.json").read_bytes())
    review.validate_state(state, registry)  # Self-consistency alone used to pass.
    put(path, state)
    with pytest.raises(ValueError, match="prior history/quota"):
        cli["audit"](target)


def test_cli_stage_checks_saved_public_lp_instead_of_recomputed_source_baseline(cli):
    cli["data"]["payload"] = payload([row("A"), row("B", first_seen_at_utc="2026-10-28T10:30:00Z")])
    target = cli["prepare"]("source-withdrawal")
    with pytest.raises(ValueError, match="strictly additive"):
        cli["stage"](target)
    assert not (target / "staged").exists()


def test_cli_audit_independently_rejects_a_source_only_stage_that_drops_public_rows(cli):
    cli["data"]["payload"] = payload([row("A"), row("B", first_seen_at_utc="2026-10-28T10:30:00Z")])
    target = cli["prepare"]("bad-stage")
    plan = json.loads((target / "plan.json").read_bytes())
    registry = ids.parse_json((target / "registry-before.json").read_bytes())
    p = cli["data"]["payload"]
    evidence = [evidence_for(h) for h in plan["eligible"]]
    # Reproduce a forged/old source-only stage without using the protected CLI.
    result = review.stage(p, registry, plan, evidence, public_baseline=baseline(p, registry), now=NOW)
    root = target / "staged"
    for name, value in {"event_identity_registry.json": result["registry"], "lp_events.json": result["lp"],
            "new_event_review_state.json": result["state"], "report.json": result["report"],
            "requests.json": {"requests": result["requests"]}, "official-evidence.json": {"evidence": evidence}}.items():
        put(root / name, value)
    with pytest.raises(ValueError, match="strictly additive"):
        cli["audit"](target)


def test_cli_stage_refuses_db_changes_after_prepare(cli):
    target = cli["prepare"]("changed-input")
    (cli["source"] / "data/events.sqlite").write_bytes(b"concurrent DB update")
    with pytest.raises(ValueError, match="MSV checkout must be clean"):
        cli["stage"](target)
    assert not (target / "staged").exists()


@pytest.mark.parametrize("name", ["requests.json", "official-evidence.json"])
def test_cli_audit_requires_private_request_and_raw_context_files(cli, name):
    target = cli["prepare"]("missing")
    cli["stage"](target)
    approval = cli["approval"](target)
    (target / "staged" / name).unlink()
    with pytest.raises(FileNotFoundError):
        cli["audit"](target, approval)


def test_cli_audit_detects_context_changed_after_verification(cli):
    target = cli["prepare"]("context")
    cli["stage"](target)
    path = target / "staged/official-evidence.json"
    value = json.loads(path.read_bytes())
    value["evidence"][0]["context"] += " never retrieved"
    put(path, value)
    with pytest.raises(ValueError, match="exact prepared observation/official evidence"):
        cli["audit"](target)


def test_cli_audit_reads_and_checks_the_exact_request_bytes(cli):
    target = cli["prepare"]("request")
    cli["stage"](target)
    path = target / "staged/requests.json"
    value = json.loads(path.read_bytes())
    value["requests"][0]["expected_revision"] += 1
    put(path, value)
    with pytest.raises(ValueError, match="exact prepared observation/official evidence"):
        cli["audit"](target)


@pytest.mark.parametrize("root_name,relative", [
    ("source", "data/events.sqlite"), ("source", "scripts/review_new_events.py"),
    ("source", "data/new_event_review_state.json"),
    ("consumer", "docs/operations/public-event-source-policy.json"),
    ("consumer", "02_Service/web_lp/scripts/event_source_policy.py"),
    ("source", "unrelated-untracked.txt"),
])
def test_cli_prepare_refuses_dirty_db_policy_script_or_untracked_work(cli, root_name, relative):
    path = cli[root_name] / relative
    path.write_text("dirty unpublished fixture")
    with pytest.raises(ValueError, match="checkout must be clean"):
        cli["prepare"]("dirty")
    assert not (cli["private"] / "dirty").exists()
    assert cli["data"]["fetches"] == 0


def test_cli_private_state_is_an_explicit_dry_run_exception_only(cli):
    state = cli["private"] / "private-state.json"
    shutil.copyfile(cli["source"] / "data/new_event_review_state.json", state)
    target = cli["private"] / "private-state-run"
    review.main(["prepare", "--state", str(state), "--consumer-repo", str(cli["consumer"]),
        "--cohort", "backlog", "--ingestion-run-id", "123", "--output", str(target)])
    cli["stage"](target)
    with pytest.raises(ValueError, match="committed canonical review state"):
        cli["audit"](target)


@pytest.mark.parametrize("field,value", [("same_occurrence_confirmed", False), ("cancellation_status", "cancelled")])
def test_cli_audit_requires_independent_occurrence_and_cancellation_checks(cli, field, value):
    target = cli["prepare"]("semantic")
    cli["stage"](target)
    path = cli["approval"](target)
    approval = json.loads(path.read_bytes())
    approval["findings"][0][field] = value
    put(path, approval)
    with pytest.raises(ValueError, match="occurrence/cancellation check"):
        cli["audit"](target, path)


@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_cli_audit_requires_explicit_independent_not_existing_identity_change_confirmation(cli, value):
    target = cli["prepare"]("newness")
    cli["stage"](target)
    path = cli["approval"](target)
    approval = json.loads(path.read_bytes())
    finding = approval["findings"][0]
    if value is not None:
        finding["not_existing_identity_change_confirmed"] = value
    else:
        finding.pop("not_existing_identity_change_confirmed", None)
    put(path, approval)
    with pytest.raises(ValueError, match="existing identity|new occurrence"):
        cli["audit"](target, path)


def test_cli_prepare_and_stage_reject_time_changed_new_source_evidence(cli):
    changed = row("SEED", record_id="different-official-record", event_start_time="20:00",
        title="架空公演SEED 夜公演")
    cli["data"]["payload"] = payload([row("SEED"), changed, row("A")])
    target = cli["prepare"]("time-conflict")
    plan = json.loads((target / "plan.json").read_bytes())
    _, held = ids.resolve_rows(cli["data"]["payload"]["events"], seed())
    h = next(h for h in held if h["identity"]["event_start_time"] == "20:00")
    assert h["reason"] == "unregistered_candidate" and h["related_event_uids"] == []
    assert h["fingerprint"] not in {e["fingerprint"] for e in plan["eligible"]}
    assert {"fingerprint": h["fingerprint"], "reason": "possible_existing_correction_or_multiple_performances"} in plan["deferred"]
    evidence = cli["private"] / "time-conflict-evidence.json"
    put(evidence, [evidence_for(h)])
    with pytest.raises(ValueError, match="non-new, related, duplicate"):
        review.main(["stage", "--prepared", str(target), "--evidence", str(evidence)])
    assert not (target / "staged").exists()


def test_cli_audit_rejects_independent_findings_from_another_bundle(cli):
    target = cli["prepare"]("old-review")
    cli["stage"](target)
    path = cli["approval"](target)
    value = json.loads(path.read_bytes())
    value["bundle_sha256"]["official-evidence.json"] = "0" * 64
    put(path, value)
    with pytest.raises(ValueError, match="another plan/staged bundle"):
        cli["audit"](target, path)


EXPIRING_FETCHES = [
    ("2026-10-28T14:59:50Z", NOW, "2026-10-28T15:00:10Z", "crossed JST"),
    (NOW, NOW, "2026-10-28T12:00:01Z", "prepared review expired"),
    (NOW, "2026-10-28T05:00:01Z", "2026-10-28T11:00:02Z", "official review expired"),
]


@pytest.mark.parametrize("start,evidence_at,end,message", EXPIRING_FETCHES)
def test_cli_stage_rechecks_real_clock_after_official_fetch_before_writing(cli, capsys, start, evidence_at, end, message):
    cli["data"].update(now=start, evidence_at=evidence_at)
    target = cli["prepare"]("stage-expiry")
    capsys.readouterr()
    cli["data"]["on_fetch"] = lambda: cli["data"].update(now=end)
    with pytest.raises(ValueError, match=message):
        cli["stage"](target)
    assert not (target / "staged").exists()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("start,evidence_at,end,message", EXPIRING_FETCHES)
def test_cli_audit_rechecks_real_clock_after_official_fetch_before_success(cli, capsys, start, evidence_at, end, message):
    cli["data"].update(now=start, evidence_at=evidence_at)
    target = cli["prepare"]("audit-expiry")
    cli["stage"](target)
    approval = cli["approval"](target)
    capsys.readouterr()
    cli["data"]["on_fetch"] = lambda: cli["data"].update(now=end)
    with pytest.raises(ValueError, match=message):
        cli["audit"](target, approval)
    assert '"audit": "passed"' not in capsys.readouterr().out


@pytest.mark.parametrize("phase", ["ingestion", "remote"])
def test_cli_audit_deadline_is_checked_after_late_external_lookups(cli, monkeypatch, capsys, phase):
    target = cli["prepare"]("lookup-expiry")
    cli["stage"](target)
    approval = cli["approval"](target)
    capsys.readouterr()
    def expire():
        cli["data"]["now"] = "2026-10-28T12:00:01Z"
    if phase == "ingestion":
        cli["data"]["on_ingestion"] = expire
    else:
        real_git = review.git
        def git(*args):
            result = real_git(*args)
            if args[0] == "ls-remote":
                expire()
            return result
        monkeypatch.setattr(review, "git", git)
    with pytest.raises(ValueError, match="prepared review expired"):
        cli["audit"](target, approval)
    assert '"audit": "passed"' not in capsys.readouterr().out


def test_cli_stage_checks_the_clock_again_after_private_writes(cli, monkeypatch, capsys):
    cli["data"]["now"] = "2026-10-28T14:59:50Z"
    target = cli["prepare"]("write-expiry")
    capsys.readouterr()
    real_write = review.write_json
    def write(path, value):
        real_write(path, value)
        cli["data"]["now"] = "2026-10-28T15:00:10Z"
    monkeypatch.setattr(review, "write_json", write)
    with pytest.raises(ValueError, match="crossed JST"):
        cli["stage"](target)
    assert capsys.readouterr().out == ""


def test_cli_prepare_rejects_a_receipt_lookup_that_outlasts_the_plan(cli):
    cli["data"]["on_ingestion"] = lambda: cli["data"].update(now="2026-10-28T12:00:01Z")
    with pytest.raises(ValueError, match="prepared review expired"):
        cli["prepare"]("prepare-expiry")
    assert not (cli["private"] / "prepare-expiry").exists()


def test_cli_within_deadline_uses_completion_time_for_the_new_batch(cli):
    target = cli["prepare"]("slow-valid")
    cli["data"]["on_fetch"] = lambda: cli["data"].update(now="2026-10-28T11:02:00Z")
    cli["stage"](target)
    state = json.loads((target / "staged/new_event_review_state.json").read_bytes())
    assert state["batches"][-1]["staged_at_utc"] == "2026-10-28T11:02:00Z"
    assert cli["audit"](target) == 0
