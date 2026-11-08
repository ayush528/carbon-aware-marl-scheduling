"""NESO Carbon Intensity API -- regional data puller (Phase 1: data freeze).

Sources (verified during the feasibility data audit, 2026-11-04):
  - National:  {BASE}/intensity/{from}/{to}
  - Regional:  {BASE}/regional/intensity/{from}/{to}/regionid/{id}
               payload nests the slot rows under {"data": {"data": [...]}}
  - All regions: {BASE}/regional/intensity/{from}/{to}
               rows carry a "regions" list (ids 1..14 DNO, 15..18 aggregates)

The API is window-limited, so range requests are chunked into <=7-day
windows (the pattern the audit scripts verified against the live API).
HTTP is injectable for testing; default uses urllib with polite retries.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE = "https://api.carbonintensity.org.uk"

# Verified against the live API on 2025-01 samples (data audit, 2026-11-04):
# 1..14 are the DNO distribution regions, 15..18 are country/GB aggregates.
REGIONS: dict[int, str] = {
    1: "North Scotland",
    2: "South Scotland",
    3: "North West England",
    4: "North East England",
    5: "Yorkshire",
    6: "North Wales & Merseyside",
    7: "South Wales",
    8: "West Midlands",
    9: "East Midlands",
    10: "East England",
    11: "South West England",
    12: "South England",
    13: "London",
    14: "South East England",
    15: "England",
    16: "Scotland",
    17: "Wales",
    18: "GB",
}
LONDON_REGION_ID = 13

HttpGet = Callable[[str], tuple[int, dict[str, Any] | None]]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_single_region(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a single-region payload into slot records.

    Regional payloads nest the rows one level deeper than national ones:
    ``{"data": {"shortname", "region_id", "data": [<slot rows>]}}``. Each row
    becomes ``{"from", "to", "forecast", "actual", "index"}`` (keys the API
    omits are normalised to None, matching :mod:`carbon_scheduling.carbon`).
    """
    inner = payload.get("data", {})
    rows = inner.get("data", []) if isinstance(inner, dict) else []
    records = []
    for row in rows:
        intensity = row.get("intensity", {})
        records.append(
            {
                "from": row.get("from"),
                "to": row.get("to"),
                "forecast": intensity.get("forecast"),
                "actual": intensity.get("actual"),
                "index": intensity.get("index"),
            }
        )
    return records


def fetch_regional(
    region_id: int,
    start: str,
    end: str,
    http_get: HttpGet | None = None,
    retries: int = 3,
    sleep: Callable[[float], None] | None = None,
) -> list[dict[str, Any]]:
    """Fetch one region's half-hourly carbon intensity over [start, end).

    Range is chunked into <=7-day windows (NESO window limits). Transient
    failures (connection errors / non-200) are retried per window up to
    ``retries`` attempts with a fixed 2 s backoff between attempts.
    """
    if http_get is None:
        http_get = _urllib_get
    if sleep is None:
        sleep = time.sleep
    if region_id not in REGIONS:
        raise ValueError(f"unknown region id {region_id}; known: {sorted(REGIONS)}")

    records: list[dict[str, Any]] = []
    for window_start, window_end in chunk_windows(start, end):
        url = f"{BASE}/regional/intensity/{window_start}/{window_end}/regionid/{region_id}"
        payload = _get_with_retry(url, http_get, retries, sleep)
        records.extend(parse_single_region(payload))
    return records


def _get_with_retry(
    url: str, http_get: HttpGet, retries: int, sleep: Callable[[float], None]
) -> dict[str, Any]:
    last_error: str | OSError = "unreachable"
    for attempt in range(retries):
        try:
            code, payload = http_get(url)
        except OSError as exc:  # urllib raises URLError (an OSError)
            last_error = str(exc)
            code, payload = 0, None
        if code == 200 and payload is not None:
            return payload
        last_error = f"HTTP {code}"
        if attempt < retries - 1:
            sleep(2.0)
    raise RuntimeError(f"NESO request failed after {retries} attempts: {url} ({last_error})")


def _urllib_get(url: str) -> tuple[int, dict[str, Any] | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "carbon-scheduling/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status, json.loads(response.read().decode())


# --- tidy CSV store (regional matrix pulls) -----------------------------------

TIDY_HEADER = ["from", "to", "regionid", "shortname", "forecast", "actual", "index"]


def write_tidy_csv(records: list[dict[str, Any]], path: str | Path) -> None:
    """Write slot records as tidy CSV: one row per (slot, region).

    None values become empty cells -- never the string "None".
    """
    with Path(path).open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TIDY_HEADER)
        writer.writeheader()
        writer.writerows(records)


def read_tidy_csv(path: str | Path) -> list[dict[str, Any]]:
    """Read a tidy CSV back into records, restoring types (ints, None)."""
    records = []
    with Path(path).open(newline="") as fh:
        for row in csv.DictReader(fh):
            records.append(
                {
                    "from": row["from"],
                    "to": row["to"],
                    "regionid": int(row["regionid"]),
                    "shortname": row["shortname"],
                    "forecast": int(row["forecast"]) if row["forecast"] else None,
                    "actual": int(row["actual"]) if row["actual"] else None,
                    "index": row["index"] or None,
                }
            )
    return records


def chunk_windows(start: str, end: str, max_days: int = 7) -> list[tuple[str, str]]:
    """Split [start, end) into contiguous windows of at most ``max_days`` days.

    Start/end are ISO-8601 with a Z suffix (NESO API format); the returned
    boundaries are rendered back in the same format. End is exclusive, so a
    full month splits into contiguous weekly chunks with no gaps.
    """
    start_dt, end_dt = _ts(start), _ts(end)
    if end_dt <= start_dt:
        raise ValueError(f"end must be after start, got {start} .. {end}")
    step = timedelta(days=max_days)
    windows: list[tuple[str, str]] = []
    cursor = start_dt
    while cursor < end_dt:
        nxt = min(cursor + step, end_dt)
        windows.append((cursor.strftime("%Y-%m-%dT%H:%MZ"), nxt.strftime("%Y-%m-%dT%H:%MZ")))
        cursor = nxt
    return windows
