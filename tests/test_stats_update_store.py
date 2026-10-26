"""Fault injection uses fictional data and real SQLite/filesystem operations."""
import importlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from scripts import stats_update_store as store


def build_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("DROP TABLE IF EXISTS updated")
        conn.execute("CREATE TABLE updated(value INTEGER)")
        conn.execute("INSERT INTO updated VALUES (2)")


@pytest.fixture
def pair(tmp_path):
    db, meta = tmp_path / "market_stats.sqlite", tmp_path / "meta.json"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.executescript("""
            CREATE TABLE updated(value INTEGER);
            INSERT INTO updated VALUES (1);
            CREATE TABLE history(id TEXT PRIMARY KEY, value TEXT);
            INSERT INTO history VALUES ('published-id', 'keep');
            CREATE INDEX idx_history_value ON history(value);
            CREATE TRIGGER retain_history BEFORE DELETE ON history
            BEGIN SELECT RAISE(ABORT, 'retain history'); END;
        """)
    meta.write_text('{"generation": 1}', encoding="utf-8")
    (tmp_path / "meta_other.json").write_text('{"untouched": true}', encoding="utf-8")
    return db, meta


def assert_generation(db, meta, generation):
    with closing(sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)) as conn:
        assert conn.execute("SELECT value FROM updated").fetchall() == [(generation,)]
        assert conn.execute("SELECT * FROM history").fetchall() == [("published-id", "keep")]
        assert conn.execute("SELECT name FROM sqlite_master WHERE name IN ('idx_history_value', 'retain_history') ORDER BY name").fetchall() == [
            ("idx_history_value",), ("retain_history",)
        ]
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert json.loads(meta.read_text()) == {"generation": generation}
    assert json.loads((db.parent / "meta_other.json").read_text()) == {"untouched": True}


@pytest.mark.parametrize("failure", ["build", "metadata", "journal", "database_replace", "metadata_replace", "commit_marker"])
def test_save_failure_retains_exact_pair_then_retry_succeeds(pair, monkeypatch, failure):
    db, meta = pair
    before = db.read_bytes(), meta.read_bytes()
    replace, write_text = os.replace, Path.write_text

    def fail_replace(source, target):
        if ((failure == "database_replace" and Path(target) == db)
            or (failure == "metadata_replace" and Path(target) == meta)
            or (failure == "commit_marker" and Path(target).name == "committed.json")):
            raise OSError("injected save failure")
        return replace(source, target)

    def fail_write(path, *args, **kwargs):
        if ((failure == "metadata" and path.name == meta.name)
            or (failure == "journal" and path.name == "prepared.json")):
            # Exercise a partial write, not just a pre-write exception.
            write_text(path, "{", encoding="utf-8")
            raise OSError("injected save failure")
        return write_text(path, *args, **kwargs)

    def build(path):
        build_database(path)
        if failure == "build":
            raise OSError("injected save failure")

    with monkeypatch.context() as patch:
        patch.setattr(store.os, "replace", fail_replace)
        patch.setattr(Path, "write_text", fail_write)
        with store.stats_update(db) as update:
            with pytest.raises(OSError, match="injected save failure"):
                update.save(meta, {"generation": 2}, build)
    # If rollback replacement failed too, the next entry must finish it.
    with store.stats_update(db):
        assert (db.read_bytes(), meta.read_bytes()) == before
    assert_generation(db, meta, 1)
    with store.stats_update(db) as update:
        update.save(meta, {"generation": 2}, build_database)
    assert_generation(db, meta, 2)
    assert not db.with_name(f".{db.name}.update").exists()


CRASHING_SAVE = """
import os, sqlite3, sys
from pathlib import Path
from contextlib import closing
from scripts import stats_update_store as store
db, meta, stop = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
replace = os.replace
def crash(source, target):
    replace(source, target)
    name = Path(target).name
    if ((stop == 'database' and Path(target) == db)
        or (stop == 'metadata' and Path(target) == meta)
        or (stop == 'committed' and name == 'committed.json')):
        os._exit(71)
store.os.replace = crash
def build(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('UPDATE updated SET value=2')
with store.stats_update(db) as update:
    update.save(meta, {'generation': 2}, build)
"""


def crash_save(db, meta, stop):
    result = subprocess.run([sys.executable, "-c", CRASHING_SAVE, str(db), str(meta), stop], capture_output=True, text=True)
    assert result.returncode == 71, result.stderr


@pytest.mark.parametrize("stop", ["database", "metadata", "committed"])
def test_process_death_recovers_pending_pair_or_retains_committed_pair(pair, stop):
    db, meta = pair
    before = db.read_bytes(), meta.read_bytes()
    crash_save(db, meta, stop)
    with store.stats_update(db):
        if stop != "committed":
            assert (db.read_bytes(), meta.read_bytes()) == before
    assert_generation(db, meta, 2 if stop == "committed" else 1)
    # Recovery is idempotent, and a fresh save never duplicates prior rows.
    with store.stats_update(db) as update:
        update.save(meta, {"generation": 2}, build_database)
    assert_generation(db, meta, 2)


@pytest.mark.parametrize("module,fetch", [
    ("update_data", "fetch_html_text"),
    ("update_ta_data", "fetch_html"),
    ("update_tcd_data", "fetch_source_page"),
    ("update_icd_data", "fetch_html"),
    ("update_airport_volume_data", "collect_recent_source_entries"),
])
def test_every_entry_recovers_before_fetch_or_noop(pair, monkeypatch, module, fetch):
    db, meta = pair
    before = db.read_bytes(), meta.read_bytes()
    crash_save(db, meta, "database")
    updater = importlib.import_module(f"scripts.{module}")
    monkeypatch.setattr(updater, "SQLITE_PATH", db)
    monkeypatch.setattr(updater, "DATA_DIR", db.parent)

    def unavailable(*args, **kwargs):
        assert (db.read_bytes(), meta.read_bytes()) == before
        raise ConnectionError("fixture source unavailable after recovery")

    monkeypatch.setattr(updater, fetch, unavailable)
    with pytest.raises(ConnectionError, match="fixture source unavailable"):
        updater.main()
    assert_generation(db, meta, 1)


def test_interrupted_recovery_can_retry_from_intact_backups(pair, monkeypatch):
    db, meta = pair
    before = db.read_bytes(), meta.read_bytes()
    crash_save(db, meta, "database")
    replace = os.replace

    def interrupt_restore(source, target):
        if Path(target) == meta:
            raise OSError("recovery metadata unavailable")
        return replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(store.os, "replace", interrupt_restore)
        with pytest.raises(OSError, match="recovery metadata unavailable"):
            with store.stats_update(db):
                pytest.fail("must not proceed with an incomplete recovery")
    with store.stats_update(db):
        assert (db.read_bytes(), meta.read_bytes()) == before
    assert_generation(db, meta, 1)


def test_corrupted_rollback_backup_fails_closed_without_changing_live_files(pair):
    db, meta = pair
    crash_save(db, meta, "database")
    before = db.read_bytes(), meta.read_bytes()
    journal = db.with_name(f".{db.name}.update")
    (journal / "old.json").write_text("corrupt", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        with store.stats_update(db):
            pytest.fail("must not use a corrupt recovery set")
    assert (db.read_bytes(), meta.read_bytes()) == before
    assert (journal / "pending.json").exists()


@pytest.mark.parametrize("existing", ["neither", "database", "metadata"])
def test_first_save_failure_restores_original_file_presence(tmp_path, monkeypatch, existing):
    db, meta = tmp_path / "market_stats.sqlite", tmp_path / "meta.json"
    if existing == "database":
        build_database(db)
    if existing == "metadata":
        meta.write_text('{"generation":1}', encoding="utf-8")
    before = tuple(path.read_bytes() if path.exists() else None for path in (db, meta))
    replace = os.replace

    def fail_metadata(source, target):
        if Path(target) == meta and Path(source).name == meta.name:
            raise OSError("metadata replace unavailable")
        return replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(store.os, "replace", fail_metadata)
        with store.stats_update(db) as update:
            with pytest.raises(OSError, match="metadata replace unavailable"):
                update.save(meta, {"generation": 2}, build_database)
    assert tuple(path.read_bytes() if path.exists() else None for path in (db, meta)) == before


def test_concurrent_writer_is_refused_before_reading_old_state(pair):
    db, meta = pair
    with store.stats_update(db):
        with pytest.raises(RuntimeError, match="already running"):
            with store.stats_update(db):
                pytest.fail("second writer entered")
    assert_generation(db, meta, 1)


def test_live_wal_database_is_refused_without_losing_committed_rows(pair):
    db, meta = pair
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO history VALUES ('wal-id', 'new')")
        conn.commit()
        before = db.read_bytes(), Path(str(db) + "-wal").read_bytes(), meta.read_bytes()
        with pytest.raises(RuntimeError, match="SQLite sidecar present"):
            with store.stats_update(db):
                pytest.fail("must not replace a live WAL database")
        assert (db.read_bytes(), Path(str(db) + "-wal").read_bytes(), meta.read_bytes()) == before
        assert conn.execute("SELECT value FROM history WHERE id='wal-id'").fetchone() == ("new",)
