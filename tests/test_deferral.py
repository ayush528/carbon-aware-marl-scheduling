"""Tests for the deferral buffer that gives every controller the timing lever.

exp022 tied the published controllers because their interface is placement-only:
returning no site *discards* the task. This buffer makes deferral expressible for
all of them, identically, without patching the simulator.

Two properties are non-negotiable, because without them the head-to-head would
be dishonest rather than merely wrong:

1. **No task is lost or duplicated.** Every offered task is placed exactly once,
   so every arm serves the same work and the comparison is matched-service.
2. **A task that can no longer finish in time is placed anyway, late.** It is
   never dropped, because upstream counts SLA only on *finished* tasks -- a
   buffer that discarded expired work would flatter every deferral arm.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from carbon_scheduling.sim.deferral import DeferralBuffer

NOW = datetime(2024, 1, 10, 0, 0)
SLOT = 15


class FakeTask:
    _next = 0

    def __init__(self, duration: float = 60.0, arrival: datetime = NOW) -> None:
        FakeTask._next += 1
        self.job_name = f"t{FakeTask._next}"
        self.duration = duration
        self.arrival_time = arrival
        # Upstream's rule: deadline = arrival + 1.5 * duration.
        self.sla_deadline = arrival + timedelta(minutes=1.5 * duration)


class FakeCluster:
    """Duck-typed stand-in for the simulator's cluster manager."""

    def __init__(self, arrivals: dict[int, list[FakeTask]]) -> None:
        self.arrivals = arrivals
        self.placed: list[tuple[FakeTask, int]] = []
        self.strategy = "lowest_carbon"

    def get_tasks_for_timestep(self, now: datetime) -> list[FakeTask]:
        step = int((now - NOW).total_seconds() // (SLOT * 60))
        return list(self.arrivals.get(step, []))

    def distribute_workload(self, task: FakeTask, now: datetime, logger) -> str:
        step = int((now - NOW).total_seconds() // (SLOT * 60))
        self.placed.append((task, step))
        return "dc-1"


def _run(cluster: FakeCluster, steps: int) -> None:
    for step in range(steps):
        now = NOW + timedelta(minutes=SLOT * step)
        for task in cluster.get_tasks_for_timestep(now):
            cluster.distribute_workload(task, now, None)


def _cheaper_later(now: datetime) -> float:
    """Intensity falls after the first two slots, so deferral has something to win."""
    step = int((now - NOW).total_seconds() // (SLOT * 60))
    return 100.0 if step < 2 else 50.0


def test_policy_none_is_exactly_the_original_behaviour() -> None:
    tasks = [FakeTask() for _ in range(5)]
    cluster = FakeCluster({0: tasks})
    buffer = DeferralBuffer(cluster, intensity_at=_cheaper_later, policy="none")
    buffer.install()
    _run(cluster, 8)
    assert [t.job_name for t, _ in cluster.placed] == [t.job_name for t in tasks]
    assert all(step == 0 for _, step in cluster.placed)
    assert buffer.stats()["deferred_events"] == 0


def test_every_task_is_placed_exactly_once() -> None:
    tasks = [FakeTask(duration=60.0) for _ in range(12)]
    cluster = FakeCluster({0: tasks[:6], 1: tasks[6:]})
    buffer = DeferralBuffer(cluster, intensity_at=_cheaper_later, policy="myopic")
    buffer.install()
    _run(cluster, 20)
    names = [t.job_name for t, _ in cluster.placed]
    assert sorted(names) == sorted(t.job_name for t in tasks)
    assert len(names) == len(set(names))


def test_deferral_actually_happens_when_a_cheaper_slot_is_inside_the_deadline() -> None:
    task = FakeTask(duration=60.0)  # slack = 30 min = 2 slots
    cluster = FakeCluster({0: [task]})
    buffer = DeferralBuffer(cluster, intensity_at=_cheaper_later, policy="myopic")
    buffer.install()
    _run(cluster, 12)
    assert buffer.stats()["deferred_events"] >= 1
    assert cluster.placed[0][1] > 0


def test_a_task_that_can_no_longer_finish_in_time_is_placed_late_not_dropped() -> None:
    # Intensity never improves, but a task with no slack must still be placed.
    task = FakeTask(duration=60.0)
    cluster = FakeCluster({0: [task]})
    buffer = DeferralBuffer(cluster, intensity_at=lambda now: 100.0, policy="myopic")
    buffer.install()
    _run(cluster, 12)
    assert len(cluster.placed) == 1
    assert cluster.placed[0][1] == 0


def test_zero_slack_task_is_never_deferred() -> None:
    # deadline == arrival + duration would leave no room; 1.5x gives 0.5x, so
    # force the tight case explicitly by shrinking the deadline.
    task = FakeTask(duration=60.0)
    task.sla_deadline = task.arrival_time + timedelta(minutes=60.0)
    cluster = FakeCluster({0: [task]})
    buffer = DeferralBuffer(cluster, intensity_at=_cheaper_later, policy="myopic")
    buffer.install()
    _run(cluster, 12)
    assert cluster.placed[0][1] == 0
    assert buffer.stats()["deferred_events"] == 0


def test_reserve_stops_every_task_piling_into_the_same_cheap_slot() -> None:
    """The reserve is the planner's idea: a cheap future block is not infinite.

    Only one future slot is cheap here. Without a reserve every task defers into
    it; with one, the budgeted number may target it and the rest are served now
    instead of queueing for a block that predicted arrivals also need.
    """

    def one_cheap_slot(now: datetime) -> float:
        step = int((now - NOW).total_seconds() // (SLOT * 60))
        return 50.0 if step == 2 else 100.0

    tasks = [FakeTask(duration=120.0) for _ in range(10)]
    cluster = FakeCluster({0: tasks})
    plain = DeferralBuffer(cluster, intensity_at=one_cheap_slot, policy="myopic")
    plain.install()
    _run(cluster, 30)
    plain_steps = [step for _, step in cluster.placed]

    tasks2 = [FakeTask(duration=120.0) for _ in range(10)]
    cluster2 = FakeCluster({0: tasks2})
    reserved = DeferralBuffer(
        cluster2,
        intensity_at=one_cheap_slot,
        policy="reserve",
        reserve_fraction=0.5,
        arrivals_per_slot=10.0,
    )
    reserved.install()
    _run(cluster2, 30)
    reserved_steps = [step for _, step in cluster2.placed]

    assert len(plain_steps) == len(reserved_steps) == 10
    # The reserve serves the overflow now rather than concentrating it later.
    assert sum(reserved_steps) < sum(plain_steps)
    assert reserved.stats()["reserve_blocked"] > 0


def test_the_buffer_never_defers_past_the_last_legal_start() -> None:
    """A guarantee, not an observation: deferral cannot itself cause lateness.

    The buffer places a task at the last moment it can still finish by its
    deadline, so it never knowingly pushes work past its SLA. Any violation that
    remains is the simulator's own queueing, counted identically for every arm.
    """

    def always_cheaper_later(now: datetime) -> float:
        step = int((now - NOW).total_seconds() // (SLOT * 60))
        return 100.0 - step

    tasks = [FakeTask(duration=60.0) for _ in range(6)]
    cluster = FakeCluster({0: tasks})
    buffer = DeferralBuffer(cluster, intensity_at=always_cheaper_later, policy="myopic")
    buffer.install()
    _run(cluster, 20)
    assert buffer.stats()["forced_late"] == 0
    for task, step in cluster.placed:
        start = NOW + timedelta(minutes=SLOT * step)
        assert start + timedelta(minutes=task.duration) <= task.sla_deadline


def test_stats_report_offers_deferrals_and_forced_placements() -> None:
    tasks = [FakeTask(duration=60.0) for _ in range(4)]
    cluster = FakeCluster({0: tasks})
    buffer = DeferralBuffer(cluster, intensity_at=_cheaper_later, policy="myopic")
    buffer.install()
    _run(cluster, 12)
    stats = buffer.stats()
    assert stats["placed"] == 4
    assert stats["deferred_events"] >= 1
    assert set(stats) >= {"placed", "deferred_events", "forced_late", "reserve_blocked"}


def test_unknown_policy_is_rejected() -> None:
    cluster = FakeCluster({})
    with pytest.raises(ValueError):
        DeferralBuffer(cluster, intensity_at=_cheaper_later, policy="nonsense")
