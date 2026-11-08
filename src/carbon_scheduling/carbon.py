"""Carbon-intensity data loading and summary statistics.

NESO (National Energy System Operator, GB) publishes half-hourly carbon
intensity at https://api.carbonintensity.org.uk (docs:
http://docs.carbonintensity.org.uk). Files follow the shape::

    {"data": [{"from": "...", "to": "...",
               "intensity": {"forecast": int, "actual": int | None, "index": str}}]}
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path


def load_neso_carbon(path: str | Path) -> list[dict]:
    """Load a NESO carbon-intensity JSON file into flat records."""
    raw = json.loads(Path(path).read_text())
    records = []
    for row in raw["data"]:
        intensity = row["intensity"]
        records.append(
            {
                "from": row["from"],
                "to": row["to"],
                # NESO omits a key entirely (rather than nulling it) when a
                # slot has no forecast/actual -- normalise to None.
                "forecast": intensity.get("forecast"),
                "actual": intensity.get("actual"),
                "index": intensity.get("index"),
            }
        )
    return records


def summarise(records: list[dict]) -> dict:
    """Deterministic descriptive statistics over loaded records.

    These numbers are the reference for Phase 1 (data freeze): any future
    re-pull of the same window must reproduce them.
    """
    actuals = [r["actual"] for r in records if r["actual"] is not None]
    forecasts = [r["forecast"] for r in records if r["forecast"] is not None]
    pairs = [
        (r["forecast"], r["actual"])
        for r in records
        if r["forecast"] is not None and r["actual"] is not None
    ]
    if not actuals:
        raise ValueError("no records with actual intensity")

    mae = sum(abs(f - a) for f, a in pairs) / len(pairs) if pairs else 0.0
    return {
        "n_slots": len(records),
        "n_actual": len(actuals),
        "actual_mean": round(statistics.fmean(actuals), 6),
        "actual_median": round(statistics.median(actuals), 6),
        "actual_stdev": round(statistics.stdev(actuals), 6) if len(actuals) > 1 else 0.0,
        "actual_min": min(actuals),
        "actual_max": max(actuals),
        "forecast_mean": round(statistics.fmean(forecasts), 6),
        "forecast_vs_actual_mae": round(mae, 6),
    }
