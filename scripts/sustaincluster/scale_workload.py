"""Resample a real SustainCluster workload pickle to a different arrival rate.

Why this exists
---------------
exp023 measured the idle-floor share at one operating point (four UK sites,
~7% utilisation, 88.7% of carbon untouchable). That number is often misread as
a property of the benchmark. It is not: the floor is fixed by the estate, so its
share falls as real work is added. exp028 reports the curve, and this tool makes
each point by resampling the *real* Alibaba 2020 task stream -- no synthetic
arrivals, no invented job shapes.

For scale < 1, tasks in each 15-minute slot are sampled without replacement;
for scale > 1 they are sampled with replacement and renamed. The per-slot
timestamps and the task fields are unchanged. A manifest records exactly what
was done so the point can be reproduced.

Usage (requires the checkout's python, which has pandas):
    .venv/bin/python scripts/sustaincluster/scale_workload.py \
        --checkout external/sustain-cluster --scale 2.0 --seed 42 \
        --out /tmp/workload_scale2.pkl --stats /tmp/workload_scale2.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from carbon_scheduling.sim.workload_scaling import scale_slots  # noqa: E402


def scale_frame(df: pd.DataFrame, scale: float, seed: int) -> pd.DataFrame:
    """Apply the tested slot resampler to an upstream workload DataFrame."""
    out = df.copy(deep=True)
    slots = scale_slots(list(df["tasks_matrix"]), scale=scale, seed=seed)
    for i, tasks in zip(df.index, slots, strict=True):
        out.at[i, "tasks_matrix"] = np.array(tasks, dtype=object)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", type=Path, required=True)
    ap.add_argument("--scale", type=float, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stats", type=Path, required=True)
    args = ap.parse_args()

    if args.scale <= 0:
        raise SystemExit("--scale must be positive")
    checkout = args.checkout.resolve()
    source = checkout / "data/workload/alibaba_2020_dataset/result_df_full_year_2020.pkl"
    if not source.is_file():
        raise SystemExit(f"missing real workload: {source}")

    original = pd.read_pickle(source)
    scaled = scale_frame(original, args.scale, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    scaled.to_pickle(args.out)

    before = [len(x) for x in original["tasks_matrix"]]
    after = [len(x) for x in scaled["tasks_matrix"]]
    stats = {
        "source": str(source.relative_to(checkout)),
        "scale": args.scale,
        "seed": args.seed,
        "slots": int(len(scaled)),
        "real_tasks": int(sum(before)),
        "scaled_tasks": int(sum(after)),
        "mean_tasks_per_slot": round(float(np.mean(after)), 3),
        "method": (
            "per-slot resampling of real Alibaba 2020 tasks; without replacement "
            "when scale < 1, with replacement and renamed when scale > 1"
        ),
    }
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True))
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
