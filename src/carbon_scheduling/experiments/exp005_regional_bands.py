"""exp005 -- regional conformal bands via national scaling (the disclosed estimator).

The NESO regional API ships no actuals (exp003), so regional error is
estimated exactly as the national residual scaled by the forecast ratio
(see bands.regional_residuals). Per region: calibrate the band half-width
on January 2025 residuals, evaluate empirical coverage on the held-out
month (February 2025). Target coverage 90% (alpha = 0.1) per region.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from carbon_scheduling.bands import conformal_quantile, regional_residuals
from carbon_scheduling.data.neso import load_slot_json, read_tidy_csv
from carbon_scheduling.runner import REPO_ROOT

ALPHA = 0.1
TARGET = 1 - ALPHA  # 0.90


def _by_region(
    records: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        grouped[r["regionid"]].append(r)
    return dict(grouped)


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {p.name: p for p in paths}

    national_jan = load_slot_json(by_name["uk_national_2025-01_full_month.json"])
    national_feb = load_slot_json(by_name["uk_national_2025-02.json"])
    regional_jan = _by_region(read_tidy_csv(by_name["uk_regional_2025-01_tidy.csv"]))
    regional_feb = _by_region(read_tidy_csv(by_name["uk_regional_2025-02_tidy.csv"]))

    regions = sorted(set(regional_jan) & set(regional_feb))
    per_region: dict[str, Any] = {}
    coverages: list[float] = []
    for rid in regions:
        calib = regional_residuals(regional_jan[rid], national_jan)
        q = conformal_quantile(calib, alpha=ALPHA)
        holdout = regional_residuals(regional_feb[rid], national_feb)
        cov = sum(1 for e in holdout if e <= q) / len(holdout)
        coverages.append(cov)
        per_region[str(rid)] = {
            "n_calibration": len(calib),
            "band_half_width_gco2_per_kwh": round(q, 3),
            "holdout_n_slots": len(holdout),
            "holdout_coverage": round(cov, 4),
        }

    n_at_target = sum(1 for c in coverages if c >= TARGET)
    return {
        "alpha": ALPHA,
        "target_coverage": TARGET,
        "n_regions": len(regions),
        "mean_coverage": round(sum(coverages) / len(coverages), 4),
        "min_coverage": round(min(coverages), 4),
        "max_coverage": round(max(coverages), 4),
        "n_regions_at_target": n_at_target,
        "per_region": per_region,
    }
