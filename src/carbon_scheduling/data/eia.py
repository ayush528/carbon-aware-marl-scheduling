"""EIA-930 hourly generation by balancing authority → carbon intensity.

Why this reader exists: NESO ships no regional actuals, so every UK experiment
estimates realized intensity by scaling a national series, and exp026 proves
that construction leaves a calibrated band nothing to decide. EIA-930 is the
counter-example the theorem needs — per-region generation by fuel, measured
hourly, so the realized intensity of each balancing authority is computed from
its *own* mix rather than borrowed from a national one.

Source and licence
------------------
EIA-930 Hourly Grid Monitor bulk CSV (US Energy Information Administration),
public domain, no API key. The audited sample on disk covers Jan–Jun 2024 for
61 balancing authorities (``docs/datasets/DATASETS.md``).

Emission factors
----------------
Published EIA averages, pounds of CO₂ per kWh of generation, from the EIA FAQ
"How much carbon dioxide is produced per kilowatthour of U.S. electricity
generation?" (eia.gov/tools/faqs/faq.php?id=74&t=11):

    coal 2.31 · natural gas 0.96 · petroleum 2.46

Nuclear, hydro, wind and solar are zero, which is also eGRID's stated
methodology. These are *national average* factors applied to each authority's
real fuel mix: the mix is measured, the factor is a disclosed modelling
assumption. What matters for the ranking question is that the mix varies by
region and by hour, and it does.

What is dropped, and why
------------------------
An hour is priced only when its fuel breakdown accounts for the reported net
generation within ``tolerance`` (default 0.5%, which is integer-rounding noise:
the audited sample's median mismatch is 0.004%). Hours with a larger gap, with
non-positive net generation, or with any *unknown* fuel are dropped and counted,
never imputed. Two authorities (PJM, NYIS) fail this gate structurally and are
excluded by it rather than by hand.

Disclosures carried by anything built on this reader
----------------------------------------------------
* Intensity is generation-weighted *own* generation. Interchange (imports and
  exports) is not attributed, so an authority importing clean power looks
  dirtier than its consumption would.
* "Other Fuel Sources" is priced at zero. Its share is reported per authority so
  a reader can see how much that assumption is worth; the site set used by
  exp027 keeps it near zero.
* Operational CO₂ only — no upstream fuel-cycle or embodied emissions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

LB_TO_G = 453.59237

#: Fuel labels exactly as they appear in the EIA-930 column suffixes.
FUELS = [
    "Coal",
    "Natural Gas",
    "Nuclear",
    "All Petroleum Products",
    "Hydropower and Pumped Storage",
    "Solar",
    "Wind",
    "Other Fuel Sources",
    "Unknown Fuel Sources",
]

#: gCO2/kWh. EIA published averages; zero for non-combustion and for "Other"
#: (disclosed above, and its share is reported so the assumption is visible).
FACTORS_G_PER_KWH: dict[str, float] = {
    "Coal": 2.31 * LB_TO_G,
    "Natural Gas": 0.96 * LB_TO_G,
    "Nuclear": 0.0,
    "All Petroleum Products": 2.46 * LB_TO_G,
    "Hydropower and Pumped Storage": 0.0,
    "Solar": 0.0,
    "Wind": 0.0,
    "Other Fuel Sources": 0.0,
    "Unknown Fuel Sources": 0.0,
}


def _num(value: Any) -> float:
    """EIA writes an empty field for a fuel with no generation: that is zero."""
    if value in (None, "", "-"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def slot_start(row: Mapping[str, Any]) -> datetime:
    """UTC start of the hour. EIA stamps the *end* of the hour, so subtract one."""
    end = datetime.strptime(row["UTC Time at End of Hour"], "%m/%d/%Y %I:%M:%S %p")
    return end - timedelta(hours=1)


def fuel_generation(row: Mapping[str, Any]) -> dict[str, float]:
    """Net generation (MW) per fuel for one authority-hour."""
    return {fuel: _num(row.get(f"Net Generation (MW) from {fuel}")) for fuel in FUELS}


def intensity(row: Mapping[str, Any], *, tolerance: float = 0.005) -> float | None:
    """gCO2/kWh for one authority-hour, or None when it cannot be priced.

    None means "do not use this hour": the mix does not account for the reported
    generation, the generation is non-positive, or some of it is of unknown
    fuel. Returning None rather than a guess is the point — a partial mix would
    silently understate intensity.
    """
    net = _num(row.get("Net Generation (MW)"))
    if net <= 0:
        return None
    generation = fuel_generation(row)
    if generation["Unknown Fuel Sources"] > 0:
        return None
    total = sum(generation.values())
    if abs(total - net) / net > tolerance:
        return None
    return sum(generation[fuel] * FACTORS_G_PER_KWH[fuel] for fuel in FUELS) / net


def intensity_series(
    rows: Iterable[Mapping[str, Any]],
    *,
    tolerance: float = 0.005,
) -> tuple[dict[str, dict[datetime, float]], dict[str, dict[str, int]]]:
    """Per-authority hourly intensity, plus per-authority usable/dropped counts.

    The counts are returned rather than logged so an experiment can report how
    much of the grid it actually priced, and a reader can see the gate biting.
    """
    series: dict[str, dict[datetime, float]] = {}
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        authority = row["Balancing Authority"]
        counts = stats.setdefault(authority, {"total": 0, "usable": 0, "dropped": 0})
        counts["total"] += 1
        value = intensity(row, tolerance=tolerance)
        if value is None:
            counts["dropped"] += 1
            continue
        counts["usable"] += 1
        series.setdefault(authority, {})[slot_start(row)] = value
    return series, stats
