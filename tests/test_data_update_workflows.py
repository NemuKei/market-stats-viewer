import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


LP_BUILDING_WORKFLOWS = (
    Path(".github/workflows/update_events_official.yml"),
    Path(".github/workflows/update_signals.yml"),
    Path(".github/workflows/update_signals_venue_web_discovery.yml"),
)
DATA_WORKFLOWS = LP_BUILDING_WORKFLOWS + (
    Path(".github/workflows/update_data.yml"),
    Path(".github/workflows/update_artist_registry.yml"),
)
REPO_ROOT = Path(__file__).resolve().parents[1]


class DataWorkflowRebaseTest(unittest.TestCase):
    """`-X ours` lets upstream silently win binary SQLite conflicts during rebase."""

    def test_push_step_rebases_with_helper_not_x_ours(self) -> None:
        for path in DATA_WORKFLOWS:
            with self.subTest(workflow=path.name):
                workflow = path.read_text(encoding="utf-8")
                self.assertNotIn("-X ours", workflow)
                self.assertNotIn("merge.ours", workflow)
                commit_step = workflow.split("- name: Commit changes (if any)", 1)[1]
                rebase = commit_step.index("python -m scripts.rebase_data_commit --branch \"$branch\"")
                self.assertLess(rebase, commit_step.index("git push origin"))

    def test_checkout_starts_from_branch_tip_not_trigger_sha(self) -> None:
        for path in DATA_WORKFLOWS[len(LP_BUILDING_WORKFLOWS):]:
            with self.subTest(workflow=path.name):
                checkout = path.read_text(encoding="utf-8").split("uses: actions/checkout@v6", 1)[1]
                self.assertIn("ref: ${{ github.ref }}", checkout.split("- uses:", 1)[0])


class LpBuildingWorkflowPushTest(unittest.TestCase):
    """Rebase text-merges lp_events.json, so it must be rebuilt and validated before push."""

    def test_checkout_starts_from_branch_tip_not_trigger_sha(self) -> None:
        for path in LP_BUILDING_WORKFLOWS:
            with self.subTest(workflow=path.name):
                workflow = path.read_text(encoding="utf-8")
                checkout = workflow.split("uses: actions/checkout@v6", 1)[1]
                checkout = checkout.split("- uses:", 1)[0]
                self.assertIn("ref: ${{ github.ref }}", checkout)

    def test_lp_events_is_rebuilt_and_validated_between_rebase_and_push(self) -> None:
        for path in LP_BUILDING_WORKFLOWS:
            with self.subTest(workflow=path.name):
                commit_step = path.read_text(encoding="utf-8").split(
                    "- name: Commit changes (if any)", 1
                )[1]
                rebase = commit_step.index("python -m scripts.rebase_data_commit")
                rebuild = commit_step.index("python -m scripts.build_lp_events", rebase)
                validate = commit_step.index(
                    "python -m scripts.validate_external_events --lp-events data/lp_events.json",
                    rebuild,
                )
                amend = commit_step.index("git commit --amend --no-edit", validate)
                push = commit_step.index("git push origin", amend)
                self.assertLess(rebase, push)
                self.assertNotIn(
                    "git pull --rebase -X ours origin \"$branch\" && git push",
                    commit_step,
                )


def _commit_step_script(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").split(
        "- name: Commit changes (if any)\n", 1
    )[1].splitlines()[1:]
    body = []
    for line in lines:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)) + "\n"


class LpBuildingWorkflowPushScriptTest(unittest.TestCase):
    """Run each workflow's real commit step against a scratch remote with a stubbed `uv`."""

    FILES = (
        "data/events.sqlite",
        "data/event_signals.sqlite",
        "data/lp_events.json",
        "data/venue_web_discovery_config.json",
        "scripts/placeholder.py",
        "docs/placeholder.md",
        "app.py",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        ".github/workflows/update_artist_registry.yml",
    )

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        stub_bin = self.tmp / "bin"
        stub_bin.mkdir()
        # build_lp_events always stamps generated_at_utc, so a rebuild always differs.
        (stub_bin / "uv").write_text(
            "#!/bin/sh\n"
            'case "$*" in\n'
            '  *scripts.build_lp_events*) python3 -c "import uuid; print(uuid.uuid4())" > data/lp_events.json ;;\n'
            f'  *scripts.rebase_data_commit*) shift 2; exec "{sys.executable}" "$@" ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        (stub_bin / "uv").chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_REF_NAME": "main",
            "PYTHONPATH": str(REPO_ROOT),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.remote = self.tmp / "remote.git"
        seed = self.tmp / "seed"
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.git(self.tmp, "clone", "-q", str(self.remote), str(seed))
        (seed / ".gitattributes").write_text("*.sqlite binary\n", encoding="utf-8")
        for name in self.FILES:
            (seed / name).parent.mkdir(parents=True, exist_ok=True)
            (seed / name).write_text("base\n", encoding="utf-8")
        self.git(seed, "add", ".")
        self.git(seed, "commit", "-qm", "base")
        self.git(seed, "push", "-q", "origin", "main")
        self.runner = self.tmp / "runner"
        self.git(self.tmp, "clone", "-q", str(self.remote), str(self.runner))
        self.upstream = seed

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def push_upstream(self, name: str, content: str) -> str:
        (self.upstream / name).write_text(content, encoding="utf-8")
        self.git(self.upstream, "commit", "-qam", "upstream update")
        self.git(self.upstream, "push", "-q", "origin", "main")
        return self.git(self.upstream, "rev-parse", "HEAD")

    def run_step(self, workflow: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-e", "-c", _commit_step_script(workflow)], cwd=self.runner,
            env=self.env, capture_output=True, text=True, timeout=60,
        )

    def test_race_rebuilds_lp_events_on_top_of_upstream(self) -> None:
        for workflow in LP_BUILDING_WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                self.setUp()
                upstream_sha = self.push_upstream("data/events.sqlite", "upstream\n")
                (self.runner / "data/event_signals.sqlite").write_text("mine\n")
                result = self.run_step(workflow)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("Push retry", result.stdout)
                tip = self.git(self.remote, "rev-parse", "main")
                self.assertEqual(self.git(self.remote, "rev-parse", "main~1"), upstream_sha)
                self.assertEqual(
                    self.git(self.remote, "show", f"{tip}:data/event_signals.sqlite"), "mine"
                )
                self.assertEqual(
                    self.git(self.remote, "show", f"{tip}:data/lp_events.json"),
                    (self.runner / "data/lp_events.json").read_text().strip(),
                )

    def test_commit_dropped_by_rebase_does_not_rewrite_upstream(self) -> None:
        # `git rebase` drops a commit whose patch is already upstream; HEAD becomes
        # the upstream commit and must not be amended (non-fast-forward push).
        for workflow in LP_BUILDING_WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                self.setUp()
                upstream_sha = self.push_upstream("data/event_signals.sqlite", "same\n")
                (self.runner / "data/event_signals.sqlite").write_text("same\n")
                result = self.run_step(workflow)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("Push retry", result.stdout)
                self.assertEqual(self.git(self.remote, "rev-parse", "main~1"), upstream_sha)
                self.assertRegex(
                    self.git(self.remote, "log", "-1", "--format=%s", "main"),
                    r"^chore: update ",
                )
                self.assertEqual(
                    self.git(self.remote, "show", "main:data/lp_events.json"),
                    (self.runner / "data/lp_events.json").read_text().strip(),
                )

    def test_conflicting_sqlite_update_fails_without_pushing(self) -> None:
        for workflow in DATA_WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                self.setUp()
                upstream_sha = self.push_upstream("data/event_signals.sqlite", "upstream\n")
                (self.runner / "data/event_signals.sqlite").write_text("mine\n")
                result = self.run_step(workflow)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("::error::", result.stderr)
                self.assertIn("data/event_signals.sqlite", result.stderr)
                self.assertNotIn("Push retry", result.stdout)
                self.assertEqual(self.git(self.remote, "rev-parse", "main"), upstream_sha)

    def test_race_keeps_this_runs_db_without_lp_rebuild(self) -> None:
        for workflow in DATA_WORKFLOWS[len(LP_BUILDING_WORKFLOWS):]:
            with self.subTest(workflow=workflow.name):
                self.setUp()
                upstream_sha = self.push_upstream("data/events.sqlite", "upstream\n")
                (self.runner / "data/event_signals.sqlite").write_text("mine\n")
                result = self.run_step(workflow)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.git(self.remote, "rev-parse", "main~1"), upstream_sha)
                self.assertEqual(self.git(self.remote, "show", "main:data/event_signals.sqlite"), "mine")
                self.assertEqual(self.git(self.remote, "show", "main:data/events.sqlite"), "upstream")


if __name__ == "__main__":
    unittest.main()
