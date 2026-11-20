"""Run one SustainCluster rule-based controller headless and emit JSON metrics.

Usage:
    python scripts/sustaincluster/run_baseline.py --checkout external/sustain-cluster \
        --strategy lowest_carbon --days 7 --seed 42 --out /tmp/lowest_carbon.json

Metrics come from ``envs/sustaindc/sustaindc_env.py`` (``__common__``) and the
cluster manager's ``transmission_cost_total_usd`` -- the same fields upstream's
Table-1 script aggregates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (  # noqa: E402
    add_checkout_to_path,
    build_env,
    checkout_commit,
    load_yaml,
    run_episode,
)

STRATEGIES = (
    "round_robin",
    "lowest_carbon",
    "lowest_price",
    "most_available",
    "least_pending",
    "lowest_utilization",
    "random",
    "local_only",
    "priority_order",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", required=True)
    ap.add_argument("--strategy", required=True, choices=STRATEGIES)
    ap.add_argument("--days", type=float, default=7.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--init-day-of-year", type=int, default=None)
    ap.add_argument("--sim-config", type=Path, default=None)
    ap.add_argument("--datacenters", type=Path, default=None)
    ap.add_argument("--reward-config", type=Path, default=None)
    args = ap.parse_args()

    checkout = Path(args.checkout).resolve()
    add_checkout_to_path(checkout)

    # RBCs never see env actions, but the env's own flags still come from
    # sim_config.yaml, exactly as upstream builds them for rule-based rows.
    sim_path = args.sim_config or (checkout / "configs" / "env" / "sim_config.yaml")
    sim = load_yaml(sim_path)["simulation"]

    env = build_env(
        checkout,
        strategy=args.strategy,
        days=args.days,
        single_action=bool(sim["single_action_mode"]),
        disable_defer=bool(sim["disable_defer_action"]),
        init_day_of_year=args.init_day_of_year,
        sim_config_path=args.sim_config,
        datacenters_path=args.datacenters,
        reward_config_path=args.reward_config,
    )
    metrics = run_episode(env, days=args.days, seed=args.seed, policy=None)

    result = {
        "sustaincluster_commit": checkout_commit(checkout),
        "controller": args.strategy,
        "kind": "rule_based",
        "seed": args.seed,
        "days": args.days,
        "init_day_of_year": args.init_day_of_year,
        "sim_config": str(args.sim_config) if args.sim_config else None,
        "datacenters": str(args.datacenters) if args.datacenters else None,
        "reward_config": str(args.reward_config) if args.reward_config else None,
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
