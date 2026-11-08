"""exp003 -- regional matrix validation + the regional-actuals gap.

Checks the 14-region x January-2025 matrix (data/uk_regional_2025-01_tidy.csv,
produced by scripts/pull_regional_matrix.py) against the committed audit
samples, and pins the load-bearing Phase 1 finding: the NESO regional
endpoint ships NO actual intensities (verified live on 2026-11-09 for
historical AND recent windows). Regional actuals must therefore be estimated
as national actual x (regional forecast / national forecast) -- the audit's
disclosed-mitigation path (findings-and-plan.md, risk table).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from carbon_scheduling.data.neso import parse_single_region, read_tidy_csv
from carbon_scheduling.runner import REPO_ROOT


def _rel(rel: str) -> Path:
    path = Path(rel)
    return path if path.is_absolute() else REPO_ROOT / path


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {Path(p).name: p for p in paths}

    matrix = read_tidy_csv(by_name["uk_regional_2025-01_tidy.csv"])

    # 1. grid shape: 14 DNO regions x identical slot count
    slots_per_region: dict[int, int] = defaultdict(int)
    for r in matrix:
        slots_per_region[r["regionid"]] += 1
    counts = set(slots_per_region.values())

    # 2. the actuals gap (drives the national-scaling strategy)
    n_with_actual = sum(1 for r in matrix if r["actual"] is not None)

    # 3. forecast consistency: London matrix rows vs single-region month sample
    london_month = parse_single_region(
        json.loads(by_name["uk_region13_london_2025-01_full_month.json"].read_text())
    )
    london_sample = {r["from"]: r["forecast"] for r in london_month}
    london_matrix = {r["from"]: r["forecast"] for r in matrix if r["regionid"] == 13}
    diffs = [
        abs(london_sample[t] - london_matrix[t])
        for t in london_sample.keys() & london_matrix.keys()
    ]

    # 4. verified literals from the bulk audit sample (2025-01-01T12:00Z)
    bulk = json.loads(by_name["uk_regional_all_2025-01-01_to_2025-01-02.json"].read_text())
    probe = next(s for s in bulk["data"] if s["from"] == "2025-01-01T12:00Z")
    bulk_fx = {r["regionid"]: r["intensity"]["forecast"] for r in probe["regions"]}
    matrix_fx = {r["regionid"]: r["forecast"] for r in matrix if r["from"] == "2025-01-01T12:00Z"}
    literal_checks = {
        "region3_forecast_4": matrix_fx.get(3) == bulk_fx.get(3) == 4,
        "london_forecast_56": matrix_fx.get(13) == bulk_fx.get(13) == 56,
    }

    return {
        "n_regions": len(slots_per_region),
        "slots_per_region": sorted(counts),
        "n_rows": len(matrix),
        "n_with_actual": n_with_actual,
        "london_forecast_slots_compared": len(diffs),
        "london_forecast_mismatches": sum(1 for d in diffs if d != 0),
        "london_forecast_max_abs_diff": max(diffs) if diffs else 0,
        "verified_literal_checks": literal_checks,
    }
