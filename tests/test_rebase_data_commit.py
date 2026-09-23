import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.rebase_data_commit import rebase_data_commit

# Isolate from the developer's global git config (signing, hooks, default branch).
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, env=GIT_ENV, check=True, capture_output=True, text=True
    ).stdout.strip()


def write(repo: Path, rel: str, content: bytes) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class RebaseDataCommitTest(unittest.TestCase):
    """Two runs start from the same base; `upstream` pushes first, `run` rebases onto it."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        origin = self.root / "origin.git"
        git(self.root, "init", "-q", "--bare", "-b", "main", str(origin))
        seed = self.root / "seed"
        git(self.root, "clone", "-q", str(origin), str(seed))
        write(seed, ".gitattributes", b"*.sqlite binary\n")
        write(seed, "data/event_signals.sqlite", b"SIGNALS-BASE\0")
        write(seed, "data/events.sqlite", b"EVENTS-BASE\0")
        write(seed, "data/lp_events.json", b'{\n  "generated_at_utc": "T0",\n  "events": []\n}\n')
        write(seed, "data/config.json", b'{"v": 0}\n')
        commit_all(seed, "base")
        git(seed, "push", "-q", "origin", "HEAD:main")
        self.upstream = self.root / "upstream"
        self.run_repo = self.root / "run"
        git(self.root, "clone", "-q", str(origin), str(self.upstream))
        git(self.root, "clone", "-q", str(origin), str(self.run_repo))

    def push_upstream(self, files: dict[str, bytes]) -> str:
        for rel, content in files.items():
            write(self.upstream, rel, content)
        sha = commit_all(self.upstream, "upstream data update")
        git(self.upstream, "push", "-q", "origin", "HEAD:main")
        return sha

    def commit_run(self, files: dict[str, bytes]) -> str:
        for rel, content in files.items():
            write(self.run_repo, rel, content)
        return commit_all(self.run_repo, "run data update")

    def rebase(self) -> tuple[bool, str]:
        old_env = os.environ.copy()
        os.environ.update(GIT_ENV)
        try:
            return rebase_data_commit(self.run_repo, remote="origin", branch="main")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def blob(self, rev: str, rel: str) -> str:
        return git(self.run_repo, "rev-parse", f"{rev}:{rel}")

    def test_sqlite_conflict_aborts_instead_of_taking_upstream(self) -> None:
        self.push_upstream({"data/event_signals.sqlite": b"SIGNALS-NEWS\0"})
        mine = self.commit_run({"data/event_signals.sqlite": b"SIGNALS-VENUE\0"})

        ok, message = self.rebase()

        self.assertFalse(ok)
        self.assertIn("data/event_signals.sqlite", message)
        self.assertEqual(git(self.run_repo, "rev-parse", "HEAD"), mine)
        self.assertFalse((self.run_repo / ".git" / "rebase-merge").exists())

    def test_disjoint_sqlite_updates_keep_this_runs_db(self) -> None:
        upstream = self.push_upstream({
            "data/events.sqlite": b"EVENTS-OFFICIAL\0",
            "data/lp_events.json": b'{\n  "generated_at_utc": "T1",\n  "events": []\n}\n',
        })
        mine = self.commit_run({
            "data/event_signals.sqlite": b"SIGNALS-VENUE\0",
            "data/lp_events.json": b'{\n  "generated_at_utc": "T2",\n  "events": []\n}\n',
        })

        ok, _ = self.rebase()

        self.assertTrue(ok)
        self.assertEqual(git(self.run_repo, "rev-parse", "HEAD~1"), upstream)
        self.assertEqual(self.blob("HEAD", "data/event_signals.sqlite"), self.blob(mine, "data/event_signals.sqlite"))
        self.assertEqual(self.blob("HEAD", "data/events.sqlite"), self.blob(upstream, "data/events.sqlite"))
        # Derived file keeps upstream's copy; the workflow rebuilds it from the rebased DBs.
        self.assertEqual(self.blob("HEAD", "data/lp_events.json"), self.blob(upstream, "data/lp_events.json"))

    def test_lp_only_commit_is_dropped_without_conflict(self) -> None:
        upstream = self.push_upstream({"data/lp_events.json": b'{\n  "generated_at_utc": "T1",\n  "events": []\n}\n'})
        self.commit_run({"data/lp_events.json": b'{\n  "generated_at_utc": "T2",\n  "events": []\n}\n'})

        ok, message = self.rebase()

        self.assertTrue(ok)
        self.assertEqual(git(self.run_repo, "rev-parse", "HEAD"), upstream)
        self.assertIn("dropped", message)

    def test_other_text_conflict_aborts(self) -> None:
        self.push_upstream({"data/config.json": b'{"v": 1}\n'})
        mine = self.commit_run({"data/config.json": b'{"v": 2}\n'})

        ok, message = self.rebase()

        self.assertFalse(ok)
        self.assertIn("data/config.json", message)
        self.assertEqual(git(self.run_repo, "rev-parse", "HEAD"), mine)

    def test_up_to_date_branch_is_left_as_is(self) -> None:
        mine = self.commit_run({"data/event_signals.sqlite": b"SIGNALS-VENUE\0"})

        ok, _ = self.rebase()

        self.assertTrue(ok)
        self.assertEqual(git(self.run_repo, "rev-parse", "HEAD"), mine)


if __name__ == "__main__":
    unittest.main()
