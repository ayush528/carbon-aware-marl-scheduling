"""Tests for the Phase 3 scheduling environment.

The env is where the paper's Phase 3 claim is made operational, so the
properties pinned here are the ones a reviewer would check first:

1. Determinism: same panel, same actions -> same episode, exactly.
2. Deadlines bind: work left past its deadline is a violation, and nothing is
   quietly dropped or double-counted.
3. Capacity binds: a site runs at most one slot's capacity, and the remainder
   stays queued for the next slot.
4. The band is an *observation*, and only when asked for: the ablation
   (with/without band in the observation) must change the observation
   dimension and nothing else about the dynamics.
5. Waiting is free of emissions but not free of cost: holding work accrues a
   penalty and every task still carries its deadline.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.cluster import Site
from carbon_scheduling.rl.env import SchedulingEnv

SITE = Site(
    name="s",
    n_gpus=1,
    gpu_idle_w=100.0,
    gpu_peak_w=700.0,
    pue=1.0,
    # 1 GPU, 3600 tokens/s -> a slot (1800 s) is 6,480,000 tokens of capacity.
    tokens_per_gpu_second=3600.0,
)
SLOT_TOKENS = SITE.n_gpus * 1800 * SITE.tokens_per_gpu_second


def make_env(
    *,
    n_slots: int = 4,
    n_sites: int = 2,
    forecast: list[list[float]] | None = None,
    realized: list[list[float]] | None = None,
    band: list[list[float]] | None = None,
    demand: list[float] | None = None,
    deadline_slots: int = 2,
    include_band: bool = True,
) -> SchedulingEnv:
    f = np.array(forecast if forecast is not None else [[100.0] * n_sites] * n_slots)
    r = np.array(realized if realized is not None else f.tolist())
    b = np.array(band if band is not None else [[10.0] * n_sites] * n_slots)
    d = np.array(demand if demand is not None else [0.0] * n_slots)
    return SchedulingEnv(
        forecast=f,
        realized=r,
        band=b,
        demand_tokens=d,
        sites=[SITE] * n_sites,
        deadline_slots=deadline_slots,
        include_band_in_obs=include_band,
    )


def test_reset_is_deterministic() -> None:
    env = make_env(demand=[SLOT_TOKENS, 0.0, 0.0, 0.0])
    obs_a, _ = env.reset()
    obs_b, _ = env.reset()
    assert np.array_equal(obs_a, obs_b)
    assert env.t == 0


def test_observation_contains_the_band_only_when_asked() -> None:
    with_band = make_env(include_band=True)
    without = make_env(include_band=False)
    assert with_band.obs_dim == without.obs_dim + 2  # two sites
    obs_with, _ = with_band.reset()
    obs_without, _ = without.reset()
    assert obs_with.shape == (with_band.obs_dim,)
    assert obs_without.shape == (without.obs_dim,)


def test_band_changes_the_observation_but_not_the_dynamics() -> None:
    wide = make_env(band=[[90.0, 1.0]] * 4, demand=[SLOT_TOKENS, 0, 0, 0])
    narrow = make_env(band=[[1.0, 1.0]] * 4, demand=[SLOT_TOKENS, 0, 0, 0])
    obs_wide, _ = wide.reset()
    obs_narrow, _ = narrow.reset()
    assert not np.array_equal(obs_wide, obs_narrow)
    # Same actions, same emissions: the band is information, not physics.
    wide.step(0)
    narrow.step(0)
    assert wide.carbon_kg == pytest.approx(narrow.carbon_kg)


def test_dispatch_emits_carbon_from_the_chosen_site() -> None:
    env = make_env(
        forecast=[[100.0, 200.0]] * 4,
        realized=[[100.0, 200.0]] * 4,
        demand=[SLOT_TOKENS, 0, 0, 0],
    )
    # Full slot at site 0: 1 GPU at peak 700 W for 0.5 h = 0.35 kWh -> 0.035 kg
    # on top of the idle draw every site pays anyway.
    idle = float(env.idle_carbon_kg[0].sum())
    env.step(0)
    assert env.carbon_kg - idle == pytest.approx(0.35 * 100.0 / 1000.0, rel=1e-6)


def test_capacity_binds_and_the_remainder_waits() -> None:
    env = make_env(
        realized=[[100.0, 200.0]] * 4,
        demand=[2 * SLOT_TOKENS, 0, 0, 0],
        deadline_slots=3,
    )
    _, _, _, _, info = env.step(0)
    assert info["served_gpu_s"] == pytest.approx(1800.0)
    # Half the work is still queued, and it kept its deadline.
    assert env.backlog == [(1800.0, 0 + 3)]
    assert env.t == 1


def test_waiting_costs_no_carbon_but_accrues_holding() -> None:
    env = make_env(realized=[[100.0, 100.0]] * 4, demand=[SLOT_TOKENS, 0, 0, 0])
    env.step(2)  # wait
    assert env.carbon_kg > 0  # idle draw only
    idle_only = env.carbon_kg
    assert env.held_gpu_s == pytest.approx(1800.0)
    assert idle_only < 0.35 * 100.0 / 1000.0  # less than actually running


def test_a_missed_deadline_is_a_violation_and_is_counted_once() -> None:
    env = make_env(
        realized=[[100.0, 100.0]] * 6,
        demand=[SLOT_TOKENS, 0, 0, 0, 0, 0],
        deadline_slots=2,
        n_slots=6,
    )
    env.step(2)  # wait: arrival at t=0 with deadline_slots=2 expires at t=2
    env.step(2)
    env.step(2)  # the start of this step is where it expires
    assert env.violated_gpu_s == pytest.approx(1800.0)
    assert env.violated_tasks == 1
    env.step(2)
    env.step(2)
    assert env.violated_gpu_s == pytest.approx(1800.0)  # not double-counted


def test_work_unfinished_at_the_end_of_the_window_is_a_violation() -> None:
    env = make_env(
        realized=[[100.0, 100.0]] * 2,
        demand=[3 * SLOT_TOKENS, 0],
        deadline_slots=10,
        n_slots=2,
    )
    env.step(0)  # runs one slot's worth, two slots' worth stays
    env.step(0)
    assert env.violated_gpu_s == pytest.approx(1800.0)
    summary = env.summary()
    # Offered 3 slots' worth, ran 2, so one third of the work missed out.
    assert summary["sla_violation_fraction"] == pytest.approx(1 / 3, abs=1e-4)


def test_summary_accounts_for_every_offered_gpu_second() -> None:
    """Nothing evaporates: served plus violated must equal offered."""
    env = make_env(
        realized=[[100.0, 200.0]] * 4,
        demand=[SLOT_TOKENS, SLOT_TOKENS, 0, 0],
        deadline_slots=2,
    )
    done = False
    for action in (0, 1, 2, 2):
        if done:
            break
        _, _, done, _, _ = env.step(action)
    s = env.summary()
    assert s["served_gpu_s"] + s["sla_violation_fraction"] * s["offered_gpu_s"] == pytest.approx(
        s["offered_gpu_s"], rel=1e-9
    )


def test_episode_ends_after_n_slots() -> None:
    env = make_env(n_slots=3)
    done = False
    steps = 0
    while not done:
        _, _, done, _, _ = env.step(2)
        steps += 1
    assert steps == 3


def test_actions_outside_the_space_are_rejected() -> None:
    env = make_env()
    with pytest.raises(ValueError):
        env.step(-1)
    with pytest.raises(ValueError):
        env.step(env.n_sites + 1)


def test_mismatched_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        make_env(forecast=[[100.0, 100.0]] * 2, band=[[1.0]] * 2)
    with pytest.raises(ValueError):
        make_env(demand=[0.0] * 3)
