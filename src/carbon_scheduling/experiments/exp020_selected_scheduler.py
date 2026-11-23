"""exp020: one shipped scheduler, with its operating point chosen on training months.

Why this experiment
-------------------
exp017, exp018 and exp019 each report a *frontier*: several arms, three prices,
two fleets, and a different winner at each corner. That is honest but it is not a
scheduler. A deployment has one price (what a missed GPU-hour costs it), so it
needs one arm, and the only defensible way to pick that arm is on data the
report's numbers do not come from.

This experiment does exactly that and nothing else:

1. Run every candidate arm over the **training** months (Jan-Sep 2024, 39 weeks).
2. For each fleet and each price, pick the arm with the best mean objective on
   those weeks. That map is the shipped scheduler.
3. Run the same arms over the **held-out** months (Oct-Dec 2024, 12 weeks) and
   report the selected arm's numbers.

The selection rule never sees a held-out week. To make that visible, the run also
reports what tuning *on* the evaluation weeks would have bought (the best arm per
cell on held-out data) -- the difference between the two is the price of honesty,
and it is the number a reviewer should ask for.

Candidates are the frontier's corners, not a fresh sweep: never defer (``run_now``),
deadline-only holding (``last_slot``), the myopic planner, the planner with exp018's
calibrated reserve, the capacity-bound fleet's best carbon arm (reserve plus ghosts),
and the reliability extreme that beats ``run_now`` at the obligation price on the
slack fleet (seasonal hold, exp019).
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


def _candidates(reserve_gpu_s: float, window: int) -> dict[str, Any]:
    """Label -> ``("rule", name)`` or ``("planner", BlockPlanner)``."""
    return {
        "run_now": ("rule", "run_now"),
        "last_slot": ("rule", "last_slot"),
        "plan_none": ("planner", BlockPlanner()),
        "plan_q95": ("planner", BlockPlanner(reserve_gpu_s=reserve_gpu_s)),
        "plan_ghost_q95": (
            "planner",
            BlockPlanner(
                arrival_model="seasonal",
                arrival_window=window,
                ghost_arrivals=True,
                reserve_gpu_s=reserve_gpu_s,
            ),
        ),
        "plan_hold_seasonal": (
            "planner",
            BlockPlanner(arrival_model="seasonal", arrival_window=window),
        ),
    }


def _run_arm(
    spec: Any,
    weeks: list,
    series,
    tokens,
    sites,
    names,
    config: dict[str, Any],
) -> list[dict[str, float]]:
    kind, payload = spec
    rows = []
    for start in weeks:
        if kind == "rule":
            env = _env_for(
                series,
                tokens,
                sites,
                names,
                start,
                config,
                communicate=True,
                include_band=True,
                price=0.0,
            )
            rows.append(run_rule(env, payload))
        else:
            rows.append(
                run_scheduler(_hybrid_env(series, tokens, sites, names, start, config), payload)
            )
    return rows


def _mean_objective(rows: list[dict[str, float]], price: float) -> float:
    return float(np.mean([_objective(r, price) for r in rows]))


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    tokens = data.demand_profile(paths["demand"], int(config["n_slots"]))
    grid = {
        "year": int(config["year"]),
        "n_slots": int(config["n_slots"]),
        "calibration_days": int(config["calibration_days"]),
    }
    train = data.weekly_windows(series, months=[int(m) for m in config["train_months"]], **grid)
    held_out = data.weekly_windows(series, months=[int(m) for m in config["eval_months"]], **grid)
    deadlines = [int(d) for d in config["deadlines"]]
    prices = [float(p) for p in config["prices"]]
    window = int(config["arrival_window"])
    level = float(config["arrival_level"])

    throughput = float(config["sites"]["tokens_per_gpu_second"])
    calibration = calibrate(tokens / throughput, level, window)
    print(f"train weeks {len(train)}  held-out weeks {len(held_out)}")

    results: dict[str, Any] = {
        "train_weeks": [f"{s:%Y-%m-%d}" for s in train],
        "held_out_weeks": [f"{s:%Y-%m-%d}" for s in held_out],
        "prices": prices,
        "calibration": {str(k): v for k, v in calibration.items()},
        "fleets": {},
        "note": (
            "The operating point for each (fleet, price) cell is the arm with the "
            "best mean objective on the training months only; the held-out months "
            "are used solely to report that choice. 'tuned_on_test' is the best arm "
            "per cell on the held-out weeks, reported as the reference a reviewer "
            "should compare against -- the gap between the two is what honest "
            "selection costs. Demand is the single real Azure week for every arm "
            "(disclosed) and every carbon number is against that identical stream."
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
        candidates = _candidates(reserve, window)
        print(f"\n=== {fleet['name']} ({n_gpus} GPUs/site, reserve {reserve:.0f} GPU-s)")

        train_rows: dict[str, list[dict[str, float]]] = {}
        eval_rows: dict[str, list[dict[str, float]]] = {}
        for label, spec in candidates.items():
            train_rows[label] = _run_arm(spec, train, series, tokens, sites, names, config)
            eval_rows[label] = _run_arm(spec, held_out, series, tokens, sites, names, config)
            print(f"  ran {label}")

        report: dict[str, Any] = {
            "n_gpus_per_site": n_gpus,
            "arms": {},
            "selection": {},
        }
        for label, rows in eval_rows.items():
            entry: dict[str, Any] = {
                "carbon_kg": round(float(np.mean([r["carbon_kg"] for r in rows])), 3),
                "missed_fraction": round(float(np.mean([r["missed_fraction"] for r in rows])), 4),
                "objective_on_held_out": {
                    str(p): round(_mean_objective(rows, p), 3) for p in prices
                },
                "objective_on_train": {
                    str(p): round(_mean_objective(train_rows[label], p), 3) for p in prices
                },
                "paired_vs_run_now": (
                    None if label == "run_now" else _paired(rows, eval_rows["run_now"])
                ),
            }
            bound = _mean_bound(
                series, tokens, sites, names, config, held_out, deadlines, capacity, rows
            )
            entry["bound_at_own_volume_kg"] = bound
            entry["gap_to_own_bound_pct"] = round((entry["carbon_kg"] / bound - 1.0) * 100.0, 2)
            report["arms"][label] = entry

        for p in prices:
            train_scores = {label: _mean_objective(rows, p) for label, rows in train_rows.items()}
            eval_scores = {label: _mean_objective(rows, p) for label, rows in eval_rows.items()}
            chosen = min(train_scores, key=lambda label: train_scores[label])
            best_test = min(eval_scores, key=lambda label: eval_scores[label])
            report["selection"][str(p)] = {
                "chosen": chosen,
                "chosen_train_objective": round(train_scores[chosen], 3),
                "chosen_held_out_objective": round(eval_scores[chosen], 3),
                "tuned_on_test": best_test,
                "tuned_on_test_objective": round(eval_scores[best_test], 3),
                "cost_of_honesty_pct": round(
                    (eval_scores[chosen] / eval_scores[best_test] - 1.0) * 100.0, 2
                ),
            }

        results["fleets"][fleet["name"]] = report
        for p in prices:
            sel = report["selection"][str(p)]
            print(
                f"  price {p:g}: chose {sel['chosen']:18s}"
                f" held-out {sel['chosen_held_out_objective']:8.1f}"
                f"  (best on test {sel['tuned_on_test']} {sel['tuned_on_test_objective']:.1f},"
                f" cost of honesty {sel['cost_of_honesty_pct']:+.2f}%)"
            )
    return results
