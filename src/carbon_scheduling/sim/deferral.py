"""Give every controller the timing lever, identically, without patching upstream.

exp022 established that our planner ties the best published controller exactly,
and exp023 explained why: the benchmark's controller interface is placement-only.
``ClusterManager.distribute_workload`` enqueues a task only when a strategy
returns a datacenter id; returning ``None`` discards it, and
``get_tasks_for_timestep`` never re-serves an arrival. So no rule-based controller
can express "run this later", and the one lever the project has shown to be worth
6-12% of carbon is unavailable to all of them.

This module makes that lever available to *every* controller on identical terms.
It wraps two methods on the cluster-manager instance at runtime:

* ``get_tasks_for_timestep`` additionally returns tasks held back earlier;
* ``distribute_workload`` may hold a task back instead of placing it.

Upstream's source is untouched, and the placement decision still belongs entirely
to whichever strategy is installed -- published or ours. That is what makes the
comparison fair: the timing policy is shared, so a difference in outcome is
attributable to the controller, not to us having given ourselves a better lever.

Two guarantees, both pinned by tests
------------------------------------
1. **No task is lost or duplicated.** Every offered task is placed exactly once,
   so all arms serve identical work and the comparison is matched-service.
2. **Deferral never pushes a task past its last legal start.** A task is placed
   at the latest slot from which it can still finish by ``sla_deadline``. This
   matters because upstream counts SLA only on *finished* tasks: a buffer that
   silently dropped expired work would flatter every deferral arm.

Policies
--------
``none``
    No deferral. Reproduces the published behaviour exactly (the control).
``myopic``
    Defer to the cheapest slot still inside the deadline, if it beats now. This
    is the natural temporal extension of ``lowest_carbon`` and is what a published
    controller would get.
``reserve``
    The same, but each future slot has a capacity budget derived from the trailing
    arrival rate, and a task that cannot book a cheap slot is served *now* rather
    than queueing for it. This is the planner's calibrated-reserve idea ported to
    a per-task stream: a cheap block is not infinite, and predicted arrivals need
    it too. exp016 measured the failure this prevents -- deferred peaks piling onto
    one slot and forcing placement on the dirtiest site.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

POLICIES = ("none", "myopic", "reserve")


class DeferralBuffer:
    """Runtime wrapper adding a shared, causal timing policy to any controller.

    ``intensity_at(timestamp)`` returns the best (lowest) forecast intensity
    available across sites at that time. It is injected rather than imported so
    the buffer is testable without the simulator, and so the caller decides
    whether the signal is a forecast or something else -- it must be causal.
    """

    def __init__(
        self,
        cluster: Any,
        *,
        intensity_at: Callable[[datetime], float],
        policy: str = "myopic",
        slot_minutes: int = 15,
        reserve_fraction: float = 0.0,
        arrivals_per_slot: float = 1.0,
        max_horizon_slots: int | None = None,
    ) -> None:
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")
        self._cluster = cluster
        self._intensity_at = intensity_at
        self._policy = policy
        self._slot = timedelta(minutes=slot_minutes)
        self._reserve_fraction = float(reserve_fraction)
        self._budget = max(1, int(arrivals_per_slot * (1.0 - self._reserve_fraction)))
        self._max_horizon_slots = max_horizon_slots

        self._pending: list[Any] = []
        self._reservation: dict[int, datetime] = {}
        self._booked: dict[datetime, int] = {}
        self._placed = 0
        self._deferred_events = 0
        self._forced_late = 0
        self._reserve_blocked = 0
        self._deferral_steps: list[int] = []
        self._first_seen: dict[int, datetime] = {}
        self._installed = False

    # -- installation ------------------------------------------------------

    def install(self) -> None:
        """Wrap the two cluster-manager methods. Idempotent."""
        if self._installed:
            return
        original_get = self._cluster.get_tasks_for_timestep
        original_dist = self._cluster.distribute_workload

        def get_tasks(current_time: Any) -> list[Any]:
            fresh = list(original_get(current_time))
            due = self._pending
            self._pending = []
            return fresh + due

        def distribute(task: Any, current_time: Any, logger: Any) -> Any:
            return self._decide(task, current_time, logger, original_dist)

        self._cluster.get_tasks_for_timestep = get_tasks
        self._cluster.distribute_workload = distribute
        self._installed = True

    # -- decision ----------------------------------------------------------

    def _has_slack(self, task: Any, now: datetime) -> bool:
        """Can the task still start now and finish by its deadline?"""
        return now + timedelta(minutes=float(task.duration)) <= task.sla_deadline

    def _legal_future(self, task: Any, now: datetime) -> list[datetime]:
        """Slots strictly after now from which the task can still finish in time."""
        out: list[datetime] = []
        step = 1
        while True:
            if self._max_horizon_slots is not None and step > self._max_horizon_slots:
                break
            slot = now + self._slot * step
            if slot + timedelta(minutes=float(task.duration)) > task.sla_deadline:
                break
            out.append(slot)
            step += 1
        return out

    def _target(self, task: Any, now: datetime) -> datetime | None:
        """The slot this task should wait for, or None to serve it now."""
        future = self._legal_future(task, now)
        if not future:
            return None
        now_intensity = self._intensity_at(now)
        # Cheapest first, earliest slot breaking ties so runs are deterministic.
        candidates = sorted(future, key=lambda s: (self._intensity_at(s), s))
        held = self._reservation.get(id(task))
        if held is not None and held in future and self._intensity_at(held) < now_intensity:
            return held
        for slot in candidates:
            if self._intensity_at(slot) >= now_intensity:
                break
            if self._policy != "reserve":
                return slot
            if self._booked.get(slot, 0) < self._budget:
                return slot
        if self._policy == "reserve":
            self._reserve_blocked += 1
        return None

    def _release(self, task: Any) -> None:
        slot = self._reservation.pop(id(task), None)
        if slot is not None:
            self._booked[slot] = max(0, self._booked.get(slot, 0) - 1)

    def _decide(
        self,
        task: Any,
        now: datetime,
        logger: Any,
        original_dist: Callable[..., Any],
    ) -> Any:
        key = id(task)
        self._first_seen.setdefault(key, now)

        if self._policy == "none":
            return self._place(task, now, logger, original_dist)

        if not self._has_slack(task, now):
            # No room left: place it rather than drop it, so it is counted.
            self._forced_late += 1
            return self._place(task, now, logger, original_dist)

        target = self._target(task, now)
        if target is None:
            return self._place(task, now, logger, original_dist)

        if key not in self._reservation:
            self._reservation[key] = target
            self._booked[target] = self._booked.get(target, 0) + 1
        self._pending.append(task)
        self._deferred_events += 1
        return None

    def _place(
        self,
        task: Any,
        now: datetime,
        logger: Any,
        original_dist: Callable[..., Any],
    ) -> Any:
        self._release(task)
        first = self._first_seen.pop(id(task), now)
        waited = int((now - first).total_seconds() // self._slot.total_seconds())
        self._deferral_steps.append(waited)
        self._placed += 1
        return original_dist(task, now, logger)

    # -- reporting ---------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        steps = self._deferral_steps
        return {
            "policy": self._policy,
            "placed": self._placed,
            "deferred_events": self._deferred_events,
            "forced_late": self._forced_late,
            "reserve_blocked": self._reserve_blocked,
            "still_held_at_end": len(self._pending),
            "reserve_budget_per_slot": self._budget if self._policy == "reserve" else None,
            "mean_wait_slots": round(sum(steps) / len(steps), 4) if steps else 0.0,
            "max_wait_slots": max(steps) if steps else 0,
        }
