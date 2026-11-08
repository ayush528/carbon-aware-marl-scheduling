"""Split-conformal prediction bands for carbon-intensity forecasts.

Method: split conformal calibration on absolute forecast residuals
(|actual - forecast|). The band half-width q is the finite-sample-corrected
empirical quantile of the calibration residuals:

    k = ceil((n + 1) * (1 - alpha));  q = sorted(residuals)[k - 1]

Under exchangeability this guarantees P(actual in [forecast - q, forecast + q])
>= 1 - alpha on held-out data. The Phase 1 exit test is empirical coverage
hitting the target on a held-out month the calibration never saw.

Everything here is deterministic -- no randomness, stdlib only (ADR-0002).
"""

from __future__ import annotations

import math
from typing import Any


def absolute_residuals(records: list[dict[str, Any]]) -> list[float]:
    """|actual - forecast| for every slot that has both; skips the rest."""
    return [
        abs(r["actual"] - r["forecast"])
        for r in records
        if r["actual"] is not None and r["forecast"] is not None
    ]


def conformal_quantile(residuals: list[float], alpha: float) -> float:
    """Finite-sample-corrected split-conformal half-width.

    Raises on empty residuals or alpha outside (0, 1). With k > n (tiny
    calibration sets) the guarantee is vacuous, so this returns +inf.
    """
    if not residuals:
        raise ValueError("no residuals to calibrate on")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    ordered = sorted(residuals)
    k = math.ceil((len(ordered) + 1) * (1 - alpha))
    if k > len(ordered):
        return math.inf
    return float(ordered[k - 1])


def coverage(records: list[dict[str, Any]], q: float) -> dict[str, Any]:
    """Empirical band coverage over records with known actuals."""
    residuals = absolute_residuals(records)
    if not residuals:
        raise ValueError("no records with both forecast and actual")
    n_inside = sum(1 for e in residuals if e <= q)
    n = len(residuals)
    return {
        "n_slots": n,
        "n_inside": n_inside,
        "coverage": n_inside / n,
        "band": f"[-{q}, +{q}] gCO2/kWh around forecast",
    }
