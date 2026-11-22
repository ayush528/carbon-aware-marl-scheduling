"""Tests for Phase 3 episode assembly, baselines and exp012 aggregation.

These are the guarantees that make a Phase 3 number readable:

1. The band for an episode comes from the days *before* it, never from the
   episode itself (rolling origin, no leakage).
2. An episode's arrays are contiguous in time and cover every site -- a gap
   raises instead of shifting the window.
3. Baseline policies are deterministic and respect the deadline rule: the
   deferral rule never waits when the oldest task is one slot from its
   deadline.
4. Aggregation reports mean and standard error, not just a mean.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from carbon_scheduling.experiments.exp012_rl_dispatch import _aggregate, _relative
from carbon_scheduling.rl import baselines
from carbon_scheduling.rl.data import episode_arrays, week_band

REGIONS = {"GB-London": 13}


def series_from(rows: list[tuple[datetime, float, float]]) -> dict:
    return {
        "GB-London": {
            "forecast": {t: f for t, f, _ in rows},
            "realized": {t: r for t, _, r in rows},
        }
    }


def test_week_band_ignores_the_episode_week_itself() -> None:
    start = datetime(2024, 5, 10)
    cal = [start - timedelta(hours=h) for h in range(1, 24 * 28)]
    inside = [start + timedelta(hours=h) for h in range(0, 48)]
    rows = [(t, 100.0, 110.0) for t in cal] + [(t, 100.0, 900.0) for t in inside]
    band = week_band(series_from(rows), start, days=28)
    # Calibration error is 10 everywhere; the 800-g/kWh errors inside the week
    # must not reach the quantile.
    assert band["GB-London"] == pytest.approx(10.0)


def test_week_band_requires_calibration_data() -> None:
    start = datetime(2024, 5, 10)
    with pytest.raises(ValueError):
        week_band(series_from([(start, 100.0, 100.0)]), start, days=28)


def test_episode_arrays_are_contiguous_and_complete() -> None:
    start = datetime(2024, 5, 10)
    stamps = [start + timedelta(minutes=30 * i) for i in range(3)]
    series = series_from([(t, 100.0, 120.0) for t in stamps])
    tokens_in = np.array([1_000.0, 1_000.0, 1_000.0])
    forecast, realized, tokens = episode_arrays(series, tokens_in, start)
    assert forecast.shape == (3, 1)
    assert realized[0, 0] == 120.0
    assert tokens.sum() == 3_000.0


def test_episode_arrays_raise_on_a_gap_instead_of_shifting() -> None:
    start = datetime(2024, 5, 10)
    stamps = [start + timedelta(minutes=30 * i) for i in range(3)]
    series = series_from([(t, 100.0, 120.0) for t in stamps[:2]])
    with pytest.raises(ValueError):
        episode_arrays(series, np.ones(3), start)


def test_episode_length_comes_from_the_demand_profile() -> None:
    start = datetime(2024, 5, 10)
    stamps = [start + timedelta(minutes=30 * i) for i in range(3)]
    series = series_from([(t, 100.0, 120.0) for t in stamps])
    forecast, _, tokens = episode_arrays(series, np.ones(2), start)
    assert forecast.shape == (2, 1)
    assert tokens.shape == (2,)


class FakeEnv:
    """Minimal stand-in exposing the fields the baselines read."""

    def __init__(self, forecast, band, backlog, t=0):
        self.forecast = np.array([forecast], dtype=float)
        self.band = np.array([band], dtype=float)
        self.backlog = backlog
        self.t = t
        self.n_slots = 1
        self.n_sites = len(forecast)
        self.lam_grid = [0.0, 1.0]
        self.wait_action = len(self.lam_grid)

    def action_for_lam(self, lam: float) -> int:
        return int(np.argmin([abs(v - lam) for v in self.lam_grid]))


def test_run_now_uses_the_zero_risk_level() -> None:
    env = FakeEnv([200.0, 50.0, 120.0], [1.0, 1.0, 1.0], backlog=[])
    assert baselines.run_now(env) == 0


def test_band_aware_uses_the_risk_aware_level() -> None:
    """The rule's risk level is an action, so the agent can match it exactly."""
    env = FakeEnv([100.0, 120.0], [90.0, 1.0], backlog=[])
    assert baselines.band_aware(env, 0.0) == 0
    assert baselines.band_aware(env, 1.0) == 1


def test_deferral_never_waits_on_an_urgent_deadline() -> None:
    env = FakeEnv([300.0, 300.0], [1.0, 1.0], backlog=[(100.0, 1)])
    assert baselines.defer(env) != env.wait_action


def test_deferral_waits_when_a_cleaner_hour_is_ahead() -> None:
    env = FakeEnv([300.0, 300.0], [1.0, 1.0], backlog=[(100.0, 6)])
    env.forecast = np.array([[300.0, 300.0], [10.0, 10.0], [10.0, 10.0]])
    env.band = np.zeros_like(env.forecast)
    env.n_slots = 3
    assert baselines.defer(env, lookahead=3) == env.wait_action


class FakeJointEnv:
    """Two agents on a one-slot clock, for the joint rules."""

    def __init__(self, forecast, band, backlog, t=0, n_slots=1):
        self.forecast = np.atleast_2d(np.array(forecast, dtype=float))
        self.band = np.atleast_2d(np.array(band, dtype=float))
        self.backlog = backlog
        self.t = t
        self.n_slots = n_slots
        self.n_agents = self.forecast.shape[1]

    def encode(self, lam: float, offer: float) -> int:
        from carbon_scheduling.rl.marl_env import OFFERS

        lam_grid = (0.0, 0.5, 1.0, 2.0)
        return int(np.argmin([abs(v - lam) for v in lam_grid])) * len(OFFERS) + int(
            np.argmin([abs(v - offer) for v in OFFERS])
        )


def test_joint_run_now_offers_everything() -> None:
    env = FakeJointEnv([[100.0, 200.0]], [[1.0, 1.0]], backlog=[])
    actions = baselines.marl_run_now(env)
    assert len(actions) == 2
    assert all(env.encode(0.0, 1.0) == a for a in actions)


def test_joint_defer_declines_when_tomorrow_is_cleaner() -> None:
    env = FakeJointEnv(
        [[300.0, 300.0], [10.0, 10.0], [10.0, 10.0]],
        [[0.0, 0.0]] * 3,
        backlog=[(100.0, 6)],
        n_slots=3,
    )
    assert baselines.marl_defer(env, lookahead=3) == [env.encode(0.0, 0.0)] * 2


def test_joint_defer_never_waits_on_an_urgent_deadline() -> None:
    env = FakeJointEnv(
        [[300.0, 300.0], [10.0, 10.0]],
        [[0.0, 0.0]] * 2,
        backlog=[(100.0, 1)],
        n_slots=2,
    )
    assert baselines.marl_defer(env, lookahead=2) != [env.encode(0.0, 0.0)] * 2


def test_aggregate_reports_mean_and_stderr() -> None:
    rows = {
        "a": [
            {"carbon_kg": 1.0, "sla_violation_fraction": 0.1, "unserved_fraction": 0.2},
            {"carbon_kg": 3.0, "sla_violation_fraction": 0.3, "unserved_fraction": 0.4},
        ]
    }
    stats = _aggregate(rows)["a"]
    assert stats["carbon_kg"] == pytest.approx(2.0, abs=1e-4)
    assert stats["carbon_kg_stderr"] > 0


def test_relative_change_is_a_percentage() -> None:
    assert _relative(90.0, 100.0) == -10.0
    assert _relative(100.0, 0.0) == 0.0


def test_spread_reports_mean_and_seed_spread() -> None:
    from carbon_scheduling.experiments.exp014_marl_seeds import _spread

    stats = _spread([-1.0, -3.0, -2.0])
    assert stats["mean"] == pytest.approx(-2.0)
    assert stats["min"] == -3.0
    assert stats["max"] == -1.0
    assert stats["sd"] > 0
    assert _spread([1.5])["sd"] == 0.0
