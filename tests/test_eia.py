"""Tests for the EIA-930 → carbon-intensity reader.

The point of this reader is that the realized intensity is a *measurement* of a
real grid, not a national series rescaled per region. That is the whole reason
exp027 exists, so the reader has to be honest about three things:

1. an empty fuel field means "no generation of that fuel", not "missing";
2. the fuel breakdown must actually account for the reported net generation,
   within integer-rounding tolerance, or the hour is dropped rather than
   priced from a partial mix;
3. the emission factors are the published EIA ones, pinned here so a silent
   change to them is caught.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from carbon_scheduling.data import eia


def _row(**overrides) -> dict[str, str]:
    base = {
        "Balancing Authority": "TEST",
        "Data Date": "01/01/2024",
        "Hour Number": "1",
        "Local Time at End of Hour": "01/01/2024 1:00:00 AM",
        "UTC Time at End of Hour": "01/01/2024 7:00:00 AM",
        "Net Generation (MW)": "1000",
    }
    for fuel in eia.FUELS:
        base[f"Net Generation (MW) from {fuel}"] = ""
    base.update(overrides)
    return base


def test_empty_fuel_fields_mean_zero_not_missing() -> None:
    row = _row(
        **{
            "Net Generation (MW)": "2903",
            "Net Generation (MW) from Coal": "1802",
            "Net Generation (MW) from Natural Gas": "997",
            "Net Generation (MW) from Wind": "104",
        }
    )
    generation = eia.fuel_generation(row)
    assert generation["Coal"] == 1802.0
    assert generation["Nuclear"] == 0.0
    assert sum(generation.values()) == 2903.0


def test_factors_are_the_published_eia_values() -> None:
    # EIA FAQ: coal 2.31, natural gas 0.96, petroleum 2.46 lb CO2/kWh.
    assert eia.FACTORS_G_PER_KWH["Coal"] == pytest.approx(2.31 * 453.59237)
    assert eia.FACTORS_G_PER_KWH["Natural Gas"] == pytest.approx(0.96 * 453.59237)
    assert eia.FACTORS_G_PER_KWH["All Petroleum Products"] == pytest.approx(2.46 * 453.59237)
    for clean in ("Nuclear", "Hydropower and Pumped Storage", "Solar", "Wind"):
        assert eia.FACTORS_G_PER_KWH[clean] == 0.0


def test_intensity_is_the_generation_weighted_factor() -> None:
    row = _row(
        **{
            "Net Generation (MW)": "1000",
            "Net Generation (MW) from Coal": "500",
            "Net Generation (MW) from Wind": "500",
        }
    )
    expected = 0.5 * eia.FACTORS_G_PER_KWH["Coal"]
    assert eia.intensity(row) == pytest.approx(expected)


def test_rounding_tolerance_keeps_integer_noise_and_drops_real_gaps() -> None:
    # 1000 MW reported, fuels sum to 1004: 0.4% is integer rounding, keep it.
    close = _row(
        **{
            "Net Generation (MW)": "1000",
            "Net Generation (MW) from Coal": "1004",
        }
    )
    assert eia.intensity(close) is not None
    # 1000 reported, fuels sum to 900: a real gap, drop it rather than price it.
    gap = _row(
        **{
            "Net Generation (MW)": "1000",
            "Net Generation (MW) from Coal": "900",
        }
    )
    assert eia.intensity(gap) is None


def test_nonpositive_or_unknown_generation_is_dropped() -> None:
    assert eia.intensity(_row(**{"Net Generation (MW)": "0"})) is None
    assert eia.intensity(_row(**{"Net Generation (MW)": "-1174570"})) is None
    unknown = _row(
        **{
            "Net Generation (MW)": "1000",
            "Net Generation (MW) from Coal": "900",
            "Net Generation (MW) from Unknown Fuel Sources": "100",
        }
    )
    assert eia.intensity(unknown) is None


def test_slot_start_is_one_hour_before_the_utc_end_stamp() -> None:
    assert eia.slot_start(_row()) == datetime(2024, 1, 1, 6, 0)


def test_series_counts_what_it_dropped() -> None:
    rows = [
        _row(**{"Net Generation (MW) from Wind": "1000"}),
        _row(**{"Net Generation (MW)": "0"}),
        _row(**{"Net Generation (MW) from Coal": "900"}),  # 10% gap
    ]
    series, stats = eia.intensity_series(rows)
    assert len(series["TEST"]) == 1
    assert stats["TEST"]["total"] == 3
    assert stats["TEST"]["usable"] == 1
    assert stats["TEST"]["dropped"] == 2
