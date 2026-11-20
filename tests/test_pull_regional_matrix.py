"""Resumable regional-matrix pull: per-window cache, merge, dedupe.

The NESO API drops connections under load (observed: HTTP 0 on the 34th
window of a year-long pull), and a year is ~57 windows. Losing the whole pull
to one transient failure is avoidable, so each window is cached the moment it
arrives and a re-run reuses it. These tests pin that behaviour with a fake
fetcher -- no network.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pull_regional_matrix.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("pull_regional_matrix", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _row(slot: str, region: int, forecast: int) -> dict[str, Any]:
    return {
        "from": slot,
        "to": slot,
        "regionid": region,
        "shortname": f"R{region}",
        "forecast": forecast,
        "actual": None,
        "index": "low",
    }


@pytest.fixture
def puller():
    return _load_script()


def test_bulk_pull_caches_each_window(puller, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_fetch(start: str, end: str) -> list[dict[str, Any]]:
        calls.append(start)
        return [_row(start, 13, 100), _row(start, 2, 20)]

    rows = puller.bulk_pull(
        "2024-01-01T00:00Z",
        "2024-01-15T00:00Z",
        tmp_path,
        fetch=fake_fetch,
        sleep=lambda _: None,
    )
    assert len(calls) == 2  # 14 days -> two weekly windows
    assert len(rows) == 4
    assert len(list(tmp_path.glob("*.csv"))) == 2


def test_bulk_pull_second_run_fetches_nothing(puller, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_fetch(start: str, _end: str) -> list[dict[str, Any]]:
        calls.append(start)
        return [_row(start, 13, 100)]

    args = ("2024-01-01T00:00Z", "2024-01-15T00:00Z", tmp_path)
    first = puller.bulk_pull(*args, fetch=fake_fetch, sleep=lambda _: None)
    calls.clear()
    second = puller.bulk_pull(*args, fetch=fake_fetch, sleep=lambda _: None)

    assert calls == []  # fully served from cache
    assert second == first


def test_bulk_pull_resumes_after_a_failure(puller, tmp_path: Path) -> None:
    """A window that fails must not poison the ones already cached."""
    fail = {"on": True}

    def flaky_fetch(start: str, _end: str) -> list[dict[str, Any]]:
        if start.startswith("2024-01-08") and fail["on"]:
            raise RuntimeError("HTTP 0")
        return [_row(start, 13, 100)]

    args = ("2024-01-01T00:00Z", "2024-01-15T00:00Z", tmp_path)
    with pytest.raises(RuntimeError):
        puller.bulk_pull(*args, fetch=flaky_fetch, sleep=lambda _: None)
    cached = len(list(tmp_path.glob("*.csv")))
    assert cached == 1  # the first window survived

    fail["on"] = False
    rows = puller.bulk_pull(*args, fetch=flaky_fetch, sleep=lambda _: None)
    assert len(rows) == 2


def test_bulk_pull_does_not_merge_a_half_written_window(puller, tmp_path: Path) -> None:
    """A crash mid-write must leave either no file or a complete one."""

    def dying_fetch(_start: str, _end: str) -> list[dict[str, Any]]:
        raise RuntimeError("HTTP 0")

    with pytest.raises(RuntimeError):
        puller.bulk_pull(
            "2024-01-01T00:00Z",
            "2024-01-08T00:00Z",
            tmp_path,
            fetch=dying_fetch,
            sleep=lambda _: None,
        )
    assert list(tmp_path.iterdir()) == []


def test_merge_dedupes_the_window_boundary_slot(puller, tmp_path: Path) -> None:
    """Adjacent windows repeat their boundary slot; the merged CSV must not."""
    boundary = "2024-01-08T00:00Z"

    def fake_fetch(start: str, _end: str) -> list[dict[str, Any]]:
        if start == "2024-01-01T00:00Z":
            # The first window runs up to the boundary and includes it.
            return [_row(start, 13, 100), _row(boundary, 13, 100)]
        return [_row(start, 13, 999)]  # the next window repeats it

    rows = puller.bulk_pull(
        "2024-01-01T00:00Z",
        "2024-01-15T00:00Z",
        tmp_path,
        fetch=fake_fetch,
        sleep=lambda _: None,
    )
    merged, dropped = puller.dedupe(rows)
    assert dropped == 1
    assert [r["from"] for r in merged] == ["2024-01-01T00:00Z", boundary]
    # First occurrence wins, so the boundary keeps the earlier window's value.
    assert merged[1]["forecast"] == 100
