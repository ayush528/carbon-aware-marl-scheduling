"""exp019: does the *shape* of the incoming work beat one constant reserve?

Why this experiment
-------------------
exp018 replaced the hand-tuned reserve with a calibrated one and it held its own:
810.1 kg at 3.65% missed on the slack fleet against the tuned 812.6 / 3.75%. But
it also exposed the limit of that idea. The reserve is a single number for the
whole week, while the workload has a diurnal shape -- the Azure trace is quiet for
hours and then bursts. A constant reserve over-holds in the quiet period (paying
carbon for capacity nothing uses) and under-holds right before a burst (losing
work the plan could have served).

exp017 measured where the remaining headroom is: every arm sits 20-25% above the
exact schedule at its own served volume, and the gap did not shrink with the
reserve or with the exact solver -- so it is arrivals the plan has not seen.

What this experiment tests
--------------------------
``BlockPlanner`` now anticipates arrivals in three ways (``rl/hybrid.py``):

* ``none`` -- no anticipation; the plan competes with its own future.
* ``flat`` -- hold the trailing mean of the last ``arrival_window`` slots in every
  future block, spread over the tightest deadline window.
* ``seasonal`` -- hold the *same slot of the previous day* (48 slots earlier),
  falling back to the trailing mean where a day of history does not exist. This
  is the shape a constant cannot express, and it is causal: it reads only slots
  before the one it predicts.

The hold is per block, not per fleet, so a cheap slot is defended only when the
plan expects to need it.

Protocol
--------
Same 12 held-out Oct-Dec 2024 weeks, same two fleets, same three prices and the
same own-volume bound as exp017/exp018, so the arms are comparable across the
three experiments. The arms are the two rules from exp016's frontier, the planner
with no anticipation, with exp018's calibrated reserve (level 0.95, the level that
won on the slack fleet), with each of the two arrival models, and with each model
*plus* the calibrated reserve -- the last pair answers whether the shape subsumes
the quantile or the two are additive.

No parameter is chosen on the evaluation weeks: the level and the window are
fixed in the config and are the values exp018 already used.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.experiments.exp013_marl_dispatch import _paired
from carbon_scheduling.experiments.exp016_queue_ownership import _env_for
from carbon_scheduling.experiments.exp018_arrival_reserve import (
    _hybrid_env,
    _mean_bound,
    _objective,
    calibrate,
)
from carbon_scheduling.rl import data
from carbon_scheduling.rl.arrival_risk import reserve_per_site_slot
from carbon_scheduling.rl.hybrid import BlockPlanner, run_scheduler
from carbon_scheduling.rl.queue_rules import run_rule

SLOT_MINUTES = 30


def _arms(reserve_gpu_s: float, window: int, level: int) -> dict[str, BlockPlanner]:
    """The planner variants, identical apart from how they anticipate arrivals.

    ``hold`` reserves capacity in every future block, spread over the tightest
    deadline window. ``ghost`` instead adds the prediction to the plan as an item
    with the tightest class, so it competes for the cheapest legal blocks and
    consumes capacity only where it would actually run. The last arm asks whether
    the static calibrated reserve still adds anything on top of the best model.
    """
    return {
        "plan_none": BlockPlanner(),
        f"plan_q{level:02d}": BlockPlanner(reserve_gpu_s=reserve_gpu_s),
        "plan_hold_flat": BlockPlanner(arrival_model="flat", arrival_window=window),
        "plan_hold_seasonal": BlockPlanner(arrival_model="seasonal", arrival_window=window),
        "plan_ghost_flat": BlockPlanner(
            arrival_model="flat", arrival_window=window, ghost_arrivals=True
        ),
        "plan_ghost_seasonal": BlockPlanner(
            arrival_model="seasonal", arrival_window=window, ghost_arrivals=True
        ),
        f"plan_ghost_seasonal_q{level:02d}": BlockPlanner(
            arrival_model="seasonal",
            arrival_window=window,
            ghost_arrivals=True,
            reserve_gpu_s=reserve_gpu_s,
        ),
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    tokens = data.demand_profile(paths["demand"], int(config["n_slots"]))
    held_out = data.weekly_windows(
        series,
        months=[int(m) for m in config["eval_months"]],
        year=int(config["year"]),
        n_slots=int(config["n_slots"]),
        calibration_days=int(config["calibration_days"]),
    )
    deadlines = [int(d) for d in config["deadlines"]]
    prices = [float(p) for p in config["prices"]]
    window = int(config["arrival_window"])
    level = float(config["arrival_level"])

    throughput = float(config["sites"]["tokens_per_gpu_second"])
    calibration = calibrate(tokens / throughput, level, window)
    print(f"arrival quantile (level {level:g}, window {window}): {calibration}")

    results: dict[str, Any] = {
        "weeks": [f"{s:%Y-%m-%d}" for s in held_out],
        "deadlines": deadlines,
        "prices": prices,
        "arrival_level": level,
        "arrival_window": window,
        "calibration": {str(k): v for k, v in calibration.items()},
        "fleets": {},
        "note": (
            "The arrival models are causal: 'flat' holds the trailing mean of the "
            "previous arrival_window slots in every future block, 'seasonal' holds "
            "the same slot of the previous day (48 slots earlier) and falls back to "
            "the trailing mean where no day of history exists. Both spread the hold "
            "over the sites and the tightest deadline window, and hold it per block "
            "rather than per fleet. The calibrated reserve is exp018's level "
            f"{level:g}, fixed here rather than chosen on these weeks. The demand "
            "profile is the same single real Azure week for every arm (disclosed), "
            "and every carbon number is against that identical stream."
        ),
    }

    for fleet in config["fleets"]:
        n_gpus = int(fleet["n_gpus"])
        sites = data.make_sites({**config["sites"], "n_gpus": n_gpus}, names)
        capacity = n_gpus * SLOT_MINUTES * 60
        reserve = reserve_per_site_slot(
            calibration["quantile_gpu_s"],
            n_sites=len(names),
            min_deadline=min(deadlines),
            capacity=capacity,
        )
        print(f"\n=== {fleet['name']} ({n_gpus} GPUs/site, {capacity:.0f} GPU-s/slot)")
        print(f"  calibrated reserve: {reserve:.0f} GPU-s per site-slot")

        arms: dict[str, list[dict[str, float]]] = {}
        for rule in config["rules"]:
            arms[rule] = [
                run_rule(
                    _env_for(
                        series,
                        tokens,
                        sites,
                        names,
                        start,
                        config,
                        communicate=True,
                        include_band=True,
                        price=0.0,
                    ),
                    rule,
                )
                for start in held_out
            ]

        level_pct = int(round(level * 100))
        for label, planner in _arms(reserve, window, level_pct).items():
            if reserve <= 0.0 and f"q{level_pct:02d}" in label:
                # A zero quantile is the no-reserve planner; do not duplicate it.
                continue
            arms[label] = [
                run_scheduler(_hybrid_env(series, tokens, sites, names, start, config), planner)
                for start in held_out
            ]

        report: dict[str, Any] = {"n_gpus_per_site": n_gpus, "arms": {}}
        for label, rows in arms.items():
            entry: dict[str, Any] = {
                "carbon_kg": round(float(np.mean([r["carbon_kg"] for r in rows])), 3),
                "missed_fraction": round(float(np.mean([r["missed_fraction"] for r in rows])), 4),
                "carbon_g_per_served_kwh": round(
                    float(np.mean([r["variable_carbon_kg"] for r in rows]))
                    / max(float(np.mean([r["served_gpu_s"] for r in rows])) / 3600.0, 1e-9)
                    * 1000.0,
                    1,
                ),
                "objective_at_price": {
                    str(p): round(float(np.mean([_objective(r, p) for r in rows])), 3)
                    for p in prices
                },
                "paired_vs_run_now": (
                    None if label == "run_now" else _paired(rows, arms["run_now"])
                ),
            }
            entry["paired_vs_plan_none"] = (
                None if label == "plan_none" else _paired(rows, arms["plan_none"])
            )
            bound = _mean_bound(
                series, tokens, sites, names, config, held_out, deadlines, capacity, rows
            )
            entry["bound_at_own_volume_kg"] = bound
            entry["gap_to_own_bound_pct"] = round((entry["carbon_kg"] / bound - 1.0) * 100.0, 2)
            report["arms"][label] = entry

        results["fleets"][fleet["name"]] = report
        for label, entry in report["arms"].items():
            objs = " ".join(f"p{p:g}={entry['objective_at_price'][str(p)]:.0f}" for p in prices)
            print(
                f"  {label:16s} carbon {entry['carbon_kg']:8.1f} kg"
                f"  missed {entry['missed_fraction']:.4f}"
                f"  {entry['carbon_g_per_served_kwh']:5.1f} g/kWh"
                f"  | {objs}"
                f"  | own-bound gap {entry['gap_to_own_bound_pct']:+6.2f}%"
            )
    return results
