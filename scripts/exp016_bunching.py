"""Measure whether a timing rule piles work onto slots the fleet cannot serve.

Why this exists
---------------
The exp016 rules differ in what they know: `run_now` knows nothing, `last_slot`
knows each class's deadline, `forecast_timing` knows the whole forecast, and
`band_timing` knows the forecast and its calibrated band. More information is
not automatically better, and in exp016 `forecast_timing` is far *worse* than
`last_slot`. The mechanism is bunching: each agent independently picks the
cheapest slot for itself, the four classes then arrive in the same slot, the
fleet cannot serve them there, and the coordinator spills the excess to a
costlier site -- giving back the carbon the wait saved.

This prints, per rule, the mean work offered beyond the fleet's per-slot
capacity. It is a property of the rule alone (no learning, no seeds), so it is
deterministic and cheap.

Usage
-----
    .venv/bin/python scripts/exp016_bunching.py [exp016-queue-ownership]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carbon_scheduling.experiments.exp016_queue_ownership import _env_for  # noqa: E402
from carbon_scheduling.rl import data  # noqa: E402
from carbon_scheduling.rl.queue_rules import RULES  # noqa: E402


def main(exp_id: str = "exp016-queue-ownership") -> None:
    config = yaml.safe_load((Path("experiments") / exp_id / "config.yaml").read_text())
    paths = data.resolve(config["data"])
    series = data.panel(paths, config["regions"])
    names = list(config["regions"])
    tokens = data.demand_profile(paths["demand"], int(config["n_slots"]))
    weeks = data.weekly_windows(
        series,
        months=[int(m) for m in config["eval_months"]],
        year=int(config["year"]),
        n_slots=int(config["n_slots"]),
        calibration_days=int(config["calibration_days"]),
    )

    for fleet in config["fleets"]:
        sites = data.make_sites({**config["sites"], "n_gpus": int(fleet["n_gpus"])}, names)
        fleet_capacity = float(fleet["n_gpus"]) * 1800.0 * len(names)
        print(f"\n=== {fleet['name']} ({fleet['n_gpus']} GPUs/site, {len(weeks)} weeks)")
        print(f"{'rule':18s} {'excess GPU-s/slot':>18s} {'% of fleet capacity':>21s}")
        for rule in config["rules"]:
            excess, same = [], []
            for start in weeks:
                env = _env_for(
                    series,
                    tokens,
                    sites,
                    names,
                    start,
                    config,
                    communicate=True,
                    include_band=True,
                    price=0.0,
                )
                env.reset()
                while True:
                    actions = [int(RULES[rule](env, i)) for i in range(env.n_agents)]
                    waits = [env.wait_slots(i, a) for i, a in enumerate(actions)]
                    # Every agent holding the same non-zero amount is the
                    # bunching pattern in its purest form.
                    same.append(float(len(set(waits)) == 1 and waits[0] > 0))
                    _, _, done, _, info = env.step(actions)
                    excess.append(max(float(info["offered_gpu_s"]) - fleet_capacity, 0.0))
                    if done:
                        break
            print(
                f"{rule:18s} {np.mean(excess):18.0f} "
                f"{np.mean(excess) / fleet_capacity * 100:20.1f}%"
                f"   (all-agents-hold-alike in {np.mean(same) * 100:4.1f}% of slots)"
            )


if __name__ == "__main__":
    main(*sys.argv[1:])
