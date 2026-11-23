"""Build the small derived artifacts the scheduler replay needs.

The replay has to lay the Azure LLM demand week over a carbon week. Reading the
660 MB trace with ``carbon_scheduling.rl.data.demand_profile`` takes ~36 s; the
result is 336 token totals. This module writes those totals to a small committed
JSON artifact with the trace's SHA-256, taken from the exp017 run manifest, so
the API can prove the numbers came from the same trace the experiment ran on.

Run it once (and again only if the trace changes)::

    .venv/bin/python -m viz.backend.build_derived

The artifact is committed. The replay refuses it when its ``source_sha256`` no
longer matches the committed run record, and says so instead of using it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from carbon_scheduling.rl import data
from viz.backend import repo

EXP_ID = "exp017-hybrid-scheduler"
SOURCE = "docs/datasets/data-audit/downloads/AzureLLMInferenceTrace_code_1week.csv"
OUT = Path(__file__).parent / "derived" / "demand_tokens.json"


def source_sha256() -> str | None:
    """The trace hash recorded by the committed exp017 run, if there is one."""
    run = repo.latest_run(EXP_ID)
    if not run:
        return None
    return (run["manifest"].get("data_hashes") or {}).get(SOURCE)


def build() -> dict:
    config = repo.config(EXP_ID)
    paths = data.resolve(config["data"])
    n_slots = int(config["n_slots"])
    tokens = data.demand_profile(paths["demand"], n_slots)
    metrics = repo.latest_metrics("exp006-azure-trace-demand") or {}
    return {
        "kind": "azure_llm_tokens_per_slot",
        "what": (
            "Context + generated tokens offered in each half-hour slot of the "
            "one real Azure LLM trace week, laid on the NESO slot grid."
        ),
        "source": SOURCE,
        "source_sha256": source_sha256(),
        "n_slots": int(len(tokens)),
        "slot_minutes": 30,
        "exp_evidence": ["exp006-azure-trace-demand", EXP_ID],
        "validated_by": {
            "n_requests": metrics.get("n_requests"),
            "mean_requests_per_slot": metrics.get("mean_requests_per_slot"),
            "peak_requests_per_slot": metrics.get("peak_requests_per_slot"),
        },
        "produced_by": "python -m viz.backend.build_derived",
        "tokens": [round(float(value), 3) for value in tokens],
    }


def main() -> int:
    if not (repo.REPO_ROOT / SOURCE).is_file():
        print(
            f"missing {SOURCE}; re-fetch it with `make data-fetch TARGET=azure-llm`",
            file=sys.stderr,
        )
        return 2
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(repo.REPO_ROOT)} ({len(payload['tokens'])} slots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
