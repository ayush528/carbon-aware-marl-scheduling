"""Tests for exp011's data plumbing (Phase 3, rung 4).

The experiment's claim is "calibrated uncertainty changes the schedule, and
here is what that costs or saves". Two things must therefore be exactly right
before any number means anything:

1. The realized intensity must be the documented national-scaling estimate,
   ``national_actual x regional_forecast / national_forecast``, and slots
   missing an input must be dropped, never guessed.
2. The calibration window must not overlap the evaluation week -- otherwise
   the band is fitted on the data it is judged on and the result is leakage.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from carbon_scheduling.experiments.exp011_band_dispatch import residuals, site_series

REGIONS = {"GB-London": 13, "GB-SouthWales": 7}


def national(rows: list[tuple[str, float | None, float | None]]) -> list[dict]:
    return [{"from": t, "forecast": f, "actual": a} for t, f, a in rows]


def regional(rows: list[tuple[str, int, float | None]]) -> list[dict]:
    return [{"from": t, "regionid": str(rid), "forecast": f} for t, rid, f in rows]


def test_realized_is_the_national_scaling_estimate() -> None:
    series = site_series(
        regional([("2024-05-10T00:00Z", 13, 100.0)]),
        national([("2024-05-10T00:00Z", 200.0, 300.0)]),
        {"GB-London": 13},
    )
    # 300 x 100 / 200 = 150
    assert series["GB-London"]["realized"][datetime(2024, 5, 10, 0)] == pytest.approx(150.0)
    assert series["GB-London"]["forecast"][datetime(2024, 5, 10, 0)] == pytest.approx(100.0)


def test_slots_without_a_national_actual_are_dropped_not_guessed() -> None:
    series = site_series(
        regional([("2024-05-10T00:00Z", 13, 100.0), ("2024-05-10T00:30Z", 13, 110.0)]),
        national(
            [
                ("2024-05-10T00:00Z", 200.0, None),
                ("2024-05-10T00:30Z", 200.0, 300.0),
            ]
        ),
        {"GB-London": 13},
    )
    realized = series["GB-London"]["realized"]
    assert len(realized) == 1
    assert datetime(2024, 5, 10, 0, 30) in realized
    # The forecast is still known for the dropped slot; only the realized value
    # is missing, and it is reported as missing rather than filled.
    assert len(series["GB-London"]["forecast"]) == 2


def test_rows_for_other_regions_are_ignored() -> None:
    series = site_series(
        regional([("2024-05-10T00:00Z", 99, 100.0)]),
        national([("2024-05-10T00:00Z", 200.0, 300.0)]),
        {"GB-London": 13},
    )
    assert series["GB-London"]["forecast"] == {}


def test_a_zero_regional_forecast_yields_a_zero_realized_value() -> None:
    """Zero forecast is a real value (a very clean grid hour), not a gap."""
    series = site_series(
        regional([("2024-05-10T00:00Z", 13, 0.0)]),
        national([("2024-05-10T00:00Z", 200.0, 300.0)]),
        {"GB-London": 13},
    )
    assert series["GB-London"]["forecast"][datetime(2024, 5, 10, 0)] == 0.0
    assert series["GB-London"]["realized"][datetime(2024, 5, 10, 0)] == 0.0


def test_residuals_ignore_the_evaluation_week() -> None:
    """Calibration must never see the slots it is judged on."""
    series = site_series(
        regional(
            [
                ("2024-05-09T23:30Z", 13, 100.0),  # last calibration slot
                ("2024-05-10T00:00Z", 13, 500.0),  # first evaluation slot
            ]
        ),
        national(
            [
                ("2024-05-09T23:30Z", 200.0, 240.0),
                ("2024-05-10T00:00Z", 200.0, 100.0),
            ]
        ),
        {"GB-London": 13},
    )
    absolute, levels, relative = residuals(series, datetime(2024, 4, 12), datetime(2024, 5, 10))
    # One slot only: |240*100/200 - 100| = |120 - 100| = 20
    assert absolute["GB-London"] == pytest.approx([20.0])
    assert levels["GB-London"] == pytest.approx([100.0])
    assert relative["GB-London"] == pytest.approx([0.2])


def test_residuals_skip_slots_where_the_forecast_is_zero() -> None:
    series = site_series(
        regional([("2024-05-10T00:00Z", 13, 0.0)]),
        national([("2024-05-10T00:00Z", 200.0, 300.0)]),
        {"GB-London": 13},
    )
    absolute, levels, relative = residuals(series, datetime(2024, 5, 9), datetime(2024, 5, 11))
    assert absolute["GB-London"] == []
    assert levels["GB-London"] == []
    assert relative["GB-London"] == []
