#!/usr/bin/env python3
"""Fetch and inspect real data from the UK Carbon Intensity API (api.carbonintensity.org.uk).

Free, no API key. Documentation: https://carbonintensity.org.uk/
Endpoints exercised (all live):
  1. National intensity, past window  -> expect forecast AND actual per half-hour slot
  2. Regional (all DNO regions), past window
  3. Single region (London = regionid 9), longer window
  4. Region list (/regional/regionid/{id} names)
Outputs raw JSON into data-audit/downloads/ and prints a summary.
"""
import json
import os
import sys
import time
from collections import Counter

import requests

BASE = "https://api.carbonintensity.org.uk"
OUT = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(OUT, exist_ok=True)
HDRS = {"User-Agent": "student-feasibility-study/1.0 (contact: project team)"}


def get(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HDRS, timeout=120)
            if r.status_code == 200:
                return r.json()
            print(f"  HTTP {r.status_code} for {url}")
            if r.status_code == 429:
                wait = 65
                print(f"  rate-limited, sleeping {wait}s")
                time.sleep(wait)
                continue
            return None
        except Exception as e:  # noqa: BLE001
            print(f"  error {e} for {url}")
            time.sleep(5)
    return None


def save(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        json.dump(obj, f)
    size = os.path.getsize(path)
    print(f"  saved {name} ({size:,} bytes)")
    return path


def summarise_national(data, label):
    rows = data.get("data", [])
    have_fc = have_ac = 0
    vals, diffs = [], []
    for r in rows:
        inten = r.get("intensity", {})
        if inten.get("forecast") is not None:
            have_fc += 1
        if inten.get("actual") is not None:
            have_ac += 1
            vals.append(inten["actual"])
            if inten.get("forecast") is not None:
                diffs.append(abs(inten["forecast"] - inten["actual"]))
    if vals:
        n = len(vals)
        print(
            f"  [{label}] slots={n} forecast-present={have_fc} actual-present={have_ac} "
            f"actual min/mean/max={min(vals)}/{sum(vals)/n:.1f}/{max(vals)} gCO2/kWh"
        )
        if diffs:
            mae = sum(diffs) / len(diffs)
            rmse = (sum(d * d for d in diffs) / len(diffs)) ** 0.5
            print(f"  [{label}] forecast-vs-actual MAE={mae:.2f} RMSE={rmse:.2f} gCO2/kWh over {len(diffs)} slots")
    else:
        print(f"  [{label}] slots={len(rows)} (no actual values in this window)")


def main():
    print("== 1. National intensity, 2025-01-01 .. 2025-01-02 (past window) ==")
    d = get(f"{BASE}/intensity/2025-01-01T00:00Z/2025-01-02T00:00Z")
    if d:
        save("uk_national_2025-01-01_to_2025-01-02.json", d)
        summarise_national(d, "national-1day")

    print("== 2. Regional (all DNO regions), 2025-01-01 .. 2025-01-02 ==")
    d = get(f"{BASE}/regional/intensity/2025-01-01T00:00Z/2025-01-02T00:00Z")
    if d:
        save("uk_regional_all_2025-01-01_to_2025-01-02.json", d)
        regs = d.get("data", [{}])[0].get("regions", [])
        names = [r.get("shortname") for r in regs]
        print(f"  regions returned: {len(regs)}")
        print("  names:", names)

    print("== 3. London (regionid 9), 2025-01-01 .. 2025-01-08 ==")
    d = get(f"{BASE}/regional/regionid/9/intensity/2025-01-01T00:00Z/2025-01-08T00:00Z")
    if d:
        save("uk_region9_london_2025-01-01_to_2025-01-08.json", d)
        blocks = d.get("data", {}).get("data", [])
        print(f"  blocks: {len(blocks)}; first block keys: {list(blocks[0].keys()) if blocks else None}")
        if blocks:
            print("  sample block:", json.dumps(blocks[0])[:300])

    print("== 4. Full-year attempt: London 2025-01-01 .. 2025-12-31 ==")
    d = get(f"{BASE}/regional/regionid/9/intensity/2025-01-01T00:00Z/2025-12-31T00:00Z")
    if d:
        save("uk_region9_london_2025_full_year.json", d)
        blocks = d.get("data", {}).get("data", [])
        print(f"  blocks: {len(blocks)}")
    else:
        print("  full-year single call failed (window limit)")

    print("== 5. Region names via /regional/regionid/1 ==")
    d = get(f"{BASE}/regional/regionid/1/intensity/2025-01-01T00:00Z/2025-01-01T01:00Z")
    if d:
        print("  regionid 1 ->", d.get("data", {}).get("shortname"))


if __name__ == "__main__":
    sys.exit(main())
