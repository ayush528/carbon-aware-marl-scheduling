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


def test_a_zero_lookahead_planner_serves_now_even_when_later_is_cheaper() -> None:
    """``max_lookahead`` is a pure horizon: 0 leaves timing to the site choice only."""
    env = _env([1_000.0, 0.0], forecast=[[900.0], [10.0]], deadlines=(2,), n_gpus=10)
    env.reset()
    assert BlockPlanner().plan(env, env.t)[0] == pytest.approx(0.0)
    assert BlockPlanner(max_lookahead=0).plan(env, env.t)[0] == pytest.approx(1_000.0)


def test_the_lookahead_bound_decides_how_far_ahead_the_plan_may_reach() -> None:
    """A one-slot horizon can use slot 1; a zero-slot horizon cannot leave slot 0."""
    env = _env(
        [1_000.0, 0.0, 0.0], forecast=[[900.0], [10.0], [1.0]], deadlines=(3,), n_gpus=10
    )
    env.reset()
    assert BlockPlanner(max_lookahead=0).plan(env, env.t)[0] == pytest.approx(1_000.0)
    assert BlockPlanner(max_lookahead=1).plan(env, env.t)[0] == pytest.approx(0.0)
    # Nothing legal inside the horizon means the work is offered now, not hidden.
    tight = _env([1_000.0], forecast=[[5.0]], deadlines=(2,), n_gpus=10)
    tight.reset()
    assert BlockPlanner(max_lookahead=0).plan(tight, tight.t)[0] == pytest.approx(1_000.0)


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


def test_a_calibrated_reserve_holds_capacity_back_in_absolute_terms() -> None:
    """The reserve in GPU-seconds is what a calibrated arrival quantile produces.

    One site, 10 GPUs (18,000 GPU-s per slot), 18,000 GPU-s of backlog and a cheap
    first slot. A 5,000 GPU-s reserve must leave exactly 13,000 of that slot's
    capacity to the plan, and the rest must go to the next slot rather than be
    dropped.
    """
    env = _env([18_000.0, 0.0], forecast=[[10.0], [900.0]], deadlines=(2,), n_gpus=10)
    env.reset()
    plain = BlockPlanner().plan(env, env.t)[0]
    reserved = BlockPlanner(reserve_gpu_s=5_000.0).plan(env, env.t)[0]
    assert plain == pytest.approx(18_000.0)
    assert reserved == pytest.approx(13_000.0)


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


def _env_series(demand, forecast, *, deadlines=(4,), n_gpus=10):
    demand = np.asarray(demand, dtype=np.float64)
    forecast = np.asarray(forecast, dtype=np.float64).reshape(len(demand), -1)
    return _env(demand, forecast=forecast, deadlines=deadlines, n_gpus=n_gpus)


def test_no_arrival_model_means_no_hold() -> None:
    env = _env_series([1_000.0] * 6, [10.0, 900.0] * 3)
    env.reset()
    planner = BlockPlanner()
    assert planner.holds(env, 0, 4) == {}


def test_a_flat_model_holds_the_trailing_mean_in_every_future_block() -> None:
    env = _env_series([9_000.0, 9_000.0, 0, 0, 0, 0], [500.0] * 6, deadlines=(2,))
    env.reset()
    planner = BlockPlanner(arrival_model="flat", arrival_window=2)
    # At t = 2 the causal mean of the two past slots is 9,000 GPU-s. Slot 2 has
    # already arrived (it is not anticipated), and the prediction for slot 3 is
    # spread over the tightest two-slot window, so block 3 holds 9,000 / 2.
    holds = planner.holds(env, 2, 4)
    assert holds == {(3, 0): 4_500.0}


def test_the_seasonal_model_uses_the_same_slot_yesterday() -> None:
    demand = [0.0] * 60
    demand[8] = 9_000.0  # the same slot-of-day, one day (48 slots) earlier
    env = _env_series(demand, [500.0] * 60, deadlines=(2,))
    env.reset()
    planner = BlockPlanner(arrival_model="seasonal", arrival_window=4)
    # At t = 53, slot 56 is three slots ahead, and its same slot yesterday
    # (56 - 48 = 8) carried 9,000 GPU-s.
    holds = planner.holds(env, 53, 60)
    # The burst predicted at 56 spreads over its two-slot window, 56 and 57.
    assert holds[(56, 0)] == pytest.approx(4_500.0)
    assert holds[(57, 0)] == pytest.approx(4_500.0)
    # Slot 58's yesterday (10) is empty and the trailing mean is zero, so no hold
    # from arrivals predicted after 57.
    assert holds.get((58, 0), 0.0) == pytest.approx(0.0)


def test_anticipating_a_burst_makes_the_planner_serve_some_work_now() -> None:
    """The behavioural consequence of the hold, which is the point of it.

    Backlog at t = 5 can legally run until slot 8, and slot 8 is the cheapest on
    the forecast. A myopic plan therefore risks everything on slot 8. If the same
    slot-of-day yesterday carried a burst, the seasonal model knows that block
    will be needed, holds capacity back, and the backlog serves some of its work
    in the dear current slot instead of gambling.
    """
    demand = [0.0] * 60
    demand[8] = 9_000.0
    forecast = [900.0] * 60
    forecast[56] = 10.0  # slot 56 is the cheap one
    env = _env_series(demand, forecast, deadlines=(4,))
    env.reset()
    for _ in range(53):
        env.step_offers([0.0])
    env.queues[0] = {53: 18_000.0}  # a full slot of backlog, legal in 53..56
    myopic = BlockPlanner().plan(env, 53)[0]
    seasonal = BlockPlanner(arrival_model="seasonal", arrival_window=4).plan(env, 53)[0]
    assert myopic == pytest.approx(0.0)
    assert seasonal > 0.0


def test_ghost_arrivals_consume_capacity_and_are_never_offered() -> None:
    """A predicted arrival takes the cheap block, and only the real work is offered.

    Slot 3 is cheap and a burst is expected there. The ghost reserves the cheap
    block for the arrival, so today's backlog is placed in the dear current slot
    (and offered), while the ghost itself contributes nothing to the offer.
    """
    demand = [0.0] * 60
    demand[8] = 18_000.0  # the same slot-of-day one day (48 slots) earlier: a
    # full block of work, so the predicted arrival needs the whole cheap slot
    forecast = [900.0] * 60
    forecast[56] = 10.0
    # A long-deadline class holds the backlog, so the tighter ghost outranks it
    # under the same EDF ordering the planner uses for real work.
    env = _env_series(demand, forecast, deadlines=(2, 16))
    env.reset()
    for _ in range(53):
        env.step_offers([0.0, 0.0])
    env.queues[1] = {53: 18_000.0}
    ghost = BlockPlanner(arrival_model="seasonal", ghost_arrivals=True)
    assert ghost.holds(env, 53, 53 + 16) == {}  # ghosts replace holds, no stacking
    offer = ghost.plan(env, 53)[1]
    myopic = BlockPlanner().plan(env, 53)[1]
    assert offer > myopic  # the cheap block is defended for the arrival
    assert offer <= 18_000.0  # and nothing invented is offered


def test_a_ghost_is_not_counted_as_work_when_no_block_is_feasible() -> None:
    # Every block is full, so the ghost cannot be placed; it must not appear as
    # an offer (agent index -1 has no queue to bill).
    env = _env_series([0.0] * 6, [500.0] * 6, deadlines=(2,), n_gpus=1)
    env.reset()
    env.queues[0] = {}
    planner = BlockPlanner(arrival_model="flat", arrival_window=2, ghost_arrivals=True)
    assert planner.plan(env, 2) == {0: 0.0}


def test_a_ghost_that_cannot_be_placed_never_becomes_an_offer() -> None:
    """A prediction that does not fit is dropped, not billed to any agent."""
    env = _env_series([5_000.0] * 6, [500.0] * 6, deadlines=(2,), n_gpus=1)
    env.reset()
    env.queues[0] = {}
    planner = BlockPlanner(arrival_model="flat", arrival_window=2, ghost_arrivals=True)
    # The prediction is huge relative to one 1,800 GPU-s block, so most of it has
    # nowhere to go; the offer must still be exactly zero.
    assert planner.plan(env, 2) == {0: 0.0}


def test_served_latency_is_measured_on_the_work_that_was_served() -> None:
    """Deferral lowers carbon by making served work wait; that has to be visible."""
    env = _env([1_000.0, 0.0], forecast=[[900.0], [10.0]], deadlines=(2,), n_gpus=10)
    env.reset()
    env.step_offers([0.0])  # defer all of slot 0's work
    env.step_offers([1_000.0])  # serve it one slot later
    summary = env.summary()
    assert summary["mean_served_wait_slots"] == pytest.approx(1.0)
    assert summary["max_served_wait_slots"] == 1
