"""The perfect-foresight planner: exact answers on cases with a known optimum."""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.rl.oracle import plan, plan_multi


def test_serves_in_the_cheapest_slot_the_deadline_allows() -> None:
    """Two slots, one site, one slot of slack: the cheap later slot wins."""
    cost = np.array([[10.0], [1.0], [30.0]])
    alloc, unserved = plan(cost, np.array([5.0, 0.0, 0.0]), capacity=10.0, deadline=2)
    assert unserved == pytest.approx(0.0)
    assert alloc[1, 0] == pytest.approx(5.0)
    assert alloc[0, 0] == pytest.approx(0.0)
    total = float((alloc * cost).sum())
    assert total == pytest.approx(5.0)  # 5 GPU-s at 1.0 per GPU-s


def test_a_deadline_of_one_slot_forbids_waiting() -> None:
    cost = np.array([[10.0], [1.0]])
    alloc, unserved = plan(cost, np.array([5.0, 0.0]), capacity=10.0, deadline=1)
    assert unserved == pytest.approx(0.0)
    assert alloc[0, 0] == pytest.approx(5.0)
    assert alloc[1, 0] == pytest.approx(0.0)


def test_capacity_splits_work_between_a_better_and_a_later_slot() -> None:
    """Four GPU-s cannot be deferred: the cheap slot only holds six."""
    cost = np.array([[10.0], [1.0]])
    alloc, unserved = plan(cost, np.array([10.0, 0.0]), capacity=6.0, deadline=2)
    assert unserved == pytest.approx(0.0)
    assert alloc[1, 0] == pytest.approx(6.0)
    assert alloc[0, 0] == pytest.approx(4.0)


def test_placement_prefers_the_cleaner_site_then_the_rest() -> None:
    cost = np.array([[10.0, 1.0]])
    alloc, m = plan(cost, np.array([10.0]), capacity=6.0, deadline=1)
    assert m == pytest.approx(0.0)
    assert alloc[0, 1] == pytest.approx(6.0)
    assert alloc[0, 0] == pytest.approx(4.0)


def test_never_serves_work_before_it_arrives() -> None:
    """Slot 0 is nearly free, but the demand only exists at slot 1."""
    cost = np.array([[0.01], [5.0]])
    alloc, unserved = plan(cost, np.array([0.0, 5.0]), capacity=10.0, deadline=1)
    assert unserved == pytest.approx(0.0)
    assert alloc[0, 0] == pytest.approx(0.0)
    assert alloc[1, 0] == pytest.approx(5.0)


def test_reports_the_work_capacity_cannot_hold_rather_than_dropping_it_silently() -> None:
    cost = np.array([[1.0]])
    alloc, unserved = plan(cost, np.array([20.0]), capacity=5.0, deadline=1)
    assert unserved == pytest.approx(15.0)
    assert alloc[0, 0] == pytest.approx(5.0)


def test_expired_work_is_not_carried_past_its_own_window() -> None:
    """With a two-slot deadline the first arrival is gone after slot 1."""
    cost = np.array([[10.0], [10.0], [0.0], [0.0]])
    alloc, unserved = plan(cost, np.array([5.0, 0.0, 0.0, 0.0]), capacity=10.0, deadline=2)
    assert unserved == pytest.approx(0.0)
    # slots 2 and 3 are free but too late: the work must run in 0 or 1.
    assert alloc[2:].sum() == pytest.approx(0.0)
    assert alloc[0:2].sum() == pytest.approx(5.0)


def _brute(cost, demand, capacity, deadline):
    """Exhaustive optimum for tiny integer instances: try every assignment of
    each unit of work to a (slot, site) that can legally serve it, then take the
    schedule that serves the most work and, among those, the cheapest."""
    slots, sites = cost.shape
    units = [t for t in range(slots) for _ in range(int(demand[t]))]
    cap_free = [[int(capacity)] * sites for _ in range(slots)]
    best = [(-1.0, float("inf"))]

    def walk(k, served, price):
        if k == len(units):
            better = served > best[0][0] + 1e-9 or (
                abs(served - best[0][0]) <= 1e-9 and price < best[0][1] - 1e-9
            )
            if better:
                best[0] = (served, price)
            return
        arrival = units[k]
        # Option: leave this unit unserved.
        walk(k + 1, served, price)
        for slot in range(arrival, min(arrival + deadline, slots)):
            for site in range(sites):
                if cap_free[slot][site] > 0:
                    cap_free[slot][site] -= 1
                    walk(k + 1, served + 1.0, price + float(cost[slot, site]))
                    cap_free[slot][site] += 1

    walk(0, 0.0, 0.0)
    return best[0]


def test_the_planner_matches_an_exhaustive_search_on_small_instances() -> None:
    rng = np.random.default_rng(7)
    for _ in range(25):
        slots = int(rng.integers(2, 5))
        sites = int(rng.integers(1, 3))
        cost = np.round(rng.uniform(0.1, 5.0, size=(slots, sites)), 3)
        demand = rng.integers(0, 4, size=slots).astype(float)
        capacity = float(rng.integers(1, 4))
        deadline = int(rng.integers(1, slots + 2))

        alloc, unserved = plan(cost, demand, capacity, deadline)
        served_flow = float(demand.sum()) - unserved
        price_flow = float((alloc * cost).sum())

        served_brute, price_brute = _brute(cost, demand, capacity, deadline)
        assert served_flow == pytest.approx(served_brute, abs=1e-6), (
            cost,
            demand,
            capacity,
            deadline,
        )
        assert price_flow == pytest.approx(price_brute, abs=1e-6), (
            cost,
            demand,
            capacity,
            deadline,
        )


def test_can_be_asked_for_a_fixed_volume_so_comparisons_are_matched_service() -> None:
    """Dropping work lowers carbon, so a matched-service comparison has to pin
    the volume: serve exactly this much, of the cheapest work available."""
    cost = np.array([[1.0], [5.0], [9.0]])
    demand = np.array([5.0, 5.0, 5.0])
    alloc, shed = plan(cost, demand, capacity=10.0, deadline=2, volume=5.0)
    assert shed == pytest.approx(10.0)  # 15 arrived, 5 asked for
    assert alloc[0, 0] == pytest.approx(5.0)  # the cheapest five units only
    assert float((alloc * cost).sum()) == pytest.approx(5.0)


def test_a_volume_larger_than_the_fleet_can_hold_is_capped_by_capacity() -> None:
    cost = np.array([[1.0], [1.0]])
    alloc, shed = plan(cost, np.array([5.0, 5.0]), capacity=2.0, deadline=2, volume=9.0)
    assert alloc.sum() == pytest.approx(4.0)
    assert shed == pytest.approx(6.0)


def test_padded_slots_are_charged_for_the_work_but_not_for_the_idle_floor() -> None:
    """The planner may schedule into slots beyond the week (so a late cohort is
    not trapped), but the environment only bills the idle floor inside its own
    window. Charging idle on padded slots would tax the planner for slots no
    baseline ever pays for."""
    from carbon_scheduling.cluster import Site
    from carbon_scheduling.experiments.exp015_timing_headroom import _carbon

    site = Site(
        name="s",
        n_gpus=1,
        gpu_idle_w=100.0,
        gpu_peak_w=300.0,
        pue=1.0,
        tokens_per_gpu_second=1.0,
    )
    realized = np.array([[100.0], [100.0]])
    alloc = np.array([[0.0], [1800.0]])  # slot 1 is padded (window = 1)
    kg = _carbon(alloc, realized, [site], window=1)
    idle_kwh = 100.0 * 1 * 0.5 / 1000.0  # 0.05 kWh in the real slot
    load_kwh = (300.0 - 100.0) * 0.5 / 1000.0  # 0.1 kWh for the padded work
    assert kg == pytest.approx((idle_kwh + load_kwh) * 100.0 / 1000.0)


def test_two_classes_share_the_clean_slot_by_deadline() -> None:
    """The tight class owns the cheap slot; the loose one takes the next."""
    cost = np.array([[1.0], [10.0]])
    demand = np.array([[5.0, 0.0], [5.0, 0.0]])  # tight, loose
    alloc, unserved = plan_multi(cost, demand, capacity=5.0, deadlines=[1, 2])
    assert unserved == pytest.approx(0.0)
    assert alloc[0, 0, 0] == pytest.approx(5.0)  # tight runs now
    assert alloc[1, 1, 0] == pytest.approx(5.0)  # loose defers


def test_a_class_that_may_wait_outranks_a_greedy_one_for_a_later_bargain() -> None:
    cost = np.array([[5.0], [1.0]])
    demand = np.array([[0.0, 5.0]])
    alloc, unserved = plan_multi(cost, demand, capacity=5.0, deadlines=[3])
    assert unserved == pytest.approx(0.0)
    assert alloc[0, 1, 0] == pytest.approx(5.0)


def test_volume_is_a_total_across_classes_not_per_class() -> None:
    cost = np.array([[1.0], [2.0]])
    demand = np.array([[5.0, 0.0], [5.0, 0.0]])
    alloc, shed = plan_multi(cost, demand, capacity=10.0, deadlines=[1, 1], volume=5.0)
    assert shed == pytest.approx(5.0)
    # The cheapest five units, regardless of which class they belong to.
    assert alloc.sum() == pytest.approx(5.0)
    assert float((alloc.sum(axis=0) * cost).sum()) == pytest.approx(5.0)


def test_rejects_a_deadline_of_zero() -> None:
    with pytest.raises(ValueError, match="deadline"):
        plan_multi(np.ones((2, 1)), np.ones((1, 2)), 1.0, [0])


def _brute_multi(cost, demand, capacity, deadlines):
    """Exhaustive optimum for tiny instances with per-class deadlines."""
    slots, sites = cost.shape
    units = [
        (k, t)
        for k in range(demand.shape[0])
        for t in range(slots)
        for _ in range(int(demand[k, t]))
    ]
    cap_free = [[int(capacity)] * sites for _ in range(slots)]
    best = [(-1.0, float("inf"))]

    def walk(idx, served, price):
        if idx == len(units):
            better = served > best[0][0] + 1e-9 or (
                abs(served - best[0][0]) <= 1e-9 and price < best[0][1] - 1e-9
            )
            if better:
                best[0] = (served, price)
            return
        k, arrival = units[idx]
        walk(idx + 1, served, price)  # leave it unserved
        for slot in range(arrival, min(arrival + deadlines[k], slots)):
            for site in range(sites):
                if cap_free[slot][site] > 0:
                    cap_free[slot][site] -= 1
                    walk(idx + 1, served + 1.0, price + float(cost[slot, site]))
                    cap_free[slot][site] += 1

    walk(0, 0.0, 0.0)
    return best[0]


def test_multi_class_planner_matches_exhaustive_search() -> None:
    rng = np.random.default_rng(11)
    for _ in range(30):
        slots = int(rng.integers(2, 5))
        sites = int(rng.integers(1, 3))
        cost = np.round(rng.uniform(0.1, 5.0, size=(slots, sites)), 3)
        demand = rng.integers(0, 3, size=(2, slots)).astype(float)
        capacity = float(rng.integers(1, 4))
        deadlines = [int(rng.integers(1, slots + 1)), int(rng.integers(1, slots + 1))]

        alloc, unserved = plan_multi(cost, demand, capacity, deadlines)
        served_flow = float(demand.sum()) - unserved
        price_flow = float((alloc.sum(axis=0) * cost).sum())
        served_brute, price_brute = _brute_multi(cost, demand, capacity, deadlines)
        assert served_flow == pytest.approx(served_brute, abs=1e-6), (
            cost,
            demand,
            capacity,
            deadlines,
        )
        assert price_flow == pytest.approx(price_brute, abs=1e-6), (
            cost,
            demand,
            capacity,
            deadlines,
        )
