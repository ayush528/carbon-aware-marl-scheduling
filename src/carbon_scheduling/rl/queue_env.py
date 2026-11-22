"""Rung 7: agents own work, and decide *when* their own queue runs.

Rung 6 showed the fleet places work well -- under the national-scaling estimator
the regional carbon ordering is exactly known -- and that the lever left is
**timing**. But under rung 6's service obligation a single agent could only
express deferral by refusing capacity, which spills its work to some other
agent: deferral there needs every agent to wait in the same slot, a joint action
independent learners never take. exp015 measured the cost of that gap: at the
4-hour deadline perfect foresight saves 29.4% (slack fleet) and 14.5%
(capacity-bound) carbon at identical served volume.

So the ownership is inverted. An agent does not own a site; it owns a **work
stream** and a backlog, and its only decision is how long to hold its own work
before offering it. Nobody else's queue moves, so deferral is unilateral and a
policy can express it. A coordinator still places whatever is offered, cheapest
forecast site first, which keeps rung 6's placement result intact.

Work classes
    Arrivals are split equally between the agents, one class each with its own
    deadline (interactive to batch). The Azure trace carries no latency labels,
    so the split is a disclosed modelling choice; every policy in an experiment
    sees the identical split, so comparisons stay matched. The classes are what
    make the agents genuinely different: a 30-minute class cannot defer, an
    8-hour class can.

Action
    A **coast fraction** ``c``: hold the class's work for
    ``round(c * (deadline - 1))`` slots before offering it. ``c = 0`` offers
    everything every slot (rung 6's immediate dispatch, and the carbon-greedy
    baseline); ``c = 1`` holds until the last legal slot. Waiting is the only
    lever, so there is no "shed" action: work is lost only when its deadline
    passes without capacity, which is what makes the carbon numbers comparable
    at matched service.

Rewards
    Local and in kilograms::

        r_i = - (carbon of i's work) - price * (i's expired GPU-seconds) / 3600

    Carbon is charged at the *marginal* energy of the work (the power curve
    above the idle floor), so ``sum(r)`` is the fleet's variable cost. The idle
    floor is the operator's standing cost: it is billed in ``summary()`` and in
    ``idle_carbon_kg`` but enters no agent's incentive, because no agent's
    decision changes it.

Tail risk
    Because a miss is charged to the queue that let it expire, the per-slot
    violation series is per-agent and non-terminal -- which is what the CVaR
    term needs, and what rung 6's terminal charge could not see.
"""

from __future__ import annotations

import numpy as np

from carbon_scheduling.cluster import Site, site_energy_kwh

SLOT_MINUTES = 30
#: The timing action: what fraction of its own slack budget a class coasts.
#:
#: An action is a *coast fraction* ``c`` in [0, 1], mapped to a wait of
#: ``round(c * (deadline - 1))`` slots for the class that is choosing. That
#: makes one action index mean the same thing to every class -- 0 is "serve
#: now", the last index is "hold until the last legal slot" -- so a class with a
#: 30-minute deadline and one with a 4-hour deadline still take comparable
#: actions, and no action is wasted on a tight class (the alternative, an
#: absolute wait in slots, gave a deadline-2 class four indistinguishable
#: actions out of six).
COAST = (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)
LOOKAHEAD = 4


class QueueEnv:
    """Cooperative fleet, four deadline classes, one queue per class."""

    def __init__(
        self,
        *,
        forecast: np.ndarray,
        realized: np.ndarray,
        band: np.ndarray,
        demand_tokens: np.ndarray,
        sites: list[Site],
        deadlines: tuple[int, ...] | list[int] = (2, 4, 8, 16),
        sla_penalty_kg_per_gpu_hour: float = 1.0,
        communicate: bool = True,
        include_band_in_obs: bool = True,
    ) -> None:
        forecast = np.asarray(forecast, dtype=np.float64)
        realized = np.asarray(realized, dtype=np.float64)
        band = np.asarray(band, dtype=np.float64)
        demand_tokens = np.asarray(demand_tokens, dtype=np.float64)
        if forecast.ndim != 2:
            raise ValueError(f"forecast must be 2-D, got shape {forecast.shape}")
        if forecast.shape != realized.shape or forecast.shape != band.shape:
            raise ValueError(
                f"forecast/realized/band must share shape, got "
                f"{forecast.shape} / {realized.shape} / {band.shape}"
            )
        if forecast.shape[0] != demand_tokens.shape[0]:
            raise ValueError(
                f"demand has {demand_tokens.shape[0]} slots but carbon has {forecast.shape[0]}"
            )
        if len(sites) != forecast.shape[1]:
            raise ValueError(f"{len(sites)} sites for {forecast.shape[1]} carbon columns")
        if len({site.name for site in sites}) != len(sites):
            raise ValueError("site names must be unique")
        if len(deadlines) < 1:
            raise ValueError("at least one deadline class is required")
        if any(int(d) < 1 for d in deadlines):
            raise ValueError(f"every deadline must be >= 1 slot, got {list(deadlines)}")
        if sla_penalty_kg_per_gpu_hour < 0:
            raise ValueError("sla_penalty must be >= 0")
        if len({s.tokens_per_gpu_second for s in sites}) != 1:
            raise ValueError("sites must share one throughput so demand is one stream")

        self.forecast = forecast
        self.realized = realized
        self.band = band
        self.demand_tokens = demand_tokens
        self.sites = sites
        self.deadlines = tuple(int(d) for d in deadlines)
        self.sla_penalty = float(sla_penalty_kg_per_gpu_hour)
        self.communicate = communicate
        self.include_band_in_obs = include_band_in_obs

        self.n_slots = forecast.shape[0]
        self.n_agents = len(self.deadlines)
        self.capacity_gpu_s = np.array(
            [site.n_gpus * SLOT_MINUTES * 60 for site in sites], dtype=np.float64
        )
        self.throughput = sites[0].tokens_per_gpu_second
        self.coast_choices = COAST
        self.n_actions = len(COAST)
        # shared 9 (hour x2, arrivals, backlog, cheapest now, four ahead)
        # + band + two peer numbers + own 5.
        self.obs_dim = 9 + (1 if include_band_in_obs else 0) + (2 if communicate else 0) + 5
        self.global_state_dim = 11 + 2 * self.n_agents
        self._max_deadline = float(max(self.deadlines))
        self.reset()

    # --- lifecycle -------------------------------------------------------

    def reset(self) -> tuple[np.ndarray, dict]:
        self.t = 0
        self.queues: list[dict[int, float]] = [{} for _ in range(self.n_agents)]
        self.carbon_kg = np.zeros(self.n_agents)
        self.idle_carbon_kg = 0.0
        self.served_gpu_s = 0.0
        self.served_by_agent = np.zeros(self.n_agents)
        self.violated_by_agent = np.zeros(self.n_agents)
        self.owned_gpu_s = np.zeros(self.n_agents)
        self.slot_violations: list[float] = []
        self.served_by_site = np.zeros(len(self.sites))
        self.last_coast = np.full(self.n_agents, np.nan)
        self.last_offered_fraction = np.zeros(self.n_agents)
        self._arrive()
        return self.observations(), {}

    def _arrive(self) -> None:
        amount = float(self.demand_tokens[self.t]) / self.throughput
        if amount <= 0:
            return
        share = amount / self.n_agents
        for i in range(self.n_agents):
            self.queues[i][self.t] = self.queues[i].get(self.t, 0.0) + share
            self.owned_gpu_s[i] += share

    # --- decisions -------------------------------------------------------

    def _expired(self, t: int) -> np.ndarray:
        """Remove and count work whose last legal slot has passed."""
        out = np.zeros(self.n_agents)
        for i, deadline in enumerate(self.deadlines):
            for arrival in [a for a in self.queues[i] if a + deadline <= t]:
                out[i] += self.queues[i].pop(arrival)
        self.violated_by_agent += out
        return out

    def _offers(self, actions: list[int], t: int) -> tuple[np.ndarray, list[tuple[int, int]]]:
        """GPU-seconds each agent offers, plus the (agent, arrival) items behind it."""
        offers = np.zeros(self.n_agents)
        items: list[tuple[int, int]] = []
        for i, action in enumerate(actions):
            deadline = self.deadlines[i]
            threshold = self.deadlines[i] - self.wait_slots(i, action)
            offered = 0.0
            for arrival in sorted(self.queues[i]):
                slack = arrival + deadline - t
                if slack <= threshold:
                    offered += self.queues[i][arrival]
                    items.append((i, arrival))
            offers[i] = offered
        return offers, items

    def wait_slots(self, i: int, action: int) -> int:
        """How long class ``i`` holds its work under coast fraction ``action``.

        ``round`` rather than ``floor`` so the middle of the grid lands in the
        middle of the slack budget for even the shortest classes, and the
        result is capped at ``deadline - 1`` so the last index always means "the
        last legal slot" instead of "one slot too late".
        """
        slack = self.deadlines[i] - 1
        return min(slack, int(round(COAST[action] * slack)))

    # --- observations ----------------------------------------------------

    def _shared(self) -> list[float]:
        t = self.t
        fleet_capacity = float(self.capacity_gpu_s.sum())
        hour = (t * SLOT_MINUTES / 60.0) % 24
        arrivals = float(self.demand_tokens[t]) / self.throughput
        backlog = float(sum(sum(q.values()) for q in self.queues))
        cheapest = float(self.forecast[t, :].min())
        # Fleet-min forecast for this slot and the next few: the timing signal.
        # Near the end of the window the last available slot is reused.
        ahead = []
        for k in range(LOOKAHEAD):
            slot = min(t + k, self.n_slots - 1)
            ahead.append(float(self.forecast[slot, :].min()) / 300.0)
        return [
            float(np.sin(2 * np.pi * hour / 24)),
            float(np.cos(2 * np.pi * hour / 24)),
            arrivals / fleet_capacity,
            backlog / fleet_capacity,
            cheapest / 300.0,
            *ahead,
        ]

    def _own(self, i: int) -> list[float]:
        t = self.t
        fleet_capacity = float(self.capacity_gpu_s.sum())
        queue = self.queues[i]
        deadline = self.deadlines[i]
        total = float(sum(queue.values()))
        tight = 0.0
        loose = 0.0
        for arrival, amount in queue.items():
            slack = arrival + deadline - t
            if slack <= 2:
                tight += amount
            elif slack <= 8:
                loose += amount
        scale = total if total > 1e-9 else 1.0
        owned = float(self.owned_gpu_s[i])
        return [
            total / fleet_capacity,
            tight / scale,
            loose / scale,
            float(self.violated_by_agent[i]) / owned if owned > 1e-9 else 0.0,
            deadline / self._max_deadline,
        ]

    def observations(self) -> np.ndarray:
        shared = self._shared()
        band = [float(self.band[self.t, :].mean()) / 300.0] if self.include_band_in_obs else []
        if self.communicate:
            finite = self.last_coast[np.isfinite(self.last_coast)]
            peers = [float(finite.mean()) if finite.size else 0.0]
            peers.append(float(self.last_offered_fraction.mean()))
        else:
            peers = []
        out = np.zeros((self.n_agents, self.obs_dim), dtype=np.float32)
        for i in range(self.n_agents):
            out[i] = np.asarray(shared + band + peers + self._own(i), dtype=np.float32)
        return out

    def global_state(self) -> np.ndarray:
        shared = self._shared()
        band = [float(self.band[self.t, :].mean()) / 300.0] if self.include_band_in_obs else []
        fleet_capacity = float(self.capacity_gpu_s.sum())
        queues = [float(sum(q.values())) / fleet_capacity for q in self.queues]
        pooled: list[float] = []
        for i in range(self.n_agents):
            owned = float(self.owned_gpu_s[i])
            pooled.append(float(self.violated_by_agent[i]) / owned if owned > 1e-9 else 0.0)
        finite = self.last_coast[np.isfinite(self.last_coast)]
        mean_coast = float(finite.mean()) if finite.size else 0.0
        return np.asarray(shared + band + queues + pooled + [mean_coast], dtype=np.float32)

    # --- dynamics --------------------------------------------------------

    def step(
        self, actions: list[int] | np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, bool, bool, dict]:
        actions = [int(a) for a in actions]
        if len(actions) != self.n_agents:
            raise ValueError(f"expected {self.n_agents} actions, got {len(actions)}")
        if any(not 0 <= a < self.n_actions for a in actions):
            raise ValueError(f"actions must be in 0..{self.n_actions - 1}")

        t = self.t
        expired = self._expired(t)
        _offers, items = self._offers(actions, t)

        # Earliest deadline first across the whole fleet: the queue that cannot
        # wait takes the capacity first. Within a class, older work leads.
        items.sort(key=lambda item: (item[1] + self.deadlines[item[0]] - t, item[0], item[1]))
        remaining = self.capacity_gpu_s.copy()
        ranking = np.argsort(self.forecast[t, :], kind="stable")
        carbon = np.zeros(self.n_agents)
        site_totals = np.zeros(len(self.sites))
        served = 0.0
        for agent, arrival in items:
            amount = self.queues[agent].get(arrival, 0.0)
            for site_index in ranking:
                if amount <= 1e-9:
                    break
                take = min(amount, remaining[site_index])
                if take <= 0:
                    continue
                remaining[site_index] -= take
                amount -= take
                served += take
                site_totals[site_index] += take
                self.served_by_agent[agent] += take
                site = self.sites[site_index]
                marginal = site_energy_kwh(site, take, SLOT_MINUTES) - site_energy_kwh(
                    site, 0.0, SLOT_MINUTES
                )
                carbon[agent] += marginal * float(self.realized[t, site_index]) / 1000.0
            if amount <= 1e-9:
                self.queues[agent].pop(arrival, None)
            else:
                self.queues[agent][arrival] = amount

        idle = sum(
            site_energy_kwh(site, 0.0, SLOT_MINUTES) * float(self.realized[t, j]) / 1000.0
            for j, site in enumerate(self.sites)
        )
        self.idle_carbon_kg += idle
        self.carbon_kg += carbon
        self.served_gpu_s += served
        self.served_by_site += site_totals
        self.slot_violations.append(float(expired.sum()))

        rewards = -carbon - self.sla_penalty * expired / 3600.0

        offered_total = float(sum(_offers))
        self.last_coast = np.array([COAST[a] for a in actions], dtype=np.float64)
        self.last_offered_fraction = np.array(
            [
                _offers[i] / float(sum(self.queues[i].values()) + _offers[i])
                if (sum(self.queues[i].values()) + _offers[i]) > 1e-9
                else 0.0
                for i in range(self.n_agents)
            ]
        )

        self.t += 1
        done = self.t >= self.n_slots
        if done:
            # The window closes: work still queued has nowhere left to run, and
            # that is a miss for its owner like any other.
            leftover = np.zeros(self.n_agents)
            for i in range(self.n_agents):
                leftover[i] = float(sum(self.queues[i].values()))
                self.queues[i] = {}
            self.violated_by_agent += leftover
            self.slot_violations[-1] += float(leftover.sum())
            rewards = rewards - self.sla_penalty * leftover / 3600.0
        else:
            self._arrive()

        obs = (
            self.observations()
            if not done
            else np.zeros((self.n_agents, self.obs_dim), dtype=np.float32)
        )
        info = {
            "served_gpu_s": served,
            "expired_gpu_s": expired,
            "offered_gpu_s": offered_total,
            "carbon_kg": carbon,
        }
        return obs, rewards, done, False, info

    # --- reporting -------------------------------------------------------

    def summary(self) -> dict:
        offered = float(self.demand_tokens.sum() / self.throughput)
        missed = float(self.violated_by_agent.sum())
        return {
            "carbon_kg": round(float(self.carbon_kg.sum() + self.idle_carbon_kg), 3),
            "variable_carbon_kg": round(float(self.carbon_kg.sum()), 3),
            "idle_carbon_kg": round(float(self.idle_carbon_kg), 3),
            "offered_gpu_s": round(offered, 1),
            "served_gpu_s": round(float(self.served_gpu_s), 1),
            "missed_fraction": round(missed / offered, 4) if offered else 0.0,
            # The learner's history logger reads this name; a missed deadline is
            # exactly what it means, so the alias is the honest one.
            "sla_violation_fraction": round(missed / offered, 4) if offered else 0.0,
            "missed_by_agent": [
                round(float(v) / float(self.owned_gpu_s[i]), 4)
                if self.owned_gpu_s[i] > 1e-9
                else 0.0
                for i, v in enumerate(self.violated_by_agent)
            ],
            "carbon_by_agent": [round(float(v), 3) for v in self.carbon_kg],
            "max_slot_violation_fraction": round(
                float(max(self.slot_violations, default=0.0) / offered), 4
            )
            if offered
            else 0.0,
            "cvar90_slot_violation_fraction": round(
                float(_cvar(self.slot_violations, 0.9) / offered), 4
            )
            if offered
            else 0.0,
        }


def _cvar(values: list[float], alpha: float) -> float:
    """Mean of the worst ``1 - alpha`` fraction of a per-slot series."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(1, int(round((1.0 - alpha) * len(ordered))))
    return sum(ordered[-k:]) / k
