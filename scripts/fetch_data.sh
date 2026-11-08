#!/usr/bin/env bash
# Re-fetch the audit datasets (catalog + URLs: docs/datasets/DATASETS.md).
# Raw downloads land in docs/datasets/data-audit/downloads/ (large CSVs are
# gitignored; small evidence JSONs are committed).
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-uk-month}"
SCRIPTS="docs/datasets/data-audit/scripts"
PY=".venv/bin/python"

case "$TARGET" in
  uk-day)   "$PY" "$SCRIPTS/fetch_uk_carbon.py" ;;
  uk-month) "$PY" "$SCRIPTS/fetch_uk_carbon_month.py" ;;
  *)
    echo "usage: fetch_data.sh [uk-day|uk-month]" >&2
    exit 1
    ;;
esac
