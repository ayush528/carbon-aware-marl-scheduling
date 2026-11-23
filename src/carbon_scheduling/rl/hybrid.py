"""A hybrid scheduler: capacity-aware planning on forecast + band, exact execution.

Why this exists
---------------
exp016 measured that the four hand-written timing rules are not ordered by how
much they know. ``forecast_timing`` sees the whole forecast and is *worse* per
served GPU-hour than ``last_slot``, which sees only the deadline. The mechanism
is capacity, not information: a rule that ranks slots by their cheapest *site*
sends every class into the same slot, that slot's cheap site saturates, and the
excess spills onto the expensive sites. Measured over the 12 held-out weeks, the
share of served work landing on the dirtiest site (South Wales, 321 gCO2/kWh
against 8 in South Scotland) is 15.0% for ``forecast_timing`` and 8.0% for
``last_slot``.

So *when* to run cannot be decided from a slot's average price; it has to be
decided against the price of the capacity the work would actually occupy. That
is what this module does, and it does it in three separable parts so each can be
attacked on its own:

1. **Price.** A (slot, site) block costs ``forecast + robust * band``. ``robust
   = 0`` is the point forecast; ``robust = 1`` prices the whole calibrated band,
   so the planner only defers when the future is cheaper even at its worst case.
   This is the only place the conformal band enters a *decision*, and it enters
   as a level, never an ordering -- exp011 proved the regional ordering is
   already exact.
2. **Plan.** Backlog is assigned to blocks cheapest-first in earliest-deadline
   order, over a horizon of one maximum deadline, respecting each class's window
   and each site's per-slot capacity. This is the online, causal form of the
   exact min-cost flow in ``oracle.py``; the flow stays the bound, this is the
   thing that has to get close to it without knowing the future.
3. **Execute.** The plan says how much of each agent's backlog runs in *this*
   slot, and the environment is stepped with exactly that amount. A coast-fraction
   action cannot express this: it can only withhold work older or younger than
   an age threshold, so the plan and the action disagree and the disagreement is
   invisible.

The planner is deterministic and costs a few hundred microseconds per slot, so it
is deployable. It is also the natural warm start for a learner: the learned
policy decides the risk level (what ``robust`` to use, per class), while the
planner keeps the schedule feasible and the deadlines met.
"""

from __future__ import annotations

import numpy as np

from carbon_scheduling.cluster import site_energy_kwh
from carbon_scheduling.rl.queue_env import QueueEnv

__all__ = ["BlockPlanner", "ForecastFlowPlanner", "HybridEnv", "run_scheduler"]


class BlockPlanner:
    """Receding-horizon cheapest-feasible-block assignment.

    Parameters
    ----------
    robust
        Multiplier on the calibrated band when pricing a block. ``0`` is
        risk-neutral on the point forecast, ``1`` prices the whole band.
    max_slots_ahead
        Planning horizon. Defaults to the longest deadline, because no queued
        item can legally run later than that.
    reserve
        Fraction of each site's per-slot capacity held back from the plan. A
        myopic planner fills a cheap slot with present backlog and leaves the
        arrivals that will land there with nowhere to run; measured on the slack
        fleet that costs 3.4% of work even though the fleet has enough capacity
        in aggregate. The reserve is what those arrivals run in.
    arrival_forecast
        Trailing window (slots) for a causal arrival-rate estimate. When set, it
        is turned into a capacity reserve directly; prefer ``reserve_gpu_s``,
        which is the calibrated form (see ``rl/arrival_risk.py``).
    reserve_gpu_s
        Absolute GPU-seconds held back from every block in the plan -- the
        per-site-per-slot share of a calibrated arrival-excess quantile. This is
        the form with a coverage claim: the reserve bounds how much more work
        arrives than the trailing mean predicted, at a stated level on weeks the
        quantile never saw.
    """

    def __init__(
        self,
        robust: float = 0.0,
        max_slots_ahead: int | None = None,
        reserve: float = 0.0,
        arrival_forecast: int = 0,
        reserve_gpu_s: float = 0.0,
    ) -> None:
        self.robust = float(robust)
        self.max_slots_ahead = max_slots_ahead
        self.reserve = float(reserve)
        # Window (in slots) of the causal arrival-rate estimate; 0 disables it.
        self.arrival_forecast = int(arrival_forecast)
        self.reserve_gpu_s = float(reserve_gpu_s)

    def _price(self, env: QueueEnv, slot: int, site: int) -> float:
        return float(env.forecast[slot, site]) + self.robust * float(env.band[slot, site])

    def plan(self, env: QueueEnv, t: int) -> dict[int, float]:
        """Volume each agent should offer in slot ``t``, and the blocks it goes to."""
        horizon = self.max_slots_ahead or max(env.deadlines)
        last = min(t + horizon, env.n_slots)

        # Capacity still free in every block of the horizon.
        keep = max(0.0, 1.0 - self.reserve)
        free = {
            (s, j): float(env.capacity_gpu_s[j]) * keep
            for s in range(t, last)
            for j in range(len(env.sites))
        }
        if self.arrival_forecast > 0:
            # Hold room for the work about to arrive. The tightest class must run
            # within its own window, so however cheap a slot looks now, that much
            # of it is not available to today's backlog. Without this the plan
            # competes with its own future and loses work on a fleet that has
            # capacity to spare -- measured on the slack fleet as 3.4% of all
            # arrivals.
            window = max(1, int(self.arrival_forecast))
            past = env.demand_tokens[max(0, t - window) : t] / env.throughput
            rate = float(past.mean()) if past.size else 0.0
            tightest = min(env.deadlines)
            held = rate / env.n_agents * tightest / len(env.sites)
            for key in free:
                free[key] = max(0.0, free[key] - held)
        if self.reserve_gpu_s > 0.0:
            for key in free:
                free[key] = max(0.0, free[key] - self.reserve_gpu_s)
        price = {key: self._price(env, key[0], key[1]) for key in free}

        # Items, tightest deadline first, then oldest arrival.
        items: list[tuple[int, int, int, float]] = []
        for i in range(env.n_agents):
            for arrival in sorted(env.queues[i]):
                items.append(
                    (arrival + env.deadlines[i] - 1, i, arrival, float(env.queues[i][arrival]))
                )
        items.sort(key=lambda item: (item[0], item[2], item[1]))

        offer_now = {i: 0.0 for i in range(env.n_agents)}
        for last_legal, i, arrival, volume in items:
            feasible = [
                key
                for key in price
                if free[key] > 1e-9 and key[0] >= max(t, arrival) and key[0] <= last_legal
            ]
            # Work whose window has already closed is offered now regardless: the
            # environment will count the miss, and hiding it would be dishonest.
            if not feasible:
                offer_now[i] += volume
                continue
            for key in sorted(feasible, key=lambda k: (price[k], k[0])):
                if volume <= 1e-9:
                    break
                take = min(volume, free[key])
                free[key] -= take
                volume -= take
                if key[0] == t:
                    offer_now[i] += take
        return offer_now


class HybridEnv(QueueEnv):
    """``QueueEnv`` with an exact offer-volume interface.

    ``step_offers(amounts)`` serves exactly the requested volume from each
    agent's oldest work, then delegates to the parent's slot dynamics. It exists
    so a planner and a coast-action policy can be scored in the same environment
    with the same accounting; the parent class is untouched, which keeps the
    coast-action experiments reproducible.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._forced: tuple[np.ndarray, list[tuple[int, int]]] | None = None
        self._remainder: dict[tuple[int, int], float] = {}
        super().__init__(*args, **kwargs)

    def _offers(self, actions, t):  # type: ignore[override]
        if self._forced is not None:
            offers, items = self._forced
            self._forced = None
            return offers, items

        offers = np.zeros(self.n_agents)
        items = []
        for i, amount in enumerate(actions):
            wanted = float(amount)
            if wanted <= 1e-9:
                continue
            for arrival in sorted(self.queues[i]):
                if wanted <= 1e-9:
                    break
                take = min(wanted, self.queues[i][arrival])
                offers[i] += take
                items.append((i, arrival))
                wanted -= take
        return offers, items

    def step_offers(self, amounts) -> tuple[np.ndarray, np.ndarray, bool, bool, dict]:
        """Offer exactly ``amounts[i]`` GPU-seconds from agent ``i``'s oldest work."""
        offers = np.zeros(self.n_agents)
        items: list[tuple[int, int]] = []
        self._remainder = {}
        for i, wanted in enumerate(amounts):
            wanted = float(wanted)
            for arrival in sorted(self.queues[i]):
                if wanted <= 1e-9:
                    break
                held = self.queues[i][arrival]
                take = min(wanted, held)
                if take < held:
                    self._remainder[(i, arrival)] = held - take
                    self.queues[i][arrival] = take
                offers[i] += take
                items.append((i, arrival))
                wanted -= take
        self._forced = (offers, items)
        obs, rewards, done, truncated, info = QueueEnv.step(
            self, np.zeros(self.n_agents, dtype=int)
        )
        # Whatever was not offered goes back to the queue, unless it expired.
        for (i, arrival), rest in self._remainder.items():
            if arrival + self.deadlines[i] > self.t:
                self.queues[i][arrival] = self.queues[i].get(arrival, 0.0) + rest
        self._remainder = {}
        return obs, rewards, done, truncated, info


def run_scheduler(env: HybridEnv, planner: BlockPlanner) -> dict:
    """Play one episode with the planner in sole control of the offer volume."""
    env.reset()
    while True:
        amounts = planner.plan(env, env.t)
        _, _, done, _, _ = env.step_offers([amounts[i] for i in range(env.n_agents)])
        if done:
            return env.summary()


class ForecastFlowPlanner(BlockPlanner):
    """The same receding-horizon idea, but solved exactly on the forecast.

    The greedy above assigns blocks one item at a time, so it can make a choice
    that blocks a tighter item later and never revisits it. This planner instead
    hands the same problem to ``oracle.plan_multi`` -- a min-cost flow -- over a
    horizon of one maximum deadline, with the calibrated forecast as the cost.
    Each backlog entry becomes its own class whose remaining window is its
    deadline, which is exactly the constraint the flow already enforces.

    The result is the cheapest *legal* schedule that a deployable scheduler can
    compute: it differs from :func:`oracle.plan_multi` only by using the forecast
    instead of the realized intensity, and by seeing the backlog rather than the
    week's entire arrivals.
    """

    def plan(self, env: QueueEnv, t: int) -> dict[int, float]:
        from carbon_scheduling.rl.oracle import plan_multi

        horizon = self.max_slots_ahead or max(env.deadlines)
        horizon = min(horizon, env.n_slots - t)
        keep = max(0.0, 1.0 - self.reserve)

        unit = np.array(
            [site_energy_kwh(site, 1.0, 30) - site_energy_kwh(site, 0.0, 30) for site in env.sites]
        )
        intensity = env.forecast[t : t + horizon] + self.robust * env.band[t : t + horizon]
        cost = unit[None, :] * intensity / 1000.0

        items: list[tuple[int, int, float, int]] = []
        for i in range(env.n_agents):
            for arrival in sorted(env.queues[i]):
                volume = float(env.queues[i][arrival])
                if volume <= 1e-9:
                    continue
                window = arrival + env.deadlines[i] - t
                items.append((i, arrival, volume, max(1, min(window, horizon))))
        if not items and not self.arrival_forecast:
            return {i: 0.0 for i in range(env.n_agents)}

        classes = [max(1, min(w, horizon)) for _i, _a, _v, w in items]
        demand = np.zeros((len(items), horizon))
        for k, (_i, _a, volume, _w) in enumerate(items):
            demand[k, 0] = volume

        if self.arrival_forecast:
            # Reserve room for the work that is about to arrive. Without this the
            # plan fills a cheap slot with today's backlog and the arrivals that
            # land there have nowhere to run -- which is why a myopic planner
            # loses work even on a fleet with capacity to spare. The rate is the
            # mean of the last `window` slots, so it is causal: nothing ahead of
            # the decision is used.
            window = max(1, int(self.arrival_forecast))
            past = env.demand_tokens[max(0, t - window) : t] / env.throughput
            rate = float(past.mean()) if past.size else 0.0
            for i in range(env.n_agents):
                for k in range(1, horizon):
                    row = np.zeros(horizon)
                    row[k] = rate / env.n_agents
                    demand = np.vstack([demand, row[None, :]])
                    classes.append(max(1, min(env.deadlines[i], horizon)))

        capacity = float(env.capacity_gpu_s.min()) * keep
        alloc, _unserved = plan_multi(cost, demand, capacity, classes)

        # Only the current slot is executed; the rest is replanned next slot with
        # the arrivals that have actually happened by then.
        offer_now = {i: 0.0 for i in range(env.n_agents)}
        for k, (i, _arrival, _volume, _w) in enumerate(items):
            offer_now[i] += float(alloc[k, 0, :].sum())
        return offer_now
