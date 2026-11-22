"""PPO for the Phase 3 scheduling environment (numpy, no torch).

Standard clipped-surrogate PPO over the :class:`SchedulingEnv` episodes:
collect one full episode, compute GAE advantages, then take a few epochs of
minibatch gradient steps on the clipped objective with a value baseline and an
entropy bonus. Episodes are whole weeks, so one rollout is a full 336-step
trajectory and "minibatch" is a shuffled partition of it.

The training loop reports per-update diagnostics (policy loss, value loss,
entropy, clip fraction) so a broken gradient shows up as a number instead of a
flat reward curve. ``train`` returns the history, and ``evaluate`` returns
episode totals from greedy actions -- the same numbers the heuristic baselines
report, so the comparison is like for like.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from carbon_scheduling.rl.numpy_net import ActorCritic, Adam


def _gae(
    rewards: list[float],
    values: list[float],
    dones: list[bool],
    gamma: float,
    lam: float,
) -> tuple[np.ndarray, np.ndarray]:
    advantages = np.zeros(len(rewards), dtype=np.float64)
    running = 0.0
    next_value = 0.0
    for t in range(len(rewards) - 1, -1, -1):
        nonterminal = 0.0 if dones[t] else 1.0
        delta = rewards[t] + gamma * next_value * nonterminal - values[t]
        running = delta + gamma * lam * running * nonterminal
        advantages[t] = running
        next_value = values[t]
    returns = advantages + np.asarray(values, dtype=np.float64)
    return advantages, returns


def rollout(
    env,
    net: ActorCritic,
    rng: np.random.Generator,
    *,
    gamma: float = 0.99,
    lam: float = 0.95,
) -> dict[str, Any]:
    """One episode of experience plus the episode's totals."""
    obs, _ = env.reset()
    obs_buf, act_buf, logp_buf, val_buf, rew_buf, done_buf = [], [], [], [], [], []
    while True:
        action, logp, value = net.act(obs, rng)
        next_obs, reward, done, truncated, _ = env.step(action)
        obs_buf.append(obs)
        act_buf.append(action)
        logp_buf.append(logp)
        val_buf.append(value)
        rew_buf.append(float(reward))
        done_buf.append(bool(done or truncated))
        obs = next_obs
        if done or truncated:
            break
    advantages, returns = _gae(rew_buf, val_buf, done_buf, gamma, lam)
    return {
        "obs": np.asarray(obs_buf, dtype=np.float64),
        "actions": np.asarray(act_buf, dtype=int),
        "logp": np.asarray(logp_buf, dtype=np.float64),
        "advantages": advantages,
        "returns": returns,
        "episode_return": float(sum(rew_buf)),
        "summary": env.summary(),
    }


def train(
    env_factory: Callable[[], Any],
    net: ActorCritic,
    *,
    episodes: int,
    seed: int = 0,
    lr: float = 3e-3,
    epochs: int = 4,
    minibatches: int = 4,
    gamma: float = 0.99,
    lam: float = 0.95,
    clip: float = 0.2,
    vf_coef: float = 0.5,
    ent_coef: float = 0.01,
    log: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Train in place; returns one history record per episode."""
    rng = np.random.default_rng(seed)
    optimiser = Adam(net.params, lr=lr)
    history: list[dict[str, Any]] = []
    for episode in range(episodes):
        env = env_factory(episode)
        batch = rollout(env, net, rng)
        adv = batch["advantages"]
        if adv.std() > 1e-9:
            adv = (adv - adv.mean()) / (adv.std() + 1e-9)
        n = len(adv)
        order = rng.permutation(n)
        chunk = max(1, n // minibatches)
        diagnostics: dict[str, float] = {}
        for _ in range(epochs):
            for start in range(0, n, chunk):
                idx = order[start : start + chunk]
                _, grads, diag = net.loss_and_grads(
                    batch["obs"][idx],
                    batch["actions"][idx],
                    batch["logp"][idx],
                    adv[idx],
                    batch["returns"][idx],
                    clip=clip,
                    vf_coef=vf_coef,
                    ent_coef=ent_coef,
                )
                optimiser.step(net.params, grads)
                diagnostics = diag
        record = {
            "episode": episode,
            "episode_return": batch["episode_return"],
            "carbon_kg": batch["summary"]["carbon_kg"],
            "sla_violation_fraction": batch["summary"]["sla_violation_fraction"],
            **diagnostics,
        }
        history.append(record)
        if log is not None:
            log(record)
    return history


def evaluate(env, net: ActorCritic) -> dict[str, float]:
    """Greedy episode totals (no exploration noise)."""
    obs, _ = env.reset()
    while True:
        logits, _, _ = net.forward(obs)
        action = int(np.argmax(logits[0]))
        obs, _, done, truncated, _ = env.step(action)
        if done or truncated:
            break
    return env.summary()
