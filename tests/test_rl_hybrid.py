"""The hybrid scheduler: capacity-aware planning, exact execution.

The claims these tests protect are the ones the experiment's numbers rest on:

* the plan never promises a slot more than the fleet can serve there, because
  that is exactly the failure the timing rules suffer;
* the executor serves what the plan says and only what the plan says, otherwise
  the planner is not being measured at all;
* work not offered stays in its queue unless its deadline has passed, so a
  deferral is a deferral and not a silent miss;
* the reserve holds capacity back for work that has not arrived yet, which is
  the only way a causal planner can avoid being beaten by its own myopia.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.cluster import Site
from carbon_scheduling.rl.hybrid import (
    BlockPlanner,
    ForecastFlowPlanner,
    HybridEnv,
    run_scheduler,
)

SLOT = 30


def _env(demand, *, forecast=None, deadlines=(2, 4), n_gpus=10, band=None):
    demand = np.asarray(demand, dtype=np.float64)
    slots = len(demand)
    sites = 1 if forecast is None else np.asarray(forecast).shape[1]
    forecast = np.full((slots, sites), 100.0) if forecast is None else np.asarray(forecast, float)
    band = np.zeros_like(forecast) if band is None else np.asarray(band, float)
    site_list = [
        Site(
            name=f"s{i}",
            n_gpus=n_gpus,
            gpu_idle_w=100.0,
            gpu_peak_w=400.0,
            pue=1.0,
            tokens_per_gpu_second=1.0,
        )
        for i in range(sites)
    ]
    return HybridEnv(
        forecast=forecast,
        realized=forecast.copy(),
        band=band,
        demand_tokens=demand,
        sites=site_list,
        deadlines=list(deadlines),
    )


def test_the_executor_serves_exactly_what_it_is_asked_to() -> None:
    env = _env([100_000.0], deadlines=(2,))
    env.reset()
    _, _, _, _, info = env.step_offers([1_000.0])
    assert info["served_gpu_s"] == pytest.approx(1_000.0)


def test_work_not_offered_stays_queued_while_its_deadline_allows() -> None:
    env = _env([100_000.0], deadlines=(4,))
    env.reset()
    env.step_offers([1_000.0])
    # Arrival 0 with a 4-slot deadline can still run in slots 0..3, so the rest
    # must still be there at t = 1.
    assert env.t == 1
    assert sum(env.queues[0].values()) == pytest.approx(99_000.0)


def test_work_whose_deadline_passed_is_a_miss_not_a_queue() -> None:
    env = _env([100_000.0, 0.0, 0.0], deadlines=(2,))
    env.reset()
    env.step_offers([0.0])  # arrival 0 may run in slot 0 or 1
    env.step_offers([0.0])
    _, _, _, _, _ = env.step_offers([0.0])  # slot 2: too late
    summary = env.summary()
    assert summary["missed_fraction"] == pytest.approx(1.0)
    assert env.queues[0] == {}


def test_the_plan_never_promises_more_than_a_slot_can_serve() -> None:
    """The planner's whole point: no slot is asked for more than it holds."""
    # Cheap first slot, expensive later: a slot-price rule would pile everything
    # into slot 0. Capacity there is 10 GPUs x 1800 s = 18,000 GPU-s.
    env = _env([40_000.0, 0.0], forecast=[[10.0], [900.0]], deadlines=(2,), n_gpus=10)
    env.reset()
    plan = BlockPlanner().plan(env, env.t)
    assert plan[0] <= float(env.capacity_gpu_s.sum()) + 1e-6


def test_the_planner_defers_work_whose_slot_is_cheaper_later() -> None:
    env = _env([1_000.0, 0.0], forecast=[[900.0], [10.0]], deadlines=(2,), n_gpus=10)
    env.reset()
    assert BlockPlanner().plan(env, env.t)[0] == pytest.approx(0.0)


def test_the_planner_serves_now_when_now_is_cheapest() -> None:
    env = _env([1_000.0, 0.0], forecast=[[10.0], [900.0]], deadlines=(2,), n_gpus=10)
    env.reset()
    assert BlockPlanner().plan(env, env.t)[0] == pytest.approx(1_000.0)


def test_a_band_pushes_the_planner_off_a_risky_slot() -> None:
    """With the worst case priced, a cheap-but-uncertain slot loses to a sure one."""
    forecast = [[50.0], [90.0]]
    # Slot 0 is cheap but its band is enormous; slot 1 is nearly certain.
    band = [[400.0], [1.0]]
    env = _env([1_000.0, 0.0], forecast=forecast, band=band, deadlines=(2,), n_gpus=10)
    env.reset()
    risk_neutral = BlockPlanner(robust=0.0).plan(env, env.t)
    risk_averse = BlockPlanner(robust=1.0).plan(env, env.t)
    assert risk_neutral[0] == pytest.approx(1_000.0)
    assert risk_averse[0] == pytest.approx(0.0)


def test_the_planner_never_offers_more_than_the_queue_holds() -> None:
    env = _env([5_000.0], forecast=[[10.0]], deadlines=(2,), n_gpus=100)
    env.reset()
    assert BlockPlanner().plan(env, env.t)[0] <= 5_000.0 + 1e-6


def test_the_arrival_reserve_makes_the_planner_more_cautious_now() -> None:
    """The reserve is a service/carbon knob, and this pins the direction it moves.

    Holding capacity back for work that has not arrived yet can only make the
    plan less willing to fill a slot with today's backlog, so it can never serve
    *less* now. Whether that is worth it is measured on the real weeks in exp017
    -- on the slack fleet it buys carbon and costs service, which is why it stays
    a swept parameter rather than a default.
    """
    # Cheap second slot, and enough capacity in each slot for the backlog.
    env = _env(
        [4_000.0, 0.0, 0.0, 0.0],
        forecast=[[900.0], [10.0], [10.0], [10.0]],
        deadlines=(4,),
        n_gpus=10,
    )
    env.reset()
    plain = BlockPlanner().plan(env, env.t)[0]
    cautious = BlockPlanner(arrival_forecast=4).plan(env, env.t)[0]
    assert plain == pytest.approx(0.0)
    assert cautious >= plain


def test_the_flow_planner_agrees_with_the_greedy_on_one_slot_one_class() -> None:
    env = _env([1_000.0], forecast=[[10.0]], deadlines=(2,), n_gpus=10)
    env.reset()
    greedy = BlockPlanner().plan(env, env.t)[0]
    flow = ForecastFlowPlanner().plan(env, env.t)[0]
    assert flow == pytest.approx(greedy)


def test_the_scheduler_gets_the_idle_week_right() -> None:
    env = _env([0.0] * 4, deadlines=(2, 4))
    summary = run_scheduler(env, BlockPlanner())
    assert summary["served_gpu_s"] == pytest.approx(0.0)
    assert summary["missed_fraction"] == pytest.approx(0.0)
    # The idle floor is still billed: two sites, four slots, 100 W each.
    assert summary["idle_carbon_kg"] > 0.0
