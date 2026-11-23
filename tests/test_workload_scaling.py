"""exp028's arrival-rate transformation: no invented work, no accidental loss."""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.sim.workload_scaling import scale_slots


def _slots() -> list[list[np.ndarray]]:
    return [[np.array([f"j{s}_{i}", float(i)]) for i in range(n)] for s, n in enumerate([4, 8, 2])]


def test_scale_one_is_identity() -> None:
    slots = _slots()
    assert _names(scale_slots(slots, scale=1.0, seed=42)) == _names(slots)


def test_halving_and_doubling_change_counts() -> None:
    slots = _slots()
    assert [len(x) for x in scale_slots(slots, scale=0.5, seed=42)] == [2, 4, 1]
    assert [len(x) for x in scale_slots(slots, scale=2.0, seed=42)] == [8, 16, 4]


def test_every_returned_task_came_from_the_input() -> None:
    slots = _slots()
    original = {str(t[0]) for slot in slots for t in slot}
    for scale in (0.25, 0.5, 2.0, 3.0):
        out = scale_slots(slots, scale=scale, seed=7)
        names = {str(t[0]).split("_r")[0] for slot in out for t in slot}
        assert names <= original


def _names(slots: object) -> list[list[str]]:
    return [[str(task[0]) for task in slot] for slot in slots]  # type: ignore[index]


def test_reproducible_from_seed_and_sensitive_to_it() -> None:
    slots = _slots()
    a = _names(scale_slots(slots, scale=2.0, seed=42))
    assert a == _names(scale_slots(slots, scale=2.0, seed=42))
    assert a != _names(scale_slots(slots, scale=2.0, seed=7))


def test_empty_slot_stays_empty_and_nonzero_never_becomes_empty() -> None:
    slots = [[], [np.array(["only", 1.0])]]
    assert _names(scale_slots(slots, scale=0.01, seed=1)) == [[], ["only"]]


def test_rejects_nonpositive_scale() -> None:
    with pytest.raises(ValueError):
        scale_slots(_slots(), scale=0, seed=1)
