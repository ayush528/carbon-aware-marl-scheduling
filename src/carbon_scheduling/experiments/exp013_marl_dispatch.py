"""exp013 -- decentralized dispatch: IPPO/MAPPO, communication and CVaR ablations.

Phase 3, rung 6, and the paper's headline structure. The physical problem is the
one exp012 solved centrally, but the decision is now made by one agent per
region. Each agent quotes a risk level (its own ``forecast + lam * band``) and
offers 0/25/50/100% of its slot capacity; an untrained clearing rule fills the
cheapest bids with spill. Agents see only their own region plus two broadcast
numbers from the previous slot: the mean peer bid and the mean accepted share.

Five variants, all trained on 2024 weeks January-September and evaluated
greedily on weeks in October-December:

===================================  ==========================================
``ippo_full``                         independent actors, band in the
                                      observation, communication on
``ippo_no_comm``                      same, with the two peer numbers removed
``ippo_cvar``                         same as full, plus the CVaR tail penalty
                                      on each agent's own violation series
``mappo_full``                        per-agent actors, centralised critic
                                      (training only), communication on
``mappo_cvar``                        same as full, plus the CVaR tail penalty
===================================  ==========================================

Three joint rules are scored on the same weeks (carbon-greedy, band-aware,
deadline-aware deferral), so every learned number has a rule beside it.

What the comparison can and cannot say is fixed in advance: this is one seed,
so variants are compared as point estimates with per-week standard errors, and
Phase 4 repeats them across seeds. The band's role here is the same as in
exp012 -- it is charged in the bid -- and exp011 already showed it cannot change
the site ordering; what it can change is *how much* an agent demands for
serving uncertain carbon, which interacts with the offer decision and with who
gets blamed when a deadline is missed.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.experiments.exp012_rl_dispatch import _aggregate, _relative
from carbon_scheduling.rl import baselines, data
from carbon_scheduling.rl.marl_env import MultiAgentEnv
from carbon_scheduling.rl.marl_ppo import evaluate_multi, train_multi

SLOT_MINUTES = 30


def _build(
    series,
    tokens: np.ndarray,
    sites,
    names: list[str],
    start,
    *,
    communicate: bool,
    include_band: bool,
    config: dict[str, Any],
) -> MultiAgentEnv:
    forecast, realized, _ = data.episode_arrays(series, tokens, start)
    band = data.week_band(series, start, days=int(config["calibration_days"]))
    band_array = np.tile(np.array([band[slug] for slug in names]), (len(tokens), 1))
    return MultiAgentEnv(
        forecast=forecast,
        realized=realized,
        band=band_array,
        demand_tokens=tokens,
        sites=sites,
        deadline_slots=int(config["deadline_slots"]),
        sla_penalty_kg_per_kwh=float(config["sla_penalty_kg_per_kwh"]),
        hold_penalty_kg_per_kwh=float(config["hold_penalty_kg_per_kwh"]),
        communicate=communicate,
        include_band_in_obs=include_band,
    )


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    n_slots = int(config["n_slots"])
    tokens = data.demand_profile(paths["demand"], n_slots)
    sites = data.make_sites(config["sites"], names)

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

    # --- joint rules, scored on the held-out weeks ---
    rule_rows: dict[str, list[dict[str, float]]] = {name: [] for name in baselines.JOINT_POLICIES}
    for start in eval_weeks:
        for name, policy in baselines.JOINT_POLICIES.items():
            env = _build(
                series,
                tokens,
                sites,
                names,
                start,
                communicate=True,
                include_band=True,
                config=config,
            )
            rule_rows[name].append(baselines.run_joint_policy(env, policy))

    # --- learned variants ---
    agent_rows: dict[str, list[dict[str, float]]] = {}
    training: dict[str, dict[str, Any]] = {}
    for variant in config["variants"]:
        label = str(variant["name"])
        communicate = bool(variant.get("communicate", True))
        include_band = bool(variant.get("band", True))
        centralized = variant["algorithm"] == "mappo"
        cvar_weight = float(config["sla_penalty_kg_per_kwh"]) if variant.get("cvar", False) else 0.0

        def factory(
            episode: int,
            _comm=communicate,
            _band=include_band,
            _weeks=train_weeks,
        ) -> MultiAgentEnv:
            start = _weeks[episode % len(_weeks)]
            return _build(
                series,
                tokens,
                sites,
                names,
                start,
                communicate=_comm,
                include_band=_band,
                config=config,
            )

        probe = factory(0)
        actors, _critic, history = train_multi(
            factory,
            n_agents=probe.n_agents,
            obs_dim=probe.obs_dim,
            n_actions=probe.n_actions,
            global_state_dim=probe.global_state_dim,
            centralized_critic=centralized,
            episodes=int(config["episodes"]),
            seed=int(config["seed"]),
            hidden=int(config["hidden"]),
            lr=float(config["lr"]),
            epochs=int(config["epochs"]),
            cvar_alpha=float(config["cvar_alpha"]) if cvar_weight > 0 else None,
            cvar_weight=cvar_weight,
        )

        rows = []
        for start in eval_weeks:
            env = _build(
                series,
                tokens,
                sites,
                names,
                start,
                communicate=communicate,
                include_band=include_band,
                config=config,
            )
            rows.append(evaluate_multi(env, actors))
        agent_rows[label] = rows
        training[label] = {
            "algorithm": variant["algorithm"],
            "communicate": communicate,
            "band_in_obs": include_band,
            "cvar_weight": cvar_weight,
            "episodes": len(history),
            "first_return": round(float(history[0]["episode_return"]), 4),
            "last_return": round(float(history[-1]["episode_return"]), 4),
            "last_entropy": round(float(history[-1]["entropy"]), 4),
        }

    all_rows = {**rule_rows, **agent_rows}
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

    def gap(left: str, right: str) -> float:
        return _relative(comparison[left]["carbon_kg"], comparison[right]["carbon_kg"])

    effects = {
        "communication_ippo_pct": gap("ippo_full", "ippo_no_comm"),
        "centralised_critic_mappo_pct": gap("mappo_full", "ippo_full"),
        "cvar_ippo_pct": gap("ippo_cvar", "ippo_full"),
        "cvar_mappo_pct": gap("mappo_cvar", "mappo_full"),
    }
    best = min(comparison, key=lambda name: comparison[name]["carbon_kg"])

    return {
        "window": {
            "n_slots": n_slots,
            "slot_minutes": SLOT_MINUTES,
            "calibration_days": int(config["calibration_days"]),
            "deadline_slots": int(config["deadline_slots"]),
            "n_agents": len(names),
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
        "effects_pct": effects,
        "best_policy": best,
        "best_carbon_kg": comparison[best]["carbon_kg"],
        "limitations": [
            "one seed: variants are point estimates with per-week standard errors; "
            "Phase 4 repeats them across seeds",
            "the peering signal is the previous slot's mean bid and mean accepted "
            "share only -- richer communication is not tested here",
            "blame for a missed deadline follows refused capacity; that rule is a "
            "disclosed modelling choice, not a measured fact",
        ],
    }
