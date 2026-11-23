"""exp021: what does the carbon saving actually cost in service?

Why this experiment
-------------------
exp017-020 report carbon savings of 21-27% against never deferring, but every one
of those arms also serves less work: on the slack fleet the chosen point misses
3.65% of arrivals where ``run_now`` misses none. A saving that comes from doing
less is not a like-for-like saving, and a reviewer is right to reject it.

This experiment measures the frontier directly instead of arguing about it. The
planner gets one new knob, ``max_lookahead``: an absolute cap on how far ahead a
block may be placed. ``0`` means "serve it now, choose only the site" -- which is
exactly ``run_now``'s lever plus the planner's capacity accounting -- and the
full horizon is exp017's planner. Everything between is a real deployment
choice, expressed in slots of allowed deferral.

The output answers three questions the earlier experiments could not:

* At **matched service** (missed fraction no worse than ``run_now``), is any arm
  below ``run_now`` on carbon? That is the Pareto question, and it is answered
  per week, not on an average.
* At **matched served volume**, what would each arm emit? Reported as an explicit
  extrapolation from the arm's own measured intensity, because the arm was not
  run at that volume and pretending otherwise would be the error this experiment
  exists to avoid.
* How much of the perfect-foresight headroom is reachable at zero misses? The
  own-volume bound is the ceiling, so the capture fraction is computed too.

Protocol
--------
Identical to exp017-020: the 12 held-out Oct-Dec 2024 weeks, both fleets, the
three prices, the same single real Azure week as the demand stream for every arm.
No parameter is chosen on these weeks; the reserve level and arrival window are
exp018/exp019's values.
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

# The deferral horizon, in slots. 0 = serve now, 16 = the longest deadline class.
LOOKAHEADS = (0, 1, 2, 4, 8, 16)


def _arms(
    reserve_gpu_s: float, window: int, level_pct: int
) -> dict[str, BlockPlanner]:
    """The frontier: horizon alone, then horizon plus each uncertainty input."""
    arms: dict[str, BlockPlanner] = {
        f"look{k}": BlockPlanner(max_lookahead=k) for k in LOOKAHEADS
    }
    if reserve_gpu_s > 0.0:
        arms[f"look4_q{level_pct:02d}"] = BlockPlanner(
            max_lookahead=4, reserve_gpu_s=reserve_gpu_s
        )
        arms[f"look8_q{level_pct:02d}"] = BlockPlanner(
            max_lookahead=8, reserve_gpu_s=reserve_gpu_s
        )
        arms[f"plan_q{level_pct:02d}"] = BlockPlanner(reserve_gpu_s=reserve_gpu_s)
        arms[f"plan_ghost_q{level_pct:02d}"] = BlockPlanner(
            arrival_model="seasonal",
            arrival_window=window,
            ghost_arrivals=True,
            reserve_gpu_s=reserve_gpu_s,
        )
    for k in (4, 8):
        arms[f"look{k}_ghost"] = BlockPlanner(
            max_lookahead=k,
            arrival_model="seasonal",
            arrival_window=window,
            ghost_arrivals=True,
        )
    return arms


def _row_summary(
    rows: list[dict[str, float]], prices: list[float], ref_served_h: float
) -> dict[str, Any]:
    """One arm's held-out numbers, including the matched-service extrapolation.

    ``carbon_kg`` sums the variable term and the idle floor over the week. The
    idle floor does not depend on which arm runs (same fleet, same sites), so the
    only thing that can differ at matched served volume is the intensity of the
    work actually served -- which is exactly what the extrapolation uses.
    """
    served_h = float(np.mean([r["served_gpu_s"] for r in rows])) / 3600.0
    variable = float(np.mean([r["variable_carbon_kg"] for r in rows]))
    idle = float(np.mean([r["idle_carbon_kg"] for r in rows]))
    intensity = variable / max(served_h, 1e-9) * 1000.0
    return {
        "carbon_kg": round(float(np.mean([r["carbon_kg"] for r in rows])), 3),
        "missed_fraction": round(float(np.mean([r["missed_fraction"] for r in rows])), 4),
        "served_gpu_h": round(served_h, 1),
        "variable_carbon_kg": round(variable, 3),
        "idle_carbon_kg": round(idle, 3),
        # NOTE: the exp017-020 key `carbon_g_per_served_kwh` holds this same
        # number; the name there is wrong -- it is grams per served GPU-hour.
        "carbon_g_per_served_gpu_h": round(intensity, 1),
        "matched_service_carbon_kg_extrapolated": round(
            idle + intensity * ref_served_h / 1000.0, 3
        ),
        "objective_at_price": {
            str(p): round(float(np.mean([_objective(r, p) for r in rows])), 3)
            for p in prices
        },
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
    level_pct = int(round(level * 100))
    print(f"arrival quantile (level {level:g}, window {window}): {calibration}")

    results: dict[str, Any] = {
        "weeks": [f"{s:%Y-%m-%d}" for s in held_out],
        "deadlines": deadlines,
        "prices": prices,
        "lookaheads": list(LOOKAHEADS),
        "arrival_level": level,
        "arrival_window": window,
        "fleets": {},
        "note": (
            "max_lookahead is the furthest slot the plan may place work in, so "
            "look0 is serve-now placement and lookk is k slots of allowed "
            "deferral. matched_service_carbon_kg_extrapolated applies the arm's "
            "own measured grams per served GPU-hour to run_now's served volume "
            "and adds the same idle floor; it is an extrapolation, not a rerun, "
            "and is labelled as such so it cannot be read as a measured total. "
            "pareto_* is true only when an arm is no worse than run_now on BOTH "
            "carbon and missed fraction on the held-out mean. Demand is the one "
            "real Azure week for every arm (disclosed)."
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
        for label, planner in _arms(reserve, window, level_pct).items():
            arms[label] = [
                run_scheduler(_hybrid_env(series, tokens, sites, names, start, config), planner)
                for start in held_out
            ]

        ref = arms["run_now"]
        ref_served_h = float(np.mean([r["served_gpu_s"] for r in ref])) / 3600.0
        ref_carbon = float(np.mean([r["carbon_kg"] for r in ref]))
        ref_missed = float(np.mean([r["missed_fraction"] for r in ref]))

        report: dict[str, Any] = {
            "n_gpus_per_site": n_gpus,
            "run_now_served_gpu_h": round(ref_served_h, 1),
            "arms": {},
            "frontier": [],
        }
        for label, rows in arms.items():
            entry = _row_summary(rows, prices, ref_served_h)
            carbon = entry["carbon_kg"]
            missed = entry["missed_fraction"]
            entry["carbon_vs_run_now_pct"] = round((carbon / ref_carbon - 1.0) * 100.0, 2)
            entry["missed_vs_run_now_pp"] = round((missed - ref_missed) * 100.0, 2)
            entry["pareto_vs_run_now"] = bool(carbon <= ref_carbon and missed <= ref_missed)
            entry["paired_vs_run_now"] = None if label == "run_now" else _paired(rows, ref)
            bound = _mean_bound(
                series, tokens, sites, names, config, held_out, deadlines, capacity, rows
            )
            entry["bound_at_own_volume_kg"] = bound
            entry["gap_to_own_bound_pct"] = round((carbon / bound - 1.0) * 100.0, 2)
            report["arms"][label] = entry

        report["frontier"] = sorted(
            (
                {
                    "arm": label,
                    "missed_fraction": entry["missed_fraction"],
                    "carbon_kg": entry["carbon_kg"],
                    "matched_service_carbon_kg_extrapolated": entry[
                        "matched_service_carbon_kg_extrapolated"
                    ],
                    "pareto_vs_run_now": entry["pareto_vs_run_now"],
                }
                for label, entry in report["arms"].items()
            ),
            key=lambda item: (item["missed_fraction"], item["carbon_kg"]),
        )

        results["fleets"][fleet["name"]] = report
        print(
            f"  {'arm':16s} {'kg':>8s} {'miss%':>6s} {'served_h':>9s}"
            f" {'g/GPU-h':>8s} {'match_kg':>9s} {'pareto':>7s}"
        )
        for label, entry in report["arms"].items():
            print(
                f"  {label:16s} {entry['carbon_kg']:8.1f} {entry['missed_fraction']*100:6.2f}"
                f" {entry['served_gpu_h']:9.1f} {entry['carbon_g_per_served_gpu_h']:8.1f}"
                f" {entry['matched_service_carbon_kg_extrapolated']:9.1f}"
                f" {str(entry['pareto_vs_run_now']):>7s}"
            )
    return results
