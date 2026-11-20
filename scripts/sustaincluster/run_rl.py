"""Evaluate a shipped SustainCluster SAC checkpoint headless and emit JSON.

Usage:
    python scripts/sustaincluster/run_rl.py --checkout external/sustain-cluster \
        --checkpoint external/sustain-cluster/checkpoints/<run>/best_eval_checkpoint.pth \
        --days 7 --seed 42 --device cuda --out /tmp/sac.json

The environment's ``single_action_mode`` / ``disable_defer_action`` are taken
from the checkpoint's own ``extra_info``, so the env always matches training.
Validation: for the multi-action + defer checkpoint over 7 days at seed 123
this reproduces upstream's printed transmission cost to the cent (3487.70 USD).
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
    greedy_policy,
    load_actor,
    run_episode,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--days", type=float, default=7.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    checkout = Path(args.checkout).resolve()
    add_checkout_to_path(checkout)

    actor, extra, ckpt_step, device = load_actor(checkout, Path(args.checkpoint), args.device)
    single_action = bool(extra.get("single_action_mode", False))
    disable_defer = bool(extra.get("disable_defer_action", False))

    env = build_env(
        checkout,
        strategy="manual_rl",
        days=args.days,
        single_action=single_action,
        disable_defer=disable_defer,
    )
    policy = greedy_policy(actor, single_action, device)
    metrics = run_episode(env, days=args.days, seed=args.seed, policy=policy)

    result = {
        "sustaincluster_commit": checkout_commit(checkout),
        "controller": "sac",
        "kind": "sac_checkpoint",
        "checkpoint": str(args.checkpoint),
        "checkpoint_step": ckpt_step,
        "single_action_mode": single_action,
        "disable_defer_action": disable_defer,
        "device": device,
        "seed": args.seed,
        "days": args.days,
        **metrics.summary(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "controller",
                    "checkpoint_step",
                    "device",
                    "days",
                    "carbon_kg",
                    "energy_kwh",
                    "sla_violation_rate",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
