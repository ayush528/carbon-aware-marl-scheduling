"""exp004 -- split-conformal forecast bands, calibrated Jan 2025, tested Feb 2025.

The Phase 1 exit test: calibrate the band half-width on January's national
forecast-vs-actual residuals (committed audit sample), then evaluate
empirical coverage on the held-out month (February 2025) the calibration
never saw. Target coverage 90% (alpha = 0.1), finite-sample corrected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from carbon_scheduling.bands import absolute_residuals, conformal_quantile, coverage
from carbon_scheduling.data.neso import load_slot_json
from carbon_scheduling.runner import REPO_ROOT

ALPHA = 0.1


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {p.name: p for p in paths}

    january = load_slot_json(by_name["uk_national_2025-01_full_month.json"])
    february = load_slot_json(by_name["uk_national_2025-02.json"])

    calib_residuals = absolute_residuals(january)
    q = conformal_quantile(calib_residuals, alpha=ALPHA)

    calib = coverage(january, q)
    held_out = coverage(february, q)
    feb_residuals = absolute_residuals(february)

    return {
        "alpha": ALPHA,
        "n_calibration": len(calib_residuals),
        "band_half_width_gco2_per_kwh": round(q, 3),
        "calibration_coverage": round(calib["coverage"], 4),
        "holdout_n_slots": held_out["n_slots"],
        "holdout_coverage": round(held_out["coverage"], 4),
        "holdout_mae_gco2_per_kwh": round(sum(feb_residuals) / len(feb_residuals), 3),
    }
