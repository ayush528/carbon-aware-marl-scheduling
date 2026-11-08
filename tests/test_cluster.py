"""Tests for the cluster energy model (Phase 2, slice 1).

Model (per the study plan, Build item 4): linear idle->peak power per GPU
(NLR measured curves), site PUE (Google priors), energy = power x slot
duration. Demand input is the exp006 per-slot stream: token counts are
slot TOTALS (sums over requests). Demand -> GPU-seconds via a per-GPU
serving throughput; the utilization may exceed 1 (offered load), and a
saturated site draws peak power -- capping is physical, queueing is the
simulator's job.

Hand-worked site used below:
    100 GPUs, idle 100 W, peak 700 W, PUE 1.2, 1000 tokens/s/GPU
    slot = 30 min = 1800 s; available = 100 x 1800 = 180,000 GPU-s

    u = 1000/180000 = 1/180  (1M tokens -> 1000 GPU-s)
      power/GPU = 100 + 600/180 = 103.333 W -> site 12.4 kW -> 6.2 kWh
    u = 0 -> idle: 100 x 100 W x 1.2 x 0.5 h = 6.0 kWh
    u >= 1 -> peak: 100 x 700 W x 1.2 x 0.5 h = 42.0 kWh
"""

from __future__ import annotations

import pytest

from carbon_scheduling.cluster import Site, slot_energy

SITE = Site(
    name="test",
    n_gpus=100,
    gpu_idle_w=100.0,
    gpu_peak_w=700.0,
    pue=1.2,
    tokens_per_gpu_second=1000.0,
)


def demand(requests: int, tokens: int) -> list[dict[str, int | str]]:
    return [
        {
            "from": "2024-05-10T00:00Z",
            "requests": requests,
            "context_tokens": tokens,
            "generated_tokens": 0,
        }
    ]


def test_slot_energy_hand_worked_low_load() -> None:
    # 1,000,000 tokens in the slot -> 1000 GPU-s -> u = 1/180
    rows = slot_energy(demand(1, 1_000_000), SITE)
    assert rows[0]["utilization"] == pytest.approx(1 / 180)
    assert rows[0]["energy_kwh"] == pytest.approx(6.2, rel=1e-6)


def test_slot_energy_zero_demand_draws_idle_through_pue() -> None:
    rows = slot_energy(demand(0, 0), SITE)
    assert rows[0]["utilization"] == 0.0
    assert rows[0]["energy_kwh"] == pytest.approx(6.0, rel=1e-6)


def test_slot_energy_saturated_site_capped_at_peak_power() -> None:
    # 360,000,000 tokens in the slot -> 360,000 GPU-s -> u = 2.0
    rows = slot_energy(demand(1, 360_000_000), SITE)
    assert rows[0]["utilization"] == pytest.approx(2.0)
    assert rows[0]["energy_kwh"] == pytest.approx(42.0, rel=1e-6)


def test_slot_energy_many_slots_preserves_order_and_markers(tmp_path=None) -> None:
    slots = [
        {
            "from": "2024-05-10T00:00Z",
            "requests": 1,
            "context_tokens": 1_800_000,
            "generated_tokens": 0,
        },
        {"from": "2024-05-10T00:30Z", "requests": 0, "context_tokens": 0, "generated_tokens": 0},
    ]
    rows = slot_energy(slots, SITE)
    assert [r["from"] for r in rows] == ["2024-05-10T00:00Z", "2024-05-10T00:30Z"]
    # slot 1: 1.8M tokens = 1800 GPU-s -> u = 1800/180000 = 0.01
    assert rows[0]["utilization"] == pytest.approx(0.01)
    assert rows[1]["utilization"] == 0.0


def test_gpu_seconds_counts_context_and_generated_tokens() -> None:
    slot = [{"from": "t", "requests": 2, "context_tokens": 3000, "generated_tokens": 1000}]
    rows = slot_energy(slot, SITE)
    # 4000 slot tokens / 1000 tok/s = 4 GPU-s of 180,000
    assert rows[0]["utilization"] == pytest.approx(4 / 180_000)


def test_site_rejects_unphysical_spec() -> None:
    with pytest.raises(ValueError):
        Site(
            name="x",
            n_gpus=1,
            gpu_idle_w=700.0,
            gpu_peak_w=100.0,
            pue=1.2,
            tokens_per_gpu_second=1.0,
        )
    with pytest.raises(ValueError):
        Site(
            name="x",
            n_gpus=1,
            gpu_idle_w=100.0,
            gpu_peak_w=700.0,
            pue=0.5,
            tokens_per_gpu_second=1.0,
        )
