"""Tests for exp010's rolling-origin calibration (synthetic data, no network)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from carbon_scheduling.data.neso import write_tidy_csv
from carbon_scheduling.experiments import exp010_rolling_bands as exp010

YEAR = 2024
START = datetime(2023, 12, 1)
END = datetime(2025, 1, 1)


def _stamp(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%MZ")


def _relative_error(index: int) -> float:
    """Deterministic uniform error on [0.02, 0.10) -- interior quantiles only.

    A two-point (good/bad) distribution puts the 90th percentile exactly on the
    boundary, where the finite-sample correction makes the band conservative and
    coverage jumps to 100%. Uniform error keeps the quantile interior, which is
    what real forecast error looks like.
    """
    return 0.02 + 0.08 * ((index % 100) / 100)


def _write_national(path: Path) -> None:
    rows: list[dict[str, Any]] = []
    slot = START
    index = 0
    while slot < END:
        forecast = 200
        # Alternate the error sign so it is an error, not a bias; NESO actuals
        # are ints, so keep the values integral.
        signed = _relative_error(index) * (1 if index % 2 else -1)
        rows.append(
            {
                "from": _stamp(slot),
                "to": _stamp(slot + timedelta(minutes=30)),
                "forecast": forecast,
                "actual": round(forecast * (1 + signed)),
                "index": "low",
            }
        )
        slot += timedelta(minutes=30)
        index += 1
    path.write_text(__import__("json").dumps({"data": rows}))


def _write_regional(path: Path, levels: dict[int, int]) -> None:
    rows: list[dict[str, Any]] = []
    for regionid, level in levels.items():
        slot = START
        while slot < END:
            rows.append(
                {
                    "from": _stamp(slot),
                    "to": _stamp(slot + timedelta(minutes=30)),
                    "regionid": regionid,
                    "shortname": f"R{regionid}",
                    "forecast": level,
                    "actual": "",  # NESO ships none; the estimator supplies it
                    "index": "low",
                }
            )
            slot += timedelta(minutes=30)
    write_tidy_csv(rows, path)


@pytest.fixture
def config(tmp_path: Path) -> dict[str, Any]:
    national = tmp_path / "uk_national_2023-12_2025-01.json"
    regional = tmp_path / "uk_regional_2024_tidy.csv"
    _write_national(national)
    # The four simulator sites, deliberately close together: a point estimate
    # would still move work between them (ratio 0.90 < 1) while a banded rule
    # would not. That is the case the migration metric has to detect.
    _write_regional(regional, {13: 210, 7: 222, 3: 205, 2: 200})
    return {
        "id": "exp010-test",
        "year": YEAR,
        "data": [str(national), str(regional)],
    }


def test_month_bounds_wrap_the_year() -> None:
    assert exp010._month_bounds(2024, 12) == (datetime(2024, 12, 1), datetime(2025, 1, 1))
    assert exp010._month_bounds(2024, 1) == (datetime(2024, 1, 1), datetime(2024, 2, 1))


def test_window_helpers_slice_half_open() -> None:
    records = [
        {"from": "2024-01-01T00:00Z", "forecast": 1, "actual": 1},
        {"from": "2024-01-01T00:30Z", "forecast": 2, "actual": 2},
        {"from": "2024-01-01T01:00Z", "forecast": 3, "actual": 3},
    ]
    index = exp010._index(records)
    got = exp010._slice(index, datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 1, 0))
    assert [r["forecast"] for r in got] == [1, 2]


def test_cells_cover_every_region_and_month(config: dict[str, Any]) -> None:
    metrics = exp010.run(config)
    assert metrics["n_regions"] == 4
    assert metrics["n_cells"] == 4 * 12
    assert {c["month"] for c in metrics["cells"]} == set(range(1, 13))


def test_calibration_never_sees_its_evaluation_month(config: dict[str, Any]) -> None:
    metrics = exp010.run(config)
    for cell in metrics["cells"]:
        calib_start = datetime.fromisoformat(
            metrics["decision_relevance"]["by_month"][str(cell["month"])][
                "calibration_start_utc"
            ].replace("Z", "")
        )
        eval_start = datetime(YEAR, cell["month"], 1)
        assert calib_start == eval_start - timedelta(days=exp010.CALIB_DAYS)
        assert calib_start < eval_start


def test_coverage_is_identical_across_regions_within_a_month(config: dict[str, Any]) -> None:
    """Under national scaling every region shares one relative error per month.

    Coverage differs *between* months (each month has its own calibration
    window, so its own q), which is expected and desirable. Within a month it
    must be identical: that is the evidence that a single national calibration
    covers every region, rather than being tuned to each one.
    """
    metrics = exp010.run(config)
    assert metrics["relative"]["coverage_identical_across_regions"] is True
    assert metrics["relative"]["max_within_month_regional_spread"] == 0.0
    by_month: dict[int, set[float]] = {}
    for cell in metrics["cells"]:
        by_month.setdefault(cell["month"], set()).add(cell["relative_coverage"])
    assert len({m for months in by_month.values() for m in months}) > 1  # months do differ


def test_relative_coverage_hits_the_target_on_synthetic_data(config: dict[str, Any]) -> None:
    """90% of slots are 5% off and 10% are 50% off -> q=0.05 -> coverage ~90%."""
    metrics = exp010.run(config)
    assert metrics["relative"]["mean_coverage"] == pytest.approx(0.9, abs=0.04)
    # The 90th percentile of U[0.02, 0.10) is 0.092 -> 9.2% of the forecast.
    assert metrics["relative"]["mean_half_width_pct_of_forecast"] == pytest.approx(9.2, abs=0.5)


def test_constant_scheme_pays_width_without_gaining_coverage(config: dict[str, Any]) -> None:
    metrics = exp010.run(config)
    # A constant absolute width scales with the region's intensity, so the
    # dirtiest region needs the widest band for the same relative accuracy.
    widths = {c["regionid"]: c["constant_half_width_gco2_per_kwh"] for c in metrics["cells"]}
    assert widths[7] > widths[13] > widths[3] > widths[2]
    assert metrics["constant"]["mean_coverage"] == pytest.approx(0.9, abs=0.04)
    # Same coverage, more width: the constant band cannot track the slot's
    # forecast, so it buys nothing on average and costs sharpness.
    assert (
        metrics["constant"]["mean_half_width_pct_of_forecast"]
        >= metrics["relative"]["mean_half_width_pct_of_forecast"]
    )


def test_ranking_certainty_uses_the_best_and_second_best_site(config: dict[str, Any]) -> None:
    """q sets how far apart the top two must be before routing is certain.

    A banded band is f*(1 +- q), so the cleanest site is confidently cleaner
    than the runner-up only when f_best/f_second < (1-q)/(1+q). That number is
    the one a risk-averse scheduler consumes: it says how often routing
    everything to one region is a defensible decision rather than a coin flip.
    """
    metrics = exp010.run(config)
    for row in metrics["decision_relevance"]["by_month"].values():
        q = row["national_relative_q"]
        assert row["threshold_ratio"] == pytest.approx((1 - q) / (1 + q), abs=1e-4)
        # Fixture sites: 200 / 205 = 0.976, well above the ~0.83 threshold.
        assert row["median_best_to_second_ratio"] == pytest.approx(200 / 205, abs=1e-4)
        assert row["band_robust_pct"] == pytest.approx(0.0)
    assert metrics["decision_relevance"]["mean_band_robust_pct"] == pytest.approx(0.0)


def test_ranking_is_certain_when_the_gap_beats_the_band(config: dict[str, Any]) -> None:
    """A wide enough gap makes the ranking band-robust, and the metric says so."""
    _write_regional(Path(config["data"][1]), {13: 200, 7: 400, 3: 100, 2: 50})
    metrics = exp010.run(config)
    # Best 50, runner-up 100 -> ratio 0.5 < threshold, so the ranking holds.
    for row in metrics["decision_relevance"]["by_month"].values():
        assert row["median_best_to_second_ratio"] == pytest.approx(0.5, abs=1e-4)
        assert row["band_robust_pct"] == pytest.approx(100.0)
    assert metrics["decision_relevance"]["mean_band_robust_pct"] == pytest.approx(100.0)


def test_sim_sites_are_reported(config: dict[str, Any]) -> None:
    metrics = exp010.run(config)
    assert set(metrics["sim_sites"]["regions"]) == {
        "GB-London",
        "GB-SouthWales",
        "GB-NorthWestEngland",
        "GB-SouthScotland",
    }
    assert 0.8 <= metrics["sim_sites"]["min_coverage"] <= 1.0


def test_missing_national_json_raises(config: dict[str, Any]) -> None:
    config["data"] = [d for d in config["data"] if d.endswith(".csv")]  # drops the JSON
    with pytest.raises(StopIteration):
        exp010.run(config)


def test_cells_report_how_many_slots_actually_paired(config: dict[str, Any]) -> None:
    """Coverage over 3 slots and coverage over 300 must not look alike.

    The regional and national series join on the slot timestamp, so a format
    change upstream would silently drop pairs and shrink every evaluation
    without changing the reported coverage. Each cell therefore states how many
    regional slots matched a national one.
    """
    metrics = exp010.run(config)
    for cell in metrics["cells"]:
        assert cell["n_regional_slots"] >= cell["n_eval"] > 0
        assert cell["paired_pct"] == pytest.approx(100.0)
    assert metrics["pairing"]["min_paired_pct"] == pytest.approx(100.0)
    # 31 days of half-hourly slots in January, minus the 48 in Feb... simplest:
    # January 2024 has 31 days -> 1488 half-hourly slots.
    assert metrics["pairing"]["slots_per_month"]["1"] == 1488


def test_pairing_flags_a_timestamp_format_mismatch(config: dict[str, Any]) -> None:
    """If the two sources disagree on timestamp shape, the run must say so."""
    regional = Path(config["data"][1])
    # One regional slot moves an hour, so it can no longer join its national
    # counterpart. A corrupt or reformatted source looks exactly like this.
    text = regional.read_text().replace("2024-01-15T00:30Z", "2024-01-15T00:45Z")
    regional.write_text(text)
    metrics = exp010.run(config)
    assert metrics["pairing"]["min_paired_pct"] < 100.0


def test_duplicate_slots_are_counted_once(config: dict[str, Any]) -> None:
    """NESO repeats the boundary slot between adjacent weekly windows.

    Leaving those in would weight a handful of slots twice and inflate or
    deflate coverage; the duplicate count is reported so the dedupe is visible
    rather than silent.
    """
    national = Path(config["data"][0])
    rows = json.loads(national.read_text())["data"]
    national.write_text(json.dumps({"data": rows + rows}))  # every slot twice

    clean = exp010.run({**config, "data": [str(national), config["data"][1]]})
    assert clean["pairing"]["duplicate_slots_dropped"]["national"] == len(rows)
    assert clean["pairing"]["slots_per_month"]["1"] == 1488
    assert clean["relative"]["mean_coverage"] == pytest.approx(0.9, abs=0.04)
