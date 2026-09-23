"""Rebase a data-update commit onto the latest upstream without discarding its outputs.

`git pull --rebase -X ours` resolves conflicts in favor of upstream, and for binary
SQLite files it does so without reporting a conflict, so a run's own DB update can be
silently dropped while its commit still pushes. Here only `data/lp_events.json`, a
derived file the workflow rebuilds after rebase, keeps upstream's copy; any other
conflict aborts the rebase so the run does not push.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DERIVED_KEEP_UPSTREAM = ("data/lp_events.json",)
MERGE_DRIVER = "keep-upstream"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=check, capture_output=True, text=True)


def _rev(repo: Path, rev: str) -> str:
    return _git(repo, "rev-parse", rev).stdout.strip()


def _prefer_upstream_for_derived(repo: Path) -> None:
    # Local-only attributes so developers' own merges are unaffected. During a rebase the
    # driver's current side (%A) is upstream, and `true` leaves it as the result.
    _git(repo, "config", f"merge.{MERGE_DRIVER}.name", "keep upstream; rebuilt after rebase")
    _git(repo, "config", f"merge.{MERGE_DRIVER}.driver", "true")
    attributes = repo / _git(repo, "rev-parse", "--git-path", "info/attributes").stdout.strip()
    attributes.parent.mkdir(parents=True, exist_ok=True)
    existing = attributes.read_text(encoding="utf-8").splitlines() if attributes.exists() else []
    lines = [f"{path} merge={MERGE_DRIVER}" for path in DERIVED_KEEP_UPSTREAM]
    missing = [line for line in lines if line not in existing]
    if missing:
        attributes.write_text("\n".join([*existing, *missing]) + "\n", encoding="utf-8")


def rebase_data_commit(repo: Path, *, remote: str, branch: str) -> tuple[bool, str]:
    mine = _rev(repo, "HEAD")
    _prefer_upstream_for_derived(repo)
    _git(repo, "fetch", remote, branch)
    upstream = _rev(repo, "FETCH_HEAD")

    if _git(repo, "rebase", upstream, check=False).returncode != 0:
        conflicted = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
        _git(repo, "rebase", "--abort", check=False)
        return False, (
            f"rebase conflict on {', '.join(conflicted) or 'unknown files'}: upstream changed the same "
            "data during this run. Not pushing; the next run starts from the new tip."
        )

    changed = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", mine).stdout.split()
    altered = [f for f in changed if f.endswith(".sqlite") and _rev(repo, f"HEAD:{f}") != _rev(repo, f"{mine}:{f}")]
    if altered:
        return False, f"{', '.join(altered)} differs from this run's output after rebase. Not pushing."

    if _rev(repo, "HEAD") == upstream:
        return True, f"commit dropped: upstream {upstream[:7]} already contains this run's changes"
    return True, f"rebased onto {upstream[:7]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    ok, message = rebase_data_commit(Path.cwd(), remote=args.remote, branch=args.branch)
    print(message if ok else f"::error::{message}", file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
