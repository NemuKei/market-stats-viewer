import copy
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.apply_venue_discovery_inbox import (
    MAX_CANDIDATES,
    MAX_DEFERRED,
    InboxSchemaError,
    empty_backlog,
    main,
    run_with_backlog,
)
from scripts.check_automation_freshness import check_backlog
from tests.test_apply_venue_discovery_inbox import ARTIST_MAPS, CONFIG, VENUE_MAPS, cand

OSAKA = {"venue_id": "kyocera_dome", "venue_name": "京セラドーム大阪", "aliases": ["京セラドーム大阪"]}
TWO_VENUES = {**CONFIG, "watch_venues": [*CONFIG["watch_venues"], OSAKA]}
from scripts.signals.entity_aliases import _build_lookup_maps  # noqa: E402

TWO_VENUE_MAPS = _build_lookup_maps([("東京ドーム", ("東京ドーム", "Tokyo Dome")),
                                     ("京セラドーム大阪", ("京セラドーム大阪",))])


def game(i, venue="東京ドーム"):
    # Baseball-style rows: one per date, no published start time.
    row = cand(event_start_date=f"2027-{7 + i // 28:02d}-{1 + i % 28:02d}", artist_name="中日ドラゴンズ",
               title=f"中日 vs 対戦{i}", venue_name=venue, evidence_snippet=f"試合 {i}")
    return row


def inbox(run_at, candidates=(), deferred=()):
    data = {"schema_version": 1, "run_at_utc": run_at, "automation_id": "msv-venue-discovery",
            "candidates": list(candidates), "rejected": []}
    if deferred:
        data["deferred_candidates"] = list(deferred)
    return data


def step(ib, config, backlog, now="2026-11-15T04:35:00Z", maps=VENUE_MAPS):
    return run_with_backlog(ib, config, backlog, venue_maps=maps, artist_maps=ARTIST_MAPS, now=now)


def test_61_rows_drain_30_30_1_without_losing_any():
    games = [game(i) for i in range(61)]
    ib = inbox("2026-11-14T03:12:29Z", games[:30], games[30:])
    config, backlog = CONFIG, empty_backlog()
    applied, remaining = [], []
    for _ in range(4):
        run = step(ib, config, backlog)  # the daily cron re-reads the same inbox
        config, backlog = run.config, run.backlog
        applied.append(run.process["applied"])
        remaining.append(backlog["pending_count"])
    assert applied == [30, 30, 1, 0]
    assert remaining == [31, 1, 0, 0]
    dates = sorted(e["event_start_date"] for e in config["confirmed_events"])
    assert dates == sorted(g["event_start_date"] for g in games)
    assert all("event_start_time" not in e for e in config["confirmed_events"])


def test_pending_rows_survive_a_later_inbox_that_no_longer_lists_them():
    games = [game(i) for i in range(45)]
    first = step(inbox("2026-11-14T03:00:00Z", games[:30], games[30:]), CONFIG, empty_backlog())
    assert first.backlog["pending_count"] == 15
    second = step(inbox("2026-11-15T03:00:00Z", [game(50)]), first.config, first.backlog)
    assert second.ingest["status"] == "ingested"
    # 15 old rows are applied before the newly found one; nothing is dropped.
    assert [s["title"] for s in second.process["settled"]] == [g["title"] for g in games[30:]] + ["中日 vs 対戦50"]
    assert second.backlog["pending_count"] == 0


def test_rerun_after_midway_failure_does_not_duplicate():
    games = [game(i) for i in range(40)]
    ib = inbox("2026-11-14T03:00:00Z", games[:30], games[30:])
    first = step(ib, CONFIG, empty_backlog())
    # The job failed before commit: config written by a partial run but backlog not saved.
    replay = step(ib, first.config, empty_backlog())
    assert len(replay.ingest["duplicates"]) == 30
    assert {d["reason"] for d in replay.ingest["duplicates"]} == {"already_confirmed"}
    assert replay.process["applied"] == 10  # only the still-unapplied deferred rows
    after = step(ib, replay.config, replay.backlog)
    assert after.ingest["status"] == "already_ingested" and after.process["processed"] == 0
    keys = [(e["event_start_date"], e["venue_name"]) for e in after.config["confirmed_events"]]
    assert len(keys) == len(set(keys)) == 40


def test_relisted_pending_row_takes_corrected_evidence_and_keeps_position():
    games = [game(i) for i in range(32)]
    first = step(inbox("2026-11-14T03:00:00Z", games[:30], games[30:]), CONFIG, empty_backlog())
    seqs = [p["seq"] for p in first.backlog["pending"]]
    fixed = dict(games[31], evidence_url="https://www.tokyo-dome.co.jp/event/fixed")
    second_inbox = inbox("2026-11-15T03:00:00Z", [fixed, game(40)])
    ingest_only = step(second_inbox, first.config, first.backlog)
    assert [u["title"] for u in ingest_only.ingest["updated"]] == [games[31]["title"]]
    settled = ingest_only.process["settled"]
    assert [s["seq"] for s in settled[:2]] == seqs
    stored = next(e for e in ingest_only.config["confirmed_events"] if e["title"] == games[31]["title"])
    assert stored["evidence_url"].endswith("/fixed")


def test_row_ingested_elsewhere_while_pending_is_settled_with_reason():
    games = [game(i) for i in range(31)]
    first = step(inbox("2026-11-14T03:00:00Z", games[:30], games[30:]), CONFIG, empty_backlog())
    config = copy.deepcopy(first.config)
    config["confirmed_events"].append({**games[30], "event_id": "manual-1"})
    second = step(None, config, first.backlog)
    assert second.process["settled"][0]["outcome"] == "duplicate"
    assert second.process["settled"][0]["matched_event_ids"] == ["manual-1"]
    assert second.backlog["pending_count"] == 0


def test_multiple_venues_are_processed_in_detection_order():
    tokyo = [game(i) for i in range(40)]
    osaka = [game(i, venue="京セラドーム大阪") for i in range(5)]
    first = step(inbox("2026-11-14T03:00:00Z", tokyo[:30], tokyo[30:]), TWO_VENUES, empty_backlog(),
                 maps=TWO_VENUE_MAPS)
    second = step(inbox("2026-11-15T03:00:00Z", osaka), first.config, first.backlog, maps=TWO_VENUE_MAPS)
    venues = [p["venue_name"] for p in second.config["confirmed_events"][30:]]
    assert venues == ["東京ドーム"] * 10 + ["京セラドーム大阪"] * 5
    assert second.backlog["pending_count"] == 0


def test_same_inbox_same_day_with_two_start_times_is_held_for_review():
    ib = inbox("2026-11-14T03:00:00Z", [cand(event_start_time="13:00"), cand(event_start_time="18:00")])
    run = step(ib, CONFIG, empty_backlog())
    assert run.ingest["rejected"][0]["reason"] == "same_day_multiple_start_times_requires_review"
    assert run.process["applied"] == 1


def test_no_change_run_leaves_backlog_identical():
    run = step(inbox("2026-11-14T03:00:00Z", [game(1)]), CONFIG, empty_backlog())
    again = step(inbox("2026-11-14T03:00:00Z", [game(1)]), run.config, run.backlog)
    assert again.ingest["status"] == "already_ingested"
    assert again.backlog == run.backlog


def test_deferred_schema_limits():
    with pytest.raises(InboxSchemaError):
        step(inbox("2026-11-14T03:00:00Z", [], [game(0)] * (MAX_DEFERRED + 1)), CONFIG, empty_backlog())
    bad = inbox("2026-11-14T03:00:00Z")
    bad["deferred_candidates"] = "x"
    with pytest.raises(InboxSchemaError):
        step(bad, CONFIG, empty_backlog())
    with pytest.raises(InboxSchemaError):
        step(inbox("2026-11-14T03:00:00Z", [game(i) for i in range(MAX_CANDIDATES + 1)]), CONFIG,
             empty_backlog())


def test_main_writes_backlog_and_config(tmp_path, monkeypatch, capsys):
    games = [game(i) for i in range(35)]
    (tmp_path / "inbox.json").write_text(json.dumps(inbox("2026-11-14T03:00:00Z", games[:30], games[30:])),
                                         encoding="utf-8")
    (tmp_path / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    monkeypatch.setattr("scripts.apply_venue_discovery_inbox.load_venue_lookup_maps", lambda: VENUE_MAPS)
    monkeypatch.setattr("scripts.apply_venue_discovery_inbox.load_artist_lookup_maps", lambda: ARTIST_MAPS)
    args = ["--inbox", str(tmp_path / "inbox.json"), "--config", str(tmp_path / "config.json"),
            "--backlog", str(tmp_path / "backlog.json")]
    assert main(args) == 0
    backlog = json.loads((tmp_path / "backlog.json").read_text(encoding="utf-8"))
    assert backlog["pending_count"] == 5
    assert len(json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["confirmed_events"]) == 30
    out = capsys.readouterr().out
    assert "pending=5" in out and "queued=35" in out
    assert main(args) == 0
    assert json.loads((tmp_path / "backlog.json").read_text(encoding="utf-8"))["pending_count"] == 0


NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def _backlog_file(pending):
    path = Path(tempfile.mkdtemp()) / "backlog.json"
    path.write_text(json.dumps({**empty_backlog(), "pending": pending}), encoding="utf-8")
    return path


def test_check_backlog_drained_draining_and_stale():
    assert check_backlog(_backlog_file([]), max_pending_age_days=7, now=NOW)[0]
    recent = [{"seq": 1, "first_detected_at_utc": "2026-11-18T03:00:00Z", "candidate": {}}]
    assert check_backlog(_backlog_file(recent), max_pending_age_days=7, now=NOW)[0]
    old = [{"seq": 1, "first_detected_at_utc": "2026-11-10T03:00:00Z", "candidate": {}}]
    ok, message = check_backlog(_backlog_file(old), max_pending_age_days=7, now=NOW)
    assert not ok and "stale backlog" in message
    assert not check_backlog(Path("/nonexistent/backlog.json"), max_pending_age_days=7, now=NOW)[0]
