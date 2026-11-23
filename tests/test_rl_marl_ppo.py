"""Tests for IPPO/MAPPO and the CVaR tail term.

The risk term is where a mistake would be invisible: a CVaR that is really the
mean, or a tail penalty applied to the wrong agent, still trains and still
produces plausible curves. So the mechanics are checked on numbers whose answer
is known, and the learners are checked on a joint bandit where the right answer
is obvious.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.cluster import Site
from carbon_scheduling.rl.marl_env import MultiAgentEnv
from carbon_scheduling.rl.marl_ppo import (
    CVaRTracker,
    _gae_multi,
    cvar_adjustment,
    cvar_tail,
    evaluate_multi,
    rollout_multi,
    train_multi,
)
from carbon_scheduling.rl.numpy_net import ActorCritic

SLOT_TOKENS = 1800 * 3600


def test_cvar_tail_takes_the_worst_fraction() -> None:
    values = np.array([0.0, 0.0, 0.0, 10.0])
    # alpha=0.75 -> worst 25% of four samples -> the single 10.
    assert cvar_tail(values, 0.75) == pytest.approx(10.0)
    # alpha=0.5 -> worst half -> mean(0, 10)
    assert cvar_tail(values, 0.5) == pytest.approx(5.0)
    assert cvar_tail(values, 0.0) == pytest.approx(values.mean())


def test_cvar_tail_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        cvar_tail(np.array([]), 0.9)
    with pytest.raises(ValueError):
        cvar_tail(np.ones(3), 1.0)


def test_cvar_adjustment_is_zero_for_uniform_violations() -> None:
    violations = np.full((4, 2), 42.0)
    assert np.allclose(cvar_adjustment(violations, 0.9, 1.0), 0.0)


def test_cvar_adjustment_penalises_only_the_spiky_agent() -> None:
    violations = np.array([[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 8.0]])
    adjustment = cvar_adjustment(violations, 0.75, 1.0)
    assert adjustment[0] == pytest.approx(0.0)
    # Worst quarter of agent 1 is 8, its mean is 2 -> 6 GPU-seconds, times the
    # four slots of the episode (the mean charge it replaces is 4 x 2).
    assert adjustment[1] == pytest.approx(-4 * 6.0 / 3600.0)


def test_cvar_adjustment_is_scaled_by_the_episode_length() -> None:
    """The mean charge it replaces is ``T * mean``, so the tail gap must be too."""
    spike = np.array([[0.0], [0.0], [3600.0]])
    # Mean 1200; CVaR of the worst half is the mean of {3600, 0} = 1800.
    assert cvar_adjustment(spike, 0.5, 1.0)[0] == pytest.approx(-3 * 600.0 / 3600.0)
    # The same series over six slots pays more, not the same: T is in the units.
    longer = cvar_adjustment(np.vstack([spike, spike]), 0.5, 1.0)[0]
    assert abs(longer) > abs(cvar_adjustment(spike, 0.5, 1.0)[0])


def test_cvar_weight_scales_and_zero_disables() -> None:
    violations = np.array([[0.0], [10.0]])
    assert np.allclose(cvar_adjustment(violations, 0.5, 0.0), 0.0)
    # Mean is 5, CVaR of the worst half is 10 -> a 5 GPU-s gap over two slots.
    assert cvar_adjustment(violations, 0.5, 1.0)[0] == pytest.approx(-2 * 5.0 / 3600.0)
    assert cvar_adjustment(violations, 0.5, 2.0)[0] == pytest.approx(-2 * 10.0 / 3600.0)


def test_cvar_adjustment_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError):
        cvar_adjustment(np.ones(4), 0.9, 1.0)
    with pytest.raises(ValueError):
        cvar_adjustment(np.ones((4, 2)), 0.9, -1.0)


def test_gae_multi_matches_discounted_returns_per_agent() -> None:
    rewards = np.array([[1.0, 0.0], [0.0, 2.0], [3.0, 0.0]])
    values = np.zeros_like(rewards)
    dones = np.array([False, False, True])
    advantages, returns = _gae_multi(rewards, values, dones, gamma=0.5, lam=1.0)
    # Agent 0: 1 + 0.5*0 + 0.25*3; agent 1: 0 + 0.5*2 + 0.
    assert returns[0, 0] == pytest.approx(1.0 + 0.25 * 3.0)
    assert returns[0, 1] == pytest.approx(1.0)
    assert np.allclose(advantages, returns)


def make_env(n_slots: int = 4, demand: list[float] | None = None) -> MultiAgentEnv:
    sites = [Site(f"s{i}", 1, 100.0, 700.0, 1.0, 3600.0) for i in range(2)]
    return MultiAgentEnv(
        forecast=np.full((n_slots, 2), 100.0),
        realized=np.full((n_slots, 2), 100.0),
        band=np.full((n_slots, 2), 10.0),
        demand_tokens=np.array(demand if demand is not None else [SLOT_TOKENS] + [0.0] * 3),
        sites=sites,
        deadline_slots=2,
    )


def test_rollout_multi_returns_one_row_per_agent_per_slot() -> None:
    env = make_env()
    actors = [ActorCritic(env.obs_dim, env.n_actions, hidden=4, seed=i) for i in range(2)]
    batch = rollout_multi(env, actors, np.random.default_rng(0))
    steps = len(batch["rewards"])
    assert batch["obs"].shape == (steps, 2, env.obs_dim)
    assert batch["actions"].shape == (steps, 2)
    assert batch["advantages"].shape == (steps, 2)
    assert batch["violations"].shape == (steps, 2)
    assert batch["states"] is None
    assert set(batch["summary"]) >= {"carbon_kg", "sla_violation_fraction"}


def test_rollout_multi_collects_global_states_for_the_critic() -> None:
    env = make_env()
    actors = [ActorCritic(env.obs_dim, env.n_actions, hidden=4, seed=i) for i in range(2)]
    from carbon_scheduling.rl.numpy_net import ValueNet

    critic = ValueNet(env.global_state_dim, hidden=4)
    batch = rollout_multi(env, actors, np.random.default_rng(0), critic=critic)
    assert batch["states"].shape[1] == env.global_state_dim
    assert np.allclose(batch["values"][0, 0], batch["values"][0, 1])  # one shared critic


class Spiky:
    """Three slots; agent 1 is blamed for all 10 gpu-s of violation at the end."""

    n_agents = 2
    obs_dim = 4
    n_actions = 2
    global_state_dim = 3

    def __init__(self) -> None:
        self.violated_by_agent = np.zeros(2)

    def reset(self):
        self.t = 0
        self.violated_by_agent = np.zeros(2)
        return np.zeros((2, 4), dtype=np.float32), {}

    def step(self, actions):
        if self.t == 2:
            self.violated_by_agent[1] += 10.0
        self.t += 1
        rewards = np.zeros(2)
        return (
            np.zeros((2, 4), dtype=np.float32),
            rewards,
            self.t >= 3,
            False,
            {},
        )

    def global_state(self):
        return np.zeros(3, dtype=np.float32)

    def summary(self) -> dict[str, float]:
        return {"carbon_kg": 0.0, "sla_violation_fraction": 0.0}


def test_cvar_changes_the_terminal_reward_only() -> None:
    actors_for = lambda: [  # noqa: E731
        ActorCritic(4, 2, hidden=4, seed=i) for i in range(2)
    ]
    plain = rollout_multi(Spiky(), actors_for(), np.random.default_rng(1))
    risky = rollout_multi(
        Spiky(), actors_for(), np.random.default_rng(1), cvar_alpha=0.5, cvar_weight=1.0
    )
    steps = len(plain["rewards"])
    assert np.allclose(plain["rewards"][: steps - 1], risky["rewards"][: steps - 1])
    # Blamed series for agent 1 is [0, 0, 10]: mean 3.33, worst half (2, 10) -> 5,
    # and the gap is scaled by the three slots of the episode.
    assert risky["rewards"][-1, 0] == pytest.approx(0.0)
    assert risky["rewards"][-1, 1] == pytest.approx(-3 * (5.0 - 10.0 / 3.0) / 3600.0)


class JointBandit:
    """One joint step; every agent is rewarded for action 0."""

    n_agents = 2
    obs_dim = 4
    n_actions = 2
    global_state_dim = 3

    def reset(self):
        return np.zeros((2, 4), dtype=np.float32), {}

    def step(self, actions):
        rewards = np.array([1.0 if int(a) == 0 else 0.0 for a in actions])
        return np.zeros((2, 4), dtype=np.float32), rewards, True, False, {}

    def global_state(self):
        return np.zeros(3, dtype=np.float32)

    def summary(self) -> dict[str, float]:
        return {"carbon_kg": 0.0, "sla_violation_fraction": 0.0}


def test_ippo_learns_the_obvious_joint_action() -> None:
    actors, critic, history = train_multi(
        lambda _ep: JointBandit(),
        n_agents=2,
        obs_dim=4,
        n_actions=2,
        episodes=40,
        seed=3,
        lr=1e-2,
    )
    assert critic is None
    assert history[-1]["episode_return"] > 0.9
    for net in actors:
        assert int(np.argmax(net.forward(np.zeros(4))[0][0])) == 0


def test_mappo_learns_with_a_centralised_critic() -> None:
    actors, critic, history = train_multi(
        lambda _ep: JointBandit(),
        n_agents=2,
        obs_dim=4,
        n_actions=2,
        global_state_dim=3,
        centralized_critic=True,
        episodes=40,
        seed=3,
        lr=1e-2,
    )
    assert critic is not None
    assert history[-1]["episode_return"] > 0.9
    for net in actors:
        assert int(np.argmax(net.forward(np.zeros(4))[0][0])) == 0


def test_mappo_requires_a_global_state_dimension() -> None:
    with pytest.raises(ValueError):
        train_multi(
            lambda _ep: JointBandit(),
            n_agents=2,
            obs_dim=4,
            n_actions=2,
            centralized_critic=True,
            episodes=1,
        )


def test_evaluate_multi_runs_a_greedy_episode() -> None:
    env = make_env()
    actors = [ActorCritic(env.obs_dim, env.n_actions, hidden=4, seed=i) for i in range(2)]
    summary = evaluate_multi(env, actors)
    assert set(summary) >= {"carbon_kg", "sla_violation_fraction", "served_gpu_s"}


def test_per_step_cvar_is_neutral_at_zero_weight() -> None:
    tracker = CVaRTracker(2, alpha=0.9, weight=0.0)
    assert tracker.charge(np.array([0.0, 1e5])) == pytest.approx([0.0, 0.0])


def test_per_step_cvar_charges_nothing_while_the_series_is_flat() -> None:
    tracker = CVaRTracker(1, alpha=0.9, weight=1.0)
    charges = [tracker.charge(np.array([500.0]))[0] for _ in range(40)]
    assert sum(charges) == pytest.approx(0.0, abs=1e-12)


def test_per_step_cvar_charges_the_spike_and_nothing_else() -> None:
    tracker = CVaRTracker(1, alpha=0.9, weight=1.0)
    for _ in range(100):  # a quiet background first
        tracker.charge(np.array([100.0]))
    charges = [tracker.charge(np.array([v]))[0] for v in (100.0, 100.0, 50000.0)]
    assert charges[0] == pytest.approx(0.0, abs=1e-9)
    assert charges[1] == pytest.approx(0.0, abs=1e-9)
    # The spike is charged far above its mean share: costlier than the mean
    # price of the same violation would be.
    mean_charge = 50000.0 / 3600.0
    assert charges[2] < -mean_charge


def test_per_step_and_terminal_charge_the_same_quantity_on_a_long_series() -> None:
    """Summed over an episode the two attributions agree to a few percent."""
    rng = np.random.default_rng(3)
    series = np.concatenate([rng.gamma(1.0, 200.0, size=80), [4e4, 6e4, 1e3, 2e4]])
    alpha, weight = 0.8, 1.0

    tracker = CVaRTracker(1, alpha=alpha, weight=weight)
    per_step = sum(tracker.charge(np.array([v]))[0] for v in series)
    terminal = cvar_adjustment(series[:, None], alpha, weight)[0]
    assert per_step == pytest.approx(terminal, rel=0.25)


def test_per_step_cvar_needs_a_valid_alpha_and_history() -> None:
    with pytest.raises(ValueError):
        CVaRTracker(1, alpha=1.0, weight=1.0)
    with pytest.raises(ValueError):
        CVaRTracker(1, alpha=0.9, weight=-1.0)
    with pytest.raises(ValueError):
        CVaRTracker(1, alpha=0.9, weight=1.0, min_history=0)
    with pytest.raises(ValueError):
        CVaRTracker(2, alpha=0.9, weight=1.0).charge(np.array([1.0]))
