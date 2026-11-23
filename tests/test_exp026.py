"""Tests for exp026's plumbing (synthetic, no network, no full-year load).

The experiment's claim is a theorem plus a measurement, so the plumbing has to
be right in three specific ways:

1. a week is scored only on slots where *every* site has both a forecast and a
   realized value, or one policy would be judged on a different slot set;
2. the counterfactual at magnitude zero must reproduce the measured series
   exactly, or the anchor point is not an anchor;
3. the aggregate must count weeks rather than average away a week that got
   worse -- "never better" is a count, and an average can hide a loss.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from carbon_scheduling.experiments import exp026_uncertainty_cannot_reorder as exp026
from carbon_scheduling.uncertainty import COMMON_MULTIPLICATIVE, REGIONAL, classify

REGIONS = {"A": 1, "B": 2}
START = datetime(2024, 3, 4)


def _series(
    realized: dict[str, dict[datetime, float]],
) -> dict[str, dict[str, dict[datetime, float]]]:
    """A tiny series where forecast is flat and realized is given."""
    return {
        slug: {"forecast": {START: 100.0, START.replace(hour=1): 100.0}, "realized": rows}
        for slug, rows in realized.items()
    }


def test_cvar_is_the_mean_of_the_worst_tail() -> None:
    values = [float(v) for v in range(1, 21)]  # 1..20
    # 5% of 20 samples is one sample, so CVaR-95 is the single worst value.
    assert exp026._cvar(values, 0.95) == pytest.approx(20.0)
    # 10% of 20 samples is two samples, so CVaR-90 is the mean of the worst two.
    assert exp026._cvar(values, 0.90) == pytest.approx(np.mean([19.0, 20.0]))
    assert exp026._cvar([5.0], 0.9) == 5.0


def test_counterfactual_at_zero_is_the_identity() -> None:
    series = {
        "A": {"forecast": {START: 100.0}, "realized": {START: 110.0}},
        "B": {"forecast": {START: 200.0}, "realized": {START: 220.0}},
    }
    rng = np.random.default_rng(0)
    out = exp026._counterfactual_series(series, {"A": 1, "B": 2}, {"A": 0.0, "B": 0.0}, rng)
    assert out == series
    assert out is not series  # a copy: the caller's series must not be mutated


def test_counterfactual_keeps_the_forecast_and_breaks_the_common_factor() -> None:
    series = {
        "A": {"forecast": {START: 100.0}, "realized": {START: 100.0}},
        "B": {"forecast": {START: 200.0}, "realized": {START: 200.0}},
    }
    rng = np.random.default_rng(7)
    out = exp026._counterfactual_series(series, {"A": 1, "B": 2}, {"A": 0.3, "B": 0.3}, rng)
    assert out["A"]["forecast"] == series["A"]["forecast"]
    assert out["B"]["forecast"] == series["B"]["forecast"]
    realized = {s: out[s]["realized"][START] for s in out}
    forecast = {s: out[s]["forecast"][START] for s in out}
    # Independent draws make the shared factor disappear; at least it is no
    # longer the exact common-multiplicative structure of the real estimator.
    assert classify(realized, forecast) != COMMON_MULTIPLICATIVE
    assert classify(realized, forecast) in {REGIONAL, "common-additive"}


def test_week_frames_keeps_only_complete_slots() -> None:
    stamps = [START.replace(minute=0), START.replace(minute=30), START.replace(hour=1)]
    series = {slug: {"forecast": {}, "realized": {}} for slug in REGIONS}
    for i, stamp in enumerate(stamps):
        for slug in REGIONS:
            series[slug]["forecast"][stamp] = 100.0 + i
            series[slug]["realized"][stamp] = 110.0 + i
    # Remove one realized value: that slot must drop from every policy.
    del series["B"]["realized"][stamps[1]]

    tokens = np.arange(exp026.WEEK_SLOTS, dtype=float)
    slots, forecast, realized = exp026._week_frames(series, START, REGIONS, tokens)
    assert len(slots) == 2
    assert len(forecast) == len(realized) == len(slots)
    # Demand is laid positionally, so the kept slots keep their own tokens.
    assert [s["context_tokens"] for s in slots] == [0.0, 2.0]
    assert all(set(row) == set(REGIONS) for row in forecast)


def _week(name: str, delta: float, tail: float, reordered: float) -> dict:
    return {
        "policies": {
            "forecast_greedy": {
                "carbon_delta_pct": 0.0,
                "tail_delta_pct": 0.0,
                "reordered_pct": 0.0,
            },
            name: {
                "carbon_delta_pct": delta,
                "tail_delta_pct": tail,
                "reordered_pct": reordered,
            },
        }
    }


def test_aggregate_counts_weeks_instead_of_averaging_them_away() -> None:
    weeks = [
        _week("band", +0.10, 0.0, 5.0),
        _week("band", -0.01, 0.0, 5.0),  # one week genuinely better
        _week("band", +0.02, 0.0, 5.0),
    ]
    agg = exp026._aggregate(weeks)
    assert agg["n_weeks"] == 3
    row = agg["by_policy"]["band"]
    assert row["weeks_better"] == 1
    assert row["weeks_worse"] == 2
    assert row["best_carbon_delta_pct"] == pytest.approx(-0.01)
    assert row["worst_carbon_delta_pct"] == pytest.approx(0.10)
    # A mean of +0.037 would have hidden that one week improved; the counts do not.
    assert agg["any_band_week_better"] == 1
