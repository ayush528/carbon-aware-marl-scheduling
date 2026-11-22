"""exp016 -- rung 7: agents own queues, so timing becomes a unilateral decision.

Why this rung exists
    exp011 closed the *ranking* question: under the national-scaling estimator
    the realized regional intensity is a per-slot monotone transform of the
    forecast, so carbon-aware placement is exactly known and an oracle ties
    forecast-greedy. What remains is *timing*. exp015 measured its value exactly
    with a min-cost-flow bound: at the 4-hour deadline, serving exactly the
    volume carbon-greedy serves, perfect foresight saves 29.4% on the slack
    fleet and 14.5% on the capacity-bound fleet, in 12/12 held-out weeks.

    Rung 6 could not reach any of it, and the reason is structural rather than
    a training failure. There, an agent owned a *site* and could defer only by
    `wait`ing, which withdraws its capacity and lets the coordinator spill the
    work elsewhere: one agent deferring accomplishes nothing, so deferral was a
    joint action that independent learners never take.

What changed
    Ownership is inverted. An agent owns a **work stream and a backlog**, not a
    site, and its only decision is how long to hold its own work before offering
    it. Nobody else's queue moves, so deferral is unilateral -- and the
    coordinator still places whatever is offered, cheapest forecast first, so
    rung 6's placement result is preserved.

    Work arrives in four classes with deadlines of 1, 2, 4 and 8 hours, one per
    agent (the 4-hour class is the deadline every rung since exp012 used). That
    is what makes the agents different, and it is the part of the problem the
    band can act on: a class that may not wait cannot use the forecast at all,
    and a class that may wait should only use it when the improvement is bigger
    than the measurement error.

What is measured
    * the four hand-written timing rules (immediate, last-legal-slot,
      forecast-aware, band-aware) on the held-out weeks, and their objective at
      every price in the sweep -- the rule frontier the learner has to beat;
    * IPPO, IPPO without communication, MAPPO, and IPPO with a CVaR tail term
      charged *per step* instead of once at the end;
    * the exact perfect-foresight bound for the same classes, twice: at the
      volume the immediate rule serves (the headline ceiling), and at each
      arm's *own* served volume. The second is what stops a policy from looking
      good by serving less -- unserved work emits nothing, so a carbon-only
      reading rewards shedding, and the bound at a lower volume is lower too.

Learning settings are chosen on a hold-out slice of the *training* months
(July-September), never on the evaluation weeks. ``gamma = 1`` is not a tuning
knob: the objective is the episode total, and a discounted return
systematically under-prices a cost that lands ten or fifteen slots after the
decision that caused it -- which is exactly the bias that makes deferral look
free. ``lam`` and the episode count *are* chosen, on that slice.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.cluster import site_energy_kwh
from carbon_scheduling.experiments.exp013_marl_dispatch import _paired
from carbon_scheduling.rl import data
from carbon_scheduling.rl.marl_ppo import train_multi
from carbon_scheduling.rl.oracle import plan_multi
from carbon_scheduling.rl.queue_env import QueueEnv
from carbon_scheduling.rl.queue_rules import run_rule

SLOT_MINUTES = 30

VARIANTS: dict[str, dict[str, Any]] = {
    "ippo": {"centralized": False, "communicate": True, "cvar": None},
    "ippo_comm_off": {"centralized": False, "communicate": False, "cvar": None},
    "ippo_cvar_step": {"centralized": False, "communicate": True, "cvar": "per_step"},
    "ippo_cvar_terminal": {"centralized": False, "communicate": True, "cvar": "terminal"},
    "mappo": {"centralized": True, "communicate": True, "cvar": None},
}


def _env_for(
    series,
    tokens: np.ndarray,
    sites,
    names: list[str],
    start,
    config: dict[str, Any],
    *,
    communicate: bool,
    include_band: bool,
    price: float,
) -> QueueEnv:
    forecast, realized, _ = data.episode_arrays(series, tokens, start)
    band = data.week_band(series, start, days=int(config["calibration_days"]))
    band_array = np.tile(np.array([band[slug] for slug in names]), (len(tokens), 1))
    return QueueEnv(
        forecast=forecast,
        realized=realized,
        band=band_array,
        demand_tokens=tokens,
        sites=sites,
        deadlines=[int(d) for d in config["deadlines"]],
        sla_penalty_kg_per_gpu_hour=price,
        communicate=communicate,
        include_band_in_obs=include_band,
    )


def objective(row: dict[str, float], price: float) -> float:
    """Carbon plus the priced misses -- exactly the reward the agents receive.

    Carbon alone would reward doing less, because unserved work emits nothing;
    this is the quantity every arm was trained on, at the price it was given.
    """
    missed_hours = row["missed_fraction"] * row["offered_gpu_s"] / 3600.0
    return float(row["carbon_kg"] + price * missed_hours)


def _play(env: QueueEnv, actors) -> tuple[dict, np.ndarray]:
    """Greedy joint episode: the summary, plus the actions taken (T, agents).

    The action trace is the mechanism evidence. A carbon cut that comes from
    every agent holding to the wire is the deadline rule rediscovered; a cut
    that comes from agents choosing *different* coasts in the same slot is
    timing that a per-agent rule could not have expressed, and only the trace
    distinguishes the two.
    """
    obs, _ = env.reset()
    picked = []
    while True:
        actions = [int(np.argmax(net.forward(obs[i])[0][0])) for i, net in enumerate(actors)]
        picked.append(actions)
        obs, _, done, _, _ = env.step(actions)
        if done:
            return env.summary(), np.asarray(picked, dtype=float)


def _mean(rows: list[dict], key: str) -> float:
    return round(float(np.mean([float(row[key]) for row in rows])), 4)


def _carbon(alloc: np.ndarray, realized: np.ndarray, sites) -> float:
    """Carbon of an allocation, with the same power model the environment bills."""
    total = alloc.sum(axis=0)  # (slots, sites): classes share the fleet
    kg = 0.0
    for t in range(total.shape[0]):
        for j, site in enumerate(sites):
            kg += (
                site_energy_kwh(site, float(total[t, j]), SLOT_MINUTES)
                * float(realized[t, j])
                / 1000.0
            )
    return kg


def _oracle(
    env: QueueEnv, deadlines: list[int], capacity: float, volume: float
) -> dict[str, float]:
    """Exact cheapest schedule for the same classes at matched served volume."""
    unit = np.array(
        [
            site_energy_kwh(site, 1.0, SLOT_MINUTES) - site_energy_kwh(site, 0.0, SLOT_MINUTES)
            for site in env.sites
        ]
    )
    cost = unit[None, :] * env.realized / 1000.0
    demand = np.tile(
        (env.demand_tokens / env.throughput)[None, :] / env.n_agents,
        (len(deadlines), 1),
    )
    alloc, unserved = plan_multi(cost, demand, capacity, deadlines, volume=volume)
    offered = float(demand.sum())
    return {
        "carbon_kg": round(_carbon(alloc, env.realized, env.sites), 3),
        "missed_fraction": round(float(unserved) / offered, 4),
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    tokens = data.demand_profile(paths["demand"], int(config["n_slots"]))
    deadlines = [int(d) for d in config["deadlines"]]

    train_starts = data.weekly_windows(
        series,
        months=[int(m) for m in config["train_months"]],
        year=int(config["year"]),
        n_slots=int(config["n_slots"]),
        calibration_days=int(config["calibration_days"]),
    )
    held_out = data.weekly_windows(
        series,
        months=[int(m) for m in config["eval_months"]],
        year=int(config["year"]),
        n_slots=int(config["n_slots"]),
        calibration_days=int(config["calibration_days"]),
    )
    if not train_starts or not held_out:
        raise ValueError("need both training and held-out weeks in the configured months")

    results: dict[str, Any] = {
        "weeks": [f"{s:%Y-%m-%d}" for s in held_out],
        "n_training_weeks": len(train_starts),
        "deadlines": deadlines,
        "fleets": {},
    }

    for fleet in config["fleets"]:
        sites = data.make_sites({**config["sites"], "n_gpus": int(fleet["n_gpus"])}, names)
        capacity = int(fleet["n_gpus"]) * SLOT_MINUTES * 60
        print(f"\n=== {fleet['name']} ({fleet['n_gpus']} GPUs/site)")

        rules: dict[str, list[dict]] = {}
        for rule in config["rules"]:
            rows = [
                run_rule(
                    _env_for(
                        series,
                        tokens,
                        sites,
                        names,
                        start,
                        config,
                        communicate=True,
                        include_band=True,
                        price=0.0,
                    ),
                    rule,
                )
                for start in held_out
            ]
            rules[rule] = rows
            print(
                f"  {rule:16s} carbon {np.mean([r['carbon_kg'] for r in rows]):8.1f} kg"
                f"  missed {np.mean([r['missed_fraction'] for r in rows]):.4f}"
            )

        # The bound, at the volume the *immediate* rule serves: every other
        # comparison is then a matched-service one.
        oracle_rows = []
        for start, now_row in zip(held_out, rules["run_now"], strict=True):
            env = _env_for(
                series,
                tokens,
                sites,
                names,
                start,
                config,
                communicate=False,
                include_band=False,
                price=0.0,
            )
            oracle_rows.append(_oracle(env, deadlines, capacity, now_row["served_gpu_s"]))
        print(
            f"  {'oracle':16s} carbon {np.mean([r['carbon_kg'] for r in oracle_rows]):8.1f} kg"
            f"  missed {np.mean([r['missed_fraction'] for r in oracle_rows]):.4f}"
        )

        prices = [float(p) for p in config["prices"]]
        learned: dict[str, Any] = {}
        for price in prices:
            for name, spec in VARIANTS.items():
                per_seed: list[dict[str, float]] = []
                per_seed_rows: list[list[dict]] = []
                for seed in config["seeds"]:

                    def factory(
                        episode: int,
                        _sites=sites,
                        _spec=spec,
                        _price=price,
                    ) -> QueueEnv:
                        index = episode * len(train_starts) // int(config["episodes"])
                        return _env_for(
                            series,
                            tokens,
                            _sites,
                            names,
                            train_starts[index],
                            config,
                            communicate=_spec["communicate"],
                            include_band=True,
                            price=_price,
                        )

                    probe = factory(0)
                    cvar_mode, alpha = spec["cvar"], config.get("cvar_alpha", 0.9)
                    actors, _critic, _history = train_multi(
                        factory,
                        n_agents=probe.n_agents,
                        obs_dim=probe.obs_dim,
                        n_actions=probe.n_actions,
                        global_state_dim=probe.global_state_dim,
                        centralized_critic=spec["centralized"],
                        episodes=int(config["episodes"]),
                        seed=int(seed),
                        hidden=int(config["hidden"]),
                        lr=float(config["lr"]),
                        gamma=float(config.get("gamma", 1.0)),
                        lam=float(config.get("lam", 0.95)),
                        cvar_alpha=alpha if cvar_mode else None,
                        cvar_weight=price if cvar_mode else 0.0,
                        cvar_mode=cvar_mode or "terminal",
                    )
                    rows = []
                    traces = []
                    for start in held_out:
                        env = _env_for(
                            series,
                            tokens,
                            sites,
                            names,
                            start,
                            config,
                            communicate=spec["communicate"],
                            include_band=True,
                            price=price,
                        )
                        summary, trace = _play(env, actors)
                        rows.append(summary)
                        traces.append(trace)
                    # One planner call per arm, at the volume the arm actually
                    # served: a matched-service bound, so serving less cannot be
                    # read as better timing. (The exact schedule costs ~2 s per
                    # call, hence the mean rather than 12 week-paired calls.)
                    own_bound = _oracle(
                        env,
                        deadlines,
                        capacity,
                        float(np.mean([r["served_gpu_s"] for r in rows])),
                    )["carbon_kg"]
                    per_seed_rows.append(rows)
                    per_seed.append(
                        {
                            "carbon_kg": float(np.mean([r["carbon_kg"] for r in rows])),
                            "missed_fraction": float(np.mean([r["missed_fraction"] for r in rows])),
                            "objective": float(np.mean([objective(r, price) for r in rows])),
                            "oracle_at_own_volume_kg": float(own_bound),
                            # Mean action index per agent (0 = serve now, the
                            # last index = hold to the last legal slot) and the
                            # share of slots each agent chose not to serve now.
                            "mean_coast_by_agent": [
                                round(float(v), 3) for v in np.mean(traces, axis=(0, 1))
                            ],
                            "hold_fraction_by_agent": [
                                round(float(v), 3)
                                for v in np.mean(
                                    [t > 0 for t in np.concatenate(traces, axis=0)], axis=0
                                )
                            ],
                        }
                    )
                learned[f"{name}@{price}"] = {
                    "variant": name,
                    "price": price,
                    "seeds": per_seed,
                    "carbon_kg": round(float(np.mean([s["carbon_kg"] for s in per_seed])), 3),
                    "missed_fraction": round(
                        float(np.mean([s["missed_fraction"] for s in per_seed])), 4
                    ),
                    "objective": round(float(np.mean([s["objective"] for s in per_seed])), 3),
                    "objective_spread": round(
                        float(
                            np.max([s["objective"] for s in per_seed])
                            - np.min([s["objective"] for s in per_seed])
                        ),
                        3,
                    ),
                    "paired_vs_run_now": _paired(per_seed_rows[0], rules["run_now"], "carbon_kg"),
                    # Carbon left on the table against the exact schedule at
                    # this arm's *own* service level. Small means the arm is
                    # near the timing optimum at the volume it chose.
                    "oracle_at_own_volume_kg": round(
                        float(np.mean([s["oracle_at_own_volume_kg"] for s in per_seed])), 3
                    ),
                    "gap_to_own_bound_pct": round(
                        (
                            float(np.mean([s["carbon_kg"] for s in per_seed]))
                            / float(np.mean([s["oracle_at_own_volume_kg"] for s in per_seed]))
                            - 1.0
                        )
                        * 100.0,
                        2,
                    ),
                    # Service is reported beside every saving, so a carbon cut
                    # cannot be read as a scheduling gain when it was bought by
                    # serving less work.
                    "mean_coast_by_agent": [
                        round(float(v), 3)
                        for v in np.mean([s["mean_coast_by_agent"] for s in per_seed], axis=0)
                    ],
                    "hold_fraction_by_agent": [
                        round(float(v), 3)
                        for v in np.mean([s["hold_fraction_by_agent"] for s in per_seed], axis=0)
                    ],
                    "missed_pp_vs_run_now": round(
                        (
                            float(np.mean([s["missed_fraction"] for s in per_seed]))
                            - float(np.mean([r["missed_fraction"] for r in rules["run_now"]]))
                        )
                        * 100.0,
                        2,
                    ),
                }
                entry = learned[f"{name}@{price}"]
                print(
                    f"  {name:18s} p={price:<4g} carbon {entry['carbon_kg']:8.1f} kg"
                    f"  missed {entry['missed_fraction']:.4f}"
                    f" ({entry['missed_pp_vs_run_now']:+.2f}pp)"
                    f"  obj {entry['objective']:8.1f} (spread {entry['objective_spread']:.1f})"
                    f"  vs bound {entry['gap_to_own_bound_pct']:+.2f}%"
                )

        baseline = float(np.mean([r["carbon_kg"] for r in rules["run_now"]]))
        bound = float(np.mean([r["carbon_kg"] for r in oracle_rows]))
        for entry in learned.values():
            captured = (
                (baseline - entry["carbon_kg"]) / (baseline - bound)
                if baseline - bound > 1e-9
                else 0.0
            )
            entry["share_of_bound_pct"] = round(float(captured) * 100.0, 2)

        results["fleets"][fleet["name"]] = {
            "n_gpus": int(fleet["n_gpus"]),
            "rules": {
                name: {
                    "carbon_kg": round(float(np.mean([r["carbon_kg"] for r in rows])), 3),
                    "missed_fraction": _mean(rows, "missed_fraction"),
                    "max_slot_violation_fraction": _mean(rows, "max_slot_violation_fraction"),
                    "cvar90_slot_violation_fraction": _mean(rows, "cvar90_slot_violation_fraction"),
                    "objective_at_price": {
                        str(p): round(float(np.mean([objective(r, p) for r in rows])), 3)
                        for p in [float(x) for x in config["prices"]]
                    },
                    "paired_vs_run_now": _paired(rows, rules["run_now"], "carbon_kg")
                    if name != "run_now"
                    else None,
                }
                for name, rows in rules.items()
            },
            "oracle": {
                "carbon_kg": round(bound, 3),
                "missed_fraction": _mean(oracle_rows, "missed_fraction"),
                "carbon_greedy_kg": round(baseline, 3),
                "available_pct": round((bound / baseline - 1.0) * 100.0, 3),
            },
            "learned": learned,
        }

    results["note"] = (
        "Every carbon number is relative to a policy on the identical demand, and "
        "the oracle is a perfect-foresight bound at matched served volume: it is "
        "not a policy, it is the ceiling a learner is measured against. The four "
        "work classes split the Azure arrivals equally because the trace has no "
        "latency labels -- a disclosed modelling choice, identical for every arm."
    )
    return results
