"""Hand-written timing rules for the rung-7 queue environment.

These are the yardsticks a learner has to beat, and they are deliberately
simple enough to describe in one sentence each:

``run_now``
    Offer everything every slot. This is carbon-greedy's immediate dispatch and
    reproduces rung 6's behaviour, so it is the baseline the earlier rungs were
    measured against.

``last_slot``
    Hold as long as the class's deadline allows: maximum deferral with no look
    at the carbon series. It shows how much of the timing lever is available
    from the deadline alone -- and, because holding work piles it into the same
    slots, it is also the rule that shows why deadline-only deferral hurts.

``forecast_timing``
    Look ahead over the window the class is allowed, and hold until the
    cheapest forecast slot in it. Uses the published NESO forecast and nothing
    else.

``band_timing``
    The same lookahead, but the comparison is uncertainty-aware: defer only if
    the future's *pessimistic* level (forecast + band) beats the present's
    *optimistic* one (forecast - band). A risk-averse scheduler should hold
    back when the improvement is inside the measurement noise, and this rule is
    what puts the calibrated band into a timing decision -- exp011 showed it
    cannot reorder sites, so this is where it can act.

Every rule is a pure function of the environment and one agent index: no hidden
state, no dependence on which agent is asked first.
"""

from __future__ import annotations

import numpy as np

from carbon_scheduling.rl.queue_env import COAST

NOW = 0  # coast 0: offer everything immediately
HOLD = len(COAST) - 1  # hold for the whole slack budget


def coast_action(env, i: int, offset: int) -> int:
    """Index of the coast that makes class ``i`` serve ``offset`` slots from now.

    The grid is per class (a fraction of its own slack), so the same index means
    "the last legal slot" for every class while the number of slots differs.
    """
    waits = [env.wait_slots(i, action) for action in range(env.n_actions)]
    return int(np.argmin([abs(w - int(offset)) for w in waits]))


def lookahead(env, i: int) -> np.ndarray:
    """Fleet-min forecast over the slots class ``i`` may still use."""
    stop = min(env.t + env.deadlines[i], env.n_slots)
    return env.forecast[env.t : stop, :].min(axis=1)


def run_now(env, i: int) -> int:
    return NOW


def last_slot(env, i: int) -> int:
    return HOLD


def forecast_timing(env, i: int) -> int:
    """Hold until the cheapest forecast slot inside this class's window."""
    offset = int(np.argmin(lookahead(env, i)))
    return coast_action(env, i, offset)


def band_timing(env, i: int) -> int:
    """Defer only when the future's worst case beats the present's best case."""
    stop = min(env.t + env.deadlines[i], env.n_slots)
    station = slice(env.t, stop)
    future = (env.forecast[station, :] + env.band[station, :]).min(axis=1)
    present_best = float((env.forecast[env.t, :] - env.band[env.t, :]).min())
    offset = int(np.argmin(future))
    if offset == 0 or future[offset] >= present_best:
        return NOW
    return coast_action(env, i, offset)


RULES = {
    "run_now": run_now,
    "last_slot": last_slot,
    "forecast_timing": forecast_timing,
    "band_timing": band_timing,
}


def run_rule(env, rule: str) -> dict:
    """Play a hand-written rule for one episode and return the summary."""
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}; known: {sorted(RULES)}")
    policy = RULES[rule]
    env.reset()
    while True:
        actions = [int(policy(env, i)) for i in range(env.n_agents)]
        _, _, done, _, _ = env.step(actions)
        if done:
            break
    return env.summary()
