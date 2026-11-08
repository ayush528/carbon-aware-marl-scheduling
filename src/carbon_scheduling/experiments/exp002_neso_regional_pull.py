"""exp002 -- live NESO regional pull vs the verified audit sample (London, week 1).

Exercise for the Phase 1 regional puller: fetch London (region 13),
2025-01-01 -> 2025-01-08 live from the NESO API and compare against the
committed audit sample downloaded during the feasibility study. The audit
sample is the oracle; if NESO revises history, the diff shows up here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from carbon_scheduling.data.neso import LONDON_REGION_ID, fetch_regional, parse_single_region
from carbon_scheduling.runner import REPO_ROOT

WINDOW_START = "2025-01-01T00:00Z"
WINDOW_END = "2025-01-08T00:00Z"


def run(config: dict[str, Any]) -> dict[str, Any]:
    sample_path = Path(config["data"][0])
    if not sample_path.is_absolute():
        sample_path = REPO_ROOT / sample_path
    sample = {r["from"]: r for r in parse_single_region(json.loads(sample_path.read_text()))}

    live_rows = fetch_regional(LONDON_REGION_ID, WINDOW_START, WINDOW_END)
    live = {r["from"]: r for r in live_rows}

    shared = sorted(set(sample) & set(live))
    diffs = [
        abs(sample[t]["forecast"] - live[t]["forecast"])
        for t in shared
        if sample[t]["forecast"] is not None and live[t]["forecast"] is not None
    ]
    return {
        "window": f"{WINDOW_START}/{WINDOW_END}",
        "region": f"{LONDON_REGION_ID} (London)",
        "n_sample": len(sample),
        "n_live": len(live),
        "n_shared_slots": len(shared),
        "n_forecast_compared": len(diffs),
        "forecast_mismatches": sum(1 for d in diffs if d != 0),
        "forecast_max_abs_diff": max(diffs) if diffs else 0,
        "forecast_mean_abs_diff": round(sum(diffs) / len(diffs), 6) if diffs else 0.0,
    }
