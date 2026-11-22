"""IPPO and MAPPO for the rung-6 environment (numpy, no torch).

Two learners share one rollout, which is what makes the comparison clean:

``IPPO``
    Every agent has its own actor-critic on its own observation, its own
    advantage estimate, its own optimiser. No agent sees another's returns.
    This is the "independent learners" rung -- it can only cooperate through
    the environment's clearing rule and the two broadcast numbers.

``MAPPO``
    Actors unchanged (still per-agent, still on local observations), but one
    *centralised* critic sees the joint state. Training uses that critic;
    execution does not, so the acting policy keeps the limited-information
    guarantee. The gap between the two is the measured value of centralised
    training.

The CVaR term is the paper's risk-aware deadlines axis. The environment already
charges each agent the *mean* of the violations it is blamed for. CVaR replaces
that with the worst ``1 - alpha`` fraction of its own per-slot violation series::

    adjustment_i = -cvar_weight * (CVaR_alpha(violations_i) - mean(violations_i))

so ``cvar_weight = 0`` is risk-neutral (exactly exp012's reward) and
``cvar_weight = sla_penalty`` makes the agent pay the tail instead of the mean.
The adjustment is applied at the terminal step, because a tail is an episode
property; nothing else about the environment changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from carbon_scheduling.rl.numpy_net import ActorCritic, Adam, ValueNet


def cvar_tail(values: np.ndarray, alpha: float) -> float:
    """Mean of the worst ``1 - alpha`` fraction of a per-slot cost series."""
    values = np.sort(np.asarray(values, dtype=np.float64).ravel())
    if values.size == 0:
        raise ValueError("no values to take a CVaR over")
    if not 0.0 <= alpha < 1.0:
        raise ValueError(f"alpha must be in [0, 1), got {alpha!r}")
    k = max(1, int(round((1.0 - alpha) * values.size)))
    return float(values[-k:].mean())


def cvar_adjustment(violations: np.ndarray, alpha: float, weight: float) -> np.ndarray:
    """Per-agent terminal reward adjustment, ``-weight * (CVaR - mean)``.

    A penalty, so it is <= 0 and shape ``(n_agents,)``, in kilograms: the
    violation series is in GPU-seconds, so it is divided by 3600 exactly as the
    environment's own per-step penalty is. Zero when the agent's violations are
    uniform, which is the property that makes "CVaR on" a tail effect and not a
    rescaling.
    """
    if weight < 0:
        raise ValueError("cvar weight must be >= 0")
    violations = np.asarray(violations, dtype=np.float64)
    if violations.ndim != 2:
        raise ValueError(f"violations must be (T, agents), got {violations.shape}")
    out = np.zeros(violations.shape[1])
    for i in range(violations.shape[1]):
        series = violations[:, i]
        out[i] = -weight * (cvar_tail(series, alpha) - float(series.mean())) / 3600.0
    return out


def _gae_multi(
    rewards: np.ndarray,
    values: np.ndarray,
    dones: np.ndarray,
    gamma: float,
    lam: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-agent GAE over a joint trajectory of shape ``(T, agents)``."""
    steps, agents = rewards.shape
    advantages = np.zeros((steps, agents))
    running = np.zeros(agents)
    next_value = np.zeros(agents)
    for t in range(steps - 1, -1, -1):
        nonterminal = 0.0 if dones[t] else 1.0
        delta = rewards[t] + gamma * next_value * nonterminal - values[t]
        running = delta + gamma * lam * running * nonterminal
        advantages[t] = running
        next_value = values[t]
    return advantages, advantages + values


def rollout_multi(
    env,
    actors: list[ActorCritic],
    rng: np.random.Generator,
    *,
    critic: ValueNet | None = None,
    gamma: float = 0.99,
    lam: float = 0.95,
    cvar_alpha: float | None = None,
    cvar_weight: float = 0.0,
) -> dict[str, Any]:
    """One joint episode: experience for every agent plus the episode totals."""
    obs, _ = env.reset()
    n_agents = env.n_agents
    obs_buf, act_buf, logp_buf, rew_buf, done_buf = [], [], [], [], []
    value_buf, state_buf, viol_buf = [], [], []

    while True:
        actions = []
        step_values = np.zeros(n_agents)
        for i, net in enumerate(actors):
            action, logp, value = net.act(obs[i], rng)
            actions.append(action)
            step_values[i] = value
            act_buf.append(action)
            logp_buf.append(logp)
        obs_buf.append(np.array(obs, copy=True))
        value_buf.append(step_values)
        if critic is not None:
            state_buf.append(env.global_state())

        before = getattr(env, "violated_by_agent", np.zeros(n_agents)).copy()
        next_obs, rewards, done, truncated, _info = env.step(actions)
        after = getattr(env, "violated_by_agent", np.zeros(n_agents))
        viol_buf.append(after - before)
        rew_buf.append(np.asarray(rewards, dtype=np.float64))
        done_buf.append(bool(done or truncated))
        obs = next_obs
        if done or truncated:
            break

    rewards = np.asarray(rew_buf)
    violations = np.asarray(viol_buf)
    if cvar_alpha is not None and cvar_weight > 0:
        # A tail is an episode property, so it is charged once, at the end.
        rewards[-1] = rewards[-1] + cvar_adjustment(violations, cvar_alpha, cvar_weight)

    values = np.asarray(value_buf)
    if critic is not None:
        states = np.asarray(state_buf)
        values = np.repeat(critic.forward(states)[:, None], n_agents, axis=1)
    advantages, returns = _gae_multi(rewards, values, np.asarray(done_buf), gamma, lam)

    return {
        "obs": np.asarray(obs_buf),  # (T, agents, obs_dim)
        "actions": np.asarray(act_buf, dtype=int).reshape(-1, n_agents),
        "logp": np.asarray(logp_buf, dtype=np.float64).reshape(-1, n_agents),
        "values": values,
        "advantages": advantages,
        "returns": returns,
        "rewards": rewards,
        "violations": violations,
        "states": np.asarray(state_buf) if critic is not None else None,
        "episode_return": float(rewards.mean(axis=1).sum()),
        "summary": env.summary(),
    }


def _update(
    net: ActorCritic,
    optimiser: Adam,
    obs: np.ndarray,
    actions: np.ndarray,
    logp: np.ndarray,
    advantages: np.ndarray,
    returns: np.ndarray,
    *,
    epochs: int,
    minibatches: int,
    rng: np.random.Generator,
    clip: float,
    vf_coef: float,
    ent_coef: float,
) -> dict[str, float]:
    adv = advantages
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
                obs[idx],
                actions[idx],
                logp[idx],
                adv[idx],
                returns[idx],
                clip=clip,
                vf_coef=vf_coef,
                ent_coef=ent_coef,
            )
            optimiser.step(net.params, grads)
            diagnostics = diag
    return diagnostics


def train_multi(
    env_factory: Callable[[int], Any],
    *,
    n_agents: int,
    obs_dim: int,
    n_actions: int,
    global_state_dim: int | None = None,
    centralized_critic: bool = False,
    episodes: int,
    seed: int = 0,
    hidden: int = 32,
    lr: float = 3e-3,
    critic_lr: float | None = None,
    epochs: int = 4,
    minibatches: int = 4,
    gamma: float = 0.99,
    lam: float = 0.95,
    clip: float = 0.2,
    vf_coef: float = 0.5,
    ent_coef: float = 0.01,
    cvar_alpha: float | None = None,
    cvar_weight: float = 0.0,
    log: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[ActorCritic], ValueNet | None, list[dict[str, Any]]]:
    """Train independent actors (IPPO) or actors with a centralised critic."""
    if centralized_critic and global_state_dim is None:
        raise ValueError("centralised critic needs global_state_dim")
    rng = np.random.default_rng(seed)
    actors = [
        ActorCritic(obs_dim, n_actions, hidden=hidden, seed=seed + i) for i in range(n_agents)
    ]
    actor_opts = [Adam(net.params, lr=lr) for net in actors]
    critic = ValueNet(global_state_dim, hidden=hidden, seed=seed) if centralized_critic else None
    critic_opt = Adam(critic.params, lr=critic_lr or lr) if critic is not None else None

    history: list[dict[str, Any]] = []
    for episode in range(episodes):
        env = env_factory(episode)
        batch = rollout_multi(
            env,
            actors,
            rng,
            critic=critic,
            gamma=gamma,
            lam=lam,
            cvar_alpha=cvar_alpha,
            cvar_weight=cvar_weight,
        )
        diags = []
        for i in range(n_agents):
            diags.append(
                _update(
                    actors[i],
                    actor_opts[i],
                    batch["obs"][:, i],
                    batch["actions"][:, i],
                    batch["logp"][:, i],
                    batch["advantages"][:, i],
                    batch["returns"][:, i],
                    epochs=epochs,
                    minibatches=minibatches,
                    rng=rng,
                    clip=clip,
                    vf_coef=vf_coef,
                    ent_coef=ent_coef,
                )
            )
        if critic is not None:
            # The shared critic regresses the fleet-mean return: it is one
            # function of the joint state, so one target per step.
            states = batch["states"]
            target = batch["returns"].mean(axis=1)
            order = rng.permutation(len(target))
            chunk = max(1, len(target) // minibatches)
            for _ in range(epochs):
                for start in range(0, len(target), chunk):
                    idx = order[start : start + chunk]
                    _, grads, _ = critic.loss_and_grads(states[idx], target[idx])
                    critic_opt.step(critic.params, grads)

        record = {
            "episode": episode,
            "episode_return": batch["episode_return"],
            "carbon_kg": batch["summary"]["carbon_kg"],
            "sla_violation_fraction": batch["summary"]["sla_violation_fraction"],
            "policy_loss": float(np.mean([d["policy_loss"] for d in diags])),
            "entropy": float(np.mean([d["entropy"] for d in diags])),
            "clip_fraction": float(np.mean([d["clip_fraction"] for d in diags])),
        }
        history.append(record)
        if log is not None:
            log(record)
    return actors, critic, history


def evaluate_multi(env, actors: list[ActorCritic]) -> dict[str, float]:
    """Greedy joint episode with the acting policies only."""
    obs, _ = env.reset()
    while True:
        actions = [int(np.argmax(net.forward(obs[i])[0][0])) for i, net in enumerate(actors)]
        obs, _rewards, done, truncated, _info = env.step(actions)
        if done or truncated:
            break
    return env.summary()
