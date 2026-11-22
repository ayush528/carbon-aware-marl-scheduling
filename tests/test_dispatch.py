"""Tests for the dispatch core (Phase 3, rung 4).

The dispatch core is the part of the scheduler that is pure and testable
without the external simulator: a risk-adjusted score per site, a
capacity-aware greedy allocation, and the carbon accounting of the result.

The properties pinned here are the ones the experiment's claims rest on:

1. A proportional (relative) band cannot change a score ranking -- adding
   ``lam * q * forecast`` to every site scales every score by ``(1 + lam*q)``.
   So a relative band produces the *same* dispatch as forecast-greedy. That is
   a theorem, and exp011 checks it in the run (flips must be 0), which is why
   it is pinned here too.
2. A site-specific *absolute* band can change the ranking, and only in the
   direction of preferring the site whose worst case is better.
3. Allocation respects capacity, spills in score order, and loses nothing:
   served + unserved = demand exactly (float-exact within tolerance).
"""

from __future__ import annotations

import math

import pytest

from carbon_scheduling.dispatch import (
    absolute_half_widths,
    allocate,
    carbon_kg,
    rank,
    relative_half_widths,
    risk_scores,
)

FORECAST = {"a": 100.0, "b": 120.0, "c": 200.0}


# --- scoring -------------------------------------------------------------


def test_relative_band_is_rank_preserving() -> None:
    """Scaling every score by the same factor cannot reorder the sites."""
    band = {site: 0.25 * value for site, value in FORECAST.items()}
    for lam in (0.0, 0.5, 1.0, 5.0):
        scores = risk_scores(FORECAST, band, lam)
        assert rank(scores) == rank(FORECAST)


def test_absolute_band_can_reorder_when_widths_differ() -> None:
    """A wide band on the low-carbon site can push it behind a narrow rival."""
    # 'a' is cheapest but has a huge band: worst case 100 + 90 = 190.
    # 'b' is dearer but tight: worst case 120 + 5 = 125.
    band = {"a": 90.0, "b": 5.0, "c": 1.0}
    assert rank(risk_scores(FORECAST, band, 0.0))[0] == "a"
    assert rank(risk_scores(FORECAST, band, 1.0))[0] == "b"
    # At a high enough lam the wide band sinks 'a' below every rival: the
    # 200 g/kWh site (band 1) has the tightest worst case of all.
    assert rank(risk_scores(FORECAST, band, 5.0)) == ["b", "c", "a"]


def test_zero_lam_is_forecast_greedy() -> None:
    band = {"a": 90.0, "b": 5.0, "c": 1.0}
    assert risk_scores(FORECAST, band, 0.0) == FORECAST


def test_scores_require_matching_site_sets() -> None:
    with pytest.raises(ValueError):
        risk_scores(FORECAST, {"a": 1.0, "b": 2.0}, 1.0)
    with pytest.raises(ValueError):
        risk_scores(FORECAST, {"a": 1.0, "b": 2.0, "c": 3.0}, -1.0)


def test_rank_breaks_ties_by_name_for_determinism() -> None:
    assert rank({"b": 1.0, "a": 1.0}) == ["a", "b"]


# --- allocation ----------------------------------------------------------


def test_allocation_fills_cheapest_first() -> None:
    alloc, unserved = allocate(
        {"a": 1.0, "b": 2.0},
        demand_gpu_seconds=60.0,
        capacity_gpu_seconds={"a": 40.0, "b": 40.0},
    )
    assert alloc == {"a": 40.0, "b": 20.0}
    assert unserved == 0.0


def test_allocation_spills_to_next_site_when_capacity_binds() -> None:
    alloc, unserved = allocate(
        {"a": 1.0, "b": 2.0},
        demand_gpu_seconds=100.0,
        capacity_gpu_seconds={"a": 40.0, "b": 40.0},
    )
    assert alloc == {"a": 40.0, "b": 40.0}
    assert unserved == pytest.approx(20.0)


def test_allocation_is_lossless() -> None:
    alloc, unserved = allocate(
        {"a": 3.0, "b": 1.0, "c": 2.0},
        demand_gpu_seconds=57.0,
        capacity_gpu_seconds={"a": 10.0, "b": 30.0, "c": 5.0},
    )
    assert sum(alloc.values()) + unserved == pytest.approx(57.0)


def test_allocation_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        allocate({"a": 1.0}, demand_gpu_seconds=-1.0, capacity_gpu_seconds={"a": 1.0})
    with pytest.raises(ValueError):
        allocate({"a": 1.0, "b": 2.0}, demand_gpu_seconds=1.0, capacity_gpu_seconds={"a": 1.0})


def test_allocation_of_zero_demand_touches_nothing() -> None:
    alloc, unserved = allocate({"a": 1.0}, demand_gpu_seconds=0.0, capacity_gpu_seconds={"a": 10.0})
    assert alloc == {"a": 0.0}
    assert unserved == 0.0


# --- accounting ----------------------------------------------------------


def test_carbon_is_energy_weighted_intensity() -> None:
    # 10 kWh at 100 g/kWh + 5 kWh at 200 g/kWh = 1000 + 1000 g = 2 kg
    assert carbon_kg({"a": 10.0, "b": 5.0}, {"a": 100.0, "b": 200.0}) == pytest.approx(2.0)


def test_carbon_requires_every_site_to_have_an_intensity() -> None:
    with pytest.raises(ValueError):
        carbon_kg({"a": 1.0}, {"b": 1.0})


# --- band construction ---------------------------------------------------


def test_absolute_half_widths_is_per_site_and_monotone_in_alpha() -> None:
    residuals = {
        "a": [float(v) for v in range(1, 41)],  # wide: up to 40
        "b": [1.0] * 40,  # perfectly forecastable
    }
    loose = absolute_half_widths(residuals, alpha=0.5)
    tight = absolute_half_widths(residuals, alpha=0.1)
    assert 1.0 < loose["a"] < tight["a"] <= 40.0
    assert loose["b"] == tight["b"] == 1.0


def test_relative_half_widths_returns_a_fraction_of_forecast() -> None:
    residuals = {"a": [10.0, 10.0, 10.0, 10.0]}
    forecasts = {"a": [100.0, 100.0, 100.0, 100.0]}
    q = relative_half_widths(residuals, forecasts, alpha=0.5)
    assert q["a"] == pytest.approx(0.1)


def test_band_construction_rejects_mismatched_inputs() -> None:
    with pytest.raises(ValueError):
        relative_half_widths({"a": [1.0]}, {"b": [1.0]}, alpha=0.5)
    with pytest.raises(ValueError):
        relative_half_widths({"a": []}, {"a": []}, alpha=0.5)
    with pytest.raises(ValueError):
        absolute_half_widths({"a": [math.inf]}, alpha=0.5)
