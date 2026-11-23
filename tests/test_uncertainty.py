"""Can a calibrated band change a carbon decision? The structural claims, pinned.

The uncertainty argument rests on one fact about how regional carbon "ground
truth" is usually built. When every region's realized intensity is a common
per-slot rescaling of its own forecast -- which is exactly what the documented
national-scaling estimator produces -- then the *ranking* of regions is the
forecast's ranking, whatever the national forecast error was. Two consequences
follow, and both are theorems rather than findings:

1. Filling sites in forecast order is already carbon-optimal for that slot, so
   no band can lower the emissions of the dispatch;
2. A band can therefore only *misprice* -- it reorders on noise.

The boundary matters just as much: when regional errors are independent, the
ranking can genuinely differ, and only then does a band have something to act
on. ``classify`` is the diagnostic that tells the two cases apart, so a reader
can run it on any regional carbon dataset before trusting a spatial-uncertainty
result built on it.
"""

from __future__ import annotations

import csv
import itertools
import json

import pytest

from carbon_scheduling import dispatch
from carbon_scheduling.runner import REPO_ROOT
from carbon_scheduling.uncertainty import (
    COMMON_ADDITIVE,
    COMMON_MULTIPLICATIVE,
    REGIONAL,
    classify,
    reorders,
)

REGIONS = {"GB-London": 13, "GB-SouthWales": 7, "GB-NorthWestEngland": 3, "GB-SouthScotland": 2}

FORECAST = {"A": 50.0, "B": 60.0, "C": 200.0, "D": 210.0}


# --------------------------------------------------------------------------
# The diagnostic: what structure does the realized series have?
# --------------------------------------------------------------------------


def test_national_scaling_is_common_multiplicative() -> None:
    """One factor per slot, shared by every region -- the scaling estimator."""
    for factor in (0.8, 1.0, 1.37):
        realized = {s: v * factor for s, v in FORECAST.items()}
        assert classify(realized, FORECAST) == COMMON_MULTIPLICATIVE


def test_common_offset_is_common_additive() -> None:
    """One offset per slot, shared by every region -- also unable to reorder.

    A zero offset is excluded on purpose: realized == forecast is the
    multiplicative case with factor 1, and classifying it as multiplicative is
    the correct answer.
    """
    for offset in (-30.0, 12.5):
        realized = {s: v + offset for s, v in FORECAST.items()}
        assert classify(realized, FORECAST) == COMMON_ADDITIVE


def test_independent_regional_error_is_regional() -> None:
    """Genuinely regional errors are the only case with ranking information."""
    realized = {"A": 50.0 * 1.2, "B": 60.0 * 0.7, "C": 200.0 * 1.1, "D": 210.0 * 0.95}
    assert classify(realized, FORECAST) == REGIONAL


def test_common_structures_never_reorder_and_regional_ones_can() -> None:
    assert not reorders({s: v * 1.4 for s, v in FORECAST.items()}, FORECAST)
    assert not reorders({s: v - 20.0 for s, v in FORECAST.items()}, FORECAST)
    # A regional error that overtakes the cheapest two sites does reorder.
    flipped = {"A": 50.0 * 1.9, "B": 60.0 * 1.0, "C": 200.0, "D": 210.0}
    assert reorders(flipped, FORECAST)


def test_classify_needs_two_regions_and_matching_keys() -> None:
    with pytest.raises(ValueError):
        classify({"A": 1.0}, {"A": 1.0})
    with pytest.raises(ValueError):
        classify({"A": 1.0, "B": 2.0}, {"A": 1.0, "C": 2.0})


# --------------------------------------------------------------------------
# The theorem: forecast order is already carbon-optimal
# --------------------------------------------------------------------------


def _carbon(order, realized, demand, capacity) -> float:
    """Carbon of filling ``order`` greedily, in arbitrary but consistent units."""
    alloc, _ = dispatch.allocate(
        {site: float(rank) for rank, site in enumerate(order)}, demand, capacity
    )
    energy = {site: gpu_s / 3600.0 for site, gpu_s in alloc.items()}
    return dispatch.carbon_kg(energy, realized)


@pytest.mark.parametrize("factor", [0.7, 1.0, 1.45])
@pytest.mark.parametrize("demand", [10.0, 5_000.0, 40_000.0])
def test_forecast_greedy_is_optimal_under_a_common_factor(factor: float, demand: float) -> None:
    """No ordering of the sites beats forecast order, for any demand.

    This is the operational form of the theorem: with realized = forecast x a
    common factor, forecast order *is* realized order, and greedy fill is the
    optimum of the linear capacity problem. Checked exhaustively on 4 sites.
    """
    realized = {s: v * factor for s, v in FORECAST.items()}
    capacity = {s: 12_000.0 for s in FORECAST}
    best = min(
        _carbon(order, realized, demand, capacity)
        for order in itertools.permutations(sorted(FORECAST))
    )
    greedy = _carbon(sorted(FORECAST, key=lambda s: FORECAST[s]), realized, demand, capacity)
    assert greedy == pytest.approx(best, rel=1e-12)


@pytest.mark.parametrize("lam", [0.5, 1.0, 2.0, 4.0])
def test_a_band_that_reorders_cannot_help_under_a_common_factor(lam: float) -> None:
    """A band wide enough to reorder still cannot lower emissions -- it only misprices.

    The band here is deliberately perverse (it nearly erases B's and D's
    width), which is the worst case: it *does* reorder, and the theorem says
    the result cannot be an improvement. This is the check that turns exp011's
    "the band only costs carbon" observation into a guarantee.
    """
    realized = {s: v * 1.15 for s, v in FORECAST.items()}
    half_width = {"A": 30.0, "B": 1.0, "C": 40.0, "D": 1.0}
    capacity = {s: 12_000.0 for s in FORECAST}
    demand = 20_000.0

    banded = dispatch.risk_scores(FORECAST, half_width, lam)
    carbon_band = _carbon(dispatch.rank(banded), realized, demand, capacity)
    carbon_greedy = _carbon(sorted(FORECAST, key=lambda s: FORECAST[s]), realized, demand, capacity)
    assert carbon_band >= carbon_greedy - 1e-12


def test_band_ordering_is_the_whole_decision() -> None:
    """Sanity: the perverse band really does reorder, or the test above is vacuous."""
    banded = dispatch.risk_scores(FORECAST, {"A": 30.0, "B": 1.0, "C": 40.0, "D": 1.0}, 1.0)
    assert dispatch.rank(banded)[:2] == ["B", "A"]


# --------------------------------------------------------------------------
# The real series: the premise holds on the data the project actually uses
# --------------------------------------------------------------------------


def _real_slots() -> list[tuple[str, dict[str, float], dict[str, float]]]:
    """(stamp, forecast, realized) per complete slot from the committed 2024 NESO files."""
    regional_path = REPO_ROOT / "data" / "uk_regional_2024_tidy.csv"
    national_path = REPO_ROOT / "data" / "uk_national_2023-12_2024-12.json"
    if not regional_path.exists() or not national_path.exists():
        pytest.skip("2024 NESO files are not present")

    national: dict[str, tuple[float, float]] = {}
    for row in json.loads(national_path.read_text())["data"]:
        if row.get("forecast") is None or row.get("actual") is None:
            continue
        national[row["from"]] = (float(row["forecast"]), float(row["actual"]))

    wanted = {rid: slug for slug, rid in REGIONS.items()}
    per_slot: dict[str, dict[str, float]] = {}
    with regional_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            slug = wanted.get(int(row["regionid"]))
            if slug is None or row["forecast"] in (None, ""):
                continue
            per_slot.setdefault(row["from"], {})[slug] = float(row["forecast"])

    out = []
    for stamp in sorted(per_slot):
        forecast = per_slot[stamp]
        if len(forecast) != len(REGIONS):
            continue
        pair = national.get(stamp)
        if pair is None or pair[0] == 0:
            continue
        realized = {s: pair[1] * v / pair[0] for s, v in forecast.items()}
        out.append((stamp, forecast, realized))
    return out


def test_the_committed_series_is_the_scaling_estimator() -> None:
    """On real data: one shared factor per slot, so no regional information.

    This is a regression guard on the data pipeline as much as a theorem check.
    If a future change made ``realized`` independent per region -- for example
    by obtaining genuine regional actuals -- this test must fail, because the
    project's uncertainty conclusion would no longer hold and the paper would
    have to be rewritten.
    """
    slots = _real_slots()[:400]
    assert slots
    assert all(
        classify(realized, forecast) == COMMON_MULTIPLICATIVE for _, forecast, realized in slots
    )


def test_the_committed_series_never_reorders() -> None:
    slots = _real_slots()[:400]
    assert slots
    assert not any(reorders(realized, forecast) for _, forecast, realized in slots)


def _top_share(slots: list[tuple[str, dict[str, float], dict[str, float]]]) -> float:
    winners = [dispatch.rank(realized)[0] for _, _, realized in slots]
    return max(winners.count(site) for site in set(winners)) / len(winners)


def test_placement_saturation_is_a_window_property_not_a_year_property() -> None:
    """Pin both the exp023 number and the caveat that limits it.

    exp023 reports the cheapest region winning 162 of 168 hours. On the same
    window this series reproduces that (324 of 336 half-hour slots), so the
    published figure is sound. But across the whole of 2024 the winner takes
    only ~85% of slots and July falls to ~60%, so "placement is saturated" is a
    property of that benchmark window and not of the grid. Recording the second
    number here is what stops the first from being quoted without its scope.
    """
    slots = _real_slots()
    assert slots
    window = [s for s in slots if "2024-01-09T18:00" <= s[0] < "2024-01-16T18:00"]
    assert len(window) == 336
    assert _top_share(window) >= 0.95

    year_share = _top_share(slots)
    assert 0.80 <= year_share < 0.90

    by_month: dict[str, list[tuple[str, dict[str, float], dict[str, float]]]] = {}
    for slot in slots:
        by_month.setdefault(slot[0][:7], []).append(slot)
    monthly = {month: _top_share(rows) for month, rows in by_month.items() if len(rows) > 500}
    assert min(monthly.values()) < 0.70
    assert monthly["2024-07"] < 0.70
