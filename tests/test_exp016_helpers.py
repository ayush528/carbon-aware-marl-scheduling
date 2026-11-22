"""The two helpers exp016's comparisons rest on.

Every claim in exp016 is a ratio against one of these, so an error here would
not crash anything -- it would just move a published percentage. They are
checked against the environment's own accounting and against hand-computed
answers.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.cluster import Site, site_energy_kwh
from carbon_scheduling.experiments.exp016_queue_ownership import _carbon, _oracle, objective
from carbon_scheduling.rl.queue_env import QueueEnv

NOW = 0


def _env(demand, *, forecast=None, realized=None, deadlines=(2, 4), n_gpus=10):
    demand = np.asarray(demand, dtype=np.float64)
    slots, sites = len(demand), 1 if forecast is None else np.asarray(forecast).shape[1]
    forecast = np.full((slots, sites), 100.0) if forecast is None else np.asarray(forecast, float)
    realized = forecast.copy() if realized is None else np.asarray(realized, float)
    site_list = [
        Site(
            name=f"s{i}",
            n_gpus=n_gpus,
            gpu_idle_w=100.0,
            gpu_peak_w=400.0,
            pue=1.0,
            tokens_per_gpu_second=1.0,
        )
        for i in range(sites)
    ]
    return QueueEnv(
        forecast=forecast,
        realized=realized,
        band=np.zeros_like(forecast),
        demand_tokens=demand,
        sites=site_list,
        deadlines=list(deadlines),
    )


def test_objective_is_carbon_plus_the_priced_misses() -> None:
    row = {"carbon_kg": 100.0, "missed_fraction": 0.25, "offered_gpu_s": 36000.0}
    # A quarter of 36,000 GPU-seconds is 9,000, which is 2.5 GPU-hours.
    assert objective(row, 1.0) == pytest.approx(102.5)
    assert objective(row, 0.5) == pytest.approx(101.25)
    # At price zero this is the carbon number, which is the carbon-only reading
    # that rewards shedding: that is why the price is always reported with it.
    assert objective(row, 0.0) == pytest.approx(100.0)


def test_objective_does_not_charge_for_being_on_time() -> None:
    row = {"carbon_kg": 42.0, "missed_fraction": 0.0, "offered_gpu_s": 36000.0}
    assert objective(row, 100.0) == pytest.approx(42.0)


def test_at_zero_volume_the_bound_is_exactly_the_idle_floor() -> None:
    """Serving nothing still means every site stands idle in every slot."""
    env = _env([2000.0, 2000.0])
    bound = _oracle(env, [2, 4], 100000.0, 0.0)
    assert bound["carbon_kg"] == pytest.approx(
        _carbon(np.zeros((1, env.n_slots, 1)), env.realized, env.sites), abs=2e-3
    )
    assert bound["missed_fraction"] == pytest.approx(1.0)


def test_the_bound_defers_into_the_cheap_slot_at_matched_volume() -> None:
    # One site, two slots: now is six times as dirty as the next slot, and the
    # workload is small enough that the fleet can hold all of it.
    env = _env([1000.0, 0.0], forecast=[[600.0], [100.0]])
    bound = _oracle(env, [2, 4], 100000.0, 1000.0)
    now = _carbon(np.array([[[1000.0], [0.0]]]), env.realized, env.sites)
    assert bound["carbon_kg"] < now
    # All of it ran in the clean slot: the answer is the load energy at 100.
    expected = _carbon(np.array([[[0.0], [1000.0]]]), env.realized, env.sites)
    assert bound["carbon_kg"] == pytest.approx(expected, abs=2e-3)


def test_the_bound_reports_the_service_it_was_asked_for() -> None:
    env = _env([2000.0, 2000.0])
    offered = float(env.demand_tokens.sum() / env.throughput)
    for volume in (0.0, 1000.0, 4000.0):
        bound = _oracle(env, [2, 4], 100000.0, volume)
        assert bound["missed_fraction"] == pytest.approx(1.0 - volume / offered)


def test_the_bounds_carbon_uses_the_environments_own_power_model() -> None:
    """_carbon and the environment must bill the same way, or every ratio moves."""
    env = _env([2000.0], forecast=[[100.0]], deadlines=(2, 4))
    env.step([NOW] * env.n_agents)
    served = env.served_gpu_s
    assert served > 0
    # One class, one slot, one site: the whole allocation is the served volume.
    alloc = np.array([[[served]]])
    assert _carbon(alloc, env.realized, env.sites) == pytest.approx(
        env.summary()["carbon_kg"], abs=2e-3
    )


def test_the_bound_charges_every_slot_the_environment_charges() -> None:
    """A slot the schedule leaves empty still bills the idle draw of each site."""
    env = _env([0.0, 0.0], forecast=[[10.0], [10.0]])
    site = env.sites[0]
    per_slot = site_energy_kwh(site, 0.0, 30) * 10.0 / 1000.0
    assert _carbon(np.zeros((1, 2, 1)), env.realized, env.sites) == pytest.approx(2 * per_slot)
