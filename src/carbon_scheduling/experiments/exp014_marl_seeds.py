"""exp014 -- does the exp013 headline survive seeds? (multi-seed replication)

exp013 found one thing that beats carbon-greedy at matched service: a CVaR-on-
deadline agent, 1.57% in the capacity-bound fleet, better in 12 of 12 weeks on
one seed. One seed is a point estimate. This experiment repeats the comparison
across five training seeds and three tail levels, so the claim is either
seed-robust or it is not.

The design is deliberately narrow: the reference is always the same
carbon-greedy rule on the same 12 held-out weeks, the evaluation demand and
carbon are identical for every run, and the only things that vary are the
training seed and the CVaR settings. A policy is summarised by the *paired*
per-week difference from the reference (weather variance cancels), reported as
a mean and spread across seeds.

Variants, each trained at deadline weight 1.0 (the exp013 setting where the
CVaR agent matched carbon-greedy's service level):

``cvar80`` / ``cvar90`` / ``cvar95``   tail levels alpha = 0.8 / 0.9 / 0.95
``risk_neutral``                       the same agent with no CVaR term

and the deadline-aware ``defer`` rule for reference. Both fleets are run, so a
seed-robust effect in the capacity-bound fleet and its absence in the slack
fleet are visible at once.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.experiments.exp013_marl_dispatch import (
    _build,
    _paired,
    learning_gate,
)
from carbon_scheduling.rl import baselines, data
from carbon_scheduling.rl.marl_ppo import evaluate_multi, train_multi


def _spread(values: list[float]) -> dict[str, float]:
    """Mean, spread and sign consistency of one per-seed quantity."""
    array = np.asarray(values, dtype=float)
    return {
        "mean": round(float(array.mean()), 3),
        "sd": round(float(array.std(ddof=1)), 3) if array.size > 1 else 0.0,
        "min": round(float(array.min()), 3),
        "max": round(float(array.max()), 3),
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    n_slots = int(config["n_slots"])
    tokens = data.demand_profile(paths["demand"], n_slots)
    penalty = float(config["sla_penalty_kg_per_kwh"])
    seeds = [int(s) for s in config["seeds"]]
    fleets = {str(f["name"]): int(f["n_gpus"]) for f in config["fleets"]}

    train_weeks = data.weekly_windows(
        series,
        months=config["train_months"],
        year=2024,
        n_slots=n_slots,
        calibration_days=int(config["calibration_days"]),
    )
    eval_weeks = data.weekly_windows(
        series,
        months=config["eval_months"],
        year=2024,
        n_slots=n_slots,
        calibration_days=int(config["calibration_days"]),
    )
    if len(train_weeks) < 2 or not eval_weeks:
        raise ValueError(
            f"not enough covered weeks: train={len(train_weeks)} eval={len(eval_weeks)}"
        )

    per_seed: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {}

    for fleet, n_gpus in fleets.items():
        sites = data.make_sites({**config["sites"], "n_gpus": n_gpus}, names)

        def make(start, _sites=sites) -> Any:
            return _build(
                series,
                tokens,
                _sites,
                names,
                start,
                communicate=True,
                include_band=True,
                allow_decline=False,
                penalty=penalty,
                config=config,
            )

        reference = []
        for start in eval_weeks:
            reference.append(
                baselines.run_joint_policy(make(start), baselines.JOINT_POLICIES["run_now"])
            )
        defer_rows = [
            baselines.run_joint_policy(make(start), baselines.JOINT_POLICIES["defer"])
            for start in eval_weeks
        ]

        base_carbon = float(np.mean([row["carbon_kg"] for row in reference]))
        rules = {
            "run_now": {
                "carbon_kg": round(base_carbon, 3),
                "sla_violation_fraction": round(
                    float(np.mean([row["sla_violation_fraction"] for row in reference])), 4
                ),
            },
            "defer": {
                "carbon_kg": round(float(np.mean([row["carbon_kg"] for row in defer_rows])), 3),
                "sla_violation_fraction": round(
                    float(np.mean([row["sla_violation_fraction"] for row in defer_rows])), 4
                ),
                "paired_vs_run_now": _paired(defer_rows, reference),
            },
        }

        rules_rows = {
            "run_now": reference,
            "defer": defer_rows,
        }
        hold_price = float(config["hold_penalty_kg_per_kwh"])

        per_seed[fleet] = {}
        summary[fleet] = {
            "run_now_carbon_kg": round(base_carbon, 3),
            "rules": rules,
            "variants": {},
        }

        for variant in config["variants"]:
            name = str(variant["name"])
            alpha = variant.get("cvar_alpha")
            cvar_weight = 0.0 if alpha is None else penalty
            seed_records: list[dict[str, Any]] = []
            for seed in seeds:

                def factory(
                    episode: int,
                    _weeks=train_weeks,
                ) -> Any:
                    return make(_weeks[episode % len(_weeks)])

                probe = factory(0)
                actors, _critic, _history = train_multi(
                    factory,
                    n_agents=probe.n_agents,
                    obs_dim=probe.obs_dim,
                    n_actions=probe.n_actions,
                    global_state_dim=probe.global_state_dim,
                    centralized_critic=False,
                    episodes=int(config["episodes"]),
                    seed=seed,
                    hidden=int(config["hidden"]),
                    lr=float(config["lr"]),
                    epochs=int(config["epochs"]),
                    cvar_alpha=float(alpha) if alpha is not None else None,
                    cvar_weight=cvar_weight,
                )
                rows = [evaluate_multi(make(start), actors) for start in eval_weeks]
                record: dict[str, Any] = {
                    "seed": seed,
                    "carbon_kg": round(float(np.mean([r["carbon_kg"] for r in rows])), 3),
                    "sla_violation_fraction": round(
                        float(np.mean([r["sla_violation_fraction"] for r in rows])), 4
                    ),
                    "paired_vs_run_now": _paired(rows, reference),
                }
                # Scored against the best rule on the learner's own objective,
                # which is the only comparison that survives a swept price.
                record["gate"] = learning_gate(rows, rules_rows, penalty, hold_price)
                seed_records.append(record)
            per_seed[fleet][name] = seed_records
            summary[fleet]["variants"][name] = {
                "cvar_alpha": alpha,
                "carbon_kg": _spread([r["carbon_kg"] for r in seed_records]),
                "sla_violation_fraction": _spread(
                    [r["sla_violation_fraction"] for r in seed_records]
                ),
                "paired_relative_pct": _spread(
                    [r["paired_vs_run_now"]["relative_pct"] for r in seed_records]
                ),
                "seeds_better_in_every_week": int(
                    sum(1 for r in seed_records if r["paired_vs_run_now"]["weeks_worse"] == 0)
                ),
                "n_seeds": len(seed_records),
                "seeds_passing_gate": int(sum(1 for r in seed_records if r["gate"]["passed"])),
            }

    return {
        "window": {
            "n_slots": n_slots,
            "calibration_days": int(config["calibration_days"]),
            "deadline_slots": int(config["deadline_slots"]),
            "sla_penalty_kg_per_kwh": penalty,
            "fleets": fleets,
            "seeds": seeds,
        },
        "episodes": {
            "n_train": len(train_weeks),
            "n_eval": len(eval_weeks),
            "eval_weeks": [w.strftime("%Y-%m-%d") for w in eval_weeks],
        },
        "rules": {fleet: summary[fleet]["rules"] for fleet in fleets},
        "summary": {fleet: summary[fleet]["variants"] for fleet in fleets},
        "per_seed": per_seed,
        "limitations": [
            "five seeds is enough to see whether an effect has the same sign every "
            "time, not to estimate its size precisely",
            "the demand profile is one real Azure week reused, identical for every "
            "policy and seed, so it cannot favour one",
            "closed-form reference is the carbon-greedy rule on the same weeks; the "
            "paired difference is what is reported",
        ],
    }
