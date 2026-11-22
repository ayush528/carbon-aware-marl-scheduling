"""Multi-agent scheduling environment: one agent per region (Phase 3, rung 6).

The physical model is the one exp012 used -- same demand week, same deadlines,
same energy curve -- but the decision is decentralised. Each region is an agent
that makes two choices every slot:

* a **risk level** ``lam``: the price it quotes is ``forecast + lam * band``,
  i.e. how much of its own forecast uncertainty it charges for;
* an **offer**: volunteer a quarter, a half, or all of its slot capacity (or
  wait, which serves nothing at all).

A coordinator we do not train fills the cheapest bids with spare capacity and
spills down the order. That is the decentralized market the paper argues for:
no agent sees the others' private forecasts, only what they broadcast.

Communication is deliberately thin, matching the "limited communication" claim:
each agent sees the *previous slot's* mean bid and mean accepted share of the
other agents. One flag removes those two numbers for the ablation.

Incentives are local, which is what makes the coordination problem real::

    r_i = - (own carbon)
            - sla_penalty * share of violated work
            - hold_penalty * share of held work

The share of a deadline miss is attributed **in proportion to capacity the
agent refused to offer**, so refusing work to protect one's own carbon bill
costs the refuser. If nobody refused, the miss is split equally. That rule is a
disclosed modelling choice, not a measured fact.
"""

from __future__ import annotations

import numpy as np

from carbon_scheduling import dispatch
from carbon_scheduling.cluster import Site, site_energy_kwh

SLOT_MINUTES = 30
OFFERS = (0.25, 0.5, 1.0)  # fraction of slot capacity volunteered; 0 = wait
LAMBDAS = (0.0, 0.5, 1.0, 2.0)  # risk levels an agent can quote


class MultiAgentEnv:
    """Joint-action env; ``agents`` are the sites, in order."""

    def __init__(
        self,
        *,
        forecast: np.ndarray,
        realized: np.ndarray,
        band: np.ndarray,
        demand_tokens: np.ndarray,
        sites: list[Site],
        deadline_slots: int = 8,
        sla_penalty_kg_per_kwh: float = 1.0,
        hold_penalty_kg_per_kwh: float = 0.05,
        communicate: bool = True,
        include_band_in_obs: bool = True,
        allow_decline: bool = True,
    ) -> None:
        forecast = np.asarray(forecast, dtype=np.float64)
        realized = np.asarray(realized, dtype=np.float64)
        band = np.asarray(band, dtype=np.float64)
        demand_tokens = np.asarray(demand_tokens, dtype=np.float64)
        if forecast.shape != realized.shape or forecast.shape != band.shape:
            raise ValueError(
                f"forecast/realized/band must share shape, got "
                f"{forecast.shape} / {realized.shape} / {band.shape}"
            )
        if forecast.ndim != 2 or forecast.shape[0] != demand_tokens.shape[0]:
            raise ValueError(
                f"demand has {demand_tokens.shape[0]} slots but carbon has {forecast.shape[0]}"
            )
        if len(sites) != forecast.shape[1]:
            raise ValueError(f"{len(sites)} sites for {forecast.shape[1]} carbon columns")
        names = [site.name for site in sites]
        if len(set(names)) != len(names):
            raise ValueError(f"site names must be unique, got {names}")
        if deadline_slots < 1:
            raise ValueError("deadline_slots must be >= 1")

        self.forecast = forecast
        self.realized = realized
        self.band = band
        self.demand_tokens = demand_tokens
        self.sites = sites
        self.deadline_slots = int(deadline_slots)
        self.sla_penalty = float(sla_penalty_kg_per_kwh)
        self.hold_penalty = float(hold_penalty_kg_per_kwh)
        self.communicate = communicate
        self.include_band_in_obs = include_band_in_obs
        self.allow_decline = allow_decline

        self.n_slots, self.n_agents = forecast.shape
        self.capacity_gpu_s = np.array(
            [site.n_gpus * SLOT_MINUTES * 60 for site in sites], dtype=np.float64
        )
        self.throughput = sites[0].tokens_per_gpu_second
        if len({site.tokens_per_gpu_second for site in sites}) != 1:
            raise ValueError("agents must share one throughput for demand to be one queue")
        # With decline allowed, an action is a (risk level, offer) pair. Under a
        # service obligation the offer is fixed at full capacity, so an action is
        # just a risk level -- and "wait" is the only way to serve nothing.
        self.offers = OFFERS if allow_decline else (1.0,)
        self.n_actions = len(LAMBDAS) * len(self.offers) + 1
        # shared(4) + local(forecast, [band], next forecast) + [two peer numbers]
        self.obs_dim = 6 + (1 if include_band_in_obs else 0) + (2 if communicate else 0)
        self.wait_action = self.n_actions - 1
        self.global_state_dim = 4 + self.n_agents * (2 if include_band_in_obs else 1) + 2
        self.reset()

    # --- action encoding -------------------------------------------------

    def decode(self, action: int) -> tuple[float, float]:
        """``action -> (lam, offer_fraction)``; raises on an out-of-range action."""
        action = int(action)
        if not 0 <= action < self.n_actions:
            raise ValueError(f"action {action!r} outside 0..{self.n_actions - 1}")
        if action == self.wait_action:
            return LAMBDAS[0], 0.0
        lam = LAMBDAS[action // len(self.offers)]
        return lam, self.offers[action % len(self.offers)]

    def encode(self, lam: float, offer: float) -> int:
        """Inverse of :meth:`decode` for the nearest grid point (rules use it)."""
        if offer == 0.0:
            return self.wait_action
        index = int(np.argmin([abs(v - lam) for v in LAMBDAS]))
        if not self.allow_decline:
            return index
        return index * len(self.offers) + int(np.argmin([abs(v - offer) for v in OFFERS]))

    # --- lifecycle -------------------------------------------------------

    def reset(self) -> tuple[np.ndarray, dict]:
        self.t = 0
        self.backlog: list[tuple[float, int]] = []
        self.carbon_kg = np.zeros(self.n_agents)
        self.violated_gpu_s = 0.0
        self.violated_tasks = 0
        self.served_gpu_s = 0.0
        self.held_gpu_s = 0.0
        self.last_bid = np.full(self.n_agents, np.nan)
        self.last_served_share = np.zeros(self.n_agents)
        self.refused_gpu_s = np.zeros(self.n_agents)
        self.violated_by_agent = np.zeros(self.n_agents)
        self.slot_violations: list[float] = []
        self._arrive()
        return self.observations(), {}

    def _arrive(self) -> None:
        amount = self.demand_tokens[self.t] / self.throughput
        if amount > 0:
            self.backlog.append((amount, self.t + self.deadline_slots))

    # --- observations ----------------------------------------------------

    def _shared(self) -> list[float]:
        t = self.t
        hour = (t * SLOT_MINUTES / 60.0) % 24
        queued = sum(item[0] for item in self.backlog)
        min_deadline = min((item[1] - t for item in self.backlog), default=self.deadline_slots)
        return [
            np.sin(2 * np.pi * hour / 24),
            np.cos(2 * np.pi * hour / 24),
            queued / self.capacity_gpu_s.sum(),
            min_deadline / self.deadline_slots,
        ]

    def _local(self, i: int) -> list[float]:
        t = self.t
        horizon = slice(t, min(t + 4, self.n_slots))
        next_fc = float(self.forecast[horizon, i].mean())
        local = [self.forecast[t, i] / 300.0]
        if self.include_band_in_obs:
            local.append(self.band[t, i] / 300.0)
        local.append(next_fc / 300.0)
        return local

    def observations(self) -> np.ndarray:
        """Per-agent observations, shape ``(n_agents, obs_dim)``."""
        shared = self._shared()
        out = np.zeros((self.n_agents, self.obs_dim), dtype=np.float32)
        others = np.ones((self.n_agents, self.n_agents), dtype=bool) & ~np.eye(
            self.n_agents, dtype=bool
        )
        for i in range(self.n_agents):
            features = shared + self._local(i)
            if self.communicate:
                peers = others[i]
                bids = self.last_bid[peers]
                bids = bids[np.isfinite(bids)]
                shares = self.last_served_share[peers]
                features.extend(
                    [
                        float(bids.mean()) / 300.0 if bids.size else 0.0,
                        float(shares.mean()) if shares.size else 0.0,
                    ]
                )
            out[i] = np.asarray(features, dtype=np.float32)
        return out

    def global_state(self) -> np.ndarray:
        """Shared summary for a centralised critic (MAPPO); no private detail."""
        shared = self._shared()
        carbon = []
        for i in range(self.n_agents):
            carbon.append(self.forecast[self.t, i] / 300.0)
            if self.include_band_in_obs:
                carbon.append(self.band[self.t, i] / 300.0)
        bids = self.last_bid[np.isfinite(self.last_bid)]
        state = (
            shared
            + carbon
            + [
                float(bids.mean()) / 300.0 if bids.size else 0.0,
                float(self.last_served_share.mean()),
            ]
        )
        return np.asarray(state, dtype=np.float32)

    # --- dynamics --------------------------------------------------------

    def _violations(self) -> float:
        expired = [item for item in self.backlog if item[1] <= self.t]
        self.backlog = [item for item in self.backlog if item[1] > self.t]
        self.violated_tasks += len(expired)
        amount = sum(item[0] for item in expired)
        self.violated_gpu_s += amount
        return amount

    def _blame(self, refused: np.ndarray) -> np.ndarray:
        """Shares of a system-wide miss: proportional to refused capacity."""
        total = float(refused.sum())
        if total > 0:
            return refused / total
        return np.full(self.n_agents, 1.0 / self.n_agents)

    def step(
        self, actions: list[int] | np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, bool, bool, dict]:
        actions = [int(a) for a in actions]
        if len(actions) != self.n_agents:
            raise ValueError(f"expected {self.n_agents} actions, got {len(actions)}")

        expired_gpu_s = self._violations()

        scores: dict[str, float] = {}
        capacity: dict[str, float] = {}
        offers = np.zeros(self.n_agents)
        bids = np.full(self.n_agents, np.nan)
        for i, action in enumerate(actions):
            lam, offer = self.decode(action)
            offers[i] = offer
            name = self.sites[i].name
            price = self.forecast[self.t, i] + lam * self.band[self.t, i]
            # A declining agent prices itself out of the market.
            scores[name] = price if offer > 0 else np.inf
            capacity[name] = offer * self.capacity_gpu_s[i]
            bids[i] = price if offer > 0 else np.nan

        queued = sum(item[0] for item in self.backlog)
        alloc, _unserved = dispatch.allocate(scores, queued, capacity)

        # Earliest deadline first: the oldest debt is the most expensive to
        # leave behind, so it takes the capacity first.
        self.backlog.sort(key=lambda item: item[1])
        to_serve = sum(alloc.values())
        remaining: list[tuple[float, int]] = []
        for amount, deadline in self.backlog:
            if to_serve <= 0:
                remaining.append((amount, deadline))
                continue
            take = min(amount, to_serve)
            to_serve -= take
            if amount - take > 0:
                remaining.append((amount - take, deadline))
        self.backlog = remaining
        served = sum(alloc.values())
        self.served_gpu_s += served
        self.slot_violations.append(float(expired_gpu_s))

        carbon = np.zeros(self.n_agents)
        for i, site in enumerate(self.sites):
            energy = site_energy_kwh(site, alloc[site.name], SLOT_MINUTES)
            carbon[i] = energy * float(self.realized[self.t, i]) / 1000.0
        self.carbon_kg += carbon

        held = sum(item[0] for item in self.backlog)
        self.held_gpu_s += held

        refused = (1.0 - offers) * self.capacity_gpu_s
        self.refused_gpu_s += refused
        blame = self._blame(refused)
        self.violated_by_agent += blame * expired_gpu_s

        rewards = (
            -carbon
            - self.sla_penalty * blame * expired_gpu_s / 3600.0
            - self.hold_penalty * held / 3600.0 / self.n_agents
        )

        self.last_bid = bids
        self.last_served_share = np.array(
            [
                alloc[self.sites[i].name] / (offers[i] * self.capacity_gpu_s[i])
                if offers[i] > 0
                else 0.0
                for i in range(self.n_agents)
            ],
            dtype=np.float64,
        )

        self.t += 1
        done = self.t >= self.n_slots
        if not done:
            self._arrive()
        else:
            # Anything left when the window closes is a missed deadline, blamed
            # by the same rule as a mid-episode miss.
            leftover = sum(item[0] for item in self.backlog)
            self.violated_gpu_s += leftover
            self.violated_tasks += len(self.backlog)
            self.backlog = []
            self.slot_violations[-1] += float(leftover)
            terminal_blame = self._blame(refused)
            self.violated_by_agent += terminal_blame * leftover
            rewards = rewards - self.sla_penalty * terminal_blame * leftover / 3600.0

        obs = (
            self.observations()
            if not done
            else np.zeros((self.n_agents, self.obs_dim), dtype=np.float32)
        )
        info = {
            "served_gpu_s": served,
            "expired_gpu_s": expired_gpu_s,
            "held_gpu_s": held,
            "carbon_kg": carbon,
            "violated_gpu_s_by_agent": blame * expired_gpu_s,
        }
        return obs, rewards, done, False, info

    def summary(self) -> dict[str, float]:
        offered = float(self.demand_tokens.sum() / self.throughput)
        return {
            "carbon_kg": round(float(self.carbon_kg.sum()), 3),
            "offered_gpu_s": round(float(offered), 1),
            "served_gpu_s": round(float(self.served_gpu_s), 1),
            "unserved_fraction": round(float((offered - self.served_gpu_s) / offered), 4)
            if offered
            else 0.0,
            "sla_violation_fraction": round(float(self.violated_gpu_s / offered), 4)
            if offered
            else 0.0,
            "violated_tasks": int(self.violated_tasks),
            # Held work, in GPU-seconds: the third term of the reward, so a
            # summary can be scored on the objective the agent was trained on.
            "held_gpu_s": round(float(self.held_gpu_s), 1),
            # Tail risk: the worst single slot, and the mean of the worst 10% of
            # slots. CVaR is supposed to move these, not the total.
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
