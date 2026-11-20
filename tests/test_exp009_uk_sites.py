"""Tests for exp009's window/index guard and aggregation (no simulator runs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from carbon_scheduling.experiments import exp009_uk_sites as exp009


def _row(controller: str, carbon: float, sla: float) -> dict[str, Any]:
    return {
        "controller": controller,
        "carbon_kg": carbon,
        "energy_kwh": 1000.0,
        "energy_cost_usd": 10.0,
        "transmission_cost_usd": 1.0,
        "sla_violation_rate": sla,
        "tasks_finished": 100,
        "mean_gpu_util_percent": 50.0,
        "per_dc": {"DC1": {"carbon_kg": carbon, "energy_kwh": 1000.0, "energy_cost_usd": 10.0}},
    }


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    # One site is enough to exercise the wiring.
    carbon = tmp_path / "carbon" / "GB-London_2024_hourly.csv"
    carbon.parent.mkdir(parents=True)
    lines = ["Datetime (UTC),Zone Id,Zone Name,Carbon Intensity gCO₂eq/kWh (direct)"]
    for hour in range(24 * 7):
        from datetime import datetime, timedelta

        ts = datetime(2024, 1, 15) + timedelta(hours=hour)
        lines.append(f"{ts:%Y-%m-%d %H:%M:%S},GB-London,GB-London,200.0")
    carbon.write_text("\n".join(lines) + "\n")

    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps({"sites": {"GB-London": {"neso_region_id": 13, "neso_region_name": "London"}}})
    )

    monkeypatch.setattr(exp009, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(exp009.sustaincluster, "checkout_dir", lambda _cfg: tmp_path)
    monkeypatch.setattr(exp009.sustaincluster, "resolve_python", lambda *_: "python")

    # The series have to be installed in the checkout first (see _require_installed).
    installed = tmp_path / "data" / "carbon_intensity" / "GB-London" / "2024"
    installed.mkdir(parents=True)
    (installed / "GB-London_2024_hourly.csv").write_text("Datetime (UTC),x\n")

    def fake_run(checkout, python, strategy, *, days, seed, out_path, **kwargs):
        return {
            "sustaincluster_commit": "deadbeef",
            # Simulator jitters the window; here it happens to match the config.
            "window": {"start_day_index": 14, "start_hour_utc": 0, "year": 2024},
            "clock_start_utc": "2024-01-15T00:00Z",
            **{
                "round_robin": _row("round_robin", 200.0, 0.0),
                "lowest_carbon": _row("lowest_carbon", 180.0, 0.01),
            }[strategy],
        }

    monkeypatch.setattr(exp009.sustaincluster, "run_strategy", fake_run)

    return {
        "id": "exp009-test",
        "seed": 42,
        "data": [
            "carbon/GB-London_2024_hourly.csv",
            "provenance.json",
        ],
        "sustaincluster": {
            "checkout": str(tmp_path),
            "device": "cpu",
            "baselines": ["round_robin", "lowest_carbon"],
        },
        "simulation": {
            "year": 2024,
            "month": 1,
            "init_day": 15,
            "init_hour": 0,
            "duration_days": 7,
            "init_day_of_year": 14,
            "workload_path": "w.pkl",
            "cloud_provider": "aws",
            "disable_defer_action": True,
            "single_action_mode": True,
            "aggregation_method": "average",
        },
        "sites": [
            {
                "dc_id": 1,
                "location": "GB-London",
                "timezone_shift": 0,
                "population_weight": 1.0,
                "total_cores": 1,
                "total_gpus": 1,
                "total_mem": 1,
                "dc_config_file": "x.json",
            }
        ],
        "reward": {"normalize": False, "components": {}},
    }


def test_missing_installed_series_names_the_fix(config: dict[str, Any], tmp_path: Path) -> None:
    (
        tmp_path / "data" / "carbon_intensity" / "GB-London" / "2024" / "GB-London_2024_hourly.csv"
    ).unlink()
    with pytest.raises(FileNotFoundError, match="make sc-uk-data"):
        exp009.run(config)


def test_index_mismatch_is_rejected(config: dict[str, Any]) -> None:
    config["simulation"]["init_day_of_year"] = 31
    with pytest.raises(ValueError, match="does not match"):
        exp009.run(config)


def test_carbon_deltas_and_exit_test_values(config: dict[str, Any]) -> None:
    metrics = exp009.run(config)

    assert metrics["carbon_vs_round_robin_pct"]["lowest_carbon"] == pytest.approx(-10.0)
    assert metrics["best_carbon_controller"] == "lowest_carbon"
    # Input CSV is 200 g/kWh throughout; the run must show the same.
    london = metrics["regional_intensity"]["GB-London"]
    assert london["input_mean_gco2_per_kwh"] == pytest.approx(200.0)
    assert london["simulated_gco2_per_kwh"] == pytest.approx(200.0)
    assert metrics["max_intensity_error_gco2_per_kwh"] == pytest.approx(0.0)
    assert london["neso_region_id"] == 13
    assert metrics["n_sites"] == 1
    assert metrics["exit_test_passed"] is True
    assert metrics["regional_ordering_matches_input"] is True
    assert metrics["carbon_window_start_utc"] == "2024-01-15T00:00Z"
    assert metrics["workload_clock_start_utc"] == "2024-01-15T00:00Z"
    assert metrics["clock_aligned_with_carbon"] is True
    assert metrics["configured_anchor_utc"] == "2024-01-15T00:00Z"


def test_exit_test_follows_the_window_the_simulator_reported(
    config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cluster reset jitters the window; verification must follow it."""
    original = exp009.sustaincluster.run_strategy

    def shifted(checkout, python, strategy, **kwargs):
        payload = original(checkout, python, strategy, **kwargs)
        # Read from 06:00, so the 7-day window runs past the fixture's end.
        payload["window"] = {"start_day_index": 14, "start_hour_utc": 6, "year": 2024}
        payload["clock_start_utc"] = "2024-01-15T06:00Z"
        return payload

    monkeypatch.setattr(exp009.sustaincluster, "run_strategy", shifted)
    with pytest.raises(ValueError, match=r"only 162 of the 168 hours"):
        exp009.run(config)


def test_controllers_on_different_windows_are_rejected(
    config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = exp009.sustaincluster.run_strategy

    def jittered(checkout, python, strategy, **kwargs):
        payload = original(checkout, python, strategy, **kwargs)
        if strategy == "lowest_carbon":
            payload["window"] = {"start_day_index": 8, "start_hour_utc": 18, "year": 2024}
            payload["clock_start_utc"] = "2024-01-09T18:00Z"
        return payload

    monkeypatch.setattr(exp009.sustaincluster, "run_strategy", jittered)
    with pytest.raises(RuntimeError, match="different data windows"):
        exp009.run(config)
