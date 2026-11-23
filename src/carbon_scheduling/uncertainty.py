"""Does a regional carbon series contain any information a band could act on?

The question is not statistical, it is structural. Almost every study of
spatial carbon-aware scheduling needs a realized intensity per region, and
almost none can get one: the regional APIs ship forecasts only. The usual
repair is to scale a national series by the regional forecast,

    realized_region(t) = national_actual(t) * forecast_region(t) / national_forecast(t)

which is what this project does too (NESO ships no regional actuals, verified in
exp003). Substituting into the definition of the forecast error shows the
consequence immediately:

    realized_region - forecast_region = forecast_region * (national_actual/national_forecast - 1)

The bracketed term is one number per slot, shared by every region. So the error
is a common per-slot factor, and the *ranking* of regions is exactly the
forecast's ranking no matter how wrong the national forecast was. Two things
follow, and they are theorems, not measurements:

* filling sites in forecast order is already the carbon optimum for that slot;
* any band that reorders the sites is reordering on noise, so it can only
  misprice. ``dispatch.absolute_half_widths`` can and does reorder, because a
  per-region conformal quantile is a functional of that region's whole forecast
  trajectory rather than a fixed multiple of its level -- but the reordering
  carries no information about realized intensity.

``classify`` is the diagnostic: run it on a dataset before trusting a
spatial-uncertainty result built on that dataset. ``REGIONAL`` is the only
answer under which a band has something to act on. A common *additive* offset
is equally uninformative, and it is worth detecting separately because it is
the failure mode of a level-shifted estimator rather than a scaled one.

The consequence for this project's own claim is stated in exp026 and is
deliberately narrow: the band cannot help *on data built this way*. It is not a
statement that forecast uncertainty is useless for carbon scheduling -- it is a
statement about which conclusions a scaled regional series can support.
"""

from __future__ import annotations

from collections.abc import Mapping

from carbon_scheduling import dispatch

COMMON_MULTIPLICATIVE = "common-multiplicative"
COMMON_ADDITIVE = "common-additive"
REGIONAL = "regional"


def classify(
    realized: Mapping[str, float],
    forecast: Mapping[str, float],
    *,
    rel_tol: float = 1e-9,
) -> str:
    """How ``realized`` relates to ``forecast`` across regions at one slot.

    ``COMMON_MULTIPLICATIVE`` -- every region shares one realized/forecast
    ratio (the national-scaling estimator). ``COMMON_ADDITIVE`` -- every region
    shares one offset. Both preserve the regional ordering, so neither leaves
    anything for a band to decide. ``REGIONAL`` -- neither holds, so the
    errors carry independent regional information.

    Needs at least two regions: with one region there is nothing to rank and
    the question is meaningless, so it raises rather than guessing.
    """
    if set(realized) != set(forecast):
        raise ValueError(
            f"region sets differ: realized={sorted(realized)} forecast={sorted(forecast)}"
        )
    if len(realized) < 2:
        raise ValueError("need at least two regions to speak of an ordering")
    if any(forecast[site] == 0 for site in forecast):
        raise ValueError("forecast must be non-zero to form a ratio")

    ratios = [realized[site] / forecast[site] for site in realized]
    if _spread(ratios) <= rel_tol * max(1.0, max(abs(r) for r in ratios)):
        return COMMON_MULTIPLICATIVE

    offsets = [realized[site] - forecast[site] for site in realized]
    if _spread(offsets) <= rel_tol * max(1.0, max(abs(o) for o in offsets)):
        return COMMON_ADDITIVE

    return REGIONAL


def reorders(realized: Mapping[str, float], forecast: Mapping[str, float]) -> bool:
    """True when the two series induce different site rankings.

    Ties are broken by name in ``dispatch.rank``, so two identical series never
    count as a reordering.
    """
    return dispatch.rank(realized) != dispatch.rank(forecast)


def _spread(values: list[float]) -> float:
    return max(values) - min(values)
