#!/usr/bin/env python3
"""Pull the regional carbon-intensity matrix: 14 DNO regions x a date range.

Writes tidy CSV, one row per slot x region. Two sources:

  single-region (default)  one request per (region, 7-day window) -- the path
                           exp003 validated; needed when actuals matter, though
                           the regional API ships none either way.
  --bulk                   one request per 7-day window for ALL regions (52 a
                           year instead of 728). Forecasts match the
                           single-region endpoint slot-for-slot (verified live
                           2026-11-20); still no actuals.

Bulk windows are cached on disk as they arrive, so a dropped connection costs
one window, not the pull. Re-running resumes from the cache.

Default: January 2025, all 14 DNO regions -> data/uk_regional_2025-01_tidy.csv
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from carbon_scheduling.data.neso import (
    REGIONS,
    chunk_windows,
    fetch_regional,
    fetch_regional_bulk,
    read_tidy_csv,
    write_tidy_csv,
)

DNO_REGIONS = [rid for rid in sorted(REGIONS) if rid <= 14]  # 15..18 are aggregates
DEFAULT_START, DEFAULT_END = "2025-01-01T00:00Z", "2025-02-01T00:00Z"
DEFAULT_OUT = "data/uk_regional_2025-01_tidy.csv"
DEFAULT_CACHE = "data/.cache/regional_bulk"
POLITE_PAUSE_S = 0.5  # between weekly windows, on top of retry backoff


def _window_name(start: str, end: str) -> str:
    return f"{start.replace(':', '').replace('-', '')}__{end.replace(':', '').replace('-', '')}.csv"


def dedupe(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop repeated (slot, region) rows; the first occurrence wins."""
    seen: set[tuple[Any, ...]] = set()
    kept: list[dict[str, Any]] = []
    for row in rows:
        key = (row.get("from"), row.get("regionid"))
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept, len(rows) - len(kept)


def bulk_pull(
    start: str,
    end: str,
    cache_dir: str | Path,
    fetch: Callable[[str, str], list[dict[str, Any]]] = fetch_regional_bulk,
    sleep: Callable[[float], None] = time.sleep,
    pause: float = POLITE_PAUSE_S,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Fetch every window, caching each one; re-runs reuse the cache.

    A window is written to a temp file and renamed into place, so an
    interrupted write can never be read back as a short window. A failure
    propagates after the completed windows are already safe on disk.
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for window_start, window_end in chunk_windows(start, end):
        path = cache / _window_name(window_start, window_end)
        if path.exists() and path.stat().st_size > 0:
            log(f"cached {window_start}")
            rows.extend(read_tidy_csv(path))
            continue
        batch = fetch(window_start, window_end)
        tmp = path.with_suffix(".tmp")
        write_tidy_csv(batch, tmp)
        tmp.replace(path)
        rows.extend(batch)
        log(f"pulled {window_start}  rows={len(batch)}")
        sleep(pause)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out", default=DEFAULT_OUT, help="output CSV path (repo-relative)")
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="use the all-regions endpoint (1 request/window, forecasts only)",
    )
    parser.add_argument("--cache", default=DEFAULT_CACHE, help="bulk window cache dir")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.bulk:
        rows = bulk_pull(args.start, args.end, args.cache)
        merged, dropped = dedupe(rows)
        write_tidy_csv(merged, out)
        print(
            f"\nwrote {len(merged)} rows -> {out}  (bulk, forecasts only; "
            f"{dropped} boundary duplicates dropped)"
        )
        return

    records: list[dict] = []
    for rid in DNO_REGIONS:
        rows = fetch_regional(rid, args.start, args.end)
        for r in rows:
            r["regionid"] = rid
            r["shortname"] = REGIONS[rid]
        records.extend(rows)
        print(f"region {rid:>2} {REGIONS[rid]:<22} slots={len(rows)}")
        time.sleep(POLITE_PAUSE_S)

    write_tidy_csv(records, out)
    actuals = sum(1 for r in records if r["actual"] is not None)
    print(f"\nwrote {len(records)} rows -> {out}  (with actual: {actuals})")


if __name__ == "__main__":
    main()
