"""Tests for exp008's aggregation (no simulator runs)."""

from __future__ import annotations

from typing import Any

import pytest

from carbon_scheduling.experiments import exp008_sustaincluster_baseline as exp008


def _row(controller: str, kind: str, carbon: float, sla: float) -> dict[str, Any]:
    return {
        "controller": controller,
        "kind": kind,
        "sustaincluster_commit": "deadbeef",
        "checkpoint": f"checkpoints/{controller}/best_eval_checkpoint.pth",
        "carbon_kg": carbon,
        "energy_kwh": 1.0,
        "energy_cost_usd": 1.0,
        "transmission_cost_usd": 1.0,
        "sla_violation_rate": sla,
        "tasks_finished": 1,
        "mean_gpu_util_percent": 1.0,
    }


@pytest.fixture
def fake_runners(monkeypatch: pytest.MonkeyPatch):
    rows = [
        _row("round_robin", "rule_based", 100.0, 0.00),
        _row("lowest_carbon", "rule_based", 90.0, 0.01),
        _row("sac_multiaction_defer", "sac_checkpoint", 95.0, 0.27),
        _row("sac_single_action", "sac_checkpoint", 92.0, 0.49),
    ]

    def fake_strategy(checkout, python, strategy, *, days, seed, out_path):
        return next(r for r in rows if r["controller"] == strategy)

    def fake_checkpoint(checkout, python, checkpoint, *, days, seed, out_path, device):
        slug = checkpoint.split("/")[-2]
        return next(r for r in rows if r["controller"] == slug)

    monkeypatch.setattr(exp008.sustaincluster, "checkout_dir", lambda _cfg: "/fake")
    monkeypatch.setattr(exp008.sustaincluster, "resolve_python", lambda *_: "python")
    monkeypatch.setattr(exp008.sustaincluster, "run_strategy", fake_strategy)
    monkeypatch.setattr(exp008.sustaincluster, "run_checkpoint", fake_checkpoint)
    return rows


def _config() -> dict[str, Any]:
    return {
        "id": "exp008-test",
        "seed": 42,
        "sustaincluster": {
            "checkout": "/fake",
            "days": 7,
            "device": "cpu",
            "baselines": ["round_robin", "lowest_carbon"],
            "checkpoints": [
                "checkpoints/sac_multiaction_defer/best_eval_checkpoint.pth",
                "checkpoints/sac_single_action/best_eval_checkpoint.pth",
            ],
        },
    }


def test_carbon_deltas_are_relative_to_round_robin(fake_runners) -> None:
    metrics = exp008.run(_config())
    assert metrics["carbon_vs_round_robin_pct"]["lowest_carbon"] == pytest.approx(-10.0)
    assert metrics["carbon_vs_round_robin_pct"]["sac:sac_multiaction_defer"] == pytest.approx(-5.0)


def test_best_carbon_and_sla_extremes_are_reported_per_kind(fake_runners) -> None:
    metrics = exp008.run(_config())
    assert metrics["best_carbon_controller"] == "lowest_carbon"
    assert metrics["rbc_min_sla_violation_rate"] == pytest.approx(0.0)
    assert metrics["sac_min_sla_violation_rate"] == pytest.approx(0.27)
    assert metrics["sac_best_carbon_kg"] == pytest.approx(92.0)


def test_controller_rows_are_keyed_by_kind(fake_runners) -> None:
    rows = exp008.run(_config())["controllers"]
    assert set(rows) == {
        "round_robin",
        "lowest_carbon",
        "sac:sac_multiaction_defer",
        "sac:sac_single_action",
    }
