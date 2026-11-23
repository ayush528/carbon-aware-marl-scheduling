"""Demand-uncertainty reserve: the one place calibrated uncertainty changes a plan.

exp011 (dispatch), exp016 (timing) and exp017 (capacity planning) each test a
different decision surface and each find that the carbon band cannot change a
decision: under national scaling the realized regional intensity is the forecast
times one common factor per slot, so the ordering the planner acts on is the
forecast's ordering and no band width can reorder two blocks.

Arrivals are the opposite case. The planner cannot see them, and the reserve it
holds for them measurably changes carbon and service (exp017: 784.0 kg at 3.4%
missed with a 30% reserve against 854.6 at 3.4% with none, slack fleet). So this
is where a calibrated quantile belongs -- and unlike the carbon band, it is a
one-sided quantity with a testable coverage claim, which the experiment reports.

The claims these tests protect:

* the predictor is causal -- it may use only slots strictly before the one it
  predicts, otherwise the reserve is fitted on the future it is hedging;
* the reserve is a *calibrated upper* bound on how much more work arrives than
  predicted, so it must be zero on a perfectly predictable stream and grow with
  the level asked for;
* the reserve never exceeds what a site can serve, or it would reserve the whole
  fleet and starve the planner.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.rl.arrival_risk import (
    exceedance_quantile,
    reserve_per_site_slot,
    trailing_predicted,
)


def test_a_perfectly_predictable_stream_needs_no_reserve() -> None:
    demand = np.full(40, 5_000.0)
    q = exceedance_quantile(demand, window=4, level=0.9)
    assert q == pytest.approx(0.0)


def test_the_predictor_uses_only_slots_before_the_one_it_predicts() -> None:
    demand = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    full = trailing_predicted(demand, window=2)
    # Rewriting everything from slot 3 on must not change predictions at 0..2.
    altered = demand.copy()
    altered[3:] = 1e6
    assert np.allclose(trailing_predicted(altered, window=2)[:3], full[:3])
    assert full[0] == pytest.approx(0.0)
    assert full[1] == pytest.approx(10.0)
    assert full[3] == pytest.approx(25.0)


def test_a_higher_level_never_reserves_less() -> None:
    rng = np.random.default_rng(0)
    demand = 5_000.0 + rng.normal(0.0, 800.0, 200).clip(0.0)
    low = exceedance_quantile(demand, window=6, level=0.5)
    high = exceedance_quantile(demand, window=6, level=0.95)
    assert 0.0 <= low <= high


def test_the_quantile_is_the_conformal_order_statistic() -> None:
    # A stream whose exceedance over the trailing mean is exactly 1..10.
    demand = np.array([0.0, 1.0, 3.0, 6.0, 10.0, 15.0, 21.0, 28.0, 36.0, 45.0, 55.0])
    q = exceedance_quantile(demand, window=1, level=0.9)
    # Predicted[t] = demand[t-1], so exceedances are 1..10; the 90% conformal
    # order statistic of ten values is the largest.
    assert q == pytest.approx(10.0)


def test_the_measured_coverage_matches_the_level() -> None:
    rng = np.random.default_rng(7)
    demand = 5_000.0 + rng.normal(0.0, 1_000.0, 400).clip(0.0)
    q = exceedance_quantile(demand, window=8, level=0.9)
    predicted = trailing_predicted(demand, window=8)
    excess = demand - predicted
    inside = float(np.mean(excess <= q))
    assert inside >= 0.85  # small-sample slack around the 0.9 target


def test_the_reserve_is_capped_by_what_a_site_can_serve() -> None:
    capacity = 45_000.0
    assert reserve_per_site_slot(1e12, n_sites=4, min_deadline=2, capacity=capacity) <= capacity
    assert reserve_per_site_slot(-5.0, n_sites=4, min_deadline=2, capacity=capacity) == 0.0


def test_the_reserve_is_spread_over_the_sites_and_the_tightest_window() -> None:
    q = 120_000.0
    # 4 sites, tightest deadline 2 slots: 120k / (4 * 2) = 15k per site-slot.
    assert reserve_per_site_slot(q, n_sites=4, min_deadline=2, capacity=1e9) == pytest.approx(
        15_000.0
    )
