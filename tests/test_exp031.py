"""Tests for exp031's demand transformations.

The experiment's claim is "the saving is not an artefact of one week", so the
variants must be what they say they are: volume changes must change volume,
reorderings must preserve it, and everything must be reproducible from the seed.
"""

from __future__ import annotations

import numpy as np
import pytest

from carbon_scheduling.experiments.exp031_demand_robustness import demand_variants


def _tokens() -> np.ndarray:
    # Seven days of half-hour slots with a clear diurnal shape.
    slot = np.arange(336)
    return 1000.0 + 500.0 * np.sin(2 * np.pi * (slot % 48) / 48)


def test_real_variant_is_a_copy_not_an_alias() -> None:
    tokens = _tokens()
    variants = demand_variants(tokens, seed=42)
    assert np.array_equal(variants["real"], tokens)
    assert variants["real"] is not tokens


def test_volume_scaling_changes_the_total_by_exactly_the_factor() -> None:
    tokens = _tokens()
    variants = demand_variants(tokens, seed=42)
    assert variants["scale_0.5"].sum() == pytest.approx(tokens.sum() * 0.5)
    assert variants["scale_2.0"].sum() == pytest.approx(tokens.sum() * 2.0)


def test_reorderings_preserve_total_volume() -> None:
    tokens = _tokens()
    variants = demand_variants(tokens, seed=42)
    for name in ("shift_12h", "day_shuffle"):
        assert variants[name].sum() == pytest.approx(tokens.sum()), name
        assert len(variants[name]) == len(tokens)


def test_shift_is_a_rotation_by_half_a_day() -> None:
    tokens = _tokens()
    variants = demand_variants(tokens, seed=42)
    assert np.array_equal(variants["shift_12h"], np.roll(tokens, 24))


def test_day_shuffle_keeps_each_day_intact() -> None:
    tokens = _tokens()
    variants = demand_variants(tokens, seed=42)
    original_days = {tuple(tokens[d * 48 : (d + 1) * 48]) for d in range(7)}
    shuffled_days = {tuple(variants["day_shuffle"][d * 48 : (d + 1) * 48]) for d in range(7)}
    assert shuffled_days == original_days


def test_bootstrap_is_reproducible_and_actually_different() -> None:
    tokens = _tokens()
    a = demand_variants(tokens, seed=42)["block_bootstrap"]
    b = demand_variants(tokens, seed=42)["block_bootstrap"]
    c = demand_variants(tokens, seed=7)["block_bootstrap"]
    assert np.array_equal(a, b)
    assert not np.array_equal(a, tokens)
    assert not np.array_equal(a, c)
    assert len(a) == len(tokens)
