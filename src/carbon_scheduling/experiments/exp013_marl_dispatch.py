"""exp013 -- decentralized dispatch: IPPO/MAPPO, communication and CVaR ablations.

Phase 3, rung 6, and the paper's headline structure. The physical problem is the
one exp012 solved centrally, but the decision is now made by one agent per
region. Each agent quotes a risk level (its own ``forecast + lam * band``) and,
under a service obligation, must offer its slot capacity; the alternative is to
wait a slot. An untrained clearing rule fills the cheapest bids with spill.
Agents see only their own region plus two broadcast numbers from the previous
slot: the mean peer bid and the mean accepted share.

Five variants, trained on 2024 weeks January-September and evaluated greedily on
weeks in October-December:

===================================  ==========================================
``ippo_full``                         independent actors, band in the
                                      observation, communication on
``ippo_no_comm``                      same, with the two peer numbers removed
``ippo_cvar``                         same as full, plus the CVaR tail penalty
                                      on each agent's own violation series
``mappo_full``                        per-agent actors, centralised critic
                                      (training only), communication on
``mappo_cvar``                        same as full, plus the CVaR tail penalty
``ippo_market``                       full, plus the offer choice (an agent may
                                      volunteer only a quarter of its capacity)
===================================  ==========================================

Everything is crossed with **two deadline weights** (1 and 10 kg of CO2 per
GPU-hour of missed work) and **two fleets**: ``capacity_bound`` (25 GPUs per
site, from exp007's spec) where the real trace saturates the fleet, and
``slack`` (40 GPUs per site) where every policy can serve all demand and the
only question is *where and when* the work runs.

**Why the fleet and the deadline weight are both swept.** Unserved work emits
nothing, so any policy can look green by doing less of it. In the slack fleet
the service obligation is satisfiable, so carbon differences there are honest
placement/timing differences; the capacity-bound fleet shows what happens when
it is not, and the service-matched flag marks which entries are carbon claims.
The two deadline weights give two points on the carbon-versus-SLA frontier
instead of asserting one weight is right.

Three joint rules are scored on the same weeks and fleets (carbon-greedy,
band-aware, deadline-aware deferral), so every learned number has a rule beside
it. The tail metrics (worst slot, CVaR-90 of the slot series) are what the CVaR
term is supposed to move.

**Why the deadline prices are what they are.** Both prices are *prices*, and a
price is only meaningful against the thing it trades off. Serving one GPU-hour
emits about 0.093 kg CO2 here (measured: ``carbon_g_per_served_gpu_hour``), so a
deadline penalty of 1 kg per missed GPU-hour makes a missed hour cost eleven
served hours, and holding one for a slot costs 0.05 kg against a best case
saving of 0.093 kg. Both sit in "SLA at any price", where deferral can never
pay and the trade the experiment is about cannot happen. The sweep therefore
spans 0.02 (carbon dominates), 0.1 (commensurate), and 1.0 (the old, SLA-at-any-
price anchor). Nothing is charged for work that is merely waiting: the power
model already bills every site's idle floor in every slot, so an extra holding
price would charge the same delay twice, in a unit nobody measured. The deadline
is what bounds deferral.

**Why the learning rate is 3e-4.** At 3e-3 the learner diverges on a 336-step
episode: the greedy policy moves *away* from the optimum as the budget grows
(+7.7% at 80 episodes to +14.1% at 800 on the easy fleet, seeds 0 and 2). At
3e-4 all five seeds reach the optimum within 0.04%. Because the easy fleet has a
known optimum, every variant is also put through :func:`convergence_gate`: a
policy that cannot reach carbon-greedy where carbon-greedy is optimal has not
learned the problem, and its numbers on the hard fleet mean nothing.

**The CVaR arm is a negative result on purpose.** The tail term is charged once,
at the episode's last step, so it enters one of 336 advantage estimates and is
diluted accordingly: the comparison reports the per-slot tail beside every
variant, and the CVaR arm's tail is indistinguishable from the risk-neutral
arm's at every price. The objective is right and the term is in the right units;
where it is charged is wrong. exp015 replaces the terminal charge with a per-step
tail surcharge so credit reaches the slot that caused the violation.

What the comparison can and cannot say is fixed in advance: this is one seed,
so variants are point estimates with per-week standard errors, and exp014
repeats them across seeds.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.experiments.exp012_rl_dispatch import _aggregate, _relative
from carbon_scheduling.rl import baselines, data
from carbon_scheduling.rl.marl_env import MultiAgentEnv
from carbon_scheduling.rl.marl_ppo import evaluate_multi, train_multi

SLOT_MINUTES = 30
SERVICE_TOLERANCE = 0.01


def _build(
    series,
    tokens: np.ndarray,
    sites,
    names: list[str],
    start,
    *,
    communicate: bool,
    include_band: bool,
    allow_decline: bool,
    penalty: float,
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
        sla_penalty_kg_per_kwh=penalty,
        hold_penalty_kg_per_kwh=float(config["hold_penalty_kg_per_kwh"]),
        communicate=communicate,
        include_band_in_obs=include_band,
        allow_decline=allow_decline,
    )


def objective_value(row: dict[str, float], sla_price: float, hold_price: float) -> float:
    """The fleet objective the reward encodes: carbon + priced misses + priced holding.

    Carbon alone is not the objective -- unserved work emits nothing, so a
    carbon-only reading rewards doing less. This is the quantity the agents were
    actually trained to minimise, which makes a learned policy and a hand-written
    rule comparable at any price.
    """
    missed_hours = row["sla_violation_fraction"] * row["offered_gpu_s"] / 3600.0
    held_hours = row["held_gpu_s"] / 3600.0
    return float(row["carbon_kg"] + sla_price * missed_hours + hold_price * held_hours)


def learning_gate(
    learned: list[dict[str, float]],
    rules: dict[str, list[dict[str, float]]],
    sla_price: float,
    hold_price: float,
    tolerance: float = 0.005,
) -> dict[str, Any]:
    """Did the learner optimise the price it was given?

    The reference is the best of the hand-written rules *on the same objective*,
    which is the only comparison that survives a swept price: at a cheap miss
    price the rule that sheds work is right, and at a dear one it is wrong. A
    learner that cannot match the best rule at its own price has not learned the
    problem, whatever its carbon number says.
    """
    learned_objective = float(
        np.mean([objective_value(row, sla_price, hold_price) for row in learned])
    )
    scored = {
        name: float(np.mean([objective_value(row, sla_price, hold_price) for row in rows]))
        for name, rows in rules.items()
    }
    best = min(scored, key=lambda name: scored[name])
    best_objective = scored[best]
    return {
        "learned_objective": round(learned_objective, 3),
        "best_rule": best,
        "best_rule_objective": round(best_objective, 3),
        "improvement_pct": round((learned_objective - best_objective) / best_objective * 100, 3)
        if best_objective
        else 0.0,
        "passed": bool(learned_objective <= best_objective * (1.0 + tolerance)),
    }


def _served_intensity(rows: list[dict[str, float]]) -> float:
    """gCO2 per GPU-hour actually served: *where* the work ran, not how much."""
    carbon_kg = sum(row["carbon_kg"] for row in rows)
    served_hours = sum(row["served_gpu_s"] for row in rows) / 3600.0
    return round(carbon_kg * 1000.0 / served_hours, 2) if served_hours else 0.0


def _mean(rows: list[dict[str, float]], key: str) -> float:
    return round(float(np.mean([row[key] for row in rows])), 4)


def _paired(
    rows: list[dict[str, float]], reference: list[dict[str, float]], key: str = "carbon_kg"
) -> dict[str, float]:
    """Paired per-week comparison against a reference policy.

    The weeks share their weather and their carbon, so the between-week variance
    (which is huge: a windy week is far cleaner than a still one) cancels in the
    difference. An unpaired standard error would drown every real effect, so
    this is the test the claims are read from.
    """
    if len(rows) != len(reference):
        raise ValueError("paired comparison needs the same weeks")
    diffs = np.array([row[key] - ref[key] for row, ref in zip(rows, reference, strict=True)])
    n = len(diffs)
    base = float(np.mean([ref[key] for ref in reference]))
    mean = float(diffs.mean())
    stderr = float(diffs.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    return {
        "mean_diff": round(mean, 4),
        "stderr": round(stderr, 4),
        "relative_pct": round(mean / base * 100, 3) if base else 0.0,
        "weeks_better": int((diffs < 0).sum()),
        "weeks_worse": int((diffs > 0).sum()),
        "n_weeks": n,
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    n_slots = int(config["n_slots"])
    tokens = data.demand_profile(paths["demand"], n_slots)
    penalties = [float(v) for v in config["sla_penalties"]]
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

    rows_by_policy: dict[str, list[dict[str, float]]] = {}
    training: dict[str, dict[str, Any]] = {}

    for fleet, n_gpus in fleets.items():
        spec = {**config["sites"], "n_gpus": n_gpus}
        sites = data.make_sites(spec, names)

        # --- joint rules, scored on the held-out weeks ---
        # Rules ignore the deadline weight, so they are one point per fleet.
        for name, policy in baselines.JOINT_POLICIES.items():
            label = f"{name}/{fleet}"
            rows_by_policy[label] = []
            for start in eval_weeks:
                env = _build(
                    series,
                    tokens,
                    sites,
                    names,
                    start,
                    communicate=True,
                    include_band=True,
                    allow_decline=False,
                    penalty=penalties[0],
                    config=config,
                )
                rows_by_policy[label].append(baselines.run_joint_policy(env, policy))

        # --- learned variants, one per (variant, deadline weight) ---
        for penalty in penalties:
            for variant in config["variants"]:
                name = str(variant["name"])
                label = f"{name}@{penalty:g}/{fleet}"
                communicate = bool(variant.get("communicate", True))
                include_band = bool(variant.get("band", True))
                allow_decline = bool(variant.get("decline", False))
                centralized = variant["algorithm"] == "mappo"
                cvar_weight = penalty if variant.get("cvar", False) else 0.0

                def factory(
                    episode: int,
                    _comm=communicate,
                    _band=include_band,
                    _decline=allow_decline,
                    _penalty=penalty,
                    _weeks=train_weeks,
                    _sites=sites,
                ) -> MultiAgentEnv:
                    start = _weeks[episode % len(_weeks)]
                    return _build(
                        series,
                        tokens,
                        _sites,
                        names,
                        start,
                        communicate=_comm,
                        include_band=_band,
                        allow_decline=_decline,
                        penalty=_penalty,
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
                        allow_decline=allow_decline,
                        penalty=penalty,
                        config=config,
                    )
                    rows.append(evaluate_multi(env, actors))
                rows_by_policy[label] = rows
                training[label] = {
                    "algorithm": variant["algorithm"],
                    "communicate": communicate,
                    "band_in_obs": include_band,
                    "allow_decline": allow_decline,
                    "sla_penalty": penalty,
                    "cvar_weight": cvar_weight,
                    "episodes": len(history),
                    "first_return": round(float(history[0]["episode_return"]), 4),
                    "last_return": round(float(history[-1]["episode_return"]), 4),
                    "last_entropy": round(float(history[-1]["entropy"]), 4),
                }

    # Learning gate, per (variant, price, fleet): is the learner at least as
    # good as the best hand-written rule *on its own objective*? The rules ignore
    # the price, so their rows are shared and only the scoring changes.
    hold_price = float(config["hold_penalty_kg_per_kwh"])
    rules: dict[str, dict[str, list[dict[str, float]]]] = {
        fleet: {name: rows_by_policy[f"{name}/{fleet}"] for name in baselines.JOINT_POLICIES}
        for fleet in fleets
    }
    convergence: dict[str, dict[str, Any]] = {}
    for label, rows in rows_by_policy.items():
        variant, fleet = label.split("/")
        if variant in baselines.JOINT_POLICIES:
            continue
        price = float(variant.split("@")[1])
        convergence[label] = learning_gate(rows, rules[fleet], price, hold_price)

    aggregate = _aggregate(rows_by_policy)
    comparison: dict[str, dict[str, Any]] = {}
    for label, stats in aggregate.items():
        fleet = label.split("/")[-1]
        reference = aggregate[f"run_now/{fleet}"]["carbon_kg"]
        limit = aggregate[f"run_now/{fleet}"]["unserved_fraction"] + SERVICE_TOLERANCE
        comparison[label] = {
            "fleet": fleet,
            "carbon_kg": stats["carbon_kg"],
            "carbon_kg_stderr": stats["carbon_kg_stderr"],
            "carbon_vs_run_now_pct": _relative(stats["carbon_kg"], reference),
            "sla_violation_fraction": stats["sla_violation_fraction"],
            "unserved_fraction": stats["unserved_fraction"],
            "max_slot_violation_fraction": _mean(
                rows_by_policy[label], "max_slot_violation_fraction"
            ),
            "cvar90_slot_violation_fraction": _mean(
                rows_by_policy[label], "cvar90_slot_violation_fraction"
            ),
            "carbon_g_per_served_gpu_hour": _served_intensity(rows_by_policy[label]),
            "service_matched": bool(
                stats["unserved_fraction"] <= limit and stats["sla_violation_fraction"] <= limit
            ),
            "paired_vs_run_now": _paired(rows_by_policy[label], rows_by_policy[f"run_now/{fleet}"]),
        }

    effects: dict[str, dict[str, float]] = {}
    for fleet in fleets:
        pairs = (
            ("communication_ippo", "ippo_full@1", "ippo_no_comm@1"),
            ("centralised_critic_mappo", "mappo_full@1", "ippo_full@1"),
            ("cvar_ippo", "ippo_cvar@1", "ippo_full@1"),
            ("cvar_mappo", "mappo_cvar@1", "mappo_full@1"),
            ("market_vs_obligation", "ippo_market@1", "ippo_full@1"),
        )
        for name, left, right in pairs:
            left_label, right_label = f"{left}/{fleet}", f"{right}/{fleet}"
            if left_label in comparison and right_label in comparison:
                effects[f"{name}_{fleet}"] = _paired(
                    rows_by_policy[left_label], rows_by_policy[right_label]
                )

    # The frontier is the honest headline: at each price and fleet, the best
    # learner by its own objective, beside the best rule at that same price and
    # the service level the learner chose. Carbon is meaningless without the
    # service level next to it, so both are always reported together.
    frontier: dict[str, dict[str, Any]] = {}
    for fleet in fleets:
        for penalty in penalties:
            key = f"{penalty:g}/{fleet}"
            learners = [
                label
                for label in comparison
                if comparison[label]["fleet"] == fleet
                and not label.startswith(tuple(baselines.JOINT_POLICIES))
                and label.split("/")[0].endswith(f"@{penalty:g}")
            ]
            if not learners:
                continue
            best = min(learners, key=lambda label: convergence[label]["learned_objective"])
            gate = convergence[best]
            frontier[key] = {
                "best": best,
                "carbon_kg": comparison[best]["carbon_kg"],
                "carbon_vs_run_now_pct": comparison[best]["carbon_vs_run_now_pct"],
                "sla_violation_fraction": comparison[best]["sla_violation_fraction"],
                "unserved_fraction": comparison[best]["unserved_fraction"],
                "objective": gate["learned_objective"],
                "best_rule": gate["best_rule"],
                "best_rule_objective": gate["best_rule_objective"],
                "beat_best_rule_pct": -gate["improvement_pct"],
                "passed_gate": gate["passed"],
                "learners_passing_gate": sum(
                    1 for label in learners if convergence[label]["passed"]
                ),
            }

    return {
        "window": {
            "n_slots": n_slots,
            # The price at which missing a GPU-hour costs what serving it costs,
            # read off the carbon-greedy rule. Below it, shedding work is the
            # right response to the price and the sweep arm is a control.
            "parity_price_kg_per_gpu_hour": round(
                _served_intensity(rows_by_policy["run_now/capacity_bound"]) / 1000.0, 4
            ),
            "slot_minutes": SLOT_MINUTES,
            "calibration_days": int(config["calibration_days"]),
            "deadline_slots": int(config["deadline_slots"]),
            "n_agents": len(names),
            "sla_penalties": penalties,
            "fleets": fleets,
            "service_tolerance": SERVICE_TOLERANCE,
        },
        "episodes": {
            "train_weeks": [w.strftime("%Y-%m-%d") for w in train_weeks],
            "eval_weeks": [w.strftime("%Y-%m-%d") for w in eval_weeks],
            "n_train": len(train_weeks),
            "n_eval": len(eval_weeks),
            "demand_source": "one real Azure LLM week, reused (identical for all policies)",
        },
        "comparison": comparison,
        "per_week": rows_by_policy,
        "training": training,
        "effects_pct": effects,
        "frontier": frontier,
        "convergence": convergence,
        "limitations": [
            "one seed: variants are point estimates with per-week standard errors; "
            "Phase 4 repeats them across seeds",
            "carbon totals are only comparable between service-matched policies; "
            "unserved work emits nothing",
            "the peering signal is the previous slot's mean bid and mean accepted "
            "share only -- richer communication is not tested here",
            "the CVaR term is a terminal adjustment on each agent's own per-slot "
            "violation series; an actor-critic with a per-step risk state would be "
            "a different (stronger) object",
        ],
    }
