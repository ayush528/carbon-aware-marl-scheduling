"""Arrival-rate transformations of a real workload, for disclosed comparisons.

The idle-floor share is a function of utilisation, not a constant of a
benchmark. exp028 varies the arrival rate by resampling real tasks per slot;
this module holds that transformation so it can be unit-tested without pandas
and without a simulator checkout. The CLI in
``scripts/sustaincluster/scale_workload.py`` adapts it to the upstream pickle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def scale_slots(slots: Sequence[Sequence[Any]], *, scale: float, seed: int) -> list[list[Any]]:
    """Resample each slot's real tasks to ``scale`` times its original count.

    * ``scale < 1`` samples without replacement (a subsample of real work);
    * ``scale > 1`` samples with replacement and appends a rename suffix, so
      duplicated tasks remain distinguishable in simulator logs;
    * an empty slot stays empty, and a slot with one task keeps at least one.

    Task fields are never invented: every returned task is one of the inputs.
    """
    if scale <= 0:
        raise ValueError("scale must be positive")
    rng = np.random.default_rng(seed)
    out: list[list[Any]] = []
    for tasks in slots:
        tasks = list(tasks)
        n = len(tasks)
        if n == 0:
            out.append([])
            continue
        target = max(1, int(round(n * scale)))
        if target == n:
            out.append(tasks)
        elif target < n:
            picks = rng.choice(n, size=target, replace=False)
            out.append([tasks[int(j)] for j in picks])
        else:
            chosen: list[Any] = []
            for k, j in enumerate(rng.integers(0, n, size=target)):
                task = tasks[int(j)]
                if isinstance(task, np.ndarray):
                    duplicate = task.copy()
                    duplicate[0] = f"{task[0]}_r{k}"
                else:
                    duplicate = list(task)
                    duplicate[0] = f"{task[0]}_r{k}"
                chosen.append(duplicate)
            out.append(chosen)
    return out
