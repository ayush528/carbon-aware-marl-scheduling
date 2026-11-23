"""exp022 -- our scheduler against the published controllers, in their simulator.

Why this experiment exists
--------------------------
Every "we beat the rules" result so far compares our planner to *our own* rules.
That is not evidence against the published algorithms, and cross-paper numbers
cannot supply it: the reported 16-60% savings are measured against different
baselines, on different work, with different SLA accounting (see
``docs/research/2024-2026-carbon-scheduling-comparison.md``).

SustainCluster is the one comparator we can hold fixed: the same simulator, the
same workload, the same four UK sites, the same carbon series, the same
accounting -- and its own published controllers as the baseline. So this
experiment puts our planner inside it as a controller.

What the planner sees and what it is scored on
----------------------------------------------
* **Decisions** use the NESO *forecast* (half-hourly regional, averaged to the
  hour) plus a conformal band calibrated on national residuals strictly before
  the run window. The band is applied with the project's estimator, so it cannot
  reorder sites; it can only change *when* work is worth doing. That is enforced
  by a unit test, not assumed.
* **Accounting** is the simulator's: it consumes the derived regional series, so
  the carbon it reports is realized, not forecast. A planner that read the same
  realized series would have perfect foresight and the comparison would be void.

The arms separate the two things a placement rule can price:

==============================  ==================  ====  =============================
arm                             execution window     lam   what it isolates
==============================  ==================  ====  =============================
``planner_instant``             one 15-minute slot   0.0   the published controller's view
``planner_window``              the task's duration  0.0   duration-aware placement
``planner_window_band``         the task's duration  1.0   + the calibrated band
==============================  ==================  ====  =============================

**Deferral is not an arm here, and that is a finding, not an omission.**
Upstream's default SLA is ``1.5 x duration``, which leaves roughly 15 minutes of
slack on a 50-minute task -- less than one 15-minute simulator step. Temporal
deferral is therefore not expressible in this environment; the published
controllers all place work immediately. The timing lever that exp021 measures
exists only once the deadline is a *policy* variable rather than a fixed
multiple of duration, which is the modelling choice our own environment makes
and this one does not.

The published baselines (``round_robin``, ``lowest_carbon``, ``lowest_price``,
``most_available``, ``least_pending``) run on the identical window with the same
``align_clock`` handling exp009 established. Tasks are fixed by the trace, so
served work is identical across controllers unless one drops tasks -- which the
SLA column exposes.

Disclosures that stay from exp009
---------------------------------
Carbon is our derived regional estimate (national actual x regional forecast /
national forecast) because NESO ships no regional actuals; price is a national
GB series (so ``lowest_price`` is degenerate, not a finding); GB has one AWS
region (so transmission cost is 0 by construction, not a finding).
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

# ``window_hours`` = 0 prices a task at the single slot it arrives in, which is
# what ``lowest_carbon`` does; ``None`` integrates over the task's own duration.
# The declared SLA is 1.5x duration, which leaves ~15 minutes of slack on a
# 50-minute task -- less than one simulator step -- so temporal deferral is not
# expressible in this environment. That is reported, not worked around.
PLANNERS = (
    {"label": "planner_instant", "window_hours": 0.0, "lam": 0.0},
    {"label": "planner_window", "window_hours": None, "lam": 0.0},
    {"label": "planner_window_band", "window_hours": None, "lam": 1.0},
)


def run(config: dict[str, Any]) -> dict[str, Any]:
    sc_cfg = config["sustaincluster"]
    sim = config["simulation"]
    checkout = sustaincluster.checkout_dir(sc_cfg)
    _require_installed(checkout, config)
    python = sustaincluster.resolve_python(checkout, sc_cfg)
    days = float(sim["duration_days"])
    seed = int(config["seed"])

    scratch = Path(tempfile.mkdtemp(prefix=f"{config['id']}-"))
    _write_configs(config, scratch)

    results: list[dict[str, Any]] = []
    for strategy in sc_cfg["baselines"]:
        results.append(
            sustaincluster.run_strategy(
                checkout,
                python,
                strategy,
                days=days,
                seed=seed,
                out_path=scratch / f"{strategy}.json",
                init_day_of_year=int(sim["init_day_of_year"]),
                sim_config=scratch / "sim_config.yaml",
                datacenters=scratch / "datacenters.yaml",
                reward_config=scratch / "reward_config.yaml",
                align_clock=True,
            )
        )

    planner = config["planner"]
    for arm in PLANNERS:
        results.append(
            sustaincluster.run_planner(
                checkout,
                python,
                days=days,
                seed=seed,
                out_path=scratch / f"{arm['label']}.json",
                forecast_csv=REPO_ROOT / planner["forecast_csv"],
                national_json=REPO_ROOT / planner["national_json"],
                region_map={k: int(v) for k, v in planner["region_ids"].items()},
                lam=float(arm["lam"]),
                window_hours=arm["window_hours"],
                alpha=float(planner["alpha"]),
                calibration_end=str(planner["calibration_end"]),
                init_day_of_year=int(sim["init_day_of_year"]),
                sim_config=scratch / "sim_config.yaml",
                datacenters=scratch / "datacenters.yaml",
                reward_config=scratch / "reward_config.yaml",
                align_clock=True,
            )
        )

    rows: dict[str, dict[str, Any]] = {
        result["controller"]: {
            **{k: round(result[k], 4) if isinstance(result[k], float) else result[k] for k in KEEP},
            "per_dc": {
                name: {k: round(v, 2) for k, v in bucket.items()}
                for name, bucket in result["per_dc"].items()
            },
        }
        for result in results
    }

    # Our planner must actually have used our forecast. A tz-aware simulator
    # clock against naive series keys made every lookup miss in the first run of
    # this experiment, so the strategy silently fell back to the simulator's own
    # carbon signal -- i.e. it *was* lowest_carbon, and the exact tie was an
    # artefact. The fallback count is now reported and asserted.
    fallbacks = {
        r["controller"]: r["forecast_fallbacks"]
        for r in results
        if r.get("forecast_fallbacks") is not None
    }
    if any(count != 0 for count in fallbacks.values()):
        raise RuntimeError(
            f"planner arms fell back to the simulator's own signal: {fallbacks}. "
            "The forecast did not resolve; the comparison would be invalid."
        )

    # Every controller must have run the same week; otherwise the comparison is
    # between different weather and different carbon.
    windows = {repr(sorted(r["window"].items())) for r in results if r.get("window")}
    clocks = {r.get("clock_start_utc") for r in results}
    if len(windows) != 1 or len(clocks) != 1:
        raise RuntimeError(
            f"controllers ran on different windows/clocks: windows={windows}, clocks={clocks}"
        )

    reference = rows["round_robin"]
    published = [name for name in sc_cfg["baselines"] if name != "round_robin"]
    best_published = min(published, key=lambda name: rows[name]["carbon_kg"])

    arms: dict[str, Any] = {}
    for label, row in rows.items():
        arms[label] = {
            **row,
            "carbon_vs_round_robin_pct": round(
                (row["carbon_kg"] / reference["carbon_kg"] - 1.0) * 100.0, 2
            ),
            "carbon_vs_lowest_carbon_pct": round(
                (row["carbon_kg"] / rows["lowest_carbon"]["carbon_kg"] - 1.0) * 100.0, 2
            ),
            "sla_vs_lowest_carbon_pp": round(
                (row["sla_violation_rate"] - rows["lowest_carbon"]["sla_violation_rate"]) * 100.0, 2
            ),
            "is_planner": label.startswith("planner"),
        }

    planners = {k: v for k, v in arms.items() if v["is_planner"]}
    best_planner = min(planners, key=lambda name: planners[name]["carbon_kg"])
    # The claim this experiment exists to test: lower carbon than the best
    # published controller, with no worse an SLA.
    winner = arms[best_planner]
    beats_published = bool(
        winner["carbon_kg"] < arms[best_published]["carbon_kg"]
        and winner["sla_violation_rate"] <= arms[best_published]["sla_violation_rate"]
    )

    return {
        "sustaincluster_commit": results[0]["sustaincluster_commit"],
        "carbon_window_start_utc": results[0].get("clock_start_utc"),
        "carbon_window_hours": int(days * 24),
        "clock_aligned_with_carbon": True,
        "days": days,
        "seed": seed,
        "n_sites": len(config["sites"]),
        "n_tasks_finished_all_arms": sorted({v["tasks_finished"] for v in arms.values()}),
        "controllers": arms,
        "planner_arms": [arm["label"] for arm in PLANNERS],
        "planner_forecast_fallbacks": fallbacks,
        "published_baselines": list(sc_cfg["baselines"]),
        "best_published_controller": best_published,
        "best_planner": best_planner,
        "planner_beats_best_published_at_no_worse_sla": beats_published,
        "note": (
            "Planner decisions use the NESO forecast plus a conformal band calibrated "
            "strictly before the window; accounting uses the simulator's realized "
            "series. Carbon is the derived regional estimate (NESO ships no regional "
            "actuals), price is national (lowest_price is degenerate, not a finding), "
            "and GB has one AWS region so transmission cost is 0 by construction."
        ),
    }
