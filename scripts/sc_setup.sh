#!/usr/bin/env bash
# Fetch the external SustainCluster checkout that exp008+ drives.
#
# The simulator is third-party (MIT, HPE Labs) and too large to vendor, so it
# lives in external/sustain-cluster (gitignored). Its own venv also carries
# numpy/torch/gymnasium, which is why the drivers run under that interpreter
# while cwd is the checkout (upstream reads configs/ and data/ relatively).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${ROOT}/external/sustain-cluster"
REPO_URL="https://github.com/HewlettPackard/sustain-cluster.git"

mkdir -p "${ROOT}/external"

if [[ -d "${DEST}/.git" ]]; then
    echo "SustainCluster checkout already present: ${DEST}"
    git -C "${DEST}" rev-parse --short HEAD
elif [[ -d "${DEST}" ]]; then
    echo "Reusing existing checkout (no .git): ${DEST}"
else
    git clone --depth 1 "${REPO_URL}" "${DEST}"
fi

# The workload trace (~75 MB zip) is tracked upstream and auto-unzipped on the
# first run, so nothing else needs downloading.
if [[ ! -d "${DEST}/.venv" ]]; then
    echo "Creating ${DEST}/.venv ..."
    python3 -m venv "${DEST}/.venv"
    "${DEST}/.venv/bin/python" -m pip install --quiet --upgrade pip
    if command -v nvidia-smi >/dev/null 2>&1; then
        echo "GPU detected: installing the CUDA torch build (falls back to CPU at runtime)"
        "${DEST}/.venv/bin/python" -m pip install --quiet "torch==2.14.1+cu130" \
            --index-url https://download.pytorch.org/whl/cu130
        "${DEST}/.venv/bin/python" -m pip install --quiet -r "${DEST}/requirements.txt"
    else
        echo "No GPU detected: installing CPU-only torch"
        "${DEST}/.venv/bin/python" -m pip install --quiet torch \
            --index-url https://download.pytorch.org/whl/cpu
        "${DEST}/.venv/bin/python" -m pip install --quiet -r "${DEST}/requirements.txt"
    fi
fi

"${DEST}/.venv/bin/python" -c "import torch, gymnasium, pandas; print('sustaincluster env ok')"
echo "Done. Run: make exp-run EXP=exp008-sustaincluster-baseline"
