#!/usr/bin/env bash
# Scaffold a new experiment from experiments/_template.
# The config is committed BEFORE the experiment is run (see PROJECT.md protocol).
set -euo pipefail
cd "$(dirname "$0")/.."

ID="${1:?usage: exp_new.sh <expNNN-slug>}"
DIR="experiments/$ID"

if [ -e "$DIR" ]; then
  echo "error: $DIR already exists" >&2
  exit 1
fi
if [[ ! "$ID" =~ ^exp[0-9]{3}-[a-z0-9-]+$ ]]; then
  echo "error: id must match expNNN-slug (lowercase, hyphenated), got: $ID" >&2
  exit 1
fi

cp -r experiments/_template "$DIR"
sed -i "s/expNNN-slug/$ID/" "$DIR/config.yaml"

cat <<EOF
Created $DIR.

Protocol:
  1. Edit $DIR/config.yaml -- state the hypothesis being tested.
  2. Add the experiment function in src/carbon_scheduling/experiments/ and
     register it in that package's __init__.py.
  3. List it in experiments/registry.yaml.
  4. COMMIT the config, then run:  make exp-run EXP=$ID
  5. Commit the run records under $DIR/runs/.
  6. Merge to main; the merge gets tagged exp/$ID (the rollback point).
EOF
