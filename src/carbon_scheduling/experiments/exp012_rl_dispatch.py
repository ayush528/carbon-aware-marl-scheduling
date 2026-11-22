"""exp012 -- learned dispatch with and without the calibrated band.

Phase 3, rung 5: the first agent. PPO (numpy, in-repo) is trained on 2024 weeks
from January to September and evaluated, greedily, on weeks it never saw
(October to December). Three rules from rung 4 are scored on the same weeks:
carbon-greedy, band-aware, and a deadline-aware deferral rule.

The ablation is the point: the same agent architecture and the same training
budget with and without the band in its observation. If the band carries
decision information, the agent that can see it should do better on the *held
out* weeks -- and if it does not, that is the honest answer, and it says the
band's value is in reporting risk rather than in steering this decision.

Leakage control (the rules that make the comparison defensible):

* each episode's band is calibrated on the 28 days before that episode's week;
* the evaluation weeks are never in the training set;
* every policy in the comparison runs on the identical demand and carbon
  arrays, so a difference is the policy and nothing else;
* the demand trace is one real Azure week reused across episodes, which is
  disclosed -- it is the same for every policy, so it cannot favour one.

What the agent controls: where the current batch runs, or whether to wait a
slot. Waiting reaches cleaner hours but risks the deadline. That is the
temporal problem exp011 showed the band cannot solve by site ranking alone.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.rl import baselines, data
from carbon_scheduling.rl.env import SchedulingEnv
from carbon_scheduling.rl.numpy_net import ActorCritic
from carbon_scheduling.rl.ppo import evaluate, train

SLOT_MINUTES = 30


def _aggregate(rows: dict[str, list[dict[str, float]]]) -> dict[str, dict[str, float]]:
    """Mean and standard error of each metric across weeks, per policy."""
    out: dict[str, dict[str, float]] = {}
    for name, episodes in rows.items():
        out[name] = {}
        for metric in ("carbon_kg", "sla_violation_fraction", "unserved_fraction"):
            values = np.array([e[metric] for e in episodes], dtype=float)
            mean = float(values.mean())
            stderr = float(values.std(ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
            out[name][metric] = round(mean, 4)
            out[name][f"{metric}_stderr"] = round(stderr, 4)
    return out


def _relative(carbon: float, reference: float) -> float:
    return round((carbon / reference - 1) * 100, 3) if reference else 0.0


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    demand = data.demand_tokens(paths["demand"])
    names = list(config["regions"])
    sites = data.make_sites(config["sites"], names)
    n_slots = int(config["n_slots"])
    deadline_slots = int(config["deadline_slots"])

    train_weeks = data.weekly_windows(
        series, demand, months=config["train_months"], year=2024, n_slots=n_slots
    )
    eval_weeks = data.weekly_windows(
        series, demand, months=config["eval_months"], year=2024, n_slots=n_slots
    )
    if len(train_weeks) < 2 or not eval_weeks:
        raise ValueError(
            f"not enough covered weeks: train={len(train_weeks)} eval={len(eval_weeks)}"
        )

    def build(start, *, include_band: bool) -> SchedulingEnv:
        forecast, realized, tokens = data.episode_arrays(series, demand, start, n_slots)
        band = data.week_band(series, start, days=int(config["calibration_days"]))
        band_array = np.tile(np.array([band[s] for s in names]), (n_slots, 1))
        return SchedulingEnv(
            forecast=forecast,
            realized=realized,
            band=band_array,
            demand_tokens=tokens,
            sites=sites,
            deadline_slots=deadline_slots,
            sla_penalty_kg_per_kwh=float(config["sla_penalty_kg_per_kwh"]),
            hold_penalty_kg_per_kwh=float(config["hold_penalty_kg_per_kwh"]),
            include_band_in_obs=include_band,
        )

    # --- rule-based rungs, scored on the held-out weeks ---
    heuristic_rows: dict[str, list[dict[str, float]]] = {name: [] for name in baselines.POLICIES}
    for start in eval_weeks:
        for name, policy in baselines.POLICIES.items():
            env = build(start, include_band=True)
            heuristic_rows[name].append(baselines.run_policy(env, policy))

    # --- learned agents: with the band, and without it ---
    agent_rows: dict[str, list[dict[str, float]]] = {}
    training: dict[str, dict[str, Any]] = {}
    for label, include_band in (("ppo_with_band", True), ("ppo_without_band", False)):
        probe = build(train_weeks[0], include_band=include_band)
        net = ActorCritic(
            probe.obs_dim,
            probe.action_space,
            hidden=int(config["hidden"]),
            seed=int(config["seed"]),
        )
        history = train(
            lambda episode, weeks=train_weeks, band=include_band: build(
                weeks[episode % len(weeks)], include_band=band
            ),
            net,
            episodes=int(config["episodes"]),
            seed=int(config["seed"]),
            lr=float(config["lr"]),
        )
        agent_rows[label] = [
            evaluate(build(start, include_band=include_band), net) for start in eval_weeks
        ]
        training[label] = {
            "episodes": len(history),
            "first_return": round(history[0]["episode_return"], 4),
            "last_return": round(history[-1]["episode_return"], 4),
            "last_entropy": round(history[-1]["entropy"], 4),
            "last_clip_fraction": round(history[-1]["clip_fraction"], 4),
        }

    all_rows = {**heuristic_rows, **agent_rows}
    aggregate = _aggregate(all_rows)
    reference = aggregate["run_now"]["carbon_kg"]

    comparison = {
        name: {
            "carbon_kg": stats["carbon_kg"],
            "carbon_kg_stderr": stats["carbon_kg_stderr"],
            "carbon_vs_run_now_pct": _relative(stats["carbon_kg"], reference),
            "sla_violation_fraction": stats["sla_violation_fraction"],
            "unserved_fraction": stats["unserved_fraction"],
        }
        for name, stats in aggregate.items()
    }

    band_effect = _relative(
        aggregate["ppo_with_band"]["carbon_kg"], aggregate["ppo_without_band"]["carbon_kg"]
    )
    best = min(comparison, key=lambda name: comparison[name]["carbon_kg"])

    return {
        "window": {
            "n_slots": n_slots,
            "slot_minutes": SLOT_MINUTES,
            "calibration_days": int(config["calibration_days"]),
            "deadline_slots": deadline_slots,
        },
        "episodes": {
            "train_weeks": [w.strftime("%Y-%m-%d") for w in train_weeks],
            "eval_weeks": [w.strftime("%Y-%m-%d") for w in eval_weeks],
            "n_train": len(train_weeks),
            "n_eval": len(eval_weeks),
            "demand_source": "one real Azure LLM week, reused (identical for all policies)",
        },
        "comparison": comparison,
        "per_week": {name: rows for name, rows in all_rows.items()},
        "training": training,
        "band_obs_effect_on_carbon_pct": band_effect,
        "best_policy": best,
        "best_carbon_kg": comparison[best]["carbon_kg"],
    }
