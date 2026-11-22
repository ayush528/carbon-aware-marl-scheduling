"""Dispatch core (Phase 3, rung 4): risk-adjusted site choice.

The scheduler's decision is a pure function of numbers we can test without the
external simulator:

    score(site) = forecast(site) + lam * half_width(site)     (gCO2/kWh)

then fill sites in ascending score order up to capacity. ``lam = 0`` is
forecast-greedy (the carbon-aware baseline); larger ``lam`` is more risk
averse, i.e. it prefers the site whose *worst plausible* intensity is lower.

Three properties matter for the paper and are pinned by tests:

* A band that is a fixed fraction of each site's forecast -- which is what a
  pooled relative conformal band gives -- multiplies every score by
  ``(1 + lam * q)`` and therefore cannot reorder the sites. The dispatch is
  identical to forecast-greedy. That is a theorem, not a finding, and it is
  why "add the band to the objective" is not by itself a contribution.
* A site-specific *absolute* band (conformal on absolute residuals *per
  region*) can reorder, because widths differ across regions: a low-carbon
  region with a wide band can lose to a higher-carbon but tighter one.
* Allocation is lossless: served + unserved equals demand.

Everything here is deterministic and stdlib-only (ADR-0002), so an experiment
that uses it is reproducible from its config alone.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from carbon_scheduling.bands import conformal_quantile


def risk_scores(
    forecast: Mapping[str, float],
    half_width: Mapping[str, float],
    lam: float,
) -> dict[str, float]:
    """Risk-adjusted score per site, ``forecast + lam * half_width``.

    Both mappings must describe exactly the same sites, and ``lam`` must be a
    finite non-negative number: a negative weight would *reward* uncertainty,
    which is not the policy under test.
    """
    if set(forecast) != set(half_width):
        raise ValueError(
            f"site sets differ: forecast={sorted(forecast)} band={sorted(half_width)}"
        )
    if not math.isfinite(lam) or lam < 0:
        raise ValueError(f"lam must be finite and >= 0, got {lam!r}")
    return {site: forecast[site] + lam * half_width[site] for site in forecast}


def rank(scores: Mapping[str, float]) -> list[str]:
    """Sites from cheapest to dearest; ties broken by name so runs repeat."""
    return sorted(scores, key=lambda site: (scores[site], site))


def allocate(
    scores: Mapping[str, float],
    demand_gpu_seconds: float,
    capacity_gpu_seconds: Mapping[str, float],
) -> tuple[dict[str, float], float]:
    """Fill sites in ascending score order, spilling when capacity binds.

    Returns ``(gpu_seconds_per_site, unserved_gpu_seconds)``. Sites that take
    no load are present with ``0.0`` so downstream accounting never has to
    guess. Unserved demand is the experiment's deadline-risk proxy: the model
    has no queue, so load a site cannot absorb is load that misses its slot.
    """
    if demand_gpu_seconds < 0 or not math.isfinite(demand_gpu_seconds):
        raise ValueError(f"demand must be finite and >= 0, got {demand_gpu_seconds!r}")
    if set(scores) != set(capacity_gpu_seconds):
        raise ValueError(
            f"site sets differ: scores={sorted(scores)} capacity={sorted(capacity_gpu_seconds)}"
        )

    remaining = float(demand_gpu_seconds)
    alloc = dict.fromkeys(scores, 0.0)
    for site in rank(scores):
        if remaining <= 0:
            break
        headroom = max(0.0, float(capacity_gpu_seconds[site]))
        take = min(remaining, headroom)
        alloc[site] = take
        remaining -= take
    return alloc, remaining


def carbon_kg(
    energy_kwh: Mapping[str, float],
    intensity_gco2_per_kwh: Mapping[str, float],
) -> float:
    """Emissions of a dispatch: sum of energy x intensity, in kilograms."""
    if set(energy_kwh) != set(intensity_gco2_per_kwh):
        raise ValueError(
            f"site sets differ: energy={sorted(energy_kwh)} "
            f"intensity={sorted(intensity_gco2_per_kwh)}"
        )
    grams = sum(energy_kwh[s] * intensity_gco2_per_kwh[s] for s in energy_kwh)
    return grams / 1000.0


def _check_bands(residuals: Mapping[str, list[float]]) -> None:
    if not residuals:
        raise ValueError("no residuals to calibrate on")
    for site, values in residuals.items():
        if not values:
            raise ValueError(f"site {site!r} has no residuals")
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"site {site!r} has a non-finite residual")


def absolute_half_widths(
    residuals: Mapping[str, list[float]],
    alpha: float,
) -> dict[str, float]:
    """Per-site absolute conformal half-width (gCO2/kWh).

    Calibrated on ``|actual - forecast|`` for that site alone, so the widths
    genuinely differ across regions -- which is what makes the band able to
    reorder sites (unlike a pooled relative band).
    """
    _check_bands(residuals)
    return {site: conformal_quantile(values, alpha) for site, values in residuals.items()}


def relative_half_widths(
    residuals: Mapping[str, list[float]],
    forecasts: Mapping[str, list[float]],
    alpha: float,
) -> dict[str, float]:
    """Per-site conformal quantile of ``|actual - forecast| / forecast``.

    Returns a *fraction* per site. Passing all sites' residual ratios under a
    single key pools them, which is the construction exp010 found best
    calibrated.
    """
    if set(residuals) != set(forecasts):
        raise ValueError(
            f"site sets differ: residuals={sorted(residuals)} forecasts={sorted(forecasts)}"
        )
    ratios: dict[str, list[float]] = {}
    for site, values in residuals.items():
        levels = forecasts[site]
        if not values or len(values) != len(levels):
            raise ValueError(
                f"site {site!r}: {len(values)} residuals vs {len(levels)} forecast levels"
            )
        if not all(math.isfinite(v) for v in list(values) + list(levels)):
            raise ValueError(f"site {site!r} has a non-finite value")
        if any(level == 0 for level in levels):
            raise ValueError(
                f"site {site!r} has a zero forecast; relative width is undefined there"
            )
        ratios[site] = [abs(value) / level for value, level in zip(values, levels, strict=True)]
    return {site: conformal_quantile(values, alpha) for site, values in ratios.items()}
