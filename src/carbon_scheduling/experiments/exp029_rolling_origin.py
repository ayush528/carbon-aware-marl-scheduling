"""exp029 — full-year rolling-origin evaluation of the shipped scheduler.

exp020 selected one arm from six using Jan-Sep and reported it on 12 held-out
weeks. That is honest, but a reviewer can still ask two questions: was the
choice stable through the year, and does the headline depend on where the train
/ test boundary was drawn? This experiment answers both.

For every week t after an eight-week warm-up:

1. score all six candidate arms on weeks 0..t-1 **only** (expanding window);
2. pick the arm with the lowest mean objective at each price and fleet;
3. run that arm on week t and record what it actually did.

No week ever selects its own arm. Carbon bands are calibrated on the 28 days
before each week (``data.week_band``), and the arrival reserve uses the same
causal quantile as exp018-021. The selection map is therefore rebuilt from
scratch as the year advances, and the reported curve is a genuine rolling
origin rather than one lucky split.

Also reported: the per-week oracle (best arm selected with knowledge of that
week) so the cost of causal selection is visible, and the number of weeks each
arm was chosen, so a one-week fluke cannot carry the result.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from carbon_scheduling.bands import conformal_quantile
from carbon_scheduling.experiments.exp013_marl_dispatch import _paired
from carbon_scheduling.experiments.exp018_arrival_reserve import (
    _mean_bound,
    _objective,
    calibrate,
)
from carbon_scheduling.experiments.exp020_selected_scheduler import (
    _candidates,
    _run_arm,
)
from carbon_scheduling.rl import data
from carbon_scheduling.rl.arrival_risk import reserve_per_site_slot

SLOT_MINUTES = 30


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    n_slots = int(config["n_slots"])
    tokens = data.demand_profile(paths["demand"], n_slots)
    weeks = data.weekly_windows(
        series,
        months=[int(m) for m in config["months"]],
        year=int(config["year"]),
        n_slots=n_slots,
        calibration_days=int(config["calibration_days"]),
    )
    prices = [float(p) for p in config["prices"]]
    deadlines = [int(d) for d in config["deadlines"]]
    window = int(config["arrival_window"])
    level = float(config["arrival_level"])
    warm = int(config["min_train_weeks"])
    if len(weeks) <= warm:
        raise RuntimeError(f"need more than {warm} weeks, got {len(weeks)}")

    throughput = float(config["sites"]["tokens_per_gpu_second"])
    calibration = calibrate(tokens / throughput, level, window)
    results: dict[str, Any] = {
        "all_weeks": [f"{s:%Y-%m-%d}" for s in weeks],
        "n_weeks_total": len(weeks),
        "n_rolling_evaluations": len(weeks) - warm,
        "min_train_weeks": warm,
        "prices": prices,
        "calibration": {str(k): v for k, v in calibration.items()},
        "fleets": {},
        "note": (
            "Selection at week t uses weeks 0..t-1 only. The 28-day carbon band and "
            "the arrival reserve are causal within each week. Demand is the single "
            "real Azure week (disclosed; exp031 tests shape sensitivity). The "
            "one-sided conformal lower bound on next week's saving is "
            "distribution-free given exchangeable weeks; carbon seasonality "
            "makes that approximate, so the bound is reported beside the mean, "
            "not as a guarantee."
        ),
    }

    for fleet in config["fleets"]:
        n_gpus = int(fleet["n_gpus"])
        sites = data.make_sites({**config["sites"], "n_gpus": n_gpus}, names)
        capacity = n_gpus * SLOT_MINUTES * 60
        reserve = reserve_per_site_slot(
            calibration["quantile_gpu_s"],
            n_sites=len(names),
            min_deadline=min(deadlines),
            capacity=capacity,
        )
        candidates = _candidates(reserve, window)

        rows: dict[str, list[dict[str, float]]] = {}
        for label, spec in candidates.items():
            rows[label] = _run_arm(spec, weeks, series, tokens, sites, names, config)
        print(f"{fleet['name']}: ran {len(candidates)} arms on {len(weeks)} weeks")

        by_price: dict[str, Any] = {}
        for p in prices:
            scores = {
                label: np.array([_objective(r, p) for r in arm_rows])
                for label, arm_rows in rows.items()
            }
            picks: list[str] = []
            picked_rows: list[dict[str, float]] = []
            oracle_rows: list[dict[str, float]] = []
            for t in range(warm, len(weeks)):
                means = {label: float(np.mean(score[:t])) for label, score in scores.items()}
                chosen = min(means, key=lambda label: means[label])
                oracle = min(scores, key=lambda label: float(scores[label][t]))
                picks.append(chosen)
                picked_rows.append(rows[chosen][t])
                oracle_rows.append(rows[oracle][t])

            baseline = rows["run_now"][warm:]
            counts = {label: picks.count(label) for label in candidates if picks.count(label)}
            by_price[str(p)] = {
                "selected_arm_counts": counts,
                "chosen_objective": round(
                    float(np.mean([_objective(r, p) for r in picked_rows])), 3
                ),
                "run_now_objective": round(float(np.mean([_objective(r, p) for r in baseline])), 3),
                "oracle_per_week_objective": round(
                    float(np.mean([_objective(r, p) for r in oracle_rows])), 3
                ),
                "objective_vs_run_now_pct": round(
                    (
                        np.mean([_objective(r, p) for r in picked_rows])
                        / np.mean([_objective(r, p) for r in baseline])
                        - 1.0
                    )
                    * 100.0,
                    3,
                ),
                "cost_of_causal_selection_vs_oracle_pct": round(
                    (
                        np.mean([_objective(r, p) for r in picked_rows])
                        / np.mean([_objective(r, p) for r in oracle_rows])
                        - 1.0
                    )
                    * 100.0,
                    3,
                ),
                "carbon_kg": round(float(np.mean([r["carbon_kg"] for r in picked_rows])), 3),
                "run_now_carbon_kg": round(float(np.mean([r["carbon_kg"] for r in baseline])), 3),
                "carbon_vs_run_now_pct": round(
                    (
                        np.mean([r["carbon_kg"] for r in picked_rows])
                        / np.mean([r["carbon_kg"] for r in baseline])
                        - 1.0
                    )
                    * 100.0,
                    3,
                ),
                # Risk-qualified headline. A one-sided split-conformal bound on
                # the *per-week* paired saving: with n rolling weeks, the
                # (1-alpha) order statistic of -saving is a distribution-free
                # upper bound on next week's loss, hence this lower bound on
                # next week's saving. It needs no exchangeability beyond the
                # weeks already used and is reported beside the mean, not
                # instead of it.
                "saving_lower_bound_alpha": float(config.get("risk_alpha", 0.1)),
                "weekly_saving_pct": [
                    round(
                        (b["carbon_kg"] - a["carbon_kg"]) / b["carbon_kg"] * 100.0,
                        3,
                    )
                    for a, b in zip(picked_rows, baseline, strict=True)
                ],
                "saving_lower_bound_pct": round(
                    -conformal_quantile(
                        [
                            -(b["carbon_kg"] - a["carbon_kg"]) / b["carbon_kg"] * 100.0
                            for a, b in zip(picked_rows, baseline, strict=True)
                        ],
                        float(config.get("risk_alpha", 0.1)),
                    ),
                    3,
                ),
                "missed_fraction": round(
                    float(np.mean([r["missed_fraction"] for r in picked_rows])), 4
                ),
                "run_now_missed_fraction": round(
                    float(np.mean([r["missed_fraction"] for r in baseline])), 4
                ),
                "paired_vs_run_now": _paired(picked_rows, baseline),
                "bound_at_own_volume_kg": round(
                    _mean_bound(
                        series,
                        tokens,
                        sites,
                        names,
                        config,
                        weeks[warm:],
                        deadlines,
                        capacity,
                        picked_rows,
                    ),
                    3,
                ),
                "weekly_picks": [
                    f"{weeks[t]:%Y-%m-%d}:{picks[t - warm]}" for t in range(warm, len(weeks))
                ],
            }
        results["fleets"][str(fleet["name"])] = by_price
        for p in prices:
            entry = by_price[str(p)]
            print(
                f"  price {p:g}: objective {entry['objective_vs_run_now_pct']:+.2f}% vs run_now, "
                f"carbon {entry['carbon_vs_run_now_pct']:+.2f}%, "
                f"cost of causality {entry['cost_of_causal_selection_vs_oracle_pct']:+.2f}%, "
                f"picks {entry['selected_arm_counts']}"
            )
    return results
