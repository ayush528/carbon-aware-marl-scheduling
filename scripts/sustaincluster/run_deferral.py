"""Run any controller with the shared deferral lever, and emit the same JSON.

Usage:
    python scripts/sustaincluster/run_deferral.py --checkout external/sustain-cluster \
        --strategy lowest_carbon --deferral myopic \
        --forecast-csv data/uk_regional_2024_tidy.csv \
        --national-json data/uk_national_2023-12_2024-12.json \
        --region-map GB-London=13,... --calibration-end 2024-01-08T00:00Z \
        --days 7 --seed 42 --init-day-of-year 14 --align-clock \
        --sim-config ... --datacenters ... --reward-config ... --out ...

``--strategy`` is either a published RBC name or ``planner_duration`` (ours,
injected into the same strategy map). ``--deferral`` selects the *shared* timing
policy, so every controller gets the identical lever and any difference in
outcome is attributable to the controller rather than to the harness.

Upstream source is untouched: the buffer wraps two methods on the cluster-manager
instance at runtime. See ``carbon_scheduling.sim.deferral`` for the two guarantees
(no task lost or duplicated; deferral never passes the last legal start).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from harness import (  # noqa: E402
    add_checkout_to_path,
    build_env,
    checkout_commit,
    run_episode,
)

from carbon_scheduling.sim.deferral import DeferralBuffer  # noqa: E402
from carbon_scheduling.sim.uk_planner import (  # noqa: E402
    DurationAwareStrategy,
    _hour,
    _parse_utc,
    calibrate_band,
    load_national,
    load_regional_forecast,
)

STRATEGY_NAME = "planner_duration"


def _parse_regions(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        slug, rid = item.split("=")
        out[slug.strip()] = int(rid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", required=True)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--deferral", default="none", choices=["none", "myopic", "reserve"])
    ap.add_argument("--reserve-fraction", type=float, default=0.0)
    ap.add_argument("--arrivals-per-slot", type=float, default=1.0)
    ap.add_argument("--max-horizon-slots", type=int, default=None)
    ap.add_argument("--sla-multiplier", type=float, default=None)
    ap.add_argument("--forecast-csv", required=True)
    ap.add_argument("--national-json", required=True)
    ap.add_argument("--region-map", required=True)
    ap.add_argument("--lam", type=float, default=0.0)
    ap.add_argument("--window-hours", type=float, default=None)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--calibration-end", required=True)
    ap.add_argument("--days", type=float, default=7.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--init-day-of-year", type=int, default=None)
    ap.add_argument("--sim-config", type=Path, default=None)
    ap.add_argument("--datacenters", type=Path, default=None)
    ap.add_argument("--reward-config", type=Path, default=None)
    ap.add_argument("--align-clock", action="store_true")
    args = ap.parse_args()

    checkout = Path(args.checkout).resolve()
    add_checkout_to_path(checkout)

    regions = _parse_regions(args.region_map)
    forecast = load_regional_forecast(args.forecast_csv, regions)
    national = load_national(args.national_json)
    q_national = calibrate_band(national, _parse_utc(args.calibration_end), args.alpha)

    strategy = None
    inject = None
    if args.strategy == STRATEGY_NAME:
        strategy = DurationAwareStrategy(
            forecast=forecast,
            national=national,
            q_national=q_national,
            lam=args.lam,
            window_hours=args.window_hours,
        )
        inject = (STRATEGY_NAME, strategy)

    env = build_env(
        checkout,
        strategy=args.strategy,
        days=args.days,
        single_action=False,
        disable_defer=False,
        init_day_of_year=args.init_day_of_year,
        sim_config_path=args.sim_config,
        datacenters_path=args.datacenters,
        reward_config_path=args.reward_config,
        seed=args.seed,
        align_clock=args.align_clock,
        inject_strategy=inject,
    )

    def best_intensity(stamp: datetime) -> float:
        """Lowest forecast intensity across sites at this hour (causal signal)."""
        hour = _hour(stamp)
        values = [series[hour] for series in forecast.values() if hour in series]
        return min(values) if values else math.inf

    # Optionally widen the declared SLA. Upstream hardcodes 1.5x duration in
    # rl_components/task.py (not a config key), which leaves ~38 minutes of slack
    # on a median 76-minute task -- barely two simulator steps. Widening it is a
    # disclosed benchmark modification applied *identically to every controller*,
    # so the lever's value can be measured as a function of available slack.
    if args.sla_multiplier is not None:
        original_get = env.cluster_manager.get_tasks_for_timestep

        def get_with_wider_sla(current_time):
            tasks = original_get(current_time)
            for task in tasks:
                task.sla_multiplier = args.sla_multiplier
                task.sla_deadline = task.arrival_time + timedelta(
                    minutes=args.sla_multiplier * float(task.duration)
                )
            return tasks

        env.cluster_manager.get_tasks_for_timestep = get_with_wider_sla

    buffer = DeferralBuffer(
        env.cluster_manager,
        intensity_at=best_intensity,
        policy=args.deferral,
        reserve_fraction=args.reserve_fraction,
        arrivals_per_slot=args.arrivals_per_slot,
        max_horizon_slots=args.max_horizon_slots,
    )
    buffer.install()

    metrics = run_episode(env, days=args.days, seed=args.seed, policy=None)
    stats = buffer.stats()

    result = {
        "sustaincluster_commit": checkout_commit(checkout),
        "controller": args.strategy,
        "deferral": args.deferral,
        "arm": (
            f"{args.strategy}__{args.deferral}"
            + (f"__sla{args.sla_multiplier:g}" if args.sla_multiplier is not None else "")
        ),
        "kind": "carbon_planner" if strategy is not None else "published_rbc",
        "lam": args.lam,
        "window_hours": args.window_hours,
        "alpha": args.alpha,
        "calibration_end": args.calibration_end,
        "q_national_gco2_per_kwh": round(q_national, 4),
        "forecast_fallbacks": strategy.fallbacks if strategy is not None else None,
        "reserve_fraction": args.reserve_fraction,
        "arrivals_per_slot": args.arrivals_per_slot,
        "max_horizon_slots": args.max_horizon_slots,
        "sla_multiplier": args.sla_multiplier,
        "seed": args.seed,
        "days": args.days,
        "init_day_of_year": args.init_day_of_year,
        "align_clock": args.align_clock,
        "deferral_stats": stats,
        **metrics.summary(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("arm", "carbon_kg", "energy_kwh", "sla_violation_rate", "tasks_finished")
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
