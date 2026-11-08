"""exp007 -- site energy envelope: real demand through the cluster model.

Streams the full Azure LLM trace (exp006 loader) through the cluster
energy model for one London-sized site, and records the energy envelope
the Phase 2 scheduler will optimize against: utilization distribution,
saturated slots, total/mean energy, energy per request.

Site spec (illustrative, disclosed -- relative claims only):
- NLR measured idle->peak per GPU: 4-GPU array 289-2851 W running
  Llama-3.1-70B (DOI 10.7799/3025227) -> 72 / 713 W per GPU.
- PUE 1.1 (Google industry priors).
- tokens_per_gpu_second = 1000: calibration knob, not measured. It scales
  the GPU fleet implied by a fixed utilization; all relative comparisons
  (site A vs site B under identical demand) cancel it.
- 100 GPUs: sized so mean utilization lands near 0.7 on this trace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from carbon_scheduling.cluster import Site, slot_energy
from carbon_scheduling.demand import requests_per_slot
from carbon_scheduling.runner import REPO_ROOT

SITE = Site(
    name="london-illustrative",
    n_gpus=100,
    gpu_idle_w=72.0,
    gpu_peak_w=713.0,
    pue=1.1,
    tokens_per_gpu_second=1000.0,
)


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {p.name: p for p in paths}

    demand = requests_per_slot(by_name["AzureLLMInferenceTrace_code_1week.csv"])
    rows = slot_energy(demand, SITE)

    n_requests = sum(s["requests"] for s in demand)
    utils = [r["utilization"] for r in rows]
    energies = [r["energy_kwh"] for r in rows]
    total_energy = sum(energies)
    n_saturated = sum(1 for u in utils if u >= 1.0)

    return {
        "site": SITE.name,
        "n_gpus": SITE.n_gpus,
        "n_slots": len(rows),
        "mean_utilization": round(sum(utils) / len(utils), 4),
        "peak_utilization": round(max(utils), 4),
        "n_saturated_slots": n_saturated,
        "total_energy_kwh": round(total_energy, 1),
        "mean_energy_kwh_per_slot": round(total_energy / len(rows), 2),
        "peak_energy_kwh_per_slot": round(max(energies), 2),
        "idle_energy_kwh_per_slot": round(SITE.n_gpus * SITE.gpu_idle_w * SITE.pue * 0.5 / 1000, 2),
        "wh_per_request": round(total_energy * 1000 / n_requests, 3),
    }
