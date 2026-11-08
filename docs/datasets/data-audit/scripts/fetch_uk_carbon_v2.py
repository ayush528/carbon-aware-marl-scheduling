#!/usr/bin/env python3
"""Second pass on UK Carbon Intensity API with corrected endpoint paths (per official docs)."""
import json
import os

import requests

BASE = "https://api.carbonintensity.org.uk"
OUT = os.path.join(os.path.dirname(__file__), "..", "downloads")
HDRS = {"User-Agent": "student-feasibility-study/1.0 (contact: project team)"}


def get(url):
    r = requests.get(url, headers=HDRS, timeout=180)
    print(f"  GET {url} -> HTTP {r.status_code}")
    if r.status_code != 200:
        return None
    return r.json()


def save(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        json.dump(obj, f)
    print(f"  saved {name} ({os.path.getsize(path):,} bytes)")


# 1. London (regionid 13), one week, correct path
d = get(f"{BASE}/regional/intensity/2025-01-01T00:00Z/2025-01-08T00:00Z/regionid/13")
if d:
    save("uk_region13_london_2025-01-01_to_2025-01-08.json", d)
    blocks = d.get("data", {}).get("data", [])
    print(f"  blocks={len(blocks)}; keys={list(blocks[0].keys()) if blocks else None}")
    if blocks:
        print("  sample:", json.dumps(blocks[0])[:260])

# 2. Full-year London attempt
d = get(f"{BASE}/regional/intensity/2025-01-01T00:00Z/2025-12-31T00:00Z/regionid/13")
if d:
    save("uk_region13_london_2025_full_year.json", d)
    blocks = d.get("data", {}).get("data", [])
    print(f"  full-year blocks={len(blocks)}")
else:
    print("  full-year regional single call FAILED")

# 3. National generation mix, one day
d = get(f"{BASE}/generation/2025-01-01T00:00Z/2025-01-02T00:00Z")
if d:
    save("uk_generation_2025-01-01_to_2025-01-02.json", d)
    rows = d.get("data", [])
    print(f"  generation rows={len(rows)}; sample:", json.dumps(rows[0])[:220] if rows else None)

# 4. National intensity, one month (forecast + actual)
d = get(f"{BASE}/intensity/2025-01-01T00:00Z/2025-02-01T00:00Z")
if d:
    save("uk_national_2025-01_month.json", d)
    rows = d.get("data", [])
    print(f"  national month rows={len(rows)}")
