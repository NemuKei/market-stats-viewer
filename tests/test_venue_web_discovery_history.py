"""Persistence regressions use disposable databases and fictional official events."""

from copy import deepcopy
from contextlib import closing
from datetime import date, datetime, timezone
import json
import sqlite3
import sys

import pytest

from scripts import update_event_signals_data as updater
from scripts.signals.sources import venue_web_discovery as discovery
from scripts.signals.types import SignalRecord, SignalSourceRecord


def event(key, day, *, start_time="18:00", status=None):
    row = dict(
        event_id=key,
        title=f"Concert {key}",
        artist_name=f"Artist {key}",
        venue_name="Test Hall",
        pref_name="東京都",
        event_start_date=day,
        event_end_date=day,
        event_start_time=start_time,
        source_class="venue_official",
        url=f"https://official.example/events/{key}",
        evidence_snippet="The fictional official schedule confirms this occurrence.",
        announced_at_utc="2026-09-01T00:00:00Z",
    )
    if status:
        row.update(
            event_status=status,
            enabled=False,
            evidence_snippet=f"The fictional official page explicitly says {status}.",
        )
    return row


@pytest.fixture
def imports(tmp_path, monkeypatch):
    config = tmp_path / "confirmed.json"
    database = tmp_path / "signals.sqlite"
    defaults = deepcopy(
        [s for s in updater.DEFAULT_SOURCES if s["source_id"] == "venue_web_discovery"]
    )
    runtime = json.loads(defaults[0]["config_json"])
    runtime["config_path"] = str(config)
    defaults[0]["config_json"] = json.dumps(runtime)
    monkeypatch.setattr(updater, "DEFAULT_SOURCES", defaults)
    monkeypatch.setattr(updater, "SIGNALS_DB_PATH", database)
    monkeypatch.setattr(updater, "load_artist_lookup_maps", lambda: ({}, {}))
    monkeypatch.setattr(updater, "load_venue_lookup_maps", lambda: ({}, {}))
    clock = {"day": "2026-10-04"}

    class ClockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(clock["day"] + "T12:00:00+00:00").astimezone(
                tz or timezone.utc
            )

    class ClockDate(date):
        @classmethod
        def today(cls):
            return date.fromisoformat(clock["day"])

    monkeypatch.setattr(discovery, "datetime", ClockDatetime)
    monkeypatch.setattr(updater, "date", ClockDate)
    monkeypatch.setattr(updater, "now_utc_z", lambda: clock["day"] + "T12:00:00Z")

    def run(
        events,
        day="2026-10-04",
        *,
        future_only=True,
        rebuild=False,
        source_ids="venue_web_discovery",
    ):
        clock["day"] = day
        # Exercise legacy settings still present in deployed configs.
        payload = {"confirmed_events": events}
        if future_only is not None:
            payload["future_only"] = future_only
        config.write_text(json.dumps(payload))
        argv = ["update_event_signals_data", "--only", source_ids]
        if rebuild:
            argv.append("--rebuild")
        monkeypatch.setattr(sys, "argv", argv)
        updater.main()

    def stored():
        if not database.exists():
            return []
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            return [
                dict(r)
                for r in conn.execute("SELECT * FROM signals ORDER BY signal_uid")
            ]

    def signature():
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
            return conn.execute(
                "SELECT last_signature FROM signal_sources WHERE source_id='venue_web_discovery'"
            ).fetchone()[0]

    run.stored = stored
    run.signature = signature
    run.database = database
    run.defaults = defaults
    return run


def test_nine_finished_occurrences_survive_next_day_and_repeat(imports):
    history = [event(str(i), "2026-10-04") for i in range(9)]
    future = event("future", "2026-10-20")
    imports(history + [future])
    baseline = imports.stored()
    assert len(baseline) == 10
    imports(history + [future], "2026-10-05")
    assert imports.stored() == baseline
    imports(history + [future], "2026-10-06")
    assert imports.stored() == baseline


def test_partial_range_keeps_history_and_omitted_future_rows(imports):
    old = event("history", "2026-10-04")
    future = event("future", "2026-10-20")
    other = event("other-future", "2026-11-20")
    imports([old, future, other])
    baseline = imports.stored()
    imports([future], "2026-10-05")
    assert imports.stored() == baseline


@pytest.mark.parametrize("future_only", [True, False, None])
def test_past_records_are_loaded_with_legacy_or_default_settings(imports, future_only):
    old = event("past", "2026-06-01")
    imports([old], "2026-10-06", future_only=future_only)
    assert len(imports.stored()) == 1
    imports([old], "2026-10-07", future_only=True)
    assert len(imports.stored()) == 1


def test_empty_fetch_keeps_every_existing_column(imports):
    imports([event("history", "2026-10-04"), event("future", "2026-10-20")])
    baseline = imports.stored()
    imports([], "2026-10-05")
    assert imports.stored() == baseline


def test_transient_fetch_failure_keeps_every_existing_column(imports, monkeypatch):
    imports([event("history", "2026-10-04"), event("future", "2026-10-20")])
    baseline = imports.stored()

    def fail(*args):
        raise TimeoutError("temporary acquisition failure")

    monkeypatch.setattr(discovery.VenueWebDiscoverySource, "fetch_signals", fail)
    with pytest.raises(SystemExit) as exc:
        imports([], "2026-10-05")
    assert exc.value.code == 1
    assert imports.stored() == baseline


def test_future_correction_updates_same_uid_and_preserves_first_seen(imports):
    past = event("history", "2026-10-04")
    future = event("future", "2026-10-20")
    imports([past, future])
    baseline = imports.stored()
    updated = {**future, "event_start_time": "19:00"}
    imports([updated], "2026-10-05")
    after = imports.stored()
    assert {r["signal_uid"] for r in after} == {r["signal_uid"] for r in baseline}
    for row in after:
        previous = next(r for r in baseline if r["signal_uid"] == row["signal_uid"])
        assert row["first_seen_at_utc"] == previous["first_seen_at_utc"]
        if row["title"] == "Concert future":
            assert json.loads(row["labels_json"])["event_start_time"] == "19:00"
            assert row["updated_at_utc"] == "2026-10-05T12:00:00Z"
        else:
            assert row == previous
    imports([updated], "2026-10-06")
    assert imports.stored() == after


@pytest.mark.parametrize("status", ["postponed", "cancelled"])
def test_explicit_status_retained_after_end_and_missing_fetch(imports, status):
    state = event("state", "2026-10-04", status=status)
    future = event("future", "2026-10-20")
    imports([state, future])
    baseline = imports.stored()
    imports([state, future], "2026-10-05")
    assert imports.stored() == baseline
    imports([future], "2026-10-06")
    assert imports.stored() == baseline


@pytest.mark.parametrize(
    "source_ids", ["venue_web_discovery", "starto_concert,venue_web_discovery"]
)
def test_vwd_rebuild_is_rejected_before_opening_a_database(imports, source_ids):
    with pytest.raises(SystemExit) as exc:
        imports([event("future", "2026-10-20")], rebuild=True, source_ids=source_ids)
    assert exc.value.code == 2
    assert not imports.database.exists()


@pytest.mark.parametrize(
    "predicate",
    [
        updater.should_prune_missing_for_source,
        updater.should_drop_past_events_for_source,
    ],
)
def test_legacy_delete_flags_cannot_enable_vwd_deletion(predicate):
    source = SignalSourceRecord(
        "venue_web_discovery",
        "VWD",
        "config",
        "codex_web_discovery",
        json.dumps({"prune_missing": True, "drop_past_events": True}),
        True,
    )
    assert predicate(source) is False


@pytest.mark.parametrize("source_id", ["starto_concert", "kstyle_music"])
def test_news_source_deletion_settings_remain_configurable(source_id):
    source = SignalSourceRecord(source_id, "News", "config", "html_list", None, True)
    assert updater.should_prune_missing_for_source(source) is True
    assert updater.should_drop_past_events_for_source(source) is False
    source.config_json = json.dumps({"prune_missing": False, "drop_past_events": True})
    assert updater.should_prune_missing_for_source(source) is False
    assert updater.should_drop_past_events_for_source(source) is True


@pytest.fixture
def with_news(imports, monkeypatch):
    original_get_source = updater.get_source
    original_load_targets = updater.load_target_sources
    news_fetches = []
    imports.defaults.append(
        dict(
            source_id="starto_concert",
            source_name="Fictional News",
            source_url="https://news.example/",
            source_type="html_list",
            config_json="{}",
        )
    )

    class NewsSource:
        def fetch_signals(self, source):
            news_fetches.append(source.source_id)
            return [
                SignalRecord(
                    "fictional-news",
                    source.source_id,
                    "2026-10-05T00:00:00Z",
                    "Fictional news report",
                    "https://news.example/item",
                    "Fictional article.",
                    1,
                    "{}",
                )
            ]

    def get_source(source_id, session):
        return (
            NewsSource()
            if source_id == "starto_concert"
            else original_get_source(source_id, session)
        )

    def vwd_first(conn, only_ids):
        return sorted(
            original_load_targets(conn, only_ids),
            key=lambda source: source.source_id != "venue_web_discovery",
        )

    monkeypatch.setattr(updater, "get_source", get_source)
    monkeypatch.setattr(updater, "load_target_sources", vwd_first)
    imports.news_fetches = news_fetches
    return imports


def test_failed_upsert_does_not_leak_rows_when_next_source_commits(
    with_news, monkeypatch
):
    imports = with_news
    imports([event("history", "2026-10-04")])
    baseline = imports.stored()
    signature = imports.signature()
    real_upsert = updater.upsert_signals

    def fail_after_write(conn, signals, **kwargs):
        changed = real_upsert(conn, signals, **kwargs)
        if signals[0].source_id == "venue_web_discovery":
            raise sqlite3.OperationalError("failure after staged rows")
        return changed

    monkeypatch.setattr(updater, "upsert_signals", fail_after_write)
    imports(
        [event("new-future", "2026-10-20")],
        "2026-10-05",
        source_ids="venue_web_discovery,starto_concert",
    )
    after = imports.stored()
    assert [r for r in after if r["source_id"] == "venue_web_discovery"] == baseline
    assert [r["signal_uid"] for r in after if r["source_id"] == "starto_concert"] == [
        "fictional-news"
    ]
    assert imports.signature() == signature


@pytest.mark.parametrize("bad_field", ["pref_name", "score", "title"])
def test_invalid_past_record_blocks_batch_without_changing_history_or_future(
    imports, monkeypatch, bad_field
):
    past = event("history", "2026-06-01")
    future = event("future", "2026-10-20")
    imports([past, future])
    baseline = imports.stored()
    signature = imports.signature()
    monkeypatch.setattr(
        discovery.VenueWebDiscoverySource,
        "_known_prefecture",
        lambda self, venue: "東京都",
    )
    bad_values = {
        "pref_name": "大阪府",
        "score": "not-an-integer",
        "title": "Concert \ufffd",
    }
    invalid = {**past, bad_field: bad_values[bad_field]}
    with pytest.raises(SystemExit) as exc:
        imports([invalid, {**future, "event_start_time": "19:00"}], "2026-10-05")
    assert exc.value.code == 1
    assert imports.stored() == baseline
    assert imports.signature() == signature


def test_conflicting_same_uid_records_fail_before_any_batch_write(imports):
    future = event("shared", "2026-10-20")
    imports([future])
    baseline = imports.stored()
    signature = imports.signature()
    conflicting_past = {
        **future,
        "event_start_date": "2026-06-01",
        "event_end_date": "2026-06-01",
    }
    with pytest.raises(SystemExit) as exc:
        imports([conflicting_past, future], "2026-10-05")
    assert exc.value.code == 1
    assert imports.stored() == baseline
    assert imports.signature() == signature


def test_identical_same_uid_records_are_repeatable(imports):
    past = event("history", "2026-06-01")
    imports([past])
    baseline = imports.stored()
    signature = imports.signature()
    imports([past, deepcopy(past)], "2026-10-05")
    assert imports.stored() == baseline
    assert imports.signature() == signature


def test_changed_url_keeps_old_record_without_guessing_identity(imports):
    future = event("future", "2026-10-20")
    imports([future])
    baseline = imports.stored()[0]
    updated = {**future, "url": future["url"] + "-v2"}
    imports([updated], "2026-10-05")
    after = imports.stored()
    assert len(after) == 2
    assert (
        next(r for r in after if r["signal_uid"] == baseline["signal_uid"]) == baseline
    )
    assert (
        next(r for r in after if r["url"] == updated["url"])["signal_uid"]
        != baseline["signal_uid"]
    )
    imports([updated], "2026-10-06")
    assert imports.stored() == after


def test_failed_signature_write_rolls_back_and_next_import_recovers(
    with_news, monkeypatch
):
    imports = with_news
    past = event("history", "2026-10-04")
    future = event("future", "2026-10-20")
    imports([past, future])
    baseline = imports.stored()
    signature = imports.signature()
    original_update = updater.update_source_signature

    def fail_after_signature(conn, source_id, value):
        original_update(conn, source_id, value)
        if source_id == "venue_web_discovery":
            raise sqlite3.OperationalError("failure after staged signature")

    monkeypatch.setattr(updater, "update_source_signature", fail_after_signature)
    corrected = {**future, "event_start_time": "19:00"}
    imports([corrected], "2026-10-05", source_ids="venue_web_discovery,starto_concert")
    assert [
        r for r in imports.stored() if r["source_id"] == "venue_web_discovery"
    ] == baseline
    assert imports.signature() == signature
    assert imports.news_fetches == ["starto_concert"]

    monkeypatch.setattr(updater, "update_source_signature", original_update)
    imports([corrected], "2026-10-06", source_ids="venue_web_discovery,starto_concert")
    recovered = imports.stored()
    assert imports.signature() != signature
    assert len(recovered) == 3
    assert next(r for r in recovered if r["title"] == "Concert history") == next(
        r for r in baseline if r["title"] == "Concert history"
    )
    row = next(r for r in recovered if r["title"] == "Concert future")
    assert json.loads(row["labels_json"])["event_start_time"] == "19:00"
    assert (
        row["first_seen_at_utc"]
        == next(r for r in baseline if r["title"] == "Concert future")[
            "first_seen_at_utc"
        ]
    )
    imports([corrected], "2026-10-07", source_ids="venue_web_discovery,starto_concert")
    assert imports.stored() == recovered


def test_rollback_failure_logs_original_failure_closes_and_stops(
    with_news, monkeypatch, caplog
):
    imports = with_news
    imports([event("history", "2026-10-04")])
    baseline = imports.stored()
    original_init = updater.init_db
    original_upsert = updater.upsert_signals
    closed = []

    class FailedRollbackConnection(sqlite3.Connection):
        def rollback(self):
            raise sqlite3.OperationalError("injected rollback failure")

        def close(self):
            closed.append(True)
            return super().close()

    def failing_connection(path):
        with closing(original_init(path)):
            pass
        return sqlite3.connect(path, factory=FailedRollbackConnection)

    def fail_after_write(conn, signals, **kwargs):
        original_upsert(conn, signals, **kwargs)
        raise RuntimeError("injected original source failure")

    monkeypatch.setattr(updater, "init_db", failing_connection)
    monkeypatch.setattr(updater, "upsert_signals", fail_after_write)
    with pytest.raises(sqlite3.OperationalError, match="injected rollback failure"):
        imports(
            [event("new-future", "2026-10-20")],
            "2026-10-05",
            source_ids="venue_web_discovery,starto_concert",
        )
    assert "injected original source failure" in caplog.text
    assert "injected rollback failure" in caplog.text
    assert closed == [True]
    assert not imports.news_fetches
    assert imports.stored() == baseline
