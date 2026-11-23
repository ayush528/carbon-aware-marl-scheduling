"""exp028 — the idle-floor share as a curve, not one number.

exp023 found that 88.7% of the benchmark's carbon is idle draw at one
operating point (four UK sites, ~7% GPU utilisation). That number is often
quoted as if it were a property of the benchmark. It is not: the floor is set
by the estate, so its *share* falls as real work is added. Since every paper
in this area reports a percentage against another controller, a reviewer is
entitled to ask what fraction of the denominator was ever a decision.

This experiment answers it with a curve. The real Alibaba task stream is
resampled per slot to five arrival rates (0.25x to 4x, all derived from real
tasks by a tested transformation), and the same sites, week and controllers
are measured at each point. The idle floor is measured once by switching the
task stream off; it does not depend on arrivals, so it is the same hard lower
bound at every point.

Every saving is then reported two ways: against total carbon (what papers
report) and against contestable carbon, total minus the floor.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from carbon_scheduling.experiments.exp009_uk_sites import KEEP, _require_installed
from carbon_scheduling.runner import REPO_ROOT
from carbon_scheduling.sim import sustaincluster

SCALE_DRIVER = REPO_ROOT / "scripts/sustaincluster/scale_workload.py"


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
    sim_cfg = dict(sim)
    datacenters = scratch / "datacenters.yaml"
    reward_config = scratch / "reward_config.yaml"
    datacenters.write_text(yaml.safe_dump({"datacenters": config["sites"]}))
    reward_config.write_text(yaml.safe_dump({"reward": config["reward"]}))
    (scratch / "floor_sim.yaml").write_text(yaml.safe_dump({"simulation": sim_cfg}))

    # The floor is workload-independent (the driver sets tasks=None), so one
    # measurement bounds every point on the curve.
    floor = sustaincluster.run_idle_floor(
        checkout,
        python,
        out_path=scratch / "floor.json",
        days=days,
        seed=seed,
        init_day_of_year=int(sim["init_day_of_year"]),
        sim_config=scratch / "floor_sim.yaml",
        datacenters=datacenters,
        reward_config=reward_config,
        align_clock=True,
    )

    floor_kg = float(floor["carbon_kg"])
    points: list[dict[str, Any]] = []
    for scale in [float(v) for v in config["arrival_scales"]]:
        workload = scratch / f"workload_{scale:g}.pkl"
        stats_path = scratch / f"workload_{scale:g}.json"
        subprocess.run(
            [
                python,
                str(SCALE_DRIVER),
                "--checkout",
                str(checkout),
                "--scale",
                str(scale),
                "--seed",
                str(seed),
                "--out",
                str(workload),
                "--stats",
                str(stats_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        stats = json.loads(stats_path.read_text())
        # The workload lives in the gitignored checkout, so the runner cannot
        # hash it via config['data']. Hash it here instead: each point carries
        # the exact bytes the simulator consumed.
        digest = hashlib.sha256()
        with workload.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        stats["workload_sha256"] = digest.hexdigest()
        scaled_sim = dict(sim_cfg, workload_path=str(workload))
        sim_path = scratch / f"sim_{scale:g}.yaml"
        sim_path.write_text(yaml.safe_dump({"simulation": scaled_sim}))

        common = dict(
            days=days,
            seed=seed,
            init_day_of_year=int(sim["init_day_of_year"]),
            sim_config=sim_path,
            datacenters=datacenters,
            reward_config=reward_config,
            align_clock=True,
        )
        results = [
            sustaincluster.run_strategy(
                checkout,
                python,
                strategy=name,
                out_path=scratch / f"{name}_{scale:g}.json",
                **common,
            )
            for name in sc_cfg["baselines"]
        ]
        results.append(
            sustaincluster.run_planner(
                checkout,
                python,
                out_path=scratch / f"planner_{scale:g}.json",
                forecast_csv=REPO_ROOT / planner["forecast_csv"],
                national_json=REPO_ROOT / planner["national_json"],
                region_map=region_ids,
                lam=float(planner["lam"]),
                window_hours=planner["window_hours"],
                alpha=float(planner["alpha"]),
                calibration_end=str(planner["calibration_end"]),
                **common,
            )
        )

        clocks = {r.get("clock_start_utc") for r in results}
        if len(clocks) != 1 or floor.get("clock_start_utc") not in clocks:
            raise RuntimeError(f"arms ran on different windows: {clocks}")
        fallbacks = {
            r["arm"]: r["forecast_fallbacks"] for r in results if r.get("forecast_fallbacks")
        }
        if fallbacks:
            raise RuntimeError(f"planner fell back to the simulator signal: {fallbacks}")

        arms: dict[str, Any] = {}
        for result in results:
            carbon = float(result["carbon_kg"])
            name = (
                "planner_duration"
                if result["controller"].startswith("planner_")
                else result["controller"]
            )
            arms[name] = {
                **{k: result[k] for k in KEEP},
                "carbon_above_floor_kg": round(carbon - floor_kg, 2),
            }
        rr = arms["round_robin"]
        contestable = rr["carbon_kg"] - floor_kg
        if contestable <= 0:
            raise RuntimeError("the floor is not below round_robin")
        for arm in arms.values():
            arm["saving_vs_round_robin_pct"] = round(
                (rr["carbon_kg"] - arm["carbon_kg"]) / rr["carbon_kg"] * 100.0, 3
            )
            arm["share_of_contestable_captured_pct"] = round(
                (rr["carbon_kg"] - arm["carbon_kg"]) / contestable * 100.0, 2
            )
            arm["floor_share_of_total_pct"] = round(floor_kg / arm["carbon_kg"] * 100.0, 2)
        points.append(
            {
                "scale": scale,
                "workload": stats,
                "idle_floor_kg": round(floor_kg, 2),
                "contestable_carbon_kg": round(contestable, 2),
                "contestable_share_of_total_pct": round(contestable / rr["carbon_kg"] * 100.0, 2),
                "arms": arms,
            }
        )
        print(
            f"scale {scale:g}: {stats['scaled_tasks']:7d} tasks, "
            f"util {rr['mean_gpu_util_percent']:5.1f}%, floor share "
            f"{rr['floor_share_of_total_pct']:5.1f}%"
        )

    return {
        "sustaincluster_commit": results[0]["sustaincluster_commit"],
        "carbon_window_start_utc": floor.get("clock_start_utc"),
        "days": days,
        "seed": seed,
        "idle_floor_kg": round(floor_kg, 2),
        "points": points,
        "disclosures": [
            "The floor is measured with the task stream switched off in the identical "
            "environment; it is the same hard lower bound at every arrival rate.",
            "Every workload point resamples real Alibaba tasks per 15-minute slot. "
            "No job shape or arrival time is invented; the transformation is seeded "
            "and recorded in each point's workload manifest.",
            "The installed carbon series is the realized estimate, so lowest_carbon "
            "reads realized intensity and is an oracle; our planner reads the forecast.",
            "The floor share is operating-point dependent. This experiment reports the "
            "curve rather than promoting the 0.25x or 4x value to a headline.",
        ],
    }
