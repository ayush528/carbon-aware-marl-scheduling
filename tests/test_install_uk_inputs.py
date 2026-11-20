"""Tests for the UK input installer (no network, no real checkout)."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "sustaincluster"))

import install_uk_inputs as installer  # noqa: E402

SLUG = "GB-London"
YEAR = 2024


def _write_carbon(path: Path, year: int, gap_hours: int, drop_first: bool = False) -> None:
    """8760/8784 rows minus a deliberate internal hole."""
    total = installer.hours_in_year(year)
    start = datetime(year, 1, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Datetime (UTC)", "Zone Id", "Zone Name", installer.CARBON_COLUMN])
        for index in range(total):
            if drop_first and index == 0:
                continue
            if 100 <= index < 100 + gap_hours:
                continue
            ts = start + timedelta(hours=index)
            writer.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), SLUG, SLUG, f"{50 + index % 7}.0"])


def _write_price(path: Path, year: int, rows: int | None = None) -> None:
    total = rows if rows is not None else installer.hours_in_year(year)
    start = datetime(year, 1, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Datetime (UTC)", "Datetime (Local)", installer.PRICE_COLUMN])
        for index in range(total):
            ts = start + timedelta(hours=index)
            stamp = ts.strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([stamp, f"{stamp}+00:00", "91.5"])


@pytest.fixture
def workspace(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "uk_inputs"
    _write_carbon(source / "carbon" / f"{SLUG}_{YEAR}_hourly.csv", YEAR, gap_hours=5)
    _write_price(source / "prices" / f"gb_{YEAR}_hourly.csv", YEAR)

    checkout = tmp_path / "checkout"
    weather = checkout / "data" / "weather" / "GB" / f"{YEAR}.json"
    weather.parent.mkdir(parents=True)
    weather.write_text('{"hourly": {}}')
    return {"source": source, "checkout": checkout}


def test_forward_fill_closes_the_gap_to_a_full_year(tmp_path: Path) -> None:
    path = tmp_path / "gappy.csv"
    _write_carbon(path, YEAR, gap_hours=5)
    _, rows = installer.read_rows(path)
    filled, n_filled = installer.forward_fill_hourly(rows, YEAR, installer.CARBON_COLUMN)

    assert len(filled) == installer.hours_in_year(YEAR)
    assert n_filled == 5
    # Filled rows carry the previous value, not the next one.
    assert filled[100][installer.CARBON_COLUMN] == filled[99][installer.CARBON_COLUMN]
    assert filled[104][installer.CARBON_COLUMN] == filled[99][installer.CARBON_COLUMN]
    assert filled[105][installer.CARBON_COLUMN] != filled[99][installer.CARBON_COLUMN]


def test_forward_fill_refuses_a_late_start(tmp_path: Path) -> None:
    path = tmp_path / "late.csv"
    _write_carbon(path, YEAR, gap_hours=0, drop_first=True)
    _, rows = installer.read_rows(path)
    with pytest.raises(ValueError, match="series starts at"):
        installer.forward_fill_hourly(rows, YEAR, installer.CARBON_COLUMN)


def test_install_writes_simulator_paths_and_manifest(workspace: dict[str, Path]) -> None:
    manifest = installer.install(workspace["source"], workspace["checkout"], YEAR)
    checkout = workspace["checkout"]

    carbon = checkout / "data" / "carbon_intensity" / SLUG / str(YEAR) / f"{SLUG}_{YEAR}_hourly.csv"
    price = (
        checkout
        / "data"
        / "electricity_prices"
        / "standardized"
        / SLUG
        / str(YEAR)
        / f"{SLUG}_electricity_prices_{YEAR}.csv"
    )
    weather = checkout / "data" / "weather" / SLUG / f"{YEAR}.json"

    assert carbon.is_file() and price.is_file()
    assert (
        weather.is_symlink()
        and weather.resolve() == (checkout / "data" / "weather" / "GB" / f"{YEAR}.json").resolve()
    )

    _, carbon_rows = installer.read_rows(carbon)
    _, price_rows = installer.read_rows(price)
    assert len(carbon_rows) == installer.hours_in_year(YEAR)
    assert len(price_rows) == installer.hours_in_year(YEAR)

    site = manifest["sites"][SLUG]
    assert site["carbon"]["forward_filled"] == 5
    assert site["carbon"]["rows"] == installer.hours_in_year(YEAR)
    assert site["weather"]["status"] == "symlink"
    assert manifest["price_source"] == f"gb_{YEAR}_hourly.csv"

    on_disk = json.loads((workspace["source"] / "install_manifest.json").read_text())
    assert on_disk["sites"][SLUG]["carbon"]["sha256"] == installer.sha256_bytes(carbon.read_bytes())


def test_install_is_idempotent(workspace: dict[str, Path]) -> None:
    first = installer.install(workspace["source"], workspace["checkout"], YEAR)
    second = installer.install(workspace["source"], workspace["checkout"], YEAR)
    assert first["sites"] == second["sites"]


def test_install_without_gb_weather_records_it(workspace: dict[str, Path]) -> None:
    (workspace["checkout"] / "data" / "weather" / "GB" / f"{YEAR}.json").unlink()
    manifest = installer.install(workspace["source"], workspace["checkout"], YEAR)
    assert manifest["sites"][SLUG]["weather"]["status"] == "missing_source"


def test_wrong_price_row_count_raises(tmp_path: Path, workspace: dict[str, Path]) -> None:
    _write_price(workspace["source"] / "prices" / f"gb_{YEAR}_hourly.csv", YEAR, rows=10)
    with pytest.raises(ValueError, match="expected 8784"):
        installer.install(workspace["source"], workspace["checkout"], YEAR)
