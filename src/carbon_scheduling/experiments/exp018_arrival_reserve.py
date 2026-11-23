"""exp018: a calibrated reserve for the arrivals the planner cannot see.

Why this experiment
-------------------
exp017 left two facts that point here. First, the capacity-aware planner beats
every timing rule where a miss is priced below the crossover, and the *only*
thing that moves its numbers afterwards is the reserve -- capacity held back for
work that has not arrived (slack fleet: 854.6 kg with none, 784.0 kg with 30% and
the same 3.4% missed). Second, the calibrated carbon band changed no decision for
the third independent time: under national scaling the realized regional
intensity is the forecast times one common factor per slot, so the ordering the
planner acts on *is* the forecast's ordering and no band width can reorder two
blocks (exp011 dispatch, exp016 timing, exp017 planning).

So uncertainty earns its place on demand, not on carbon. This experiment replaces
the hand-set reserve with a **calibrated quantile of arrival exceedance**: a
one-step trailing-mean predictor is scored against what actually arrived, and the
reserve is the split-conformal upper quantile of the positive error, in
GPU-seconds, spread over the sites and the tightest deadline window
(``rl/arrival_risk.py``). Unlike the carbon band, this quantity has a coverage
claim that can be checked on data the quantile never saw, so the run reports it.

Protocol
--------
The demand profile is the one real Azure LLM week reused across all weeks (the
disclosed choice every rung since exp012 makes). To keep the reserve honest the
week is split: the quantile is calibrated on the first half (168 slots) and its
coverage is measured on the second half, which the calibration never saw. The
quantile is a single number per level, so this is a split-conformal check, not a
tuning loop -- the levels and the trailing window are fixed in the config, not
chosen on the evaluation weeks.

Arms: the two rules that matter from exp016's frontier, the planner with no
reserve, with the fixed fractional reserve exp017 swept, and with the calibrated
quantile at three levels. Scored on 12 held-out Oct-Dec 2024 weeks, both fleets,
on carbon + price * missed GPU-hours at the parity price (0.1), the crossover
(0.3) and a service obligation (1.0), each also against the exact schedule at its
own served volume.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.experiments.exp013_marl_dispatch import _paired
from carbon_scheduling.experiments.exp016_queue_ownership import _env_for, _oracle
from carbon_scheduling.rl import data
from carbon_scheduling.rl.arrival_risk import (
    exceedance_quantile,
    reserve_per_site_slot,
    trailing_predicted,
)
from carbon_scheduling.rl.hybrid import BlockPlanner, HybridEnv, run_scheduler
from carbon_scheduling.rl.queue_rules import run_rule

SLOT_MINUTES = 30


def _hybrid_env(series, tokens, sites, names, start, config: dict[str, Any]) -> HybridEnv:
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


def _split(demand: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """First half calibrates the quantile, second half measures its coverage."""
    half = len(demand) // 2
    return demand[:half], demand[half:]


def _coverage(q: float, hold: np.ndarray, window: int) -> float:
    """Share of held-out slots whose exceedance is inside the quantile."""
    predicted = trailing_predicted(hold, window)
    excess = (hold - predicted)[1:]  # slot 0 of the half has no in-half history
    return round(float(np.mean(excess <= q)), 4)


def calibrate(demand_gpu_s: np.ndarray, level: float, window: int) -> dict[str, float]:
    """Quantile of arrival exceedance in GPU-seconds, and its coverage both ways.

    The demand profile is one week, so a single split is a weak test of
    exchangeability: the two halves of a diurnal trace are not identically
    distributed (one may hold the busy period). Reporting the coverage in both
    directions makes that visible instead of hiding it behind one number, and the
    experiment says plainly that the guarantee is only as good as the
    exchangeability it assumes.
    """
    first, second = _split(demand_gpu_s)
    q = exceedance_quantile(first, window, level)
    q_reverse = exceedance_quantile(second, window, level)
    return {
        "quantile_gpu_s": round(q, 1),
        "quantile_reverse_gpu_s": round(q_reverse, 1),
        "coverage_forward": _coverage(q, second, window),
        "coverage_reverse": _coverage(q_reverse, first, window),
        "n_held_out_slots": int(len(second) - 1),
    }


def _objective(row: dict[str, float], price: float) -> float:
    missed_hours = row["missed_fraction"] * row["offered_gpu_s"] / 3600.0
    return float(row["carbon_kg"] + price * missed_hours)


def _mean_bound(series, tokens, sites, names, config, held_out, deadlines, capacity, rows):
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
    deadlines = [int(d) for d in config["deadlines"]]
    prices = [float(p) for p in config["prices"]]
    window = int(config["arrival_window"])
    levels = [float(level) for level in config["arrival_levels"]]

    # The reserve is in GPU-seconds; the trace is in tokens, so convert once here
    # rather than everywhere downstream.
    throughput = float(config["sites"]["tokens_per_gpu_second"])
    demand_gpu_s = tokens / throughput
    calibration = {level: calibrate(demand_gpu_s, level, window) for level in levels}

    results: dict[str, Any] = {
        "weeks": [f"{s:%Y-%m-%d}" for s in held_out],
        "deadlines": deadlines,
        "prices": prices,
        "arrival_window": window,
        "calibration": {str(k): v for k, v in calibration.items()},
        "fleets": {},
        "note": (
            "The reserve is a split-conformal upper quantile of arrival excess: "
            "calibrated on the first half of the one real Azure week and scored on "
            "the second half, which the calibration never saw. The demand profile "
            "is the same week for every arm (disclosed). Every carbon number is "
            "against the identical demand stream and each arm is scored against the "
            "exact schedule at its own served volume."
        ),
    }

    for fleet in config["fleets"]:
        n_gpus = int(fleet["n_gpus"])
        sites = data.make_sites({**config["sites"], "n_gpus": n_gpus}, names)
        capacity = n_gpus * SLOT_MINUTES * 60
        min_deadline = min(deadlines)
        reserves = {
            level: reserve_per_site_slot(
                calibration[level]["quantile_gpu_s"],
                n_sites=len(names),
                min_deadline=min_deadline,
                capacity=capacity,
            )
            for level in levels
        }
        print(f"\n=== {fleet['name']} ({n_gpus} GPUs/site, capacity {capacity:.0f} GPU-s/slot)")
        print(
            "  reserves per site-slot: "
            + "  ".join(f"level {lv:g} -> {reserves[lv]:.0f}" for lv in levels)
        )

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

        planners: dict[str, BlockPlanner] = {
            "plan_none": BlockPlanner(),
            f"plan_frac{int(float(config['fixed_reserve']) * 100):02d}": BlockPlanner(
                reserve=float(config["fixed_reserve"])
            ),
        }
        for level in levels:
            planners[f"plan_q{int(level * 100):02d}"] = BlockPlanner(reserve_gpu_s=reserves[level])
        for label, planner in planners.items():
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
            bound = _mean_bound(
                series, tokens, sites, names, config, held_out, deadlines, capacity, rows
            )
            entry["bound_at_own_volume_kg"] = bound
            entry["gap_to_own_bound_pct"] = round((entry["carbon_kg"] / bound - 1.0) * 100.0, 2)
            report["arms"][label] = entry
        report["reserve_gpu_s_per_site_slot"] = {
            str(level): round(reserves[level], 1) for level in levels
        }

        results["fleets"][fleet["name"]] = report
        for label, entry in report["arms"].items():
            objs = " ".join(f"p{p:g}={entry['objective_at_price'][str(p)]:.0f}" for p in prices)
            print(
                f"  {label:12s} carbon {entry['carbon_kg']:8.1f} kg"
                f"  missed {entry['missed_fraction']:.4f}"
                f"  {entry['carbon_g_per_served_kwh']:5.1f} g/kWh"
                f"  | {objs}"
                f"  | own-bound gap {entry['gap_to_own_bound_pct']:+6.2f}%"
            )
    return results
