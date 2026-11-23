"""exp023 -- how much of the published benchmark's carbon is a decision at all?

The question this answers
-------------------------
exp022 found our planner ties SustainCluster's best published controller exactly.
A tie can mean two very different things:

1. our rule is no better than theirs, or
2. there is nothing left to win, because most of the reported carbon is not a
   decision.

This experiment separates them by measuring the floor. The identical environment
-- same four UK sites, same jittered week, same carbon and price series, same
HVAC and server power model -- is run with the task stream switched off. What it
still emits is the idle draw of the estate: servers, cooling, pumps, fans. No
placement rule and no deferral rule can remove it, so it is a hard lower bound on
any controller in this benchmark.

The decomposition reported is therefore

    carbon(controller) = floor + controllable(controller)

and the only meaningful score for a controller is what share of ``floor to
round_robin`` it removes. A percentage quoted against another controller -- the
form every published number in this area takes -- hides how large that range is.

Why placement saturates (the second half of the answer)
------------------------------------------------------
The benchmark's controller interface is placement-only: ``distribute_workload``
queues a task only if the strategy returns a datacenter id, ``None`` discards it,
and ``get_tasks_for_timestep`` never re-serves it, so deferral exists only in the
``manual_rl`` action path the rule-based controllers do not use. Placement is
then the argmin of regional intensity, so if one site is the argmin in nearly
every hour, every correct rule computes the same assignment. That is measured
here from the forecast series directly: how often the same site is cheapest, and
how large the gap to the runner-up is.

Nothing here is tuned, and no arithmetic is asserted: the floor is a run, the
controller range is runs, and the stability statistic is a count over the series.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from carbon_scheduling.experiments.exp009_uk_sites import (
    KEEP,
    _require_installed,
    _write_configs,
)
from carbon_scheduling.runner import REPO_ROOT
from carbon_scheduling.sim import sustaincluster
from carbon_scheduling.sim.uk_planner import _parse_utc, load_regional_forecast

# The two controllers that bracket the range: spread the work as evenly as the
# benchmark can, versus send it to the cheapest site. Plus our own rule, so the
# floor can be read against an arm that already ties the best published one.
CONTROLLERS = ("round_robin", "lowest_carbon")


def _placement_stability(
    forecast_csv: Path,
    region_ids: dict[str, int],
    start: str,
    hours: int,
) -> dict[str, Any]:
    """How often one site is the cheapest, and by how much it wins.

    Counts hours, not 15-minute steps, because carbon in the simulator is hourly:
    any rule that reads it is choosing between four numbers per hour.
    """
    series = load_regional_forecast(forecast_csv, region_ids)
    begin = _parse_utc(start)
    counts: dict[str, int] = {}
    gaps: list[float] = []
    gaps_rel: list[float] = []
    for offset in range(hours):
        hour = begin + timedelta(hours=offset)
        values = {
            slug: per_hour[hour]
            for slug, per_hour in series.items()
            if per_hour.get(hour) is not None
        }
        if len(values) < 2:
            continue
        ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
        cheapest, best = ordered[0]
        counts[cheapest] = counts.get(cheapest, 0) + 1
        second = ordered[1][1]
        gaps.append(second - best)
        if second > 0:
            gaps_rel.append((second - best) / second)
    total = sum(counts.values())
    if not total:
        raise RuntimeError("no complete hours in the window to score stability on")
    dominant = max(counts, key=lambda name: (counts[name], name))
    return {
        "hours_scored": total,
        "argmin_counts": dict(sorted(counts.items())),
        "dominant_site": dominant,
        "dominant_share": round(counts[dominant] / total, 4),
        "mean_gap_to_runner_up_gco2_per_kwh": round(sum(gaps) / len(gaps), 2),
        "median_relative_gap": round(sorted(gaps_rel)[len(gaps_rel) // 2], 4),
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    sc_cfg = config["sustaincluster"]
    sim = config["simulation"]
    planner = config["planner"]
    checkout = sustaincluster.checkout_dir(sc_cfg)
    _require_installed(checkout, config)
    python = sustaincluster.resolve_python(checkout, sc_cfg)
    days = float(sim["duration_days"])
    seed = int(config["seed"])
    region_ids = {k: int(v) for k, v in planner["region_ids"].items()}

    scratch = Path(tempfile.mkdtemp(prefix=f"{config['id']}-"))
    _write_configs(config, scratch)
    common = dict(
        init_day_of_year=int(sim["init_day_of_year"]),
        sim_config=scratch / "sim_config.yaml",
        datacenters=scratch / "datacenters.yaml",
        reward_config=scratch / "reward_config.yaml",
        align_clock=True,
    )

    floor = sustaincluster.run_idle_floor(
        checkout, python, days=days, seed=seed, out_path=scratch / "floor.json", **common
    )
    runs: dict[str, dict[str, Any]] = {}
    for name in CONTROLLERS:
        runs[name] = sustaincluster.run_strategy(
            checkout,
            python,
            name,
            days=days,
            seed=seed,
            out_path=scratch / f"{name}.json",
            **common,
        )
    runs["planner"] = sustaincluster.run_planner(
        checkout,
        python,
        days=days,
        seed=seed,
        out_path=scratch / "planner.json",
        forecast_csv=REPO_ROOT / planner["forecast_csv"],
        national_json=REPO_ROOT / planner["national_json"],
        region_map=region_ids,
        lam=float(planner["lam"]),
        window_hours=planner["window_hours"],
        alpha=float(planner["alpha"]),
        calibration_end=str(planner["calibration_end"]),
        **common,
    )

    # Our planner must have used our forecast, not silently fallen back to the
    # simulator's own (realized) carbon signal -- see exp022's correction.
    if runs["planner"].get("forecast_fallbacks"):
        raise RuntimeError(
            f"planner fell back to the simulator's signal "
            f"{runs['planner']['forecast_fallbacks']} times; the decomposition "
            "would compare lowest_carbon with itself."
        )

    # All arms must describe the same week, or the decomposition is across
    # different weather and means nothing.
    clocks = {r.get("clock_start_utc") for r in runs.values()}
    if len(clocks) != 1:
        raise RuntimeError(f"controllers ran on different clocks: {clocks}")
    start = runs["round_robin"]["clock_start_utc"]
    if start != floor.get("clock_start_utc"):
        raise RuntimeError("the floor run and the controllers read different weeks")

    floor_kg = float(floor["carbon_kg"])
    rr_kg = float(runs["round_robin"]["carbon_kg"])
    controllable_kg = rr_kg - floor_kg
    if controllable_kg <= 0:
        raise RuntimeError(
            f"floor {floor_kg:.1f} kg is not below round_robin {rr_kg:.1f} kg; "
            "the decomposition is invalid"
        )

    rows: dict[str, Any] = {}
    for name, result in runs.items():
        carbon = float(result["carbon_kg"])
        rows[name] = {
            **{k: round(result[k], 4) if isinstance(result[k], float) else result[k] for k in KEEP},
            "carbon_above_floor_kg": round(carbon - floor_kg, 2),
            # The only score that means anything: how much of the *decision*
            # space this controller removes, with round_robin as the ceiling.
            "share_of_controllable_captured_pct": round(
                (rr_kg - carbon) / controllable_kg * 100.0, 2
            ),
            "carbon_vs_floor_pct": round((carbon / floor_kg - 1.0) * 100.0, 2),
        }

    best = min(rows, key=lambda name: rows[name]["carbon_kg"])
    return {
        "sustaincluster_commit": runs["round_robin"]["sustaincluster_commit"],
        "carbon_window_start_utc": start,
        "carbon_window_hours": int(days * 24),
        "days": days,
        "seed": seed,
        "n_sites": len(config["sites"]),
        "floor": {
            "carbon_kg": round(floor_kg, 2),
            "energy_kwh": round(float(floor["energy_kwh"]), 2),
            "note": (
                "The same environment with the task stream switched off: servers, "
                "cooling, pumps and fans. A hard lower bound, not a controller."
            ),
        },
        "controllable_carbon_kg": round(controllable_kg, 2),
        "controllable_share_of_total_pct": round(controllable_kg / rr_kg * 100.0, 2),
        "controllers": rows,
        "best_controller": best,
        "best_share_of_controllable_captured_pct": rows[best]["share_of_controllable_captured_pct"],
        "placement_stability": _placement_stability(
            REPO_ROOT / planner["forecast_csv"], region_ids, start, int(days * 24)
        ),
        "note": (
            "Carbon values are the simulator's own (derived regional estimate -- NESO "
            "ships no regional actuals). The floor is measured by an identical run with "
            "no arrivals, so 'controllable' is exactly the part of emissions that a "
            "placement decision can move in this benchmark. Deferral is not available "
            "to any strategy-map controller: returning None discards the task and the "
            "stream is never re-served, so this range is the whole arena."
        ),
    }
