"""exp008 -- SustainCluster as-is: rule-based baselines and shipped SAC checkpoints.

Purpose (Phase 2 exit test, part 1): reproduce upstream's baseline behaviour
before swapping in NESO regional carbon. Every controller is evaluated on the
same 7-day window, same seed, same workload, so the rows are directly
comparable.

What this measures -- and what it does not:
  * Carbon here is SustainCluster's own per-site carbon intensity data
    (Electricity Maps style, 5 non-UK regions), NOT NESO. This experiment is
    the "as-is" reference point only; the NESO substitution is the next step.
  * ``sla_violation_rate`` comes from SustainCluster's own task SLA check.
    Upstream's reward config has the ``timeliness_penalty`` component
    commented out, so SAC has no SLA incentive -- that asymmetry is a finding,
    not a bug in this experiment.

Driver validation: the in-repo drivers reproduce upstream's evaluation script
exactly on the one number it prints -- for the multi-action + defer checkpoint
over 7 days at seed 123, transmission cost is 3487.70 USD in both.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from carbon_scheduling.sim import sustaincluster


def _rows(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep the comparable fields, keyed by controller name."""
    keep = (
        "carbon_kg",
        "energy_kwh",
        "energy_cost_usd",
        "transmission_cost_usd",
        "sla_violation_rate",
        "tasks_finished",
        "mean_gpu_util_percent",
    )
    out: dict[str, dict[str, Any]] = {}
    for row in results:
        name = row["controller"]
        if row["kind"] == "sac_checkpoint":
            name = f"sac:{row['checkpoint'].split('/')[-2]}"
        out[name] = {k: round(row[k], 4) if isinstance(row[k], float) else row[k] for k in keep}
    return out


def run(config: dict[str, Any]) -> dict[str, Any]:
    sc_cfg = config["sustaincluster"]
    checkout = sustaincluster.checkout_dir(sc_cfg)
    python = sustaincluster.resolve_python(checkout, sc_cfg)
    days = float(sc_cfg["days"])
    seed = int(config["seed"])
    # Per-controller JSONs are scratch: every field they carry is folded into
    # the metrics below, which the runner writes to the immutable run record.
    scratch = Path(tempfile.mkdtemp(prefix=f"{config['id']}-"))

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
            )
        )

    for checkpoint in sc_cfg["checkpoints"]:
        slug = checkpoint.split("/")[-2]
        results.append(
            sustaincluster.run_checkpoint(
                checkout,
                python,
                checkpoint,
                days=days,
                seed=seed,
                out_path=scratch / f"sac_{slug}.json",
                device=sc_cfg["device"],
            )
        )

    rows = _rows(results)
    reference = rows["round_robin"]
    sac_rows = {k: v for k, v in rows.items() if k.startswith("sac:")}
    rbc_rows = {k: v for k, v in rows.items() if not k.startswith("sac:")}
    best_carbon = min(rows, key=lambda k: rows[k]["carbon_kg"])

    return {
        "sustaincluster_commit": results[0]["sustaincluster_commit"],
        "days": days,
        "seed": seed,
        "n_controllers": len(rows),
        "controllers": rows,
        # Relative only -- identical demand for every row.
        "carbon_vs_round_robin_pct": {
            name: round((row["carbon_kg"] / reference["carbon_kg"] - 1) * 100, 2)
            for name, row in rows.items()
            if name != "round_robin"
        },
        "best_carbon_controller": best_carbon,
        "best_carbon_kg": rows[best_carbon]["carbon_kg"],
        "min_sla_violation_rate": min(v["sla_violation_rate"] for v in rows.values()),
        "sac_best_carbon_kg": min(v["carbon_kg"] for v in sac_rows.values()),
        "sac_min_sla_violation_rate": min(v["sla_violation_rate"] for v in sac_rows.values()),
        "rbc_best_carbon_kg": min(v["carbon_kg"] for v in rbc_rows.values()),
        "rbc_min_sla_violation_rate": min(v["sla_violation_rate"] for v in rbc_rows.values()),
    }
