"""exp015 -- how much carbon is left on the table by not controlling *when*?

exp011 killed the uncertainty argument for site *ranking*: under the national-
scaling estimator the realized intensity is a per-slot monotone transform of the
forecast, so carbon-aware placement is an exactly-known problem and the oracle
ties forecast-greedy. What is left is *timing*, and every learner in exp012 and
exp013 collapsed onto carbon-greedy's immediate dispatch.

This experiment measures the value of timing exactly. For each held-out week it
serves the same volume of work that carbon-greedy serves, and asks a linear
program (solved here as a min-cost flow, so the answer is a proven optimum, not
a heuristic) for the cheapest legal schedule at a range of deadline horizons.

The result is an upper bound on any causal policy, which is what makes it
readable: if perfect foresight could only save 2%, no observation change would
matter. It can save far more than that, so the next rung is about expressing the
lever, not about learning harder.

Deadline horizons are swept because the levers' size *is* the deadline: at
half an hour there is no room to move work, and by a day the fleet can chase
whole weather systems.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np

from carbon_scheduling.cluster import site_energy_kwh
from carbon_scheduling.experiments.exp013_marl_dispatch import _build
from carbon_scheduling.rl import baselines, data
from carbon_scheduling.rl.oracle import plan

SLOT_MINUTES = 30


def _carbon(alloc: np.ndarray, realized: np.ndarray, sites, window: int) -> float:
    """Carbon with the same physical model the environment uses.

    ``window`` is how many slots the environment actually runs. Inside it every
    site is billed its idle floor in every slot (exactly as ``MultiAgentEnv``
    does); outside it -- the padding that lets a late cohort be scheduled at all
    -- only the energy of the work itself is charged, because no baseline ever
    pays for idle time there.
    """
    kg = 0.0
    for t in range(alloc.shape[0]):
        for i, site in enumerate(sites):
            load_only = t >= window
            energy = site_energy_kwh(site, float(alloc[t, i]), SLOT_MINUTES)
            if load_only:
                energy -= site_energy_kwh(site, 0.0, SLOT_MINUTES)
            kg += energy * float(realized[t, i]) / 1000.0
    return kg


def _next_week_tail(
    series: dict, tokens: np.ndarray, start: datetime, slots: int
) -> np.ndarray | None:
    """Realized intensities for the slots just after the week.

    Without them a cohort arriving in the last four hours is trapped by the edge
    of the window: the optimum cannot place work the environment would let it
    place, and the bound would be measured against a scheduling problem nobody
    faces. ``None`` when the next week is not in the data (the last held-out
    week of the year).
    """
    try:
        _forecast, realized, _demand = data.episode_arrays(
            series, tokens, start + timedelta(days=7)
        )
    except (ValueError, KeyError):
        return None
    return realized[:slots]


def run(config: dict[str, Any]) -> dict[str, Any]:
    names = list(config["regions"])
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    tokens = data.demand_profile(paths["demand"], int(config["n_slots"]))
    starts = data.weekly_windows(
        series,
        months=[int(m) for m in config["months"]],
        year=int(config["year"]),
        n_slots=int(config["n_slots"]),
    )
    if not starts:
        raise ValueError("no held-out weeks for the configured months")

    horizons = [int(h) for h in config["horizons"]]
    results: dict[str, Any] = {"weeks": [f"{s:%Y-%m-%d}" for s in starts], "fleets": {}}

    for fleet in config["fleets"]:
        sites = data.make_sites({**config["sites"], "n_gpus": int(fleet["n_gpus"])}, names)
        capacity = int(fleet["n_gpus"]) * SLOT_MINUTES * 60
        unit_kwh = np.array(
            [
                site_energy_kwh(site, 1.0, SLOT_MINUTES) - site_energy_kwh(site, 0.0, SLOT_MINUTES)
                for site in sites
            ]
        )

        baseline: list[float] = []
        defer_rule: list[float] = []
        per_horizon: dict[int, dict[str, list[float]]] = {
            h: {"relative_pct": [], "unserved": [], "baseline_unserved": [], "carbon_kg": []}
            for h in horizons
        }
        matched: dict[int, bool] = {h: True for h in horizons}

        for start in starts:
            env = _build(
                series,
                tokens,
                sites,
                names,
                start,
                communicate=False,
                include_band=False,
                allow_decline=False,
                penalty=0.1,
                config=config,
            )
            now = baselines.run_joint_policy(env, baselines.JOINT_POLICIES["run_now"])
            later = baselines.run_joint_policy(env, baselines.JOINT_POLICIES["defer"])
            baseline.append(now["carbon_kg"])
            defer_rule.append(later["carbon_kg"])

            demand = env.demand_tokens / env.throughput
            tail = _next_week_tail(series, tokens, start, max(horizons))
            realized = np.vstack([env.realized, tail]) if tail is not None else env.realized
            padded = np.zeros(realized.shape[0])
            padded[: demand.size] = demand
            cost = unit_kwh[None, :] * realized / 1000.0

            for horizon in horizons:
                alloc, unserved = plan(cost, padded, capacity, horizon, volume=now["served_gpu_s"])
                kg = _carbon(alloc, realized, sites, window=int(config["n_slots"]))
                per_horizon[horizon]["relative_pct"].append(kg / now["carbon_kg"] - 1.0)
                per_horizon[horizon]["carbon_kg"].append(kg)
                offered = float(demand.sum())
                # Computed here rather than read from the summary: the summary
                # rounds its fractions to four decimals, which is fine to print
                # and not fine to compare against a flow that lands on the same
                # volume to ten.
                baseline_served = float(now["served_gpu_s"]) / offered
                served = offered - unserved
                per_horizon[horizon]["unserved"].append(unserved / offered)
                # Clamped: the baseline's served volume can land a float epsilon
                # above the offered total, and "-0.0" in an evidence file is a
                # needless distraction.
                per_horizon[horizon]["baseline_unserved"].append(max(0.0, 1.0 - baseline_served))
                # Matched service means the optimum placed the volume it was
                # asked for; if capacity forbids it, the row is not a comparison
                # and says so instead of flattering or punishing the bound.
                if served / offered < baseline_served - 1e-6:
                    matched[horizon] = False

        rows: dict[str, Any] = {}
        for horizon in horizons:
            row = per_horizon[horizon]
            relative = np.asarray(row["relative_pct"]) * 100.0
            rows[f"{horizon} slots"] = {
                "deadline_hours": round(horizon * SLOT_MINUTES / 60.0, 2),
                "carbon_kg_mean": round(float(np.mean(row["carbon_kg"])), 3),
                "relative_pct_mean": round(float(relative.mean()), 3),
                "relative_pct_worst": round(float(relative.max()), 3),
                "relative_pct_best": round(float(relative.min()), 3),
                "weeks_better": int((relative < 0).sum()),
                "unserved_fraction": round(float(np.mean(row["unserved"])), 4),
                "baseline_unserved_fraction": round(float(np.mean(row["baseline_unserved"])), 4),
                "service_matched": bool(matched[horizon]),
            }

        results["fleets"][fleet["name"]] = {
            "n_gpus": int(fleet["n_gpus"]),
            "carbon_greedy_kg_mean": round(float(np.mean(baseline)), 3),
            "defer_rule_kg_mean": round(float(np.mean(defer_rule)), 3),
            "defer_rule_relative_pct": round(
                (float(np.mean(defer_rule)) / float(np.mean(baseline)) - 1.0) * 100.0, 3
            ),
            "horizons": rows,
        }

    headline = config.get("headline_deadline_slots")
    if headline is not None:
        key = f"{int(headline)} slots"
        results["headline"] = {
            fleet_name: fleet_result["horizons"][key]
            for fleet_name, fleet_result in results["fleets"].items()
            if key in fleet_result["horizons"]
        }
    results["note"] = (
        "The optimum is a perfect-foresight bound: it knows every realized "
        "intensity. It is not a policy, but it bounds what any causal policy "
        "could save at the same served volume."
    )
    return results
