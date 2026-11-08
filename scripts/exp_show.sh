#!/usr/bin/env bash
# Show an experiment's config, rollback tag and run history.
set -euo pipefail
cd "$(dirname "$0")/.."

EXP="${1:?usage: exp_show.sh <exp-id>}"

if [ ! -f "experiments/$EXP/config.yaml" ]; then
  echo "error: no such experiment: $EXP" >&2
  exit 1
fi

echo "== config (experiments/$EXP/config.yaml) =="
cat "experiments/$EXP/config.yaml"

echo "== rollback tag =="
TAGS=$(git tag --list "exp/$EXP")
if [ -n "$TAGS" ]; then echo "$TAGS"; else echo "(not tagged yet -- merge to main first)"; fi

echo "== runs =="
if [ -d "experiments/$EXP/runs" ]; then
  ls -1 "experiments/$EXP/runs"
  LAST=$(ls -1 "experiments/$EXP/runs" | tail -1)
  if [ -f "experiments/$EXP/runs/$LAST/metrics.json" ]; then
    echo "== latest metrics =="
    cat "experiments/$EXP/runs/$LAST/metrics.json"
  fi
else
  echo "(no runs yet)"
fi
