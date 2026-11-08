"""Tests for split-conformal forecast bands (the project's core method).

Expected values are hand-worked literals, not recomputed outputs: for
residuals 1..10 (n=10), the finite-sample corrected split-conformal
quantile at alpha is sorted[k-1] with k = ceil((n+1)*(1-alpha)):
  alpha=0.1 -> k = ceil(9.9)  = 10 -> q = 10
  alpha=0.2 -> k = ceil(8.8)  = 9  -> q = 9
  alpha=0.5 -> k = ceil(5.5)  = 6  -> q = 6
"""

from __future__ import annotations

import pytest

from carbon_scheduling.bands import absolute_residuals, conformal_quantile, coverage

RECORDS = [
    {"forecast": 100, "actual": 90},  # residual 10
    {"forecast": 100, "actual": 105},  # residual 5
    {"forecast": 200, "actual": 195},  # residual 5
    {"forecast": 50, "actual": 49},  # residual 1
    {"forecast": 80, "actual": None},  # skipped (no actual yet)
]


def test_absolute_residuals_ignores_missing_actuals() -> None:
    residuals = absolute_residuals(RECORDS)
    assert residuals == [10.0, 5.0, 5.0, 1.0]


def test_conformal_quantile_hand_worked_values() -> None:
    residuals = [float(x) for x in range(1, 11)]
    assert conformal_quantile(residuals, alpha=0.1) == 10.0
    assert conformal_quantile(residuals, alpha=0.2) == 9.0
    assert conformal_quantile(residuals, alpha=0.5) == 6.0


def test_conformal_quantile_ignores_order() -> None:
    residuals = [10.0, 1.0, 9.0, 2.0, 8.0, 3.0, 7.0, 4.0, 6.0, 5.0]
    assert conformal_quantile(residuals, alpha=0.1) == 10.0


def test_conformal_quantile_empty_raises() -> None:
    with pytest.raises(ValueError):
        conformal_quantile([], alpha=0.1)


def test_coverage_counts_slots_inside_band() -> None:
    # q = 5: residuals 10, 5, 5, 1 -> inside: 3 of 4
    stats = coverage(RECORDS, q=5.0)
    assert stats["n_slots"] == 4
    assert stats["n_inside"] == 3
    assert stats["coverage"] == pytest.approx(0.75)
    assert stats["band"] == "[-5.0, +5.0] gCO2/kWh around forecast"


def test_coverage_no_actuals_raises() -> None:
    with pytest.raises(ValueError):
        coverage([{"forecast": 1, "actual": None}], q=5.0)
