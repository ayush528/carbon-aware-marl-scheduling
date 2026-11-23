"""exp030 — the head-to-head with the timing lever available to everyone equally.

exp022 compared placement only, because the benchmark's controller interface
cannot express deferral: ``distribute_workload`` enqueues a task only when a
strategy returns a site, and returning ``None`` discards it. exp023 then measured
that 88.7% of the benchmark's carbon is idle draw, so the contestable range is
only 11.3%. Together they left one question open, and it is the question the
project's claim actually rests on:

    when every controller is given the *same* timing lever, does ours win?

This experiment answers it. A runtime buffer (``sim/deferral.py``) wraps two
cluster-manager methods so any controller may hold a task back; upstream source
is untouched, and two guarantees are pinned by tests: no task is lost or
duplicated, and deferral never pushes a task past its last legal start.

The declared SLA is widened identically for every controller. Upstream hardcodes
``sla_multiplier = 1.5``, which leaves a median 76-minute task about 38 minutes of
room -- barely two simulator steps. Reporting one number at that arbitrary
deadline would hide the fact that the lever's value is a function of slack, so the
multiplier is swept and the whole curve is reported.

Finally, every saving is scored two ways: against total carbon (what papers
report) and against the **contestable** carbon, total minus the measured idle
floor. That is what reconciles this benchmark's ~1% with our own environment's
6-12%: they are the same fraction of the carbon a controller can actually move.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from carbon_scheduling.experiments.exp009_uk_sites import (
    KEEP,
    _require_installed,
    _write_configs,
)
from carbon_scheduling.runner import REPO_ROOT
from carbon_scheduling.sim import sustaincluster

PLANNER = "planner_duration"


def run(config: dict[str, Any]) -> dict[str, Any]:
    sc_cfg = config["sustaincluster"]
    sim = config["simulation"]
    checkout = sustaincluster.checkout_dir(sc_cfg)
    _require_installed(checkout, config)
    python = sustaincluster.resolve_python(checkout, sc_cfg)
    days = float(sim["duration_days"])
    seed = int(config["seed"])
    planner = config["planner"]
    region_ids = {k: int(v) for k, v in planner["region_ids"].items()}

    scratch = Path(tempfile.mkdtemp(prefix=f"{config['id']}-"))
    _write_configs(config, scratch)

    common = dict(
        days=days,
        seed=seed,
        forecast_csv=REPO_ROOT / planner["forecast_csv"],
        national_json=REPO_ROOT / planner["national_json"],
        region_map=region_ids,
        calibration_end=str(planner["calibration_end"]),
        alpha=float(planner["alpha"]),
        init_day_of_year=int(sim["init_day_of_year"]),
        sim_config=scratch / "sim_config.yaml",
        datacenters=scratch / "datacenters.yaml",
        reward_config=scratch / "reward_config.yaml",
        align_clock=True,
    )

    floor = sustaincluster.run_idle_floor(
        checkout,
        python,
        out_path=scratch / "floor.json",
        **{
            k: v
            for k, v in common.items()
            if k not in ("forecast_csv", "national_json", "region_map", "calibration_end", "alpha")
        },
    )

    controllers = [*sc_cfg["baselines"], PLANNER]
    reserve = config["reserve"]
    results: list[dict[str, Any]] = []
    for sla in [float(v) for v in config["sla_multipliers"]]:
        for controller in controllers:
            for policy in config["deferral_policies"]:
                results.append(
                    sustaincluster.run_deferral(
                        checkout,
                        python,
                        strategy=controller,
                        deferral=policy,
                        sla_multiplier=sla,
                        lam=float(planner["lam"]),
                        window_hours=planner["window_hours"],
                        out_path=scratch / f"{controller}_{policy}_sla{sla:g}.json",
                        **common,
                    )
                )
        # Our reserve arm: the planner's capacity-budget idea, ours alone.
        results.append(
            sustaincluster.run_deferral(
                checkout,
                python,
                strategy=PLANNER,
                deferral="reserve",
                sla_multiplier=sla,
                lam=float(planner["lam"]),
                window_hours=planner["window_hours"],
                reserve_fraction=float(reserve["fraction"]),
                arrivals_per_slot=float(reserve["arrivals_per_slot"]),
                out_path=scratch / f"{PLANNER}_reserve_sla{sla:g}.json",
                **common,
            )
        )

    # Guards: identical week, and our planner must have used our forecast.
    clocks = {r.get("clock_start_utc") for r in results}
    if len(clocks) != 1:
        raise RuntimeError(f"arms ran on different clocks: {clocks}")
    if floor.get("clock_start_utc") not in clocks:
        raise RuntimeError("the idle floor was measured on a different week")
    fallbacks = {r["arm"]: r["forecast_fallbacks"] for r in results if r.get("forecast_fallbacks")}
    if fallbacks:
        raise RuntimeError(f"planner arms fell back to the simulator's signal: {fallbacks}")

    floor_kg = float(floor["carbon_kg"])
    rows: dict[str, Any] = {}
    for result in results:
        carbon = float(result["carbon_kg"])
        rows[result["arm"]] = {
            **{k: round(result[k], 4) if isinstance(result[k], float) else result[k] for k in KEEP},
            "controller": result["controller"],
            "deferral": result["deferral"],
            "sla_multiplier": result["sla_multiplier"],
            "carbon_above_floor_kg": round(carbon - floor_kg, 2),
            "deferral_stats": result["deferral_stats"],
        }

    # Reference points, all measured on the same week.
    rr = rows[f"round_robin__none__sla{config['sla_multipliers'][0]:g}"]["carbon_kg"]
    contestable = rr - floor_kg
    if contestable <= 0:
        raise RuntimeError("the idle floor is not below round_robin; decomposition invalid")

    by_sla: dict[str, Any] = {}
    for sla in [float(v) for v in config["sla_multipliers"]]:
        key = f"{sla:g}"
        published = [
            name
            for name, row in rows.items()
            if row["sla_multiplier"] == sla and row["controller"] != PLANNER
        ]
        best_published = min(published, key=lambda n: rows[n]["carbon_kg"])
        ours = [
            name
            for name, row in rows.items()
            if row["sla_multiplier"] == sla and row["controller"] == PLANNER
        ]
        best_ours = min(ours, key=lambda n: rows[n]["carbon_kg"])
        arms = {}
        for name in [*published, *ours]:
            row = rows[name]
            arms[name] = {
                **row,
                "carbon_vs_round_robin_pct": round((row["carbon_kg"] / rr - 1.0) * 100.0, 3),
                "carbon_vs_best_published_pct": round(
                    (row["carbon_kg"] / rows[best_published]["carbon_kg"] - 1.0) * 100.0, 3
                ),
                "share_of_controllable_captured_pct": round(
                    (rr - row["carbon_kg"]) / contestable * 100.0, 2
                ),
            }
        by_sla[key] = {
            "arms": arms,
            "best_published": best_published,
            "best_ours": best_ours,
            "ours_beats_best_published_on_carbon": bool(
                rows[best_ours]["carbon_kg"] < rows[best_published]["carbon_kg"]
            ),
            "ours_sla_vs_best_published_pp": round(
                (rows[best_ours]["sla_violation_rate"] - rows[best_published]["sla_violation_rate"])
                * 100.0,
                3,
            ),
        }

    return {
        "sustaincluster_commit": results[0]["sustaincluster_commit"],
        "carbon_window_start_utc": results[0].get("clock_start_utc"),
        "days": days,
        "seed": seed,
        "idle_floor_kg": round(floor_kg, 2),
        "round_robin_carbon_kg": round(rr, 2),
        "controllable_carbon_kg": round(contestable, 2),
        "controllable_share_of_total_pct": round(contestable / rr * 100.0, 2),
        "sla_multipliers": config["sla_multipliers"],
        "by_sla_multiplier": by_sla,
        "planner_forecast_fallbacks": fallbacks,
        "disclosures": [
            "The deferral buffer is a runtime wrapper on the cluster-manager instance; "
            "upstream source is unmodified. Every controller gets the identical timing policy.",
            "Widening sla_multiplier is a disclosed benchmark modification applied identically "
            "to every controller. Upstream's own value is 1.5 and is included as the reference.",
            "The installed carbon series is the realized estimate, so lowest_carbon reads "
            "realized intensity and is an oracle; our planner reads the NESO forecast.",
            "Savings are reported against total carbon and against the contestable carbon "
            "(total minus the measured idle floor). Only the second is comparable across "
            "benchmarks with different idle shares.",
            "The reserve fraction is a single disclosed setting, not tuned on this window; "
            "the arrival rate it budgets against is measured from the workload.",
        ],
    }
