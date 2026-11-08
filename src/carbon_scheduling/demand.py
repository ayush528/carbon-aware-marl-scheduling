"""Demand-side loading: Azure LLM inference traces -> per-slot demand.

The trace (`AzureLLMInferenceTrace_code_1week.csv`, 16.8M requests, CC-BY-4.0)
is per-request rows -- far too big to hold in memory, so aggregation streams
line by line (stdlib csv, ADR-0002). The aggregation unit is a configurable
slot (default 30 minutes) aligned to the NESO carbon-intensity grid, so the
Phase 2 simulator joins demand and carbon on one timeline.

Slots with no arrivals are zero-filled: a gap in the arrival stream is real
demand information for scheduling, not missing data.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

SLOT_MINUTES = 30  # NESO half-hourly grid


def _parse_timestamp(raw: str) -> datetime:
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"unparseable trace timestamp: {raw!r}") from exc
    if ts.tzinfo is None:  # trace is UTC; offset-free cells are not expected
        raise ValueError(f"trace timestamp without UTC offset: {raw!r}")
    return ts.astimezone(UTC)


def _slot_start(ts: datetime, slot: timedelta) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return epoch + ((ts - epoch) // slot) * slot


def requests_per_slot(
    path: str | Path,
    slot_minutes: int = SLOT_MINUTES,
) -> list[dict[str, int | str]]:
    """Stream a trace CSV, aggregate to per-slot demand.

    Returns one record per slot covering [first arrival, last arrival]:

        {"from": "2024-05-10T00:00Z", "requests": n,
         "context_tokens": n, "generated_tokens": n}

    Zero-request slots appear in the span with zero counters.
    """
    slot = timedelta(minutes=slot_minutes)
    counts: dict[datetime, list[int]] = {}  # slot start -> [requests, ctx, gen]
    for row in csv.DictReader(Path(path).open(newline="")):
        ts = _parse_timestamp(row["TIMESTAMP"])
        start = _slot_start(ts, slot)
        acc = counts.setdefault(start, [0, 0, 0])
        acc[0] += 1
        acc[1] += int(row["ContextTokens"])
        acc[2] += int(row["GeneratedTokens"])

    slots: list[dict[str, int | str]] = []
    if counts:
        first, last = min(counts), max(counts)
        cursor = first
        while cursor <= last:
            requests, ctx, gen = counts.get(cursor, [0, 0, 0])
            slots.append(
                {
                    "from": cursor.strftime("%Y-%m-%dT%H:%MZ"),
                    "requests": requests,
                    "context_tokens": ctx,
                    "generated_tokens": gen,
                }
            )
            cursor += slot
    return slots
