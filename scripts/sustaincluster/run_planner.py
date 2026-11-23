"""Run our carbon-aware planner inside SustainCluster and emit the same JSON.

Usage:
    python scripts/sustaincluster/run_planner.py --checkout external/sustain-cluster \
        --forecast-csv data/uk_regional_2024_tidy.csv \
        --national-json data/uk_national_2023-12_2024-12.json \
        --region-map GB-London=13,GB-SouthWales=7,... \
        --lam 1.0 --lookahead 4 --margin 0.15 --alpha 0.1 \
        --calibration-end 2024-01-08T00:00Z \
        --days 7 --seed 42 --init-day-of-year 14 --align-clock \
        --sim-config /tmp/sim.yaml --datacenters /tmp/dc.yaml --reward-config /tmp/rw.yaml \
        --out /tmp/planner.json

The action space is upstream's multi-action, defer-enabled one: one integer per
pending task, ``0`` = defer, ``1..N`` = route to that datacenter. Strategy is
``manual_rl`` because that is the only mode in which upstream hands the tasks to
the controller instead of its own rule.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from harness import (  # noqa: E402
    add_checkout_to_path,
    build_env,
    checkout_commit,
    run_episode,
)

from carbon_scheduling.sim.uk_planner import (  # noqa: E402
    DurationAwareStrategy,
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
    ap.add_argument("--forecast-csv", required=True)
    ap.add_argument("--national-json", required=True)
    ap.add_argument("--region-map", required=True)
    ap.add_argument("--lam", type=float, default=1.0)
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

    strategy = DurationAwareStrategy(
        forecast=forecast,
        national=national,
        q_national=q_national,
        lam=args.lam,
        window_hours=args.window_hours,
    )
    # Injected into the cluster manager's own strategy map, so tasks take the
    # identical assignment path as the published controllers.
    env = build_env(
        checkout,
        strategy=STRATEGY_NAME,
        days=args.days,
        single_action=False,
        disable_defer=False,
        init_day_of_year=args.init_day_of_year,
        sim_config_path=args.sim_config,
        datacenters_path=args.datacenters,
        reward_config_path=args.reward_config,
        seed=args.seed,
        align_clock=args.align_clock,
        inject_strategy=(STRATEGY_NAME, strategy),
    )
    metrics = run_episode(env, days=args.days, seed=args.seed, policy=None)

    result = {
        "sustaincluster_commit": checkout_commit(checkout),
        "controller": (
            "planner_instant" if args.window_hours == 0 else f"planner_window_lam{args.lam:g}"
        ),
        "kind": "carbon_planner",
        "lam": args.lam,
        "window_hours": args.window_hours,
        "alpha": args.alpha,
        "calibration_end": args.calibration_end,
        "q_national_gco2_per_kwh": round(q_national, 4),
        "seed": args.seed,
        "days": args.days,
        "init_day_of_year": args.init_day_of_year,
        "sim_config": str(args.sim_config) if args.sim_config else None,
        "datacenters": str(args.datacenters) if args.datacenters else None,
        "reward_config": str(args.reward_config) if args.reward_config else None,
        "align_clock": args.align_clock,
        **metrics.summary(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("controller", "days", "carbon_kg", "energy_kwh", "sla_violation_rate")
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
