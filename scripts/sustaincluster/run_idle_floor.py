"""Measure the carbon a controller cannot touch: the same sites, same week, no work.

Every published controller in this benchmark reports a percentage against another
controller, which says nothing about how much of the total was ever a decision.
This driver answers that directly: it runs the identical environment -- same four
UK sites, same jittered window, same carbon and price series, same HVAC and
server power model -- with the task stream switched off.

What remains is the idle draw of the estate: servers, cooling, pumps, fans. No
placement decision and no deferral decision can change it, so it is a hard lower
bound on the carbon any controller configuration can reach.

Usage:
    python scripts/sustaincluster/run_idle_floor.py --checkout external/sustain-cluster \
        --days 7 --seed 42 --init-day-of-year 14 --align-clock \
        --sim-config /tmp/sim.yaml --datacenters /tmp/dc.yaml --reward-config /tmp/rw.yaml \
        --out /tmp/floor.json
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", required=True)
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

    env = build_env(
        checkout,
        strategy="round_robin",
        days=args.days,
        single_action=True,
        disable_defer=True,
        init_day_of_year=args.init_day_of_year,
        sim_config_path=args.sim_config,
        datacenters_path=args.datacenters,
        reward_config_path=args.reward_config,
        seed=args.seed,
        align_clock=args.align_clock,
    )
    # ``get_tasks_for_timestep`` returns [] when the stream is absent, so this is
    # the same environment with no arrivals rather than a different one.
    env.cluster_manager.tasks = None

    metrics = run_episode(env, days=args.days, seed=args.seed, policy=None)
    result = {
        "sustaincluster_commit": checkout_commit(checkout),
        "controller": "idle_floor",
        "kind": "bound",
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
            {k: result[k] for k in ("controller", "days", "carbon_kg", "energy_kwh")},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
