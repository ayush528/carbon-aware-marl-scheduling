"""Install the derived UK inputs where SustainCluster's loaders expect them.

The simulator hardcodes its input paths relative to the checkout, and GB is
incomplete upstream (national single-zone carbon, no price series, no per-site
weather), so our derived series have to be materialised into the checkout.

This step is also where the one data gap is repaired: NESO's regional endpoint
has a 16-hour outage on 2024-06-11/12 (all regions), and the simulator indexes
series *positionally*, so an internal hole would shift every later timestamp.
Missing hours are forward-filled from the previous value to reach the 8784
hours of the leap year, and the number of filled rows is written to the
manifest. Nothing else is altered.

Idempotent: re-running rewrites the same bytes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CARBON_COLUMN = "Carbon Intensity gCO₂eq/kWh (direct)"
PRICE_COLUMN = "Price (USD/MWh)"
HOURS_PER_YEAR = {2024: 8784, 2020: 8784}


def hours_in_year(year: int) -> int:
    return HOURS_PER_YEAR.get(year, 8760)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def forward_fill_hourly(
    rows: list[dict[str, str]], year: int, column: str
) -> tuple[list[dict[str, str]], int]:
    """Return exactly ``hours_in_year(year)`` hourly rows, fill gaps forward.

    Raises if the series starts late (nothing to carry) so a bad pull is not
    silently smeared.
    """
    by_hour: dict[datetime, str] = {}
    for row in rows:
        ts = datetime.strptime(row["Datetime (UTC)"], "%Y-%m-%d %H:%M:%S")
        by_hour[ts] = row[column]

    start = datetime(year, 1, 1)
    first = min(by_hour)
    if first != start:
        raise ValueError(f"series starts at {first}, expected {start}")

    filled: list[dict[str, str]] = []
    carried: str | None = None
    n_filled = 0
    for index in range(hours_in_year(year)):
        ts = start + timedelta(hours=index)
        if ts in by_hour:
            carried = by_hour[ts]
        else:
            if carried is None:
                raise ValueError(f"no value to carry into {ts}")
            n_filled += 1
        filled.append({"Datetime (UTC)": ts.strftime("%Y-%m-%d %H:%M:%S"), column: carried})
    return filled, n_filled


def write_carbon_csv(path: Path, rows: list[dict[str, str]], slug: str) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Datetime (UTC)", "Zone Id", "Zone Name", CARBON_COLUMN])
        for row in rows:
            writer.writerow([row["Datetime (UTC)"], slug, slug, row[CARBON_COLUMN]])
    return path.read_bytes()


def write_price_csv(path: Path, rows: list[dict[str, str]]) -> bytes:
    """Price rows keep upstream's two timestamp columns and the USD/MWh value."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Datetime (UTC)", "Datetime (Local)", PRICE_COLUMN])
        for row in rows:
            ts = row["Datetime (UTC)"]
            local = row.get("Datetime (Local)") or f"{ts}+00:00"
            writer.writerow([f"{ts}+00:00", local, row[PRICE_COLUMN]])
    return path.read_bytes()


def link_weather(checkout: Path, slug: str, year: int) -> dict[str, Any]:
    source = checkout / "data" / "weather" / "GB" / f"{year}.json"
    target = checkout / "data" / "weather" / slug / f"{year}.json"
    if not source.is_file():
        return {"status": "missing_source", "source": str(source.relative_to(checkout))}
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.exists():
        target.unlink()
    # Relative link so the checkout stays movable.
    os.symlink(os.path.join("..", "GB", f"{year}.json"), target)
    return {"status": "symlink", "target": str(target.relative_to(checkout))}


def install(source_dir: Path, checkout: Path, year: int) -> dict[str, Any]:
    """Materialise carbon/price/weather for every site; return the manifest."""
    source_dir = Path(source_dir)
    checkout = Path(checkout)
    carbon_files = sorted((source_dir / "carbon").glob(f"*_{year}_hourly.csv"))
    if not carbon_files:
        raise FileNotFoundError(f"no carbon CSVs for {year} in {source_dir / 'carbon'}")

    price_files = sorted((source_dir / "prices").glob(f"*_{year}_hourly.csv"))
    if len(price_files) != 1:
        raise FileNotFoundError(
            f"expected exactly one GB price CSV for {year}, found {len(price_files)}"
        )
    _, price_rows = read_rows(price_files[0])
    if len(price_rows) != hours_in_year(year):
        raise ValueError(
            f"{price_files[0].name}: {len(price_rows)} rows, "
            f"expected {hours_in_year(year)} (upstream asserts 8760/8784)"
        )

    manifest: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "year": year,
        "checkout": str(checkout),
        "checkout_commit": _git_commit(checkout),
        "price_source": price_files[0].name,
        "sites": {},
    }

    for carbon_file in carbon_files:
        slug = carbon_file.name[: -len(f"_{year}_hourly.csv")]
        _, rows = read_rows(carbon_file)
        filled, n_filled = forward_fill_hourly(rows, year, CARBON_COLUMN)

        carbon_path = (
            checkout / "data" / "carbon_intensity" / slug / str(year) / f"{slug}_{year}_hourly.csv"
        )
        carbon_bytes = write_carbon_csv(carbon_path, filled, slug)

        price_path = (
            checkout
            / "data"
            / "electricity_prices"
            / "standardized"
            / slug
            / str(year)
            / f"{slug}_electricity_prices_{year}.csv"
        )
        price_bytes = write_price_csv(price_path, price_rows)

        manifest["sites"][slug] = {
            "carbon": {
                "path": str(carbon_path.relative_to(checkout)),
                "rows": len(filled),
                "forward_filled": n_filled,
                "sha256": sha256_bytes(carbon_bytes),
            },
            "price": {
                "path": str(price_path.relative_to(checkout)),
                "rows": len(price_rows),
                "sha256": sha256_bytes(price_bytes),
            },
            "weather": link_weather(checkout, slug, year),
        }

    manifest_path = source_dir / "install_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _git_commit(checkout: Path) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/sustaincluster_uk")
    ap.add_argument("--checkout", default="external/sustain-cluster")
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()

    manifest = install(Path(args.source), Path(args.checkout), args.year)
    for slug, entry in manifest["sites"].items():
        print(
            f"{slug:<22} carbon {entry['carbon']['rows']} rows "
            f"({entry['carbon']['forward_filled']} filled)  "
            f"price {entry['price']['rows']} rows  weather {entry['weather']['status']}"
        )
    print(f"manifest: {Path(args.source) / 'install_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
