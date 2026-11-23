"""How much cheap capacity to hold back for the work that has not arrived yet.

The planner in ``rl/hybrid.py`` sees the arrivals that have happened and the
carbon forecast for the horizon; it cannot see the arrivals to come. A myopic
plan therefore fills a cheap slot with today's backlog and the work arriving *in*
that slot has nowhere legal to run. exp017 measured both sides of that: on the
slack fleet a 30% capacity reserve moved 854.6 kg / 3.4% missed to 784.0 kg /
3.4% missed, and on the capacity-bound fleet a 20% reserve moved 811.3 / 13.6% to
770.9 / 15.6%. So the reserve is a real knob and its size is a real decision.

This module makes that decision *calibrated* instead of fixed. A one-step
arrival predictor is scored against what actually arrived, and the reserve is the
split-conformal upper quantile of the error -- the same finite-sample-corrected
estimator the carbon bands use (``bands.conformal_quantile``), only one-sided
and in GPU-seconds rather than gCO2/kWh. That gives the reserve a coverage claim
the experiment can test on weeks it never calibrated on, which the carbon band
could never earn: under national scaling the carbon band cannot reorder a
decision, while this one changes the plan by construction.

Everything here is causal and deterministic: predictions at slot ``t`` use slots
strictly before ``t``, and no randomness is involved.
"""

from __future__ import annotations

import numpy as np

from carbon_scheduling.bands import conformal_quantile

__all__ = ["exceedance_quantile", "reserve_per_site_slot", "trailing_predicted"]


def trailing_predicted(demand: np.ndarray, window: int) -> np.ndarray:
    """One-step prediction of each slot from the mean of the ``window`` before it.

    Causal by construction: prediction ``t`` is the mean of ``demand[t-window:t]``.
    The first slot has no history, so its prediction is 0.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    demand = np.asarray(demand, dtype=np.float64)
    predicted = np.zeros_like(demand)
    for t in range(1, len(demand)):
        past = demand[max(0, t - window) : t]
        predicted[t] = float(past.mean())
    return predicted


def exceedance_quantile(demand: np.ndarray, window: int, level: float) -> float:
    """Upper ``level`` quantile of how much more arrives than the trailing mean.

    This is the quantity a reserve has to bound: not the noise amplitude but the
    *shortfall* between what the plan assumed and what showed up. Negative
    exceedances (a quieter slot than predicted) need no reserve, so they are
    dropped rather than clipped, which keeps the quantile's level honest.
    """
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1), got {level}")
    demand = np.asarray(demand, dtype=np.float64)
    predicted = trailing_predicted(demand, window)
    excess = demand - predicted
    positive = [float(e) for e in excess[1:] if e > 0.0]
    if not positive:
        return 0.0
    # conformal_quantile returns the (1 - alpha) order statistic, so a one-sided
    # upper bound at `level` is alpha = 1 - level.
    q = conformal_quantile(positive, 1.0 - level)
    return float(min(q, float(demand.max())))


def reserve_per_site_slot(
    quantile_gpu_s: float, *, n_sites: int, min_deadline: int, capacity: float
) -> float:
    """Turn a fleet-wide arrival excess into a per-site-per-slot reserve.

    The excess has to run inside the tightest deadline window, spread over the
    fleet, so the per-block share is ``q / (n_sites * min_deadline)``. That is
    deliberately conservative: it assumes the whole excess lands in one slot and
    must fit inside the shortest window. It is capped at the block's own capacity
    so an extreme quantile cannot reserve the entire fleet and starve the plan.
    """
    if n_sites < 1:
        raise ValueError(f"n_sites must be >= 1, got {n_sites}")
    if min_deadline < 1:
        raise ValueError(f"min_deadline must be >= 1, got {min_deadline}")
    share = max(0.0, float(quantile_gpu_s)) / (n_sites * min_deadline)
    return float(min(share, float(capacity)))
