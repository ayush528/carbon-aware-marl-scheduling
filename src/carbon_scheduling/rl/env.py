"""Scheduling environment for Phase 3 agents (ours; no upstream code).

The gym the agents learn in, built on the data the earlier phases validated:

    forecast_i(t)  NESO regional forecast for region i           (input)
    realized_i(t)  national_actual x forecast_i / national_forecast
    demand(t)      Azure LLM trace, per half-hour slot           (input)
    band_i(t)      calibrated conformal half-width, from the 28 days *before*
                   the episode's week -- never from the week itself

One slot at a time the agent decides where the accumulated batch runs, or
whether to wait a slot. Waiting is the only way to reach a cleaner hour, and
every task carries a deadline, so waiting has a price. That trade -- carbon now
against carbon later, with a deadline at risk -- is the problem Phase 3 exists
to solve, and it is the axis along which calibrated uncertainty can actually
change a decision (exp011 showed it cannot change site *ranking*).

Rewards are in kilograms of CO2 with two penalties: violated work (missed the
deadline) and held work (a small per-slot cost for keeping capacity busy with
debt). All three terms are reported separately by the evaluation code, so a
policy's carbon advantage can never be an artefact of a penalty weight.

Everything is deterministic given the panel and the episode start; there is no
hidden randomness to average away.
"""

from __future__ import annotations

import numpy as np

from carbon_scheduling.cluster import Site, site_energy_kwh

SLOT_MINUTES = 30


class SchedulingEnv:
    """Single-agent view of the multi-region dispatch problem.

    Action space: ``0..N-1`` dispatch the batch to that region, ``N`` wait one
    slot. Observations are float32 vectors; see :meth:`_obs`.
    """

    def __init__(
        self,
        *,
        forecast: np.ndarray,  # (T, N) gCO2/kWh
        realized: np.ndarray,  # (T, N) gCO2/kWh
        band: np.ndarray,  # (T, N) gCO2/kWh half-width
        demand_tokens: np.ndarray,  # (T,) tokens offered per slot
        sites: list[Site],
        deadline_slots: int = 8,
        sla_penalty_kg_per_kwh: float = 1.0,
        hold_penalty_kg_per_kwh: float = 0.05,
        include_band_in_obs: bool = True,
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
        self.include_band_in_obs = include_band_in_obs

        self.n_slots, self.n_sites = forecast.shape
        self.capacity_gpu_s = np.array(
            [s.n_gpus * SLOT_MINUTES * 60 for s in sites], dtype=np.float64
        )
        self.throughput = sites[0].tokens_per_gpu_second
        self.action_space = self.n_sites + 1  # +1 = wait
        self.obs_dim = 6 + self.n_sites * (4 if include_band_in_obs else 3)
        self.idle_carbon_kg = self._idle_carbon_per_slot()
        self.reset()

    # --- internals -------------------------------------------------------

    def _idle_carbon_per_slot(self) -> np.ndarray:
        """Carbon of an idle fleet per slot (sites never power down)."""
        idle_energy = np.array(
            [site_energy_kwh(site, 0.0, SLOT_MINUTES) for site in self.sites]
        )
        return idle_energy[None, :] * self.realized / 1000.0  # kg

    def _obs(self) -> np.ndarray:
        t = self.t
        hour = (t * SLOT_MINUTES / 60.0) % 24
        day_angle = 2 * np.pi * t / self.n_slots
        backlog = sum(item[0] for item in self.backlog)
        min_deadline = min((item[1] - t for item in self.backlog), default=self.deadline_slots)
        horizon = slice(t, min(t + 4, self.n_slots))
        features = [
            np.sin(2 * np.pi * hour / 24),
            np.cos(2 * np.pi * hour / 24),
            np.sin(day_angle),
            np.cos(day_angle),
            backlog / (self.capacity_gpu_s.sum()),
            min_deadline / self.deadline_slots,
        ]
        fc = self.forecast[horizon]
        bd = self.band[horizon]
        next_fc = fc.mean(axis=0) if fc.size else np.zeros(self.n_sites)
        next_bd = bd.mean(axis=0) if bd.size else np.zeros(self.n_sites)
        for i in range(self.n_sites):
            features.append(self.forecast[t, i] / 300.0)
            if self.include_band_in_obs:
                features.append(self.band[t, i] / 300.0)
            features.extend([next_fc[i] / 300.0, next_bd[i] / 300.0])
        return np.asarray(features, dtype=np.float32)

    def _violations(self) -> tuple[float, int]:
        """Work whose deadline has passed: (gpu-seconds, tasks)."""
        expired = [item for item in self.backlog if item[1] <= self.t]
        self.backlog = [item for item in self.backlog if item[1] > self.t]
        return sum(item[0] for item in expired), len(expired)

    # --- gym API ---------------------------------------------------------

    def reset(self) -> tuple[np.ndarray, dict]:
        self.t = 0
        self.backlog: list[tuple[float, int]] = []
        self.carbon_kg = 0.0
        self.violated_gpu_s = 0.0
        self.violated_tasks = 0
        self.held_gpu_s = 0.0
        self.served_gpu_s = 0.0
        self._arrive()
        return self._obs(), {}

    def _arrive(self) -> None:
        amount = self.demand_tokens[self.t] / self.throughput
        if amount > 0:
            self.backlog.append((amount, self.t + self.deadline_slots))

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        if not 0 <= action <= self.n_sites:
            raise ValueError(f"action {action!r} outside 0..{self.n_sites}")

        # Everything already queued had its chance to run this slot; anything
        # whose deadline was this slot and is still here has now missed it.
        expired_gpu_s, expired_tasks = self._violations()
        self.violated_gpu_s += expired_gpu_s
        self.violated_tasks += expired_tasks

        carbon = float(self.idle_carbon_kg[self.t].sum())
        ran = 0.0
        if action < self.n_sites:
            # Earliest deadline first at the chosen site: the oldest debt is
            # the most expensive to leave behind.
            self.backlog.sort(key=lambda item: item[1])
            room = float(self.capacity_gpu_s[action])
            remaining: list[tuple[float, int]] = []
            for amount, deadline in self.backlog:
                if room <= 0:
                    remaining.append((amount, deadline))
                    continue
                take = min(amount, room)
                ran += take
                room -= take
                if amount - take > 0:
                    remaining.append((amount - take, deadline))
            self.backlog = remaining
            carbon += site_energy_kwh(self.sites[action], ran, SLOT_MINUTES) * float(
                self.realized[self.t, action]
            ) / 1000.0

        self.carbon_kg += carbon
        self.served_gpu_s += ran
        held = sum(item[0] for item in self.backlog)
        self.held_gpu_s += held

        reward = -(
            carbon
            + self.sla_penalty * expired_gpu_s / 3600.0
            + self.hold_penalty * held / 3600.0
        )

        self.t += 1
        done = self.t >= self.n_slots
        if not done:
            self._arrive()
        else:
            # Anything left when the window closes is a missed deadline.
            leftover = sum(item[0] for item in self.backlog)
            self.violated_gpu_s += leftover
            self.violated_tasks += len(self.backlog)
            self.backlog = []
            reward -= self.sla_penalty * leftover / 3600.0

        info = {
            "carbon_kg": carbon,
            "served_gpu_s": ran,
            "held_gpu_s": held,
            "violated_gpu_s": expired_gpu_s,
        }
        obs = (
            self._obs()
            if not done
            else np.zeros(self.obs_dim, dtype=np.float32)
        )
        return obs, reward, done, False, info

    def summary(self) -> dict[str, float]:
        """Episode totals; the units the experiment reports."""
        offered = float(self.demand_tokens.sum() / self.throughput)
        served = self.served_gpu_s
        return {
            "carbon_kg": round(self.carbon_kg, 3),
            "offered_gpu_s": round(offered, 1),
            "served_gpu_s": round(served, 1),
            "unserved_fraction": round((offered - served) / offered, 4) if offered else 0.0,
            "sla_violation_fraction": round(
                self.violated_gpu_s / offered, 4
            )
            if offered
            else 0.0,
            "violated_tasks": self.violated_tasks,
            "deferred_kwh_slots": round(self.held_gpu_s / 3600.0, 3),
        }
