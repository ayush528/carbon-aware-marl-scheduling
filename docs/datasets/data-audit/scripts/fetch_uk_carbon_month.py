#!/usr/bin/env python3
"""Determine UK CI API window limits, then chunk-download one month of national +
regional-London data, and compute audit statistics (counts, gaps, forecast-vs-actual error)."""
import json
import os

import requests

BASE = "https://api.carbonintensity.org.uk"
OUT = os.path.join(os.path.dirname(__file__), "..", "downloads")
AN = os.path.join(os.path.dirname(__file__), "..", "analysis")
os.makedirs(AN, exist_ok=True)
HDRS = {"User-Agent": "student-feasibility-study/1.0 (contact: project team)"}


def get(url):
    r = requests.get(url, headers=HDRS, timeout=180)
    return r.status_code, (r.json() if r.status_code == 200 else None)


def iso(day, hour=0):
    return f"2025-01-{day:02d}T{hour:02d}:00Z"


# --- window-limit probe ---
print("== window limit probe (national) ==")
for days in (7, 14, 15, 30):
    code, _ = get(f"{BASE}/intensity/2025-01-01T00:00Z/2025-01-{1 + days:02d}T00:00Z")
    print(f"  {days} days -> HTTP {code}")
    if code != 200:
        break

# --- chunked month download: national + London, weekly chunks ---
print("== chunked month download ==")
national, london = [], []
for start in (1, 8, 15, 22, 29):
    end = min(start + 7, 32)
    code, d = get(f"{BASE}/intensity/{iso(start)}/{iso(end) if end <= 31 else '2025-02-01T00:00Z'}")
    if code == 200 and d:
        national += d["data"]
    code, d = get(f"{BASE}/regional/intensity/{iso(start)}/{iso(end) if end <= 31 else '2025-02-01T00:00Z'}/regionid/13")
    if code == 200 and d:
        london += d["data"]["data"]
print(f"  national slots={len(national)}, london slots={len(london)}")
json.dump({"data": national}, open(os.path.join(OUT, "uk_national_2025-01_full_month.json"), "w"))
json.dump({"data": {"shortname": "London", "region_id": 13, "data": london}},
          open(os.path.join(OUT, "uk_region13_london_2025-01_full_month.json"), "w"))

# --- statistics ---
print("== statistics ==")
fc, ac, pairs = [], [], []
for r in national:
    it = r["intensity"]
    if it.get("forecast") is not None:
        fc.append(it["forecast"])
    if it.get("actual") is not None:
        ac.append(it["actual"])
        if it.get("forecast") is not None:
            pairs.append((it["forecast"], it["actual"]))

n = len(ac)
mean = sum(ac) / n
mae = sum(abs(f - a) for f, a in pairs) / len(pairs)
rmse = (sum((f - a) ** 2 for f, a in pairs) / len(pairs)) ** 0.5
# expected slot count for the window
print(f"  national: slots={len(national)} actual-present={n} min={min(ac)} mean={mean:.1f} max={max(ac)} gCO2/kWh")
print(f"  forecast-vs-actual: n={len(pairs)} MAE={mae:.2f} RMSE={rmse:.2f} gCO2/kWh")

# London stats + regional spread on a sample day
lon_vals = [b["intensity"]["forecast"] for b in london if b["intensity"].get("forecast") is not None]
print(f"  london (forecast field): slots={len(lon_vals)} min={min(lon_vals)} mean={sum(lon_vals)/len(lon_vals):.1f} max={max(lon_vals)}")

# regional spread across all 14 DNO regions on 2025-01-15 12:00-12:30
code, d = get(f"{BASE}/regional/intensity/2025-01-15T12:00Z/2025-01-15T12:30Z")
if code == 200:
    regs = {r["shortname"]: r["intensity"]["forecast"] for r in d["data"][0]["regions"]
            if r["shortname"] not in ("England", "Scotland", "Wales", "GB")}
    lo, hi = min(regs.values()), max(regs.values())
    print(f"  regional spread at 2025-01-15 12:00Z: min={lo} max={hi} (span {hi - lo} gCO2/kWh across {len(regs)} DNO regions)")
    print(f"  extremes: {min(regs, key=regs.get)}={lo} / {max(regs, key=regs.get)}={hi}")

# missing-slot check (national month): count gaps in the half-hour series
from datetime import datetime, timedelta
ts = [datetime.strptime(r["from"], "%Y-%m-%dT%H:%MZ") for r in national]
ts = sorted(set(ts))
gaps = sum(1 for a, b in zip(ts, ts[1:]) if (b - a) != timedelta(minutes=30))
print(f"  national month: unique slots={len(ts)} unexpected gaps={gaps}")

# persist audit summary
summary = {
    "source": "UK Carbon Intensity API (NESO), api.carbonintensity.org.uk",
    "national_month_slots": len(national),
    "national_actual_min_mean_max": [min(ac), round(mean, 1), max(ac)],
    "forecast_vs_actual_n": len(pairs),
    "forecast_vs_actual_MAE": round(mae, 2),
    "forecast_vs_actual_RMSE": round(rmse, 2),
    "london_forecast_slots": len(lon_vals),
    "london_min_mean_max": [min(lon_vals), round(sum(lon_vals) / len(lon_vals), 1), max(lon_vals)],
    "unexpected_gaps": gaps,
}
json.dump(summary, open(os.path.join(AN, "uk_carbon_summary.json"), "w"), indent=2)
print("  summary written to analysis/uk_carbon_summary.json")
