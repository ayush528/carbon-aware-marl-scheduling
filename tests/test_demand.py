"""Tests for the Azure LLM trace loader (demand side).

The trace is per-request rows (TIMESTAMP, ContextTokens, GeneratedTokens),
16.8M rows for the real file -- too big to load, so the loader streams and
aggregates. Aggregation unit: half-hour slots, aligned to the NESO carbon
grid so demand and carbon join on one timeline. Idle slots appear as
zero-request rows (a gap in arrivals is real demand information).

Hand-worked example used below (slot = 30 min, trace starting 00:00):
    00:00:00  1 request   -> slot 00:00
    00:29:59  1 request   -> slot 00:00  (boundary: before 00:30)
    00:59:00  1 request   -> slot 00:30  (boundary: before 01:00)
    01:00:00  (nothing)   -> slot 01:00 is zero-filled
    01:59:00  2 requests  -> slot 01:30
"""

from __future__ import annotations

from pathlib import Path

import pytest

from carbon_scheduling.demand import requests_per_slot

ROWS = [
    ("2024-05-10 00:00:00.009930+00:00", 2162, 5),
    ("2024-05-10 00:29:59.000001+00:00", 100, 6),
    ("2024-05-10 00:59:00.500000+00:00", 300, 40),
    ("2024-05-10 01:59:00.000000+00:00", 50, 7),
    ("2024-05-10 01:59:59.999999+00:00", 60, 8),
]


def write_trace(tmp_path: Path, rows: list[tuple[str, int, int]]) -> Path:
    path = tmp_path / "trace.csv"
    lines = ["TIMESTAMP,ContextTokens,GeneratedTokens"]
    lines += [f"{ts},{ctx},{gen}" for ts, ctx, gen in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_requests_per_slot_buckets_by_half_hour_and_zero_fills(tmp_path: Path) -> None:
    path = write_trace(tmp_path, ROWS)
    slots = requests_per_slot(path)
    assert slots == [
        {
            "from": "2024-05-10T00:00Z",
            "requests": 2,
            "context_tokens": 2262,
            "generated_tokens": 11,
        },
        {"from": "2024-05-10T00:30Z", "requests": 1, "context_tokens": 300, "generated_tokens": 40},
        {"from": "2024-05-10T01:00Z", "requests": 0, "context_tokens": 0, "generated_tokens": 0},
        {"from": "2024-05-10T01:30Z", "requests": 2, "context_tokens": 110, "generated_tokens": 15},
    ]


def test_requests_per_slot_span_days_uses_utc_markers(tmp_path: Path) -> None:
    path = write_trace(
        tmp_path,
        [
            ("2024-05-10 23:30:00.000000+00:00", 10, 1),
            ("2024-05-11 00:00:00.000000+00:00", 20, 2),
        ],
    )
    slots = requests_per_slot(path)
    assert [s["from"] for s in slots] == ["2024-05-10T23:30Z", "2024-05-11T00:00Z"]
    assert [s["requests"] for s in slots] == [1, 1]


def test_requests_per_slot_slot_minutes_parameter(tmp_path: Path) -> None:
    path = write_trace(tmp_path, ROWS[:3])  # 00:00, 00:29, 00:59
    # 00:59 falls inside the 00:00-01:00 hour slot
    slots = requests_per_slot(path, slot_minutes=60)
    assert slots == [
        {
            "from": "2024-05-10T00:00Z",
            "requests": 3,
            "context_tokens": 2562,
            "generated_tokens": 51,
        },
    ]


def test_requests_per_slot_empty_trace_gives_no_slots(tmp_path: Path) -> None:
    path = write_trace(tmp_path, [])
    assert requests_per_slot(path) == []


def test_requests_per_slot_rejects_bad_row(tmp_path: Path) -> None:
    path = tmp_path / "trace.csv"
    path.write_text("TIMESTAMP,ContextTokens,GeneratedTokens\nnot-a-time,10,5\n")
    with pytest.raises(ValueError):
        requests_per_slot(path)
