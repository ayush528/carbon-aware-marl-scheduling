#!/usr/bin/env bash
# Roll back to a tagged experiment state in an ISOLATED worktree --
# never touches your current tree or main.
#
# Usage:
#   scripts/rollback.sh <exp-id>              # read-only reproduction worktree
#   scripts/rollback.sh <exp-id> --continue   # new branch revive/<exp-id>
set -euo pipefail
cd "$(dirname "$0")/.."

EXP="${1:?usage: rollback.sh <exp-id> [--continue]}"
MODE="${2:-}"
TAG="exp/$EXP"

if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "error: tag $TAG not found. Tagged experiments:" >&2
  git tag --list 'exp/*' >&2
  exit 1
fi

DEST=".worktrees/$EXP"
if [ -e "$DEST" ]; then
  echo "error: $DEST already exists (remove it first: git worktree remove $DEST)" >&2
  exit 1
fi

if [ "$MODE" = "--continue" ]; then
  git worktree add -b "revive/$EXP" "$DEST" "$TAG"
else
  git worktree add --detach "$DEST" "$TAG"
fi

cat <<EOF
Experiment $EXP checked out at $DEST (tag $TAG).

To reproduce it exactly:
    cd $DEST
    make setup
    make exp-run EXP=$EXP
The new run's config_hash must match the one recorded in the tagged
runs/ directory -- that match is the reproducibility proof.

To continue development from that state, re-run with --continue.
EOF
