"""Timing rules: the yardsticks, and the properties that make them fair."""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.cluster import Site
from carbon_scheduling.rl import queue_rules as rules
from carbon_scheduling.rl.queue_env import QueueEnv

NOW = 0  # coast 0: offer everything


def _env(forecast, demand, deadlines=(2, 8), band=None):
    forecast = np.asarray(forecast, dtype=float)
    slots, sites = forecast.shape
    band = np.zeros_like(forecast) if band is None else np.asarray(band, dtype=float)
    return QueueEnv(
        forecast=forecast,
        realized=forecast.copy(),
        band=band,
        demand_tokens=np.asarray(demand, dtype=float),
        sites=[
            Site(
                name=f"s{i}",
                n_gpus=50,
                gpu_idle_w=100.0,
                gpu_peak_w=400.0,
                pue=1.0,
                tokens_per_gpu_second=1.0,
            )
            for i in range(sites)
        ],
        deadlines=list(deadlines),
    )


def test_run_now_offers_everything_and_last_slot_holds_everything() -> None:
    env = _env([[100.0, 100.0]] * 4, [4000.0, 0.0, 0.0, 0.0])
    assert rules.run_now(env, 0) == NOW
    assert rules.last_slot(env, 0) == rules.HOLD


def test_forecast_timing_waits_for_a_cheaper_slot_inside_the_window() -> None:
    # Class 0 may wait 2 slots (deadline 2), class 1 up to 8.
    env = _env([[100.0, 100.0], [50.0, 50.0], [10.0, 10.0], [100.0, 100.0]], [0.0, 0.0, 0.0, 0.0])
    # Deadline 2: offset 1 is the cheapest reachable slot, so it holds one slot.
    action = rules.forecast_timing(env, 0)
    assert env.wait_slots(0, action) == 1


def test_forecast_timing_serves_now_when_now_is_the_cheapest_slot() -> None:
    env = _env([[1.0, 1.0], [9.0, 9.0], [9.0, 9.0], [9.0, 9.0]], [0.0] * 4)
    assert env.wait_slots(1, rules.forecast_timing(env, 1)) == 0


def test_forecast_timing_never_looks_past_the_class_deadline() -> None:
    # The bargain is in slot 3, which a deadline-2 class cannot reach.
    env = _env([[100.0], [100.0], [1.0], [100.0]], [0.0] * 4, deadlines=(2, 8))
    action = rules.forecast_timing(env, 0)
    # Offsets it may use are 0 and 1; both cost 100, so the earliest wins.
    assert env.wait_slots(0, action) == 0


def test_band_timing_holds_off_when_the_improvement_is_inside_the_noise() -> None:
    # Future is 40 vs 50 now, but the band is 20: worst-case future (60) is
    # worse than the best-case present (30), so a risk-averse rule stays put.
    env = _env(
        [[50.0], [40.0], [40.0]],
        [0.0] * 3,
        deadlines=(2, 8),
        band=[[20.0], [20.0], [20.0]],
    )
    assert rules.band_timing(env, 0) == NOW


def test_band_timing_still_defers_when_the_improvement_is_large() -> None:
    env = _env(
        [[100.0], [10.0], [10.0]],
        [0.0] * 3,
        deadlines=(2, 8),
        band=[[5.0], [5.0], [5.0]],
    )
    assert env.wait_slots(0, rules.band_timing(env, 0)) == 1


def test_a_flat_forecast_serves_now_and_loses_nothing() -> None:
    env = _env([[100.0, 100.0]] * 4, [4000.0, 0.0, 0.0, 0.0])
    for rule in ("run_now", "forecast_timing", "band_timing"):
        summary = rules.run_rule(env, rule)
        assert summary["missed_fraction"] == pytest.approx(0.0), rule


def test_last_slot_costs_nothing_when_capacity_is_ample() -> None:
    """Capacity per slot is 90,000 GPU-s; one slot's arrivals fit easily."""
    # Twelve slots, so even the eight-slot class can reach its last legal slot
    # without falling off the end of the window.
    env = _env([[100.0, 100.0]] * 12, [2000.0, 2000.0] + [0.0] * 10)
    summary = rules.run_rule(env, "last_slot")
    assert summary["missed_fraction"] == pytest.approx(0.0)
    assert summary["served_gpu_s"] == pytest.approx(4000.0)


def test_deferring_into_a_clean_slot_cuts_carbon_at_the_same_volume() -> None:
    # Slot 1 is ten times cleaner and there is room for everything.
    forecast = [[1000.0], [10.0], [1000.0], [1000.0], [1000.0], [1000.0]]
    demand = [2000.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    now = rules.run_rule(_env(forecast, demand, deadlines=(2, 8)), "run_now")
    later = rules.run_rule(_env(forecast, demand, deadlines=(2, 8)), "forecast_timing")
    assert later["missed_fraction"] == pytest.approx(now["missed_fraction"])
    assert later["carbon_kg"] < now["carbon_kg"]


def test_unknown_rule_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown rule"):
        rules.run_rule(_env([[1.0]] * 2, [0.0, 0.0]), "oracle")
