"""Tests for the NESO regional carbon-intensity puller (Phase 1, data freeze).

Independent source of truth for expected values: the verified data-audit
samples in docs/datasets/data-audit/downloads/ and the NESO API docs
(https://docs.carbonintensity.org.uk). HTTP is injected -- no test touches
the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from carbon_scheduling.data.neso import (
    LONDON_REGION_ID,
    REGIONS,
    chunk_windows,
    fetch_national,
    fetch_regional,
    load_slot_json,
    parse_single_region,
)

AUDIT = Path(__file__).resolve().parents[1] / "docs/datasets/data-audit/downloads"


# --- seam 1: window chunking -------------------------------------------------


def test_chunk_windows_one_week_is_single_chunk() -> None:
    assert chunk_windows("2025-01-01T00:00Z", "2025-01-08T00:00Z") == [
        ("2025-01-01T00:00Z", "2025-01-08T00:00Z")
    ]


def test_chunk_windows_month_becomes_weekly_chunks() -> None:
    windows = chunk_windows("2025-01-01T00:00Z", "2025-02-01T00:00Z")
    # Jan has 31 days: 7+7+7+7+3
    assert len(windows) == 5
    assert windows[0][0] == "2025-01-01T00:00Z"
    assert windows[-1][1] == "2025-02-01T00:00Z"
    # contiguous: each window starts where the previous ended
    for (_, end), (start, _) in zip(windows, windows[1:], strict=False):
        assert start == end


def test_chunk_windows_rejects_backwards_range() -> None:
    with pytest.raises(ValueError):
        chunk_windows("2025-01-08T00:00Z", "2025-01-01T00:00Z")


# --- seam 4: region registry (from the verified audit sample) ----------------


def test_region_registry_matches_verified_audit_sample() -> None:
    sample = json.loads((AUDIT / "uk_regional_all_2025-01-01_to_2025-01-02.json").read_text())
    from_sample = {r["regionid"]: r["shortname"] for r in sample["data"][0]["regions"]}
    assert REGIONS == from_sample  # exact match, ids 1..18 incl. aggregates


def test_london_is_region_13() -> None:
    assert LONDON_REGION_ID == 13
    assert REGIONS[13] == "London"


def test_dno_regions_are_first_fourteen() -> None:
    assert len(REGIONS) == 18
    assert set(REGIONS) == set(range(1, 19))


# --- seam 2: fetch_regional (injected HTTP; no network) -----------------------


def _fake_http(responses: list[tuple[int, dict | None]]):
    calls: list[str] = []

    def get(url: str) -> tuple[int, dict | None]:
        calls.append(url)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    get.calls = calls  # type: ignore[attr-defined]
    return get


def test_fetch_regional_builds_correct_urls_and_concatenates() -> None:
    window_a = {
        "data": {
            "shortname": "London",
            "region_id": 13,
            "data": [
                {
                    "from": "2025-01-01T00:00Z",
                    "to": "2025-01-01T00:30Z",
                    "intensity": {"forecast": 50, "actual": 48, "index": "low"},
                }
            ],
        }
    }
    window_b = {
        "data": {
            "shortname": "London",
            "region_id": 13,
            "data": [
                {
                    "from": "2025-01-08T00:00Z",
                    "to": "2025-01-08T00:30Z",
                    "intensity": {"forecast": 60, "actual": None, "index": "low"},
                }
            ],
        }
    }
    http = _fake_http([(200, window_a), (200, window_b)])

    records = fetch_regional(
        13,
        "2025-01-01T00:00Z",
        "2025-01-10T00:00Z",
        http_get=http,
        sleep=lambda _s: None,
    )

    assert len(http.calls) == 2  # 9 days -> two weekly windows
    assert "/regional/intensity/2025-01-01T00:00Z/2025-01-08T00:00Z/regionid/13" in http.calls[0]
    assert "/regional/intensity/2025-01-08T00:00Z/2025-01-10T00:00Z/regionid/13" in http.calls[1]
    assert [r["forecast"] for r in records] == [50, 60]
    assert records[1]["actual"] is None


def test_fetch_regional_retries_then_succeeds() -> None:
    window = {
        "data": {
            "data": [
                {
                    "from": "2025-01-01T00:00Z",
                    "to": "2025-01-01T00:30Z",
                    "intensity": {"forecast": 50, "actual": 48, "index": "low"},
                }
            ]
        }
    }
    http = _fake_http([(503, None), (503, None), (200, window)])
    naps: list[float] = []

    records = fetch_regional(
        13,
        "2025-01-01T00:00Z",
        "2025-01-02T00:00Z",
        http_get=http,
        retries=3,
        sleep=naps.append,
    )

    assert len(records) == 1
    assert len(http.calls) == 3  # two 503s, then success
    assert naps == [2.0, 2.0]


def test_fetch_regional_gives_up_after_retries() -> None:
    http = _fake_http([(500, None)])
    with pytest.raises(RuntimeError, match="3 attempts"):
        fetch_regional(
            13,
            "2025-01-01T00:00Z",
            "2025-01-02T00:00Z",
            http_get=http,
            retries=3,
            sleep=lambda _s: None,
        )


def test_fetch_regional_rejects_unknown_region() -> None:
    with pytest.raises(ValueError, match="unknown region id"):
        fetch_regional(99, "2025-01-01T00:00Z", "2025-01-02T00:00Z", http_get=_fake_http([]))


# --- national fetcher (injected HTTP; no network) -----------------------------


def test_fetch_national_uses_national_endpoint_and_parses() -> None:
    window = {
        "data": [
            {
                "from": "2025-02-01T00:00Z",
                "to": "2025-02-01T00:30Z",
                "intensity": {"forecast": 100, "actual": 98, "index": "low"},
            },
            {
                "from": "2025-02-01T00:30Z",
                "to": "2025-02-01T01:00Z",
                "intensity": {"forecast": 90},
            },  # actual omitted entirely
        ]
    }
    http = _fake_http([(200, window)])

    records = fetch_national("2025-02-01T00:00Z", "2025-02-04T00:00Z", http_get=http)

    assert len(http.calls) == 1  # 3 days -> single window
    assert http.calls[0].startswith("https://api.carbonintensity.org.uk/intensity/")
    assert "/regional/" not in http.calls[0]
    assert records[0] == {
        "from": "2025-02-01T00:00Z",
        "to": "2025-02-01T00:30Z",
        "forecast": 100,
        "actual": 98,
        "index": "low",
    }
    assert records[1]["actual"] is None  # omitted key -> None


def test_fetch_national_chunks_month_weekly() -> None:
    http = _fake_http(
        [
            (
                200,
                {
                    "data": [
                        {
                            "from": "x",
                            "to": "y",
                            "intensity": {"forecast": 1, "actual": 1, "index": "low"},
                        }
                    ]
                },
            )
        ]
    )
    records = fetch_national("2025-02-01T00:00Z", "2025-03-01T00:00Z", http_get=http)
    assert len(http.calls) == 4  # 28 days -> 7+7+7+7
    assert len(records) == 4  # one row per (repeated) fake window


# --- seam 3: parsing, against the committed real payload ----------------------


@pytest.mark.skipif(
    not (AUDIT / "uk_region13_london_2025-01_full_month.json").is_file(),
    reason="audit sample not present",
)
def test_parse_london_month_sample() -> None:
    payload = json.loads((AUDIT / "uk_region13_london_2025-01_full_month.json").read_text())
    records = parse_single_region(payload)
    # Verified literals from the audit download (2026-11-04). Note: the
    # regional feed ships 1,476 slots for January, not the national 1,493.
    assert len(records) == 1476
    assert records[0]["from"] == "2024-12-31T23:30Z"
    assert records[-1]["to"] == "2025-02-01T00:00Z"


# --- seam 4: slot-JSON loader (both producer shapes) ---------------------------


def test_load_slot_json_reads_api_shape(tmp_path: Path) -> None:
    # audit downloads: rows carry an "intensity" sub-dict
    path = tmp_path / "api.json"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {"from": "f", "to": "t", "intensity": {"forecast": 56, "actual": 54}},
                ]
            }
        )
    )
    assert load_slot_json(path) == [
        {"from": "f", "to": "t", "forecast": 56, "actual": 54, "index": None}
    ]


def test_load_slot_json_reads_normalized_shape(tmp_path: Path) -> None:
    # our pulls: rows already normalized
    path = tmp_path / "norm.json"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {"from": "f", "to": "t", "forecast": 90, "actual": 100, "index": "low"},
                ]
            }
        )
    )
    assert load_slot_json(path) == [
        {"from": "f", "to": "t", "forecast": 90, "actual": 100, "index": "low"}
    ]
