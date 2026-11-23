"""Heuristic policies for the Phase 3 environment (the baselines to beat).

Every policy is ``policy(env) -> action`` and is run through
:func:`run_policy`, so all of them are scored by the same episode code as the
learned agent. Three rungs, matching the roadmap:

``run_now``      dispatch to the region with the lowest forecast, never wait.
                 This is exp011's forecast-greedy in the temporal env.
``band_aware``   same, but score with ``forecast + lam * band`` -- risk averse
                 about the level of the intensity it is about to buy.
``defer``        wait if the next few slots are expected to be cleaner and the
                 backlog has room before its deadline. This is the first policy
                 that uses the *time* axis, and the one a band can improve:
                 the decision is taken on the upper end of the band, and it is
                 refused when the deadline margin is thin (the CVaR idea, as a
                 rule).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np


def _horizon(env, slots: int) -> tuple[np.ndarray, np.ndarray]:
    start = env.t
    stop = min(env.t + slots, env.n_slots)
    return env.forecast[start:stop], env.band[start:stop]


def run_now(env) -> int:
    """Dispatch carbon-greedily (risk level 0), never wait."""
    return env.action_for_lam(0.0)


def band_aware(env, lam: float = 1.0) -> int:
    """Dispatch with the band in the score (the risk level closest to lam)."""
    return env.action_for_lam(lam)


def defer(env, *, lookahead: int = 4, lam: float = 1.0, margin: float = 0.0) -> int:
    """Wait when waiting is safer *and* the deadline allows it.

    Compares the risk-adjusted cost of running now with the best risk-adjusted
    cost in the next ``lookahead`` slots. It never waits when the oldest queued
    task is within one slot of its deadline: missing a deadline is not worth a
    few grams, which is the risk-aversion the CVaR term formalises.
    """
    if not env.backlog:
        return env.action_for_lam(0.0)
    urgency = min(item[1] - env.t for item in env.backlog)
    if urgency <= 1:
        return band_aware(env, lam)
    now = env.forecast[env.t] + lam * env.band[env.t]
    fc, bd = _horizon(env, lookahead)
    future = (fc + lam * bd).min(axis=1)
    if future.size and future.min() < now.min() - margin:
        return env.wait_action
    return band_aware(env, lam)


def run_policy(env, policy: Callable[[Any], int]) -> dict[str, float]:
    """Run a policy through one episode; return the env's own totals."""
    env.reset()
    while True:
        _obs, _reward, done, truncated, _info = env.step(policy(env))
        if done or truncated:
            break
    return env.summary()


def marl_run_now(env) -> list[int]:
    """Every agent offers everything and quotes its bare forecast."""
    return [env.encode(0.0, 1.0)] * env.n_agents


def marl_band_aware(env, lam: float = 1.0) -> list[int]:
    """Every agent offers everything and charges its band at risk level ``lam``."""
    return [env.encode(lam, 1.0)] * env.n_agents


def marl_defer(env, *, lookahead: int = 4, lam: float = 1.0, margin: float = 0.0) -> list[int]:
    """Joint rule: decline for everyone when a cleaner slot is genuinely ahead.

    The multi-agent version of :func:`defer`. It only waits if every agent is
    better off later, so no agent is asked to sit out a slot the others are
    going to use -- otherwise the rule would manufacture violations.
    """
    if not env.backlog:
        return marl_run_now(env)
    urgency = min(item[1] - env.t for item in env.backlog)
    if urgency <= 1:
        return marl_band_aware(env, lam)
    now = float((env.forecast[env.t] + lam * env.band[env.t]).min())
    horizon = slice(env.t, min(env.t + lookahead, env.n_slots))
    future = float((env.forecast[horizon] + lam * env.band[horizon]).min())
    if future < now - margin:
        return [env.encode(0.0, 0.0)] * env.n_agents
    return marl_band_aware(env, lam)


POLICIES: dict[str, Callable[[Any], int]] = {
    "run_now": run_now,
    "band_aware": lambda env: band_aware(env, 1.0),
    "defer": lambda env: defer(env, lookahead=4, lam=1.0),
}

JOINT_POLICIES: dict[str, Callable[[Any], list[int]]] = {
    "run_now": marl_run_now,
    "band_aware": lambda env: marl_band_aware(env, 1.0),
    "defer": lambda env: marl_defer(env, lookahead=4, lam=1.0),
}


def run_joint_policy(env, policy: Callable[[Any], list[int]]) -> dict[str, float]:
    """Run a joint policy through one episode."""
    env.reset()
    while True:
        _obs, _reward, done, truncated, _info = env.step(policy(env))
        if done or truncated:
            break
    return env.summary()
