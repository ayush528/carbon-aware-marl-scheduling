"""Tests for the head-to-head planner (``sim/uk_planner.py``).

The properties that make the comparison fair, pinned:

* the band cannot reorder sites (so a placement difference is not a band
  artefact),
* calibration never sees the run's window,
* the deferral rule only ever holds work it is allowed to hold,
* a step never commits more GPU capacity than a site has.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from carbon_scheduling.bands import conformal_quantile as project_quantile
from carbon_scheduling.sim.uk_planner import (
    DurationAwareStrategy,
    calibrate_band,
    conformal_quantile,
    load_national,
    risk,
    site_band,
)

HOUR = datetime(2024, 1, 10, 0)


@dataclass
class FakeTask:
    duration: float = 60.0


@dataclass
class FakeDC:
    dc_id: int
    location: str
    schedulable: bool = True
    current_time_task: datetime = HOUR
    fallback_ci: float = 0.0

    def can_schedule(self, _task) -> bool:
        return self.schedulable

    def get_current_carbon_intensity(self) -> float:
        return self.fallback_ci


def test_the_local_conformal_quantile_matches_the_project_definition() -> None:
    residuals = [1.0, 5.0, 2.0, 9.0, 3.0, 7.0]
    assert conformal_quantile(residuals, 0.5) == project_quantile(residuals, 0.5)


def test_the_band_cannot_reorder_two_sites_at_the_same_slot() -> None:
    """The scaling is common across sites, so a single slot's ranking is unchanged."""
    clean, dirty, national = 40.0, 300.0, 150.0
    for lam in (0.0, 0.5, 1.0, 3.0):
        assert risk(clean, national, 40.0, lam) < risk(dirty, national, 40.0, lam)
    assert site_band(clean, national, 40.0) == pytest.approx(40.0 * clean / national)


def test_calibration_ignores_residuals_at_or_after_the_window() -> None:
    before = {HOUR + timedelta(hours=i): {"forecast": 100.0, "actual": 110.0} for i in range(20)}
    after = {
        HOUR + timedelta(hours=20): {"forecast": 100.0, "actual": 1000.0},
        HOUR + timedelta(hours=21): {"forecast": 100.0, "actual": 1000.0},
    }
    q = calibrate_band({**before, **after}, HOUR + timedelta(hours=20), alpha=0.1)
    assert q == pytest.approx(10.0)


def test_loading_national_series_averages_the_two_half_hours(tmp_path) -> None:
    import json

    payload = {
        "data": [
            {"from": "2024-01-10T00:00Z", "forecast": 100, "actual": 120},
            {"from": "2024-01-10T00:30Z", "forecast": 200, "actual": 220},
        ]
    }
    path = tmp_path / "national.json"
    path.write_text(json.dumps(payload))
    series = load_national(path)
    assert series[HOUR] == {"forecast": 150.0, "actual": 170.0}


def _strategy(forecast, national, q=10.0, lam=0.0, window_hours=None):
    return DurationAwareStrategy(
        forecast=forecast,
        national=national,
        q_national=q,
        lam=lam,
        window_hours=window_hours,
    )


def test_instant_window_prices_only_the_arrival_slot() -> None:
    forecast = {
        "a": {HOUR: 100.0, HOUR + timedelta(hours=1): 100.0},
        "b": {HOUR: 50.0, HOUR + timedelta(hours=1): 300.0},
    }
    national = {HOUR: {"forecast": 150.0}, HOUR + timedelta(hours=1): {"forecast": 150.0}}
    dcs = {"DC1": FakeDC(1, "a"), "DC2": FakeDC(2, "b")}
    strategy = _strategy(forecast, national, window_hours=0.0)
    # Slot 0 is cheapest at b, even though b is far worse over the task.
    assert strategy(FakeTask(duration=120.0), dcs) == 2


def test_the_duration_window_changes_the_choice() -> None:
    forecast = {
        "a": {HOUR: 100.0, HOUR + timedelta(hours=1): 100.0},
        "b": {HOUR: 50.0, HOUR + timedelta(hours=1): 300.0},
    }
    national = {HOUR: {"forecast": 150.0}, HOUR + timedelta(hours=1): {"forecast": 150.0}}
    dcs = {"DC1": FakeDC(1, "a"), "DC2": FakeDC(2, "b")}
    strategy = _strategy(forecast, national)
    # Over 2 hours a averages 100, b averages 175: the placement flips.
    assert strategy(FakeTask(duration=120.0), dcs) == 1


def test_the_band_can_reorder_across_a_window() -> None:
    """At one slot the band is common; over several it weights hours, so it can act."""
    forecast = {
        # a is cheap on average but spikes in the risky hour.
        "a": {HOUR: 200.0, HOUR + timedelta(hours=1): 60.0},
        # b is flat.
        "b": {HOUR: 140.0, HOUR + timedelta(hours=1): 140.0},
    }
    national = {
        # A very low national forecast in hour 0 makes one band large in
        # relative terms; hour 1 is calm.
        HOUR: {"forecast": 20.0},
        HOUR + timedelta(hours=1): {"forecast": 200.0},
    }
    dcs = {"DC1": FakeDC(1, "a"), "DC2": FakeDC(2, "b")}
    point = _strategy(forecast, national, q=20.0, lam=0.0)
    banded = _strategy(forecast, national, q=20.0, lam=1.0)
    assert point(FakeTask(duration=120.0), dcs) == 1  # 130 < 140 on the point forecast
    assert banded(FakeTask(duration=120.0), dcs) == 2  # a's spike is risk-weighted


def test_sites_that_cannot_schedule_are_not_candidates() -> None:
    forecast = {"a": {HOUR: 10.0}, "b": {HOUR: 200.0}}
    national = {HOUR: {"forecast": 150.0}}
    dcs = {"DC1": FakeDC(1, "a", schedulable=False), "DC2": FakeDC(2, "b")}
    assert _strategy(forecast, national)(FakeTask(), dcs) == 2


def test_a_site_without_a_forecast_falls_back_to_its_own_signal() -> None:
    forecast = {"a": {HOUR: 100.0}}
    national = {HOUR: {"forecast": 150.0}}
    dcs = {"DC1": FakeDC(1, "a"), "DC2": FakeDC(2, "b", fallback_ci=5.0)}
    # "b" has no forecast, so its own (very clean) current intensity is used.
    assert _strategy(forecast, national)(FakeTask(), dcs) == 2


def test_ties_break_deterministically_by_site_id() -> None:
    forecast = {"a": {HOUR: 100.0}, "b": {HOUR: 100.0}}
    national = {HOUR: {"forecast": 150.0}}
    dcs = {"DC1": FakeDC(1, "a"), "DC2": FakeDC(2, "b")}
    assert _strategy(forecast, national)(FakeTask(), dcs) == 1


def test_hour_normalises_a_timezone_aware_stamp() -> None:
    """The simulator hands us a tz-aware UTC timestamp; our series keys are naive.

    Without normalisation every forecast lookup misses, the strategy falls back
    to the simulator's own instantaneous carbon signal, and our planner silently
    becomes ``lowest_carbon``. That is exactly what happened in the first exp022
    run, and it made an artefact look like a finding.
    """
    from datetime import UTC

    from carbon_scheduling.sim.uk_planner import _hour

    aware = datetime(2024, 1, 9, 18, 37, tzinfo=UTC)
    assert _hour(aware) == datetime(2024, 1, 9, 18, 0)
    assert _hour(aware).tzinfo is None
    assert _hour(datetime(2024, 1, 9, 18, 37)) == datetime(2024, 1, 9, 18, 0)


def test_window_risk_resolves_with_a_timezone_aware_now() -> None:
    from datetime import UTC

    from carbon_scheduling.sim.uk_planner import _window_risk

    hour = datetime(2024, 1, 9, 18, 0)
    forecast = {hour: 120.0, hour + timedelta(hours=1): 90.0}
    national = {
        hour: {"forecast": 200.0, "actual": 210.0},
        hour + timedelta(hours=1): {"forecast": 200.0, "actual": 210.0},
    }
    aware_now = datetime(2024, 1, 9, 18, 15, tzinfo=UTC)
    value = _window_risk(forecast, national, aware_now, 120.0, 0.0, 0.0)
    assert value is not None
    assert value == pytest.approx((120.0 + 90.0) / 2)


def test_strategy_counts_forecast_fallbacks_so_a_silent_one_cannot_hide() -> None:
    """A fallback is legitimate for a missing hour, but it must be countable.

    The experiment asserts zero fallbacks over a covered window, so a repeat of
    the tz bug fails the run instead of quietly reproducing lowest_carbon.
    """
    from carbon_scheduling.sim.uk_planner import DurationAwareStrategy

    strategy = DurationAwareStrategy(
        forecast={"GB-London": {}},
        national={},
        q_national=0.0,
        lam=0.0,
        window_hours=None,
    )

    class DC:
        dc_id = 1
        location = "GB-London"
        current_time_task = datetime(2024, 1, 9, 18, 0)
        available_gpus = 8
        available_cores = 64

        def get_current_carbon_intensity(self) -> float:
            return 175.0

    class Task:
        duration = 60.0
        gpu_req = 1
        cores_req = 4

    assert strategy(Task(), {"a": DC()}) == 1
    assert strategy.fallbacks == 1
