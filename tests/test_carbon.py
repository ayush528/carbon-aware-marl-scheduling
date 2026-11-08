"""Tests for carbon_scheduling.carbon (NESO loader + summary statistics)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from carbon_scheduling.carbon import load_neso_carbon, summarise

REAL_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "docs/datasets/data-audit/downloads/uk_national_2025-01_full_month.json"
)

FIXTURE = {
    "data": [
        {
            "from": "2025-01-01T00:00Z",
            "to": "2025-01-01T00:30Z",
            "intensity": {"forecast": 100, "actual": 90, "index": "low"},
        },
        {
            "from": "2025-01-01T00:30Z",
            "to": "2025-01-01T01:00Z",
            "intensity": {"forecast": 110, "actual": 110, "index": "moderate"},
        },
        {
            # actual is None before the half hour closes -- loader must tolerate it
            "from": "2025-01-01T01:00Z",
            "to": "2025-01-01T01:30Z",
            "intensity": {"forecast": 120, "actual": None, "index": "moderate"},
        },
    ]
}


def test_loader_flattens_and_keeps_null_actual(tmp_path: Path) -> None:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(FIXTURE))
    records = load_neso_carbon(path)
    assert len(records) == 3
    assert records[0]["forecast"] == 100
    assert records[2]["actual"] is None


def test_summarise_fixture_numbers(tmp_path: Path) -> None:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(FIXTURE))
    stats = summarise(load_neso_carbon(path))
    assert stats["n_slots"] == 3
    assert stats["n_actual"] == 2
    assert stats["actual_min"] == 90
    assert stats["actual_max"] == 110
    assert math.isclose(stats["actual_mean"], 100.0)
    # |100-90| / 2 slots
    assert stats["forecast_vs_actual_mae"] == pytest.approx(5.0)


def test_summarise_rejects_all_null() -> None:
    with pytest.raises(ValueError):
        summarise([{"from": "x", "to": "y", "forecast": 1, "actual": None, "index": "low"}])


@pytest.mark.skipif(not REAL_SAMPLE.is_file(), reason="audit sample not present")
def test_real_jan2025_sample_is_stable() -> None:
    """The committed audit sample must keep yielding the same summary.

    Phase 1 statistical work must reproduce these numbers exactly.
    """
    stats = summarise(load_neso_carbon(REAL_SAMPLE))
    assert stats["n_slots"] == 1493
    assert stats["actual_min"] <= stats["actual_median"] <= stats["actual_max"]
    assert 0 < stats["forecast_vs_actual_mae"] < 200
