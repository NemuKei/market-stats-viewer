#!/usr/bin/env bash
set -euo pipefail

branch="${GITHUB_REF_NAME:-main}"
git check-ref-format "refs/heads/$branch"

# A generated SQLite/LP snapshot must be based on the current remote tree.
# Never rebase a completed generation onto a different input snapshot.
git fetch --quiet origin "refs/heads/$branch:refs/remotes/origin/$branch"
base_sha="$(git rev-parse HEAD^)"
remote_sha="$(git rev-parse "refs/remotes/origin/$branch")"
if [ "$remote_sha" != "$base_sha" ]; then
  echo "Remote $branch advanced; discard this generated snapshot and rerun from the current branch." >&2
  exit 1
fi

# A concurrent push after the fetch is rejected by Git's fast-forward check.
git push origin "HEAD:refs/heads/$branch"
