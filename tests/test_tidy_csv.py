"""Tests for the tidy-CSV store used by the regional matrix pull (Phase 1).

Background fact verified from the audit sample (uk_regional_all_*.json): the
bulk all-regions endpoint ships forecasts only -- no "actual" key on any of
882 region-slots. The matrix pull therefore loops the single-region endpoint
(which does return actuals) over the 14 DNO regions and stores tidy CSV.
"""

from __future__ import annotations

import csv
from pathlib import Path

from carbon_scheduling.data.neso import read_tidy_csv, write_tidy_csv

RECORDS = [
    {
        "from": "2025-01-01T00:00Z",
        "to": "2025-01-01T00:30Z",
        "regionid": 13,
        "shortname": "London",
        "forecast": 56,
        "actual": 54,
        "index": "low",
    },
    {
        "from": "2025-01-01T00:00Z",
        "to": "2025-01-01T00:30Z",
        "regionid": 3,
        "shortname": "North West England",
        "forecast": 4,
        # bulk endpoint omits "actual" -- must roundtrip as empty, not "None"
        "actual": None,
        "index": "very low",
    },
]

HEADER = ["from", "to", "regionid", "shortname", "forecast", "actual", "index"]


def test_write_tidy_csv_exact_header_and_rows(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    write_tidy_csv(RECORDS, path)
    lines = path.read_text().splitlines()
    assert lines[0].split(",") == HEADER
    assert lines[1] == "2025-01-01T00:00Z,2025-01-01T00:30Z,13,London,56,54,low"
    # None -> empty cell (csv module default); never the string "None"
    assert lines[2].endswith(",4,,very low")


def test_read_tidy_csv_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    write_tidy_csv(RECORDS, path)
    records = read_tidy_csv(path)
    assert records == RECORDS  # types restored: ints for regionid/forecast/actual


def test_read_write_roundtrip_with_missing_actual(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    write_tidy_csv(RECORDS, path)
    raw = list(csv.DictReader(path.read_text().splitlines()))
    assert raw[1]["actual"] == ""  # empty cell in the file
    assert read_tidy_csv(path)[1]["actual"] is None  # None after read
