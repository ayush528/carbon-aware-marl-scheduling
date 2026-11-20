"""Pull the UK inputs SustainCluster needs, in its own CSV schema.

Why a script: upstream's loaders hardcode their paths and columns, and GB is
incomplete upstream (national single-zone carbon, no electricity prices), so
the UK run needs derived files. Regenerating them must be one command.

What it produces (all hourly, 2024 = 8784 rows, SustainCluster's expected
column names):

  carbon/<slug>_2024_hourly.csv   regional intensity per site
      = national_actual x regional_forecast / national_forecast
      (the documented estimate: NESO's regional endpoint ships forecasts only,
      `actual` is null for every regional row -- verified 2026-11-20)
  prices/gb_2024_hourly.csv       national GB day-ahead proxy (Elexon MID,
      APXMIDP, GBP/MWh) converted to USD/MWh at the 2024 mean ECB rate
  provenance.json                 URLs, row counts, gaps, FX rate, formula

Sources
  NESO Carbon Intensity API  https://api.carbonintensity.org.uk
  Elexon BMRS                https://data.elexon.co.uk/bmrs/api/v1
  FX (ECB reference rates)   https://api.frankfurter.app

Nothing is invented: gaps are counted and reported, and only forward-filled
when a series is required to have exactly 8784 rows (prices); the number of
filled hours is recorded in provenance.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from carbon_scheduling.data.neso import REGIONS, fetch_national, fetch_regional

ELEXON_MID = "https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index"
FX_URL = "https://api.frankfurter.app"

# Site slug -> (NESO region id, display name). Region ids verified against the
# live API in the data audit; see REGIONS in carbon_scheduling.data.neso.
UK_SITES: dict[str, tuple[int, str]] = {
    "GB-London": (13, "London"),
    "GB-SouthWales": (7, "South Wales"),
    "GB-NorthWestEngland": (3, "North West England"),
    "GB-SouthScotland": (2, "South Scotland"),
}


def _get_json(url: str, retries: int = 4) -> Any:
    """GET JSON with modest retries (public APIs, occasional 5xx)."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=90) as response:
                return json.loads(response.read().decode())
        except Exception as exc:  # noqa: BLE001 - reported after the last try
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}") from last


def _half_hours(year: int) -> list[datetime]:
    start = datetime(year, 1, 1, tzinfo=UTC)
    return [start + timedelta(minutes=30 * i) for i in range(366 * 48)]


def _to_hourly_half_hourly(
    points: dict[datetime, float], year: int
) -> tuple[dict[datetime, float], list[datetime]]:
    """Average half-hourly points into hours; report hours with no data."""
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for ts, value in points.items():
        buckets[ts.replace(minute=0)].append(value)
    hours = [datetime(year, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(366 * 24)]
    out = {hour: mean(buckets[hour]) for hour in hours if hour in buckets}
    missing = [hour for hour in hours if hour not in out]
    return out, missing


def _key(record: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(record["from"].replace("Z", "+00:00")).astimezone(UTC)


def regional_actual_estimates(year: int, region_id: int) -> tuple[dict[datetime, float], dict]:
    """regional_actual ~= national_actual * regional_forecast / national_forecast."""
    start = f"{year}-01-01T00:00Z"
    end = f"{year + 1}-01-01T00:00Z"
    national = fetch_national(start, end)
    regional = fetch_regional(region_id, start, end)

    national_actual = {_key(r): float(r["actual"]) for r in national if r.get("actual") is not None}
    national_forecast = {
        _key(r): float(r["forecast"]) for r in national if r.get("forecast") is not None
    }
    regional_forecast = {
        _key(r): float(r["forecast"]) for r in regional if r.get("forecast") is not None
    }

    estimates: dict[datetime, float] = {}
    skipped = 0
    for ts, regional_value in regional_forecast.items():
        actual = national_actual.get(ts)
        forecast = national_forecast.get(ts)
        if actual is None or not forecast:
            skipped += 1
            continue
        estimates[ts] = actual * regional_value / forecast

    stats = {
        "national_rows": len(national),
        "regional_rows": len(regional),
        "regional_rows_with_actual": sum(1 for r in regional if r.get("actual") is not None),
        "paired_slots": len(estimates),
        "skipped_slots": skipped,
    }
    return estimates, stats


def gb_half_hourly_prices(year: int) -> tuple[dict[datetime, float], dict]:
    """Elexon Market Index Data (APXMIDP), GBP/MWh, half-hourly."""
    prices: dict[datetime, float] = {}
    windows = 0
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=7), end)
        url = (
            f"{ELEXON_MID}?from={cursor:%Y-%m-%dT%H:%MZ}"
            f"&to={window_end:%Y-%m-%dT%H:%MZ}&dataProviders=APXMIDP"
        )
        payload = _get_json(url)
        for row in payload.get("data", []):
            ts = datetime.fromisoformat(row["startTime"].replace("Z", "+00:00")).astimezone(UTC)
            prices[ts] = float(row["price"])
        windows += 1
        cursor = window_end
    return prices, {"windows": windows, "rows": len(prices)}


def gbp_usd_mean(year: int) -> tuple[float, dict]:
    """2024 mean of ECB daily GBP->USD reference rates."""
    url = f"{FX_URL}/{year}-01-01..{year}-12-31?from=GBP&to=USD"
    payload = _get_json(url)
    rates = [float(v["USD"]) for v in payload["rates"].values()]
    return mean(rates), {"days": len(rates), "min": min(rates), "max": max(rates)}


def _write_carbon_csv(path: Path, hourly: dict[datetime, float], slug: str, region: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Datetime (UTC)", "Zone Id", "Zone Name", "Carbon Intensity gCO₂eq/kWh (direct)"]
        )
        for ts in sorted(hourly):
            writer.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), slug, region, f"{hourly[ts]:.4f}"])


def _write_price_csv(path: Path, hourly: dict[datetime, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Datetime (UTC)", "Datetime (Local)", "Price (USD/MWh)"])
        for ts in sorted(hourly):
            writer.writerow(
                [
                    ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    f"{hourly[ts]:.6f}",
                ]
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--out", default="data/sustaincluster_uk")
    args = ap.parse_args()
    year = args.year
    out = Path(args.out)

    provenance: dict[str, Any] = {
        "year": year,
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "carbon": "NESO Carbon Intensity API (api.carbonintensity.org.uk)",
            "prices": "Elexon BMRS market-index (data.elexon.co.uk), dataProviders=APXMIDP",
            "fx": "ECB reference rates via api.frankfurter.app",
        },
        "carbon_formula": (
            "regional_actual = national_actual * regional_forecast / national_forecast"
        ),
        "disclosures": [
            "NESO's regional endpoint ships forecasts only; `actual` is null for every "
            "regional row, so regional intensity is the documented national-scaling estimate.",
            "GB electricity price is the national Elexon MID series, replicated for every "
            "site: regional wholesale price differences are not modelled.",
            "Prices arrive in GBP/MWh and are converted to USD/MWh at the mean ECB rate "
            "for the year, because SustainCluster's column is 'Price (USD/MWh)'.",
        ],
        "sites": {},
        "price": {},
    }

    fx_rate, fx_stats = gbp_usd_mean(year)
    provenance["price"]["fx_gbp_usd_mean"] = round(fx_rate, 6)
    provenance["price"]["fx_stats"] = fx_stats

    prices_30, price_stats = gb_half_hourly_prices(year)
    prices_hourly, missing_price = _to_hourly_half_hourly(prices_30, year)
    filled = 0
    if missing_price:
        last_value = None
        for hour in sorted(set(prices_hourly) | set(missing_price)):
            if hour in prices_hourly:
                last_value = prices_hourly[hour]
            elif last_value is not None:
                prices_hourly[hour] = last_value
                filled += 1
    prices_usd = {ts: value * fx_rate for ts, value in prices_hourly.items()}
    _write_price_csv(out / "prices" / f"gb_{year}_hourly.csv", prices_usd)

    provenance["price"].update(
        {
            **price_stats,
            "half_hours": len(prices_30),
            "hours_written": len(prices_usd),
            "hours_forward_filled": filled,
            "mean_usd_per_mwh": round(mean(prices_usd.values()), 3),
        }
    )

    for slug, (region_id, region_name) in UK_SITES.items():
        estimates, stats = regional_actual_estimates(year, region_id)
        hourly, missing = _to_hourly_half_hourly(estimates, year)
        _write_carbon_csv(out / "carbon" / f"{slug}_{year}_hourly.csv", hourly, slug, region_name)
        values = list(hourly.values())
        provenance["sites"][slug] = {
            "neso_region_id": region_id,
            "neso_region_name": REGIONS[region_id],
            **stats,
            "hours_written": len(hourly),
            "hours_missing": len(missing),
            "mean_gco2_per_kwh": round(mean(values), 2),
            "min_gco2_per_kwh": round(min(values), 2),
            "max_gco2_per_kwh": round(max(values), 2),
        }
        print(
            f"{slug:<22} region {region_id:>2} {region_name:<20} "
            f"mean {mean(values):6.1f} gCO2/kWh  hours={len(hourly)}"
        )

    out.mkdir(parents=True, exist_ok=True)
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(
        f"\nGB price: {provenance['price']['mean_usd_per_mwh']} USD/MWh "
        f"({fx_rate:.4f} USD/GBP, {len(prices_usd)} hours)"
    )
    print(f"wrote {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
