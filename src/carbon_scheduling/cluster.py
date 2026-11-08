"""Cluster energy model (Phase 2, slice 1).

Per the study plan (findings-and-plan.md, Build item 4): a linear
idle->peak power curve per GPU (NLR measured profiles, DOI
10.7799/3025227), a site PUE (Google industry priors), and

    energy = mean power over the slot x slot duration x PUE.

Demand maps to GPU-seconds through a per-GPU serving throughput
(`tokens_per_gpu_second`) applied to the slot token TOTALS (the exp006
stream already sums tokens over requests) -- a disclosed calibration
knob, not a measured constant. It scales utilization linearly and
cancels in relative comparisons (same value everywhere), per the
project's claims rule.

Offered load may exceed capacity: `utilization` is the raw ratio (can be
> 1) and a saturated site draws peak power -- capping is the physics;
queueing/deferral decisions belong to the simulator (slice 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SLOT_MINUTES = 30  # NESO half-hourly grid


@dataclass(frozen=True)
class Site:
    """A data-center site: homogeneous GPUs behind a PUE."""

    name: str
    n_gpus: int
    gpu_idle_w: float  # W per GPU at zero load (NLR idle)
    gpu_peak_w: float  # W per GPU at full load (NLR peak)
    pue: float  # site PUE (Google priors: ~1.1-1.2)
    tokens_per_gpu_second: float  # serving throughput (calibration knob)

    def __post_init__(self) -> None:
        if self.gpu_idle_w <= 0 or self.gpu_peak_w <= self.gpu_idle_w:
            raise ValueError("require 0 < idle < peak GPU power")
        if self.pue < 1.0:
            raise ValueError("PUE below 1.0 is unphysical")
        if self.n_gpus <= 0 or self.tokens_per_gpu_second <= 0:
            raise ValueError("n_gpus and tokens_per_gpu_second must be positive")


def slot_energy(
    demand_slots: list[dict[str, Any]],
    site: Site,
    slot_minutes: int = SLOT_MINUTES,
) -> list[dict[str, Any]]:
    """Energy for one site over a per-slot demand stream (from demand.py).

    Returns one row per demand slot, order preserved:

        {"from", "gpu_seconds", "utilization", "energy_kwh"}

    utilization = gpu-seconds demanded / gpu-seconds available (may be > 1);
    energy uses min(utilization, 1) at the power curve.
    """
    slot_hours = slot_minutes / 60
    gpu_seconds_available = site.n_gpus * slot_minutes * 60
    rows: list[dict[str, Any]] = []
    for slot in demand_slots:
        tokens = slot["context_tokens"] + slot["generated_tokens"]
        gpu_seconds = tokens / site.tokens_per_gpu_second
        utilization = gpu_seconds / gpu_seconds_available
        power_per_gpu_w = site.gpu_idle_w + (site.gpu_peak_w - site.gpu_idle_w) * min(
            utilization, 1.0
        )
        energy_kwh = site.n_gpus * power_per_gpu_w * site.pue * slot_hours / 1000
        rows.append(
            {
                "from": slot["from"],
                "gpu_seconds": gpu_seconds,
                "utilization": utilization,
                "energy_kwh": energy_kwh,
            }
        )
    return rows
