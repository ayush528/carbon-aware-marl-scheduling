"""Tests for the numpy actor-critic and PPO plumbing.

Two failure modes matter here and both are cheap to catch:

* Hand-written backprop that does not match the loss it claims to minimise.
  The gradient check below compares every parameter's analytic gradient with a
  central finite difference, so a sign error or a missing term fails loudly
  instead of training a slightly-wrong policy for hours.
* A training loop that runs but learns nothing because the advantages, the
  clipping or the bootstrap are wrong. The bandit test makes the right action
  obvious, so "PPO finds it" is a real assertion.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.rl.numpy_net import ActorCritic, Adam
from carbon_scheduling.rl.ppo import _gae, rollout, train


def _make_net(seed: int = 0, n_actions: int = 3) -> ActorCritic:
    return ActorCritic(obs_dim=4, n_actions=n_actions, hidden=5, seed=seed)


def test_forward_shapes_and_probabilities() -> None:
    net = _make_net()
    logits, probs, value = net.forward(np.zeros((2, 4)))
    assert logits.shape == (2, 3)
    assert probs.shape == (2, 3)
    assert value.shape == (2,)
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_analytic_gradients_match_finite_differences() -> None:
    net = _make_net()
    # Keep every hidden pre-activation away from the ReLU kink, where a central
    # difference is not a derivative. Negative observations then say nothing
    # about whether the gradient is right.
    net.params["W1"] = np.abs(net.params["W1"]) + 0.1
    net.params["b1"] = np.full_like(net.params["b1"], 0.5)
    rng = np.random.default_rng(1)
    obs = rng.normal(size=(6, 4))
    actions = rng.integers(0, 3, size=6)
    old_logp = np.log(np.full(6, 1 / 3))
    advantages = rng.normal(size=6)
    returns = rng.normal(size=6)
    kwargs = dict(clip=10.0, vf_coef=0.5, ent_coef=0.02)  # no clipping here

    _, grads, _ = net.loss_and_grads(obs, actions, old_logp, advantages, returns, **kwargs)

    def loss() -> float:
        total, _, _ = net.loss_and_grads(obs, actions, old_logp, advantages, returns, **kwargs)
        return total

    eps = 1e-6
    for name, param in net.params.items():
        numeric = np.zeros_like(param)
        flat = param.reshape(-1)
        for i in range(flat.size):
            original = flat[i]
            flat[i] = original + eps
            plus = loss()
            flat[i] = original - eps
            minus = loss()
            flat[i] = original
            numeric.reshape(-1)[i] = (plus - minus) / (2 * eps)
        assert np.allclose(grads[name], numeric, atol=1e-9, rtol=1e-6), name


def test_policy_gradient_is_zero_when_the_action_is_already_certain() -> None:
    """With a saturated policy the policy term contributes (almost) nothing."""
    net = _make_net()
    for key, value in net.params.items():
        net.params[key] = np.zeros_like(value)
    net.params["b1"] = np.ones_like(net.params["b1"])  # hidden units fire
    net.params["Wp"][0, 0] = 50.0  # action 0 dominates for any positive input
    obs = np.ones((1, 4))
    _, grads, diag = net.loss_and_grads(
        obs, np.array([0]), np.array([0.0]), np.array([1.0]), np.array([0.0]), ent_coef=0.0
    )
    assert diag["entropy"] < 1e-6
    assert np.allclose(grads["Wp"][0], 0.0, atol=1e-6)


def test_adam_moves_parameters_against_the_gradient() -> None:
    net = _make_net()
    optimiser = Adam(net.params, lr=0.1)
    before = net.params["bp"].copy()
    optimiser.step(net.params, {k: np.ones_like(v) for k, v in net.params.items()})
    assert np.all(net.params["bp"] < before + 1e-12)


def test_gae_reduces_to_discounted_return_without_bootstrapping() -> None:
    rewards = [1.0, 0.0, 2.0]
    values = [0.0, 0.0, 0.0]
    dones = [False, False, True]
    advantages, returns = _gae(rewards, values, dones, gamma=0.5, lam=1.0)
    # Terminal at the end: advantages are exactly the discounted returns.
    assert returns[2] == pytest.approx(2.0)
    assert returns[1] == pytest.approx(0.5 * 2.0)
    assert returns[0] == pytest.approx(1.0 + 0.5 * (0.5 * 2.0))


class Bandit:
    """One-step environment: action 0 pays 1, action 1 pays 0."""

    obs_dim = 4
    n_slots = 1
    n_sites = 1
    action_space = 2

    def reset(self):
        return np.zeros(self.obs_dim, dtype=np.float32), {}

    def step(self, action):
        reward = 1.0 if action == 0 else 0.0
        return np.zeros(self.obs_dim, dtype=np.float32), reward, True, False, {}

    def summary(self) -> dict[str, float]:
        return {"carbon_kg": 0.0, "sla_violation_fraction": 0.0}


def test_ppo_learns_an_obvious_bandit() -> None:
    net = ActorCritic(obs_dim=4, n_actions=2, hidden=4, seed=0)
    history = train(lambda _ep: Bandit(), net, episodes=40, seed=3, lr=1e-2)
    assert history[-1]["episode_return"] > 0.9
    logits, _, _ = net.forward(np.zeros(4))
    assert int(np.argmax(logits[0])) == 0


def test_rollout_reports_the_episode_and_shapes() -> None:
    from carbon_scheduling.cluster import Site
    from carbon_scheduling.rl.env import SchedulingEnv

    site_a = Site("a", 1, 100.0, 700.0, 1.0, 3600.0)
    site_b = Site("b", 1, 100.0, 700.0, 1.0, 3600.0)
    env = SchedulingEnv(
        forecast=np.full((4, 2), 100.0),
        realized=np.full((4, 2), 100.0),
        band=np.full((4, 2), 10.0),
        demand_tokens=np.array([6_480_000.0, 0.0, 0.0, 0.0]),
        sites=[site_a, site_b],
        deadline_slots=2,
    )
    batch = rollout(env, ActorCritic(env.obs_dim, env.action_space, 4), np.random.default_rng(0))
    assert batch["obs"].shape == (4, env.obs_dim)
    assert batch["actions"].shape == (4,)
    assert batch["advantages"].shape == (4,)
    assert set(batch["summary"]) >= {"carbon_kg", "sla_violation_fraction"}
