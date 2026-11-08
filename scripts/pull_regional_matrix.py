#!/usr/bin/env python3
"""Pull the regional carbon-intensity matrix: 14 DNO regions x a date range.

Writes tidy CSV (one row per slot x region, forecast AND actual -- the bulk
all-regions endpoint omits actuals, so this loops the single-region endpoint).
Default: January 2025, all 14 DNO regions -> data/uk_regional_2025-01_tidy.csv
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from carbon_scheduling.data.neso import REGIONS, fetch_regional, write_tidy_csv

DNO_REGIONS = [rid for rid in sorted(REGIONS) if rid <= 14]  # 15..18 are aggregates
DEFAULT_START, DEFAULT_END = "2025-01-01T00:00Z", "2025-02-01T00:00Z"
DEFAULT_OUT = "data/uk_regional_2025-01_tidy.csv"
POLITE_PAUSE_S = 0.5  # between weekly windows, on top of retry backoff


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out", default=DEFAULT_OUT, help="output CSV path (repo-relative)")
    args = parser.parse_args()

    records: list[dict] = []
    for rid in DNO_REGIONS:
        rows = fetch_regional(rid, args.start, args.end)
        for r in rows:
            r["regionid"] = rid
            r["shortname"] = REGIONS[rid]
        records.extend(rows)
        print(f"region {rid:>2} {REGIONS[rid]:<22} slots={len(rows)}")
        time.sleep(POLITE_PAUSE_S)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_tidy_csv(records, out)
    actuals = sum(1 for r in records if r["actual"] is not None)
    print(f"\nwrote {len(records)} rows -> {out}  (with actual: {actuals})")


if __name__ == "__main__":
    main()
