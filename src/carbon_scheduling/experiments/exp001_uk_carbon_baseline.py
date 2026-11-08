"""exp001 -- baseline statistics of NESO national carbon intensity (Jan 2025).

Deterministic reference experiment: validates the loader, the runner's
hashing/reproducibility contract, and pins the January-2025 national numbers
that Phase 1 (data freeze) must reproduce.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from carbon_scheduling.carbon import load_neso_carbon, summarise
from carbon_scheduling.runner import REPO_ROOT


def run(config: dict[str, Any]) -> dict[str, Any]:
    data_path = Path(config["data"][0])
    if not data_path.is_absolute():
        data_path = REPO_ROOT / data_path
    records = load_neso_carbon(data_path)
    return summarise(records)
