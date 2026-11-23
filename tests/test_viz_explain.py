"""The explanation text must be generated from the numbers it is given.

These tests do not care about style. They pin two properties the dashboard
needs: the reason *code* classifies the decision correctly, and every quantity
the sentence quotes is the quantity in the arguments. If a code could be produced
by a different situation, the dashboard would be explaining the wrong thing.
"""

from __future__ import annotations

import pytest

from viz.backend import explain


def _verdict(**over: object) -> dict:
    base = dict(
        site="Glasgow",
        price=20.0,
        chosen_site="Glasgow",
        chosen_price=20.0,
        take_gpu_s=1000.0,
        volume_gpu_s=1000.0,
        free_gpu_s=5000.0,
        capacity_gpu_s=9000.0,
    )
    base.update(over)
    return explain.candidate_verdict(**base)  # type: ignore[arg-type]


def test_candidate_verdict_chosen_when_it_is_the_cheapest_used_block() -> None:
    verdict = _verdict()
    assert verdict["status"] == "chosen"
    assert verdict["code"] == "chosen"
    assert "Glasgow" in verdict["text"]
    assert "20.0 g/kWh" in verdict["text"]
    assert "5,000 GPU-s free" in verdict["text"]
    assert "1,000 GPU-s" in verdict["text"]


def test_candidate_verdict_pricier_quotes_the_delta_and_the_percentage() -> None:
    verdict = _verdict(site="Cardiff", price=30.0, take_gpu_s=0.0)
    assert verdict["code"] == "pricier"
    assert verdict["status"] == "rejected"
    assert "+10.0 g/kWh" in verdict["text"]
    assert "50.0%" in verdict["text"]
    assert "Cardiff" in verdict["text"]


def test_candidate_verdict_full_only_when_there_is_no_free_capacity() -> None:
    verdict = _verdict(site="Manchester", price=10.0, take_gpu_s=0.0, free_gpu_s=0.0)
    assert verdict["code"] == "full"
    assert "no capacity left" in verdict["text"]


def test_candidate_verdict_reports_a_cheaper_unused_block_instead_of_hiding_it() -> None:
    verdict = _verdict(site="Manchester", price=10.0, take_gpu_s=0.0, free_gpu_s=500.0)
    assert verdict["code"] == "cheaper_unused"
    assert "flagged rather than explained away" in verdict["text"]


def test_candidate_verdict_calls_a_tie_a_tie() -> None:
    verdict = _verdict(site="Manchester", price=20.0, take_gpu_s=0.0)
    assert verdict["code"] == "tie"
    assert "ties" in verdict["text"]


def test_candidate_verdict_marks_a_site_outside_the_window_illegal() -> None:
    verdict = _verdict(legal=False)
    assert verdict["code"] == "illegal"
    assert "deadline window" in verdict["text"]


def _item(**over: object) -> dict:
    base = dict(
        item_id="class-2h/slot-10",
        class_label="2 h",
        volume_gpu_s=1000.0,
        slot=100,
        arrival=10,
        last_legal_slot=103,
        chosen_slot=102,
        chosen_site="Glasgow",
        chosen_price=5.0,
        now_price=22.0,
        executed_now_gpu_s=0.0,
        deferred_gpu_s=1000.0,
        unassigned_gpu_s=0.0,
        spilled=False,
        alternatives=[
            {
                "site": "Glasgow",
                "label": "Glasgow",
                "price": 5.0,
                "status": "chosen",
                "code": "deferred_cheaper",
                "take_gpu_s": 1000.0,
                "free_gpu_s": 9000.0,
                "slot": 102,
            }
        ],
        slot_options=[
            {"slot": 100, "free_gpu_s": 400.0, "min_price_g_per_kwh": 22.0},
            {"slot": 102, "free_gpu_s": 9000.0, "min_price_g_per_kwh": 5.0},
        ],
        slot_label=lambda value: f"slot {value}",
    )
    base.update(over)
    return explain.item_explanation(**base)  # type: ignore[arg-type]


def test_item_explanation_explains_a_cheaper_later_slot() -> None:
    result = _item(
        slot_options=[
            {"slot": 100, "free_gpu_s": 2000.0, "min_price_g_per_kwh": 22.0},
            {"slot": 102, "free_gpu_s": 9000.0, "min_price_g_per_kwh": 5.0},
        ]
    )
    assert result["code"] == "deferred_cheaper"
    assert "1,000 GPU-s" in result["detail"]
    assert "17.0 g/kWh cheaper" in result["detail"]
    assert "Glasgow" in result["detail"]


def test_item_explanation_blames_capacity_when_now_cannot_hold_it() -> None:
    result = _item(now_price=1.0)
    assert result["code"] == "deferred_capacity"
    assert "400 GPU-s free" in result["detail"]
    assert "1,000 GPU-s of work" in result["detail"]


def test_item_explanation_says_when_the_deadline_forced_the_choice() -> None:
    result = _item(
        chosen_slot=103,
        slot_options=[
            {"slot": 100, "free_gpu_s": 2000.0, "min_price_g_per_kwh": 22.0},
            {"slot": 103, "free_gpu_s": 9000.0, "min_price_g_per_kwh": 5.0},
        ],
    )
    assert result["code"] == "deferred_to_deadline"
    assert "last legal slot" in result["detail"]


def test_item_explanation_reports_a_miss_when_the_window_closed() -> None:
    result = _item(slot=104, last_legal_slot=103)
    assert result["code"] == "expired"
    assert result["flags"]["expired"] is True
    assert "counted as a miss" in result["detail"]


def test_item_explanation_reports_running_now_and_its_spill() -> None:
    result = _item(
        chosen_slot=100,
        executed_now_gpu_s=700.0,
        deferred_gpu_s=0.0,
        spilled=True,
        alternatives=[
            {
                "site": "Glasgow",
                "label": "Glasgow",
                "price": 5.0,
                "status": "chosen",
                "code": "chosen",
                "take_gpu_s": 700.0,
                "free_gpu_s": 700.0,
                "slot": 100,
            },
            {
                "site": "London",
                "label": "London",
                "price": 20.0,
                "status": "chosen",
                "code": "spill",
                "take_gpu_s": 300.0,
                "free_gpu_s": 5000.0,
                "slot": 100,
            },
        ],
    )
    assert result["code"] == "served_now_spilled"
    assert result["flags"]["spilled"] is True
    assert "spilled to London" in result["detail"]


def test_item_explanation_never_prints_none() -> None:
    """A missing number must render as an em dash, not the string 'None'."""
    for result in (_item(), _item(slot=104, last_legal_slot=103)):
        assert "None" not in result["detail"]
        assert "None" not in result["headline"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
