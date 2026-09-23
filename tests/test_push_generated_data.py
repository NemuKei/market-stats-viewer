"""Check that scheduled data writes stop when the remote branch has moved."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PUSH_SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/push_generated_data.sh"


def git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE
    ).strip()


class PushGeneratedDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.remote = root / "remote.git"
        self.writer = root / "writer"
        self.other = root / "other"
        git("init", "--bare", str(self.remote), cwd=root)
        git("clone", str(self.remote), str(self.writer), cwd=root)
        for clone in (self.writer, self.other):
            if clone == self.other:
                git("clone", str(self.remote), str(clone), cwd=root)
            git("config", "user.name", "Test", cwd=clone)
            git("config", "user.email", "test@example.invalid", cwd=clone)
        git("checkout", "-b", "main", cwd=self.writer)
        (self.writer / "data.txt").write_text("original\n", encoding="utf-8")
        git("add", "data.txt", cwd=self.writer)
        git("commit", "-m", "base", cwd=self.writer)
        git("push", "origin", "main", cwd=self.writer)
        git("fetch", "origin", "main", cwd=self.other)
        git("checkout", "-b", "main", "origin/main", cwd=self.other)

    def _commit(self, clone: Path, contents: str) -> str:
        (clone / "data.txt").write_text(contents, encoding="utf-8")
        git("add", "data.txt", cwd=clone)
        git("commit", "-m", "generated data", cwd=clone)
        return git("rev-parse", "HEAD", cwd=clone)

    def _push_writer(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(PUSH_SCRIPT)],
            cwd=self.writer,
            env={**os.environ, "GITHUB_REF_NAME": "main"},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_publishes_when_base_is_current(self) -> None:
        expected = self._commit(self.writer, "new version\n")

        result = self._push_writer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git("rev-parse", "refs/heads/main", cwd=self.remote), expected)

    def test_stops_instead_of_overwriting_concurrent_data(self) -> None:
        self._commit(self.writer, "stale generated data\n")
        current = self._commit(self.other, "newer generated data\n")
        git("push", "origin", "main", cwd=self.other)

        result = self._push_writer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Remote main advanced", result.stderr)
        self.assertEqual(git("rev-parse", "refs/heads/main", cwd=self.remote), current)
        self.assertEqual((self.writer / "data.txt").read_text(encoding="utf-8"), "stale generated data\n")


if __name__ == "__main__":
    unittest.main()
