"""Rung 7: agents own queues, and decide *when* their own work runs.

The rung-6 experiment established that the fleet can place work well (site
ranking is exactly known under the national-scaling estimator) and that the
remaining lever is timing. This environment is built so a *single* agent can
act on that lever: it owns a work stream and a backlog, and chooses how long to
hold its own work before offering it. Nothing about one agent's choice forces
another agent to change, so deferral is unilateral instead of a joint action.

Four work classes share the fleet, one per agent, with different deadlines
(interactive to batch). The Azure trace has no latency labels, so arrivals are
split equally between the classes -- a disclosed modelling choice, identical for
every policy in an experiment, so comparisons stay matched.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.cluster import Site, site_energy_kwh
from carbon_scheduling.rl.queue_env import COAST, QueueEnv

NOW = 0  # coast 0: offer everything immediately
HOLD = len(COAST) - 1  # hold for the whole slack budget


def _sites(n: int = 2) -> list[Site]:
    return [
        Site(
            name=f"s{i}",
            n_gpus=10,
            gpu_idle_w=100.0,
            gpu_peak_w=400.0,
            pue=1.0,
            tokens_per_gpu_second=1.0,
        )
        for i in range(n)
    ]


def _env(demand, *, deadlines=(1, 4), forecast=None, realized=None, **kw):
    demand = np.asarray(demand, dtype=np.float64)
    slots, sites = len(demand), 2
    forecast = np.full((slots, sites), 100.0) if forecast is None else np.asarray(forecast, float)
    realized = forecast.copy() if realized is None else np.asarray(realized, float)
    return QueueEnv(
        forecast=forecast,
        realized=realized,
        band=np.zeros_like(forecast),
        demand_tokens=demand,
        sites=_sites(sites),
        deadlines=list(deadlines),
        **kw,
    )


def test_arrivals_are_split_equally_between_the_owning_agents() -> None:
    env = _env([400.0, 0.0], deadlines=(1, 4))
    assert env.queues[0][0] == pytest.approx(200.0)
    assert env.queues[1][0] == pytest.approx(200.0)


def test_nothing_runs_before_it_arrives() -> None:
    env = _env([0.0, 400.0])
    env.step([NOW] * env.n_agents)  # offer everything available this slot
    assert env.served_gpu_s == pytest.approx(0.0)


def test_serving_everything_now_leaves_no_backlog_when_capacity_allows() -> None:
    env = _env([2000.0, 0.0])
    for _ in range(env.n_slots):
        env.step([NOW] * env.n_agents)
    summary = env.summary()
    assert summary["missed_fraction"] == pytest.approx(0.0)
    assert summary["served_gpu_s"] == pytest.approx(2000.0)


def test_a_class_that_may_wait_is_not_served_until_it_asks() -> None:
    env = _env([2000.0, 0.0, 0.0, 0.0], deadlines=(1, 4))
    # Agent 1 holds its work; agent 0's class cannot wait, so it must run.
    env.step([NOW, HOLD])
    assert float(env.queues[1][0]) == pytest.approx(1000.0)
    assert 0 not in env.queues[0]


def test_a_coast_of_one_third_holds_work_for_a_third_of_the_slack() -> None:
    """The action is a fraction of the class's own slack, not a slot count."""
    env = _env([0.0] * 6, deadlines=(4, 4))
    assert [env.wait_slots(0, a) for a in range(env.n_actions)] == [0, 1, 2, 3]
    for i in range(env.n_agents):
        env.queues[i][0] = 500.0
        env.owned_gpu_s[i] = 500.0
    env.step([1, 0])  # class 0 holds one slot; class 1 serves immediately
    assert env.served_by_agent[1] == pytest.approx(500.0)
    assert env.served_by_agent[0] == pytest.approx(0.0)
    env.step([1, 0])  # class 0's hold is over
    assert env.served_by_agent[0] == pytest.approx(500.0)


def test_the_longest_coast_is_the_last_legal_slot_for_every_class() -> None:
    env = _env([0.0] * 8, deadlines=(2, 16))
    assert env.wait_slots(0, HOLD) == 1  # a one-slot budget has one slot of slack
    assert env.wait_slots(1, HOLD) == 15


def test_a_wait_longer_than_the_deadline_is_clamped_to_the_last_legal_slot() -> None:
    env = _env([1000.0, 0.0, 0.0], deadlines=(2, 2))
    env.step([HOLD, HOLD])  # the hold is 15 slots but the class has 2
    assert env.served_gpu_s == pytest.approx(0.0)
    env.step([HOLD, HOLD])  # its last legal slot
    assert env.served_gpu_s == pytest.approx(1000.0)
    while True:
        _, _, done, _, _ = env.step([HOLD, HOLD])
        if done:
            break
    assert env.summary()["missed_fraction"] == pytest.approx(0.0)


def test_a_miss_from_contention_is_charged_to_the_owner() -> None:
    # Capacity is 36,000 GPU-s per slot. Each class gets 20,000 in each of the
    # first two slots; class 1 holds its first arrival, so at t=1 the held work
    # competes with class 0's new work and 4,000 of it cannot run in time.
    env = _env([40000.0, 40000.0, 0.0, 0.0], deadlines=(1, 2))
    env.step([NOW, HOLD])
    env.step([NOW, HOLD])
    env.step([NOW, HOLD])  # the held remainder expires here
    assert env.violated_by_agent[0] == pytest.approx(0.0)
    assert env.violated_by_agent[1] == pytest.approx(4000.0)


def test_capacity_is_shared_and_the_tightest_deadline_is_served_first() -> None:
    # Two sites x 10 GPUs x 1800 s = 36,000 GPU-s of capacity per slot; offer
    # 40,000 in one slot so something must be dropped, and the class that
    # cannot wait must be the one that runs.
    env = _env([40000.0, 0.0], deadlines=(1, 4))
    env.step([NOW] * env.n_agents)
    assert env.served_gpu_s == pytest.approx(36000.0)
    assert env.violated_by_agent[0] == pytest.approx(0.0)  # tight class served
    assert env.violated_by_agent[1] == pytest.approx(0.0)  # loose class may wait
    assert float(sum(env.queues[1].values())) == pytest.approx(4000.0)


def test_placement_follows_the_forecast_and_carbon_follows_the_realized() -> None:
    # Site 0 looks clean and is dirty in reality; placement must trust the
    # forecast (that is what a scheduler has) and the bill must use reality.
    forecast = [[10.0, 90.0], [10.0, 90.0]]
    realized = [[500.0, 1.0], [500.0, 1.0]]
    env = _env([2000.0, 0.0], deadlines=(1, 4), forecast=forecast, realized=realized)
    env.step([NOW] * env.n_agents)
    assert env.served_by_site[0] == pytest.approx(2000.0)
    assert env.served_by_site[1] == pytest.approx(0.0)
    # All of it ran at site 0, whose real intensity is 500 while its forecast
    # said 10: the bill uses reality, the placement used the forecast.
    site0 = _sites(2)[0]
    load_kwh = site_energy_kwh(site0, 2000.0) - site_energy_kwh(site0, 0.0)
    idle_kg = sum(
        site_energy_kwh(site, 0.0) * intensity / 1000.0
        for site, intensity in zip(_sites(2), [500.0, 1.0], strict=True)
    )
    assert env.summary()["variable_carbon_kg"] == pytest.approx(load_kwh * 500.0 / 1000.0, abs=2e-3)
    assert env.summary()["carbon_kg"] == pytest.approx(
        load_kwh * 500.0 / 1000.0 + idle_kg, abs=2e-3
    )


def test_per_agent_carbon_sums_to_the_fleet_marginal_and_idle_is_separate() -> None:
    env = _env([2000.0, 2000.0], deadlines=(1, 4))
    total = np.zeros(env.n_agents)
    while True:
        _, rewards, done, _, _ = env.step([NOW] * env.n_agents)
        total += rewards
        if done:
            break
    carbon = env.summary()["carbon_kg"]
    idle = env.idle_carbon_kg
    # ``carbon_kg`` is reported rounded to a gram, so compare to that.
    assert carbon == pytest.approx(-total.sum() + idle, abs=2e-3)


def test_leftover_work_at_the_window_edge_counts_as_missed() -> None:
    env = _env([1000.0], deadlines=(1, 4))
    while True:
        _, _, done, _, _ = env.step([NOW] * env.n_agents)
        if done:
            break
    assert env.summary()["missed_fraction"] == pytest.approx(0.0)
    # Half of the arrivals belong to the class that cannot wait, so holding
    # loses exactly that half at the window edge.
    env = _env([1000.0], deadlines=(1, 8))
    while True:
        _, _, done, _, _ = env.step([HOLD, HOLD])
        if done:
            break
    assert env.summary()["missed_fraction"] == pytest.approx(0.5)


def test_one_agent_holding_does_not_withdraw_anybody_else_capacity() -> None:
    """Deferral is unilateral: no other agent's queue or capacity moves."""
    env = _env([2000.0, 0.0], deadlines=(1, 4))
    env.step([NOW, NOW])
    both_served = env.served_gpu_s
    env = _env([2000.0, 0.0], deadlines=(1, 4))
    env.step([NOW, HOLD])
    assert env.served_gpu_s == pytest.approx(both_served / 2.0)
    # The tight class ran in full either way: the holding agent only changed
    # its own work.
    assert env.violated_by_agent[0] == pytest.approx(0.0)
    assert float(sum(env.queues[1].values())) == pytest.approx(1000.0)


def test_communication_flag_changes_the_observation_size_and_nothing_else() -> None:
    loud = _env([2000.0, 0.0], deadlines=(1, 4), communicate=True)
    quiet = _env([2000.0, 0.0], deadlines=(1, 4), communicate=False)
    assert loud.obs_dim == quiet.obs_dim + 2
    for _ in range(2):
        loud.step([NOW, NOW])
        quiet.step([NOW, NOW])
    assert loud.summary()["carbon_kg"] == pytest.approx(quiet.summary()["carbon_kg"])


def test_band_flag_adds_one_feature() -> None:
    with_band = _env([2000.0], deadlines=(1, 4), include_band_in_obs=True)
    without = _env([2000.0], deadlines=(1, 4), include_band_in_obs=False)
    assert with_band.obs_dim == without.obs_dim + 1


def test_observations_are_finite_and_shaped_per_agent() -> None:
    env = _env([2000.0, 500.0, 0.0, 800.0], deadlines=(1, 4))
    obs, _ = env.reset()
    assert obs.shape == (env.n_agents, env.obs_dim)
    assert np.isfinite(obs).all()
    assert env.global_state().shape == (env.global_state_dim,)


def test_the_same_run_twice_gives_the_same_numbers() -> None:
    runs = []
    for _ in range(2):
        env = _env([2000.0, 500.0, 0.0, 800.0], deadlines=(1, 4))
        while True:
            _, _, done, _, _ = env.step([2, 0])
            if done:
                break
        runs.append(env.summary())
    assert runs[0] == runs[1]


def test_rejects_a_bad_action_and_mismatched_configuration() -> None:
    env = _env([1000.0], deadlines=(1, 4))
    with pytest.raises(ValueError):
        env.step([0, len(COAST)])
    with pytest.raises(ValueError):
        env.step([0])
    with pytest.raises(ValueError):
        _env([1000.0], deadlines=(0,))
    with pytest.raises(ValueError):
        QueueEnv(
            forecast=np.ones((4, 2)),
            realized=np.ones((4, 2)),
            band=np.zeros((4, 2)),
            demand_tokens=np.ones(3),  # wrong length
            sites=_sites(2),
            deadlines=[1, 4],
        )
