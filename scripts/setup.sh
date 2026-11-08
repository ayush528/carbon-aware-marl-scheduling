#!/usr/bin/env bash
# One-time environment setup: virtualenv + pinned deps + editable install.
set -euo pipefail
cd "$(dirname "$0")/.."

# Prefer uv when available (fast; avoids the missing-python3-venv trap on
# Debian/Ubuntu); fall back to the stdlib venv module.
if command -v uv >/dev/null 2>&1; then
  if [ ! -x .venv/bin/python ]; then
    uv venv .venv --python python3
  fi
  UV_PY="--python .venv/bin/python"
  uv pip install $UV_PY -r requirements-dev.txt
  uv pip install $UV_PY -e . --no-deps
else
  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements-dev.txt
  ./.venv/bin/pip install -e . --no-deps
fi

echo
echo "Setup complete. Activate with:  source .venv/bin/activate"
echo "Then run:                       make test"
