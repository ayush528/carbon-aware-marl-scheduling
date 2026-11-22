"""Tests for the rung-6 multi-agent environment.

Rung 6 is the paper's headline structure -- per-region agents with limited
communication -- so the properties a reviewer will probe are pinned here:

1. Each agent sees its own region's carbon and only broadcast numbers about its
   peers; removing communication removes exactly those numbers.
2. Declining to serve really prices an agent out: it takes no load and emits
   only its idle draw.
3. The market fills the cheapest bid first and spills the remainder.
4. A missed deadline is blamed on the agents that refused capacity, so the
   incentive to free-ride is priced, not assumed away.
5. Nothing is lost in the accounting: served plus violated equals offered.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.cluster import Site, site_energy_kwh
from carbon_scheduling.rl.marl_env import OFFERS, MultiAgentEnv

SLOT_TOKENS = 1800 * 3600  # one GPU-slot at 3600 tokens/s


def site(name: str) -> Site:
    return Site(name, 1, 100.0, 700.0, 1.0, 3600.0)


def make_env(
    *,
    n_slots: int = 4,
    forecast: list[list[float]] | None = None,
    realized: list[list[float]] | None = None,
    band: list[list[float]] | None = None,
    demand: list[float] | None = None,
    deadline_slots: int = 2,
    communicate: bool = True,
    include_band: bool = True,
) -> MultiAgentEnv:
    n_agents = len(forecast[0]) if forecast else 2
    if forecast is not None:
        n_slots = len(forecast)  # the panel is the clock
    f = np.array(forecast if forecast is not None else [[100.0] * n_agents] * n_slots)
    r = np.array(realized if realized is not None else f.tolist())
    b = np.array(band if band is not None else [[10.0] * n_agents] * n_slots)
    d = np.array(demand if demand is not None else [0.0] * n_slots)
    return MultiAgentEnv(
        forecast=f,
        realized=r,
        band=b,
        demand_tokens=d,
        sites=[site(f"s{i}") for i in range(n_agents)],
        deadline_slots=deadline_slots,
        communicate=communicate,
        include_band_in_obs=include_band,
    )


def run(env: MultiAgentEnv, actions_per_slot) -> None:
    env.reset()
    for actions in actions_per_slot:
        _, _, done, _, _ = env.step(actions)
        if done:
            break


def test_reset_is_deterministic_and_observation_shapes_hold() -> None:
    env = make_env()
    first, _ = env.reset()
    second, _ = env.reset()
    assert np.array_equal(first, second)
    assert first.shape == (2, env.obs_dim)


def test_action_encoding_round_trips() -> None:
    env = make_env()
    for action in range(env.n_actions):
        lam, offer = env.decode(action)
        assert env.decode(env.encode(lam, offer)) == (lam, offer)
    assert env.encode(0.0, 1.0) == OFFERS.index(1.0)


def test_out_of_range_actions_are_rejected() -> None:
    env = make_env()
    with pytest.raises(ValueError):
        env.decode(env.n_actions)
    with pytest.raises(ValueError):
        env.step([0])
    with pytest.raises(ValueError):
        env.step([0, -1])


def test_agents_see_their_own_region_and_the_shared_clock() -> None:
    env = make_env(forecast=[[100.0, 200.0]] * 4, include_band=False, communicate=False)
    obs, _ = env.reset()
    assert obs[0].shape == obs[1].shape == (env.obs_dim,)
    # Shared features (sin/cos clock, queue, deadline) are identical; the local
    # carbon feature is not.
    assert obs[0, 0] == pytest.approx(obs[1, 0])
    assert obs[0, 4] != pytest.approx(obs[1, 4])
    # The first local feature is the region's own forecast.
    assert obs[0, 4] == pytest.approx(100.0 / 300.0, rel=1e-5)
    assert obs[1, 4] == pytest.approx(200.0 / 300.0, rel=1e-5)


def test_communication_adds_two_numbers_and_changes_nothing_else() -> None:
    linked = make_env(demand=[SLOT_TOKENS, 0, 0, 0], communicate=True)
    alone = make_env(demand=[SLOT_TOKENS, 0, 0, 0], communicate=False)
    assert linked.obs_dim == alone.obs_dim + 2
    linked.reset()
    alone.reset()
    _, rew_linked, _, _, info_linked = linked.step([3, 3])
    _, rew_alone, _, _, info_alone = alone.step([3, 3])
    assert info_linked["served_gpu_s"] == pytest.approx(info_alone["served_gpu_s"])
    assert np.allclose(rew_linked, rew_alone)


def test_a_declining_agent_serves_nothing_and_emits_only_idle_power() -> None:
    env = make_env(
        forecast=[[100.0, 100.0]] * 4,
        demand=[SLOT_TOKENS, 0, 0, 0],
    )
    decline = env.encode(0.0, 0.0)
    serve = env.encode(0.0, 1.0)
    _, rewards, _, _, _ = env.step([decline, serve])
    idle = site_energy_kwh(site("s0"), 0.0) * 100.0 / 1000.0
    running = site_energy_kwh(site("s0"), 1800.0) * 100.0 / 1000.0
    assert env.carbon_kg[0] == pytest.approx(idle, rel=1e-9)
    assert env.carbon_kg[1] == pytest.approx(running, rel=1e-9)
    assert rewards[1] < rewards[0]  # the working agent pays for the energy


def test_the_market_fills_the_cheapest_bid_then_spills() -> None:
    env = make_env(
        forecast=[[100.0, 200.0]] * 4,
        realized=[[100.0, 200.0]] * 4,
        demand=[1.5 * SLOT_TOKENS, 0, 0, 0],
    )
    serve = env.encode(0.0, 1.0)
    _, _, _, _, info = env.step([serve, serve])
    assert info["served_gpu_s"] == pytest.approx(1.5 * 1800.0)
    # The cheap site is saturated, the expensive one takes the half slot.
    assert env.last_served_share[0] == pytest.approx(1.0)
    assert env.last_served_share[1] == pytest.approx(0.5)
    expected = (
        site_energy_kwh(site("s0"), 1800.0) * 100.0 + site_energy_kwh(site("s1"), 900.0) * 200.0
    ) / 1000.0
    assert env.carbon_kg.sum() == pytest.approx(expected, rel=1e-9)


def test_a_risk_averse_bid_can_hand_the_slot_to_a_tighter_region() -> None:
    env = make_env(
        forecast=[[100.0, 120.0]] * 4,
        band=[[90.0, 1.0]] * 4,
        demand=[SLOT_TOKENS, 0, 0, 0],
    )
    greedy = env.encode(0.0, 1.0)
    cautious = env.encode(1.0, 1.0)
    env.step([greedy, greedy])
    assert env.last_served_share[0] == pytest.approx(1.0)
    env.reset()
    env.step([cautious, cautious])
    assert env.last_served_share[1] == pytest.approx(1.0)


def test_a_missed_deadline_is_blamed_on_the_agent_that_refused() -> None:
    env = make_env(
        forecast=[[100.0, 100.0]] * 6,
        demand=[2 * SLOT_TOKENS, 0, 0, 0, 0, 0],
        deadline_slots=1,
    )
    decline = env.encode(0.0, 0.0)
    serve = env.encode(0.0, 1.0)
    # Slot 0: one site works, the other refuses and the remainder ages out.
    _, rewards, _, _, _ = env.step([decline, serve])
    _, rewards_t1, _, _, info = env.step([decline, serve])
    assert info["expired_gpu_s"] == pytest.approx(SLOT_TOKENS / 3600.0)
    # All of the blame lands on the refuser; the working agent is barely
    # touched, and both are judged at the same step so the comparison is fair.
    assert env.violated_gpu_s == pytest.approx(1800.0)
    assert rewards_t1[1] - rewards_t1[0] > 0.4


def test_terminal_leftover_counts_as_a_violation() -> None:
    env = make_env(
        demand=[6 * SLOT_TOKENS, 0],
        deadline_slots=10,
        n_slots=2,
    )
    serve = env.encode(0.0, 1.0)
    run(env, [[serve, serve], [serve, serve]])
    # Six slots' worth offered, two sites x two slots served: two are left.
    assert env.violated_gpu_s == pytest.approx(2 * 1800.0)
    summary = env.summary()
    assert summary["sla_violation_fraction"] == pytest.approx(1 / 3, abs=1e-4)
    assert summary["served_gpu_s"] + summary["sla_violation_fraction"] * summary[
        "offered_gpu_s"
    ] == pytest.approx(summary["offered_gpu_s"], rel=1e-3)


def test_violation_blame_sums_to_the_system_total() -> None:
    env = make_env(
        forecast=[[100.0, 100.0]] * 4,
        demand=[3 * SLOT_TOKENS, 0, 0, 0],
        deadline_slots=1,
    )
    decline = env.encode(0.0, 0.0)
    serve = env.encode(0.0, 1.0)
    env.reset()
    env.step([decline, serve])
    env.step([decline, serve])
    assert env.violated_by_agent.sum() == pytest.approx(env.violated_gpu_s)
    assert env.violated_by_agent[0] == pytest.approx(env.violated_gpu_s)


def test_global_state_has_no_private_detail_per_agent() -> None:
    env = make_env()
    env.reset()
    state = env.global_state()
    assert state.shape == (env.global_state_dim,)
    assert env.global_state_dim == 4 + 2 * env.n_agents + 2


def test_one_throughput_for_all_agents_is_required() -> None:
    with pytest.raises(ValueError):
        MultiAgentEnv(
            forecast=np.full((2, 2), 100.0),
            realized=np.full((2, 2), 100.0),
            band=np.full((2, 2), 1.0),
            demand_tokens=np.zeros(2),
            sites=[site("a"), Site("b", 1, 100.0, 700.0, 1.0, 7200.0)],
        )


def test_exp013_builder_propagates_the_ablation_flags() -> None:
    """The communication and band ablations are flags of the same builder, so a
    variant really differs only in what the agents are allowed to see."""
    from datetime import datetime, timedelta

    from carbon_scheduling.experiments import exp013_marl_dispatch as exp013

    start = datetime(2024, 5, 10)
    stamps = [start - timedelta(days=28) + timedelta(minutes=30 * i) for i in range(28 * 48 + 336)]
    series = {
        "GB-London": {
            "forecast": {t: 100.0 for t in stamps},
            "realized": {t: 110.0 for t in stamps},
        }
    }
    config = {
        "calibration_days": 28,
        "deadline_slots": 8,
        "sla_penalty_kg_per_kwh": 1.0,
        "hold_penalty_kg_per_kwh": 0.05,
    }
    tokens = np.full(336, 1_000.0)
    sites = [site("s0")]
    common = {
        "series": series,
        "tokens": tokens,
        "sites": sites,
        "names": ["GB-London"],
        "start": start,
        "config": config,
    }
    full = exp013._build(communicate=True, include_band=True, **common)
    quiet = exp013._build(communicate=False, include_band=True, **common)
    blind = exp013._build(communicate=True, include_band=False, **common)
    assert full.obs_dim == quiet.obs_dim + 2
    assert full.obs_dim == blind.obs_dim + 1
    assert full.global_state_dim == blind.global_state_dim + 1
