"""exp006 -- Azure LLM trace demand stream, loader validation on real data.

Streams the full 1-week Azure LLM inference trace (16.8M requests, 692 MB,
gitignored -- refetchable via `make data-fetch`) through the demand loader
and records the per-half-hour demand shape: span, mean/peak arrivals per
slot, and token workload per request. This pins the loader against the real
file and gives the Phase 2 simulator its demand-input envelope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from carbon_scheduling.demand import requests_per_slot
from carbon_scheduling.runner import REPO_ROOT


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {p.name: p for p in paths}

    slots = requests_per_slot(by_name["AzureLLMInferenceTrace_code_1week.csv"])
    n_requests = sum(s["requests"] for s in slots)
    n_ctx = sum(s["context_tokens"] for s in slots)
    n_gen = sum(s["generated_tokens"] for s in slots)
    peak = max(slots, key=lambda s: s["requests"])

    return {
        "n_requests": n_requests,
        "n_slots": len(slots),
        "first_slot": slots[0]["from"],
        "last_slot": slots[-1]["from"],
        "mean_requests_per_slot": round(n_requests / len(slots), 1),
        "peak_requests_per_slot": peak["requests"],
        "peak_slot": peak["from"],
        "mean_context_tokens_per_request": round(n_ctx / n_requests, 1),
        "mean_generated_tokens_per_request": round(n_gen / n_requests, 1),
    }
