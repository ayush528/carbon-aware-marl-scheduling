"""exp031 — does the headline survive a different workload?

Every dispatch experiment in this project lays the *same* real Azure LLM week
over each carbon week. That is disclosed, and it is also the weakest point in the
evaluation: a reviewer is entitled to ask whether the 6-12% saving is a property
of the scheduler or of that one week's shape.

This experiment answers it by re-running the shipped arms on transformations of
the real trace. Every variant is derived from real arrivals -- none is synthetic
demand -- and each is labelled as a transformation:

``real``
    The trace itself. The reference every other row is compared against.
``scale_0.5`` / ``scale_2.0``
    Volume halved and doubled. Tests load sensitivity, and doubles as the
    utilisation axis the idle-floor result needs.
``shift_12h``
    The week rotated by 12 hours. Tests whether the saving depends on the
    workload's diurnal phase lining up with the grid's.
``day_shuffle``
    The seven days permuted. Each day keeps its real shape; their order changes.
``block_bootstrap``
    Contiguous four-hour blocks resampled with replacement. Preserves short-range
    structure, breaks the specific week. This is the strongest test: if the
    saving survives it, the saving is not that week.

The reserve is re-calibrated on each variant's own arrivals, so the comparison
stays causal and no variant inherits a reserve tuned for another.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.experiments.exp016_queue_ownership import _env_for
from carbon_scheduling.experiments.exp018_arrival_reserve import _hybrid_env, calibrate
from carbon_scheduling.experiments.exp021_service_frontier import _row_summary
from carbon_scheduling.rl import data
from carbon_scheduling.rl.arrival_risk import reserve_per_site_slot
from carbon_scheduling.rl.hybrid import BlockPlanner, run_scheduler
from carbon_scheduling.rl.queue_rules import run_rule

SLOT_MINUTES = 30
SLOTS_PER_DAY = 48


def demand_variants(
    tokens: np.ndarray, *, seed: int, block_slots: int = 8
) -> dict[str, np.ndarray]:
    """Transformations of the real trace. All derived from real arrivals."""
    rng = np.random.default_rng(seed)
    n = len(tokens)
    out: dict[str, np.ndarray] = {"real": tokens.copy()}
    out["scale_0.5"] = tokens * 0.5
    out["scale_2.0"] = tokens * 2.0
    out["shift_12h"] = np.roll(tokens, SLOTS_PER_DAY // 2)

    days = n // SLOTS_PER_DAY
    if days > 1:
        order = rng.permutation(days)
        blocks = [tokens[d * SLOTS_PER_DAY : (d + 1) * SLOTS_PER_DAY] for d in order]
        out["day_shuffle"] = np.concatenate(blocks + [tokens[days * SLOTS_PER_DAY :]])

    n_blocks = n // block_slots
    picks = rng.integers(0, n_blocks, size=n_blocks)
    resampled = np.concatenate([tokens[i * block_slots : (i + 1) * block_slots] for i in picks])
    out["block_bootstrap"] = np.concatenate([resampled, tokens[n_blocks * block_slots :]])
    return out


def _arms(reserve_gpu_s: float, window: int) -> dict[str, BlockPlanner]:
    """The exp021 headline arms, unchanged. No new operating point is chosen here."""
    arms = {
        f"look{k}_ghost": BlockPlanner(
            max_lookahead=k,
            arrival_model="seasonal",
            arrival_window=window,
            ghost_arrivals=True,
        )
        for k in (4, 8)
    }
    if reserve_gpu_s > 0.0:
        arms["look4_reserve"] = BlockPlanner(max_lookahead=4, reserve_gpu_s=reserve_gpu_s)
    return arms


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    n_slots = int(config["n_slots"])
    base_tokens = data.demand_profile(paths["demand"], n_slots)
    held_out = data.weekly_windows(
        series,
        months=[int(m) for m in config["eval_months"]],
        year=int(config["year"]),
        n_slots=n_slots,
        calibration_days=int(config["calibration_days"]),
    )
    deadlines = [int(d) for d in config["deadlines"]]
    window = int(config["arrival_window"])
    level = float(config["arrival_level"])
    throughput = float(config["sites"]["tokens_per_gpu_second"])
    prices = [float(p) for p in config["prices"]]

    variants = demand_variants(base_tokens, seed=int(config["seed"]))
    results: dict[str, Any] = {
        "weeks": [f"{s:%Y-%m-%d}" for s in held_out],
        "n_weeks": len(held_out),
        "fleets": {},
        "note": (
            "Every demand variant is a transformation of the one real Azure week, "
            "not synthetic demand. The reserve is re-calibrated on each variant's "
            "own arrivals. Arms are exp021's, unchanged; no operating point is "
            "selected on these weeks."
        ),
    }

    for fleet in config["fleets"]:
        n_gpus = int(fleet["n_gpus"])
        sites = data.make_sites({**config["sites"], "n_gpus": n_gpus}, names)
        capacity = n_gpus * SLOT_MINUTES * 60
        by_variant: dict[str, Any] = {}
        for label, tokens in variants.items():
            calibration = calibrate(tokens / throughput, level, window)
            reserve = reserve_per_site_slot(
                calibration["quantile_gpu_s"],
                n_sites=len(names),
                min_deadline=min(deadlines),
                capacity=capacity,
            )
            rows: dict[str, list[dict[str, float]]] = {"run_now": []}
            for start in held_out:
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
                rows["run_now"].append(run_rule(env, "run_now"))
            for arm, planner in _arms(reserve, window).items():
                rows[arm] = []
                for start in held_out:
                    env = _hybrid_env(series, tokens, sites, names, start, config)
                    rows[arm].append(run_scheduler(env, planner))

            ref_served_h = float(np.mean([r["served_gpu_s"] for r in rows["run_now"]])) / 3600.0
            base = _row_summary(rows["run_now"], prices, ref_served_h, [0.0] * len(held_out))
            arms_out: dict[str, Any] = {"run_now": base}
            for arm, arm_rows in rows.items():
                if arm == "run_now":
                    continue
                summary = _row_summary(arm_rows, prices, ref_served_h, [0.0] * len(held_out))
                summary["carbon_vs_run_now_pct"] = round(
                    (summary["carbon_kg"] / base["carbon_kg"] - 1.0) * 100.0, 3
                )
                summary["missed_vs_run_now_pp"] = round(
                    (summary["missed_fraction"] - base["missed_fraction"]) * 100.0, 3
                )
                summary["matched_service_vs_run_now_pct"] = round(
                    (summary["matched_service_carbon_kg_extrapolated"] / base["carbon_kg"] - 1.0)
                    * 100.0,
                    3,
                )
                summary["pareto_vs_run_now"] = bool(
                    summary["carbon_kg"] <= base["carbon_kg"]
                    and summary["missed_fraction"] <= base["missed_fraction"]
                )
                arms_out[arm] = summary
            by_variant[label] = {
                "mean_tokens_per_slot": round(float(np.mean(tokens)), 1),
                "reserve_gpu_s_per_site_slot": round(reserve, 1),
                "arms": arms_out,
            }
            print(
                f"{fleet['name']:15s} {label:16s} reserve={reserve:8.0f} "
                f"run_now={base['carbon_kg']:9.1f}kg miss={base['missed_fraction'] * 100:5.2f}%"
            )
        results["fleets"][str(fleet["name"])] = by_variant

    return results
