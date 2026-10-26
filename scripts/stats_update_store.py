"""Recoverable DB/meta saves for the POSIX core-statistics update commands.

All writers must hold stats_update() from before reading old data through save.
Readers should open SQLite read-only. Existing SQLite sidecars are refused;
uncoordinated writers are unsupported.
Two path replacements are not a reader-atomic snapshot. The rollback journal
protects failed commands and is recovered before any subsequent no-op decision.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path


def _sync(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _sync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _require_standalone(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise RuntimeError(f"SQLite sidecar present; stop other users before updating: {path.name}{suffix}")


class StatsUpdate:
    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path
        self.journal = sqlite_path.with_name(f".{sqlite_path.name}.update")

    def _recover(self) -> None:
        pending = self.journal / "pending.json"
        if pending.exists():
            manifest = json.loads(pending.read_text(encoding="utf-8"))
            name = manifest["meta_name"]
            if (
                manifest.get("version") != 1
                or not isinstance(name, str)
                or Path(name).name != name
                or not name.endswith(".json")
                or name == self.sqlite_path.name
            ):
                raise RuntimeError("Invalid statistics rollback journal; retain it for recovery")
            targets = [(self.sqlite_path, "old.sqlite"), (self.sqlite_path.with_name(name), "old.json")]
            # Validate every backup before restoring either live path. Keep the
            # originals until both restores finish, so recovery can itself retry.
            for _, backup in targets:
                expected = manifest[backup]
                if expected is not None and _digest(self.journal / backup) != expected:
                    raise RuntimeError("Statistics rollback backup checksum mismatch")
            _require_standalone(self.sqlite_path)
            for target, backup in targets:
                if manifest[backup] is None:
                    target.unlink(missing_ok=True)
                else:
                    restored = self.journal / f"restore-{backup}"
                    shutil.copy2(self.journal / backup, restored)
                    _sync(restored)
                    os.replace(restored, target)
            _sync_dir(self.sqlite_path.parent)
            # Restore is now durable. If cleanup is interrupted, do not mistake
            # a partially removed backup directory for a pending transaction.
            os.replace(pending, self.journal / "restored.json")
            _sync_dir(self.journal)
        if self.journal.exists():
            shutil.rmtree(self.journal)
            _sync_dir(self.sqlite_path.parent)

    def save(self, meta_path: Path, meta: dict, build_database: Callable[[Path], None]) -> None:
        meta_path = meta_path.absolute()
        if meta_path.parent.resolve() != self.sqlite_path.parent or not meta_path.name.endswith(".json"):
            raise ValueError("Statistics metadata must be a JSON file beside the database")
        _require_standalone(self.sqlite_path)
        self.journal.mkdir()
        pending = self.journal / "pending.json"
        committed = self.journal / "committed.json"
        try:
            manifest = {"version": 1, "meta_name": meta_path.name}
            for target, backup in [(self.sqlite_path, "old.sqlite"), (meta_path, "old.json")]:
                manifest[backup] = None
                if target.exists():
                    shutil.copy2(target, self.journal / backup)
                    _sync(self.journal / backup)
                    manifest[backup] = _digest(self.journal / backup)

            staged_db = self.journal / "new.sqlite"
            if self.sqlite_path.exists():
                shutil.copy2(self.journal / "old.sqlite", staged_db)
            build_database(staged_db)
            _require_standalone(staged_db)
            with closing(sqlite3.connect(f"{staged_db.as_uri()}?mode=ro", uri=True)) as conn:
                if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise RuntimeError("Staged statistics database failed integrity check")
            staged_meta = self.journal / meta_path.name
            staged_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            if meta_path.exists():
                shutil.copymode(meta_path, staged_meta)
            _sync(staged_db)
            _sync(staged_meta)
            prepared = self.journal / "prepared.json"
            prepared.write_text(json.dumps(manifest), encoding="utf-8")
            _sync(prepared)
            os.replace(prepared, pending)
            _sync_dir(self.journal)
            _sync_dir(self.sqlite_path.parent)

            _require_standalone(self.sqlite_path)
            os.replace(staged_db, self.sqlite_path)
            os.replace(staged_meta, meta_path)
            _sync_dir(self.sqlite_path.parent)
            # This rename is the commit point. Both new paths are durable first.
            os.replace(pending, committed)
            _sync_dir(self.journal)
        except BaseException:
            # A rollback failure intentionally leaves pending.json and backups.
            # The next invocation retries recovery before reading DB or meta.
            self._recover()
            raise
        # Cleanup failure can leave a committed journal, never a pending one.
        self._recover()


@contextmanager
def stats_update(sqlite_path: Path) -> Iterator[StatsUpdate]:
    sqlite_path = sqlite_path.resolve()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = sqlite_path.with_name(f".{sqlite_path.name}.update.lock")
    # Keep the inode stable: unlinking the lock permits two simultaneous owners.
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another statistics update is already running") from error
        try:
            update = StatsUpdate(sqlite_path)
            update._recover()
            _require_standalone(sqlite_path)
            yield update
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
