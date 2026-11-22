"""exp017: a deployable carbon-aware scheduler that plans against capacity.

What this is
------------
exp016 measured that per-agent timing rules are not ordered by how much they
know: ``forecast_timing`` sees the whole forecast and is worse per served
GPU-hour than ``last_slot``, which sees only the deadline, because the cost is
the *placement* that timing forces (15.0% of its served work landed on the
dirtiest site against 8.0%). A timing rule cannot see placement, so no amount of
forecast accuracy fixes it.

This experiment tests the scheduler that can. At each slot it prices every
(slot, site) block it could use -- ``forecast + robust * band`` -- and assigns
the backlog to the cheapest blocks that can legally hold it, respecting each
class's deadline window and each site's per-slot capacity. It executes only the
current slot's share and replans next slot. The plan is the online form of the
exact flow in ``oracle.plan_multi``; the flow stays the bound.

Three things are swept, each a real deployment decision:

* ``robust`` -- 0 prices the point forecast, 1 prices the whole calibrated band.
  This is where forecast uncertainty enters a decision. exp011 showed it cannot
  reorder sites (the ordering is exact under national scaling); here it can only
  change *when* work runs and which capacity absorbs it.
* ``reserve`` -- capacity held back from the plan. A myopic planner fills a cheap
  slot with today's backlog and leaves the arrivals that land there nowhere to
  run, so the reserve is the demand-uncertainty hedge. It is a knob, not a
  default: it trades service for carbon and both numbers are reported.
* the planner itself -- the greedy block assignment, and a rolling min-cost flow
  on the same forecast, so the cost of greediness is measured, not assumed.

Measured on 12 held-out Oct-Dec 2024 weeks, both fleets, on the objective
``carbon + price * missed GPU-hours`` at three prices (0.1 = parity with the
carbon of serving, 0.3 = the rule frontier's crossover, 1.0 = a service
obligation). Every arm is also scored against the exact schedule at *its own*
served volume, week by week, because unserved work emits nothing and a
carbon-only reading rewards shedding.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.experiments.exp013_marl_dispatch import _paired
from carbon_scheduling.experiments.exp016_queue_ownership import _env_for, _oracle
from carbon_scheduling.rl import data
from carbon_scheduling.rl.hybrid import (
    BlockPlanner,
    ForecastFlowPlanner,
    HybridEnv,
    run_scheduler,
)
from carbon_scheduling.rl.queue_rules import run_rule

SLOT_MINUTES = 30

# The deployment grid: risk appetite x demand hedge. ``plan_flow`` is the same
# problem solved exactly on the same forecast, so the cost of greediness is
# visible rather than assumed.
PLANNERS: dict[str, dict[str, Any]] = {
    "plan_r0": {"kind": "greedy", "robust": 0.0, "reserve": 0.0},
    "plan_r0_res10": {"kind": "greedy", "robust": 0.0, "reserve": 0.1},
    "plan_r0_res20": {"kind": "greedy", "robust": 0.0, "reserve": 0.2},
    "plan_r0_res30": {"kind": "greedy", "robust": 0.0, "reserve": 0.3},
    "plan_r1": {"kind": "greedy", "robust": 1.0, "reserve": 0.0},
    "plan_r1_res20": {"kind": "greedy", "robust": 1.0, "reserve": 0.2},
    "plan_arr16": {"kind": "greedy", "robust": 0.0, "reserve": 0.0, "arrival_forecast": 16},
    "plan_flow": {"kind": "flow", "robust": 0.0, "reserve": 0.0},
    "plan_flow_res20": {"kind": "flow", "robust": 0.0, "reserve": 0.2},
}


def _hybrid_env(series, tokens, sites, names, start, config: dict[str, Any]) -> HybridEnv:
    """The planner's environment: identical accounting, offers set by the plan."""
    forecast, realized, _ = data.episode_arrays(series, tokens, start)
    band = data.week_band(series, start, days=int(config["calibration_days"]))
    band_array = np.tile(np.array([band[slug] for slug in names]), (len(tokens), 1))
    return HybridEnv(
        forecast=forecast,
        realized=realized,
        band=band_array,
        demand_tokens=tokens,
        sites=sites,
        deadlines=[int(d) for d in config["deadlines"]],
        sla_penalty_kg_per_gpu_hour=0.0,
        communicate=False,
        include_band_in_obs=False,
    )


def _planner(spec: dict[str, Any]):
    cls = ForecastFlowPlanner if spec["kind"] == "flow" else BlockPlanner
    return cls(
        robust=float(spec.get("robust", 0.0)),
        reserve=float(spec.get("reserve", 0.0)),
        arrival_forecast=int(spec.get("arrival_forecast", 0)),
    )


def _objective(row: dict[str, float], price: float) -> float:
    """Carbon plus priced misses -- the same scalar every arm is ranked on."""
    missed_hours = row["missed_fraction"] * row["offered_gpu_s"] / 3600.0
    return float(row["carbon_kg"] + price * missed_hours)


def _mean_bound(
    series,
    tokens,
    sites,
    names,
    config: dict[str, Any],
    held_out,
    deadlines: list[int],
    capacity: float,
    rows: list[dict[str, float]],
) -> float:
    """Mean over weeks of the exact schedule at that week's served volume.

    Averaging the bound over the same weeks as the arm is what makes the gap a
    like-for-like comparison: a carbon reading alone rewards serving less, and a
    bound taken at one fixed volume would do the same.
    """
    bounds = []
    for start, row in zip(held_out, rows, strict=True):
        env = _env_for(
            series,
            tokens,
            sites,
            names,
            start,
            config,
            communicate=False,
            include_band=False,
            price=0.0,
        )
        bounds.append(_oracle(env, deadlines, capacity, float(row["served_gpu_s"]))["carbon_kg"])
    return round(float(np.mean(bounds)), 3)


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
    if not held_out:
        raise ValueError("need held-out weeks in the configured months")
    deadlines = [int(d) for d in config["deadlines"]]
    prices = [float(p) for p in config["prices"]]

    results: dict[str, Any] = {
        "weeks": [f"{s:%Y-%m-%d}" for s in held_out],
        "deadlines": deadlines,
        "prices": prices,
        "fleets": {},
        "note": (
            "Every carbon number is against the identical demand stream, and each "
            "arm is also scored against the exact schedule at its own served "
            "volume, week by week, because unserved work emits nothing. The "
            "planner is causal: it sees the calibrated forecast and its own "
            "backlog, never the realized intensity. Absolute totals are "
            "illustrative of this workload and fleet size, not a general claim."
        ),
    }

    for fleet in config["fleets"]:
        n_gpus = int(fleet["n_gpus"])
        sites = data.make_sites({**config["sites"], "n_gpus": n_gpus}, names)
        capacity = n_gpus * SLOT_MINUTES * 60
        print(f"\n=== {fleet['name']} ({n_gpus} GPUs/site)")

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
        for label, spec in PLANNERS.items():
            arms[label] = [
                run_scheduler(
                    _hybrid_env(series, tokens, sites, names, start, config), _planner(spec)
                )
                for start in held_out
            ]

        report: dict[str, Any] = {
            "n_gpus_per_site": n_gpus,
            "arms": {},
            "oracle_at_run_now_volume": _mean_bound(
                series, tokens, sites, names, config, held_out, deadlines, capacity, arms["run_now"]
            ),
        }
        for label, rows in arms.items():
            entry: dict[str, Any] = {
                "carbon_kg": round(float(np.mean([r["carbon_kg"] for r in rows])), 3),
                "missed_fraction": round(float(np.mean([r["missed_fraction"] for r in rows])), 4),
                "served_gpu_h": round(
                    float(np.mean([r["served_gpu_s"] for r in rows])) / 3600.0, 1
                ),
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
            bound = _mean_bound(
                series, tokens, sites, names, config, held_out, deadlines, capacity, rows
            )
            entry["bound_at_own_volume_kg"] = bound
            entry["gap_to_own_bound_pct"] = round((entry["carbon_kg"] / bound - 1.0) * 100.0, 2)
            report["arms"][label] = entry

        results["fleets"][fleet["name"]] = report
        for label, entry in report["arms"].items():
            objs = " ".join(
                f"p{p:g}={entry['objective_at_price'][str(p)]:.0f}" for p in prices
            )
            print(
                f"  {label:18s} carbon {entry['carbon_kg']:8.1f} kg"
                f"  missed {entry['missed_fraction']:.4f}"
                f"  {entry['carbon_g_per_served_kwh']:5.1f} g/kWh"
                f"  | {objs}"
                f"  | own-bound gap {entry['gap_to_own_bound_pct']:+6.2f}%"
            )
    return results
