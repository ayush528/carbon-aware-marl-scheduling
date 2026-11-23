"""The scheduler replay must be reproducible, self-consistent and honest.

The dashboard explains a decision that a committed planner actually made. These
tests pin the contract:

* the replay's recording agrees with ``BlockPlanner`` on every slot;
* the numbers decompose (per-site carbon sums to the fleet total, shares sum to
  100);
* every alternative is classified and every cited quantity exists in the frame;
* a missing artifact yields ``available: false`` and a reason, never a schedule;
* the cache is keyed by the configuration and the result is identical on a hit.
"""

from __future__ import annotations

import pytest

from viz.backend import schedule


@pytest.fixture(scope="module")
def payload(tmp_path_factory: pytest.TempPathFactory) -> dict:
    schedule._MEM.clear()
    schedule.CACHE_DIR = tmp_path_factory.mktemp("viz-cache")
    meta = schedule.meta()
    assert meta["available"], meta["reason"]
    return schedule.replay(
        week=meta["defaults"]["week"],
        fleet="capacity_bound",
        price=meta["defaults"]["price"],
        robust=0.0,
        reserve=0.2,
        reserve_level=None,
    )


def test_meta_reports_the_committed_knobs(monkeypatch: pytest.MonkeyPatch) -> None:
    meta = schedule.meta()
    assert meta["available"], meta["reason"]
    assert meta["exp_id"] == "exp017-hybrid-scheduler"
    assert len(meta["weeks"]) == 12
    assert meta["weeks"] == sorted(meta["weeks"])
    assert {row["name"] for row in meta["fleets"]} == {"capacity_bound", "slack"}
    assert [row["slots"] for row in meta["deadlines"]] == [2, 4, 8, 16]
    assert meta["prices"] == [0.1, 0.3, 1.0]
    assert meta["objective"]["formula"] == "carbon_kg + price * missed_gpu_hours"
    assert meta["defaults"]["week"] == "2024-12-23"
    # Every site carries a map position and the assumption label's explanation.
    assert len(meta["sites"]) == 4
    for site in meta["sites"]:
        assert site["short"] and site["lat"] and site["lon"]
        assert "assumption" in site["geo_note"] or "representative" in site["geo_note"]


def test_band_evidence_states_it_changes_no_decision() -> None:
    evidence = schedule.meta()["band"]["evidence"]
    assert evidence["available"] is True
    assert evidence["relative_flipped_slots"] == 0
    assert evidence["relative_flipped_pct"] == 0.0
    assert evidence["n_slots"] >= 300


def test_calibrated_reserve_comes_from_the_exp018_record() -> None:
    levels = schedule.meta()["reserve_options"]["calibrated"]["levels"]
    assert [row["level"] for row in levels] == [0.5, 0.9, 0.95]
    assert all(row["reserve_gpu_s_per_site_slot"] is not None for row in levels)
    # The reserve must be a real quantity, not a percentage of capacity.
    assert levels[0]["reserve_gpu_s_per_site_slot"] > 0


def test_replay_available_and_matches_the_planner(payload: dict) -> None:
    assert payload["available"], payload["reason"]
    assert payload["trace"]["matches_planner"] is True
    assert payload["trace"]["mismatch_slots"] == []
    assert payload["trace"]["n_slots"] == payload["n_slots"] == 336
    assert payload["week"] == "2024-12-23"


def test_frames_are_complete_and_capacity_is_positive(payload: dict) -> None:
    frames = payload["frames"]
    assert [frame["slot"] for frame in frames] == list(range(336))
    for frame in frames:
        assert len(frame["forecast_g_per_kwh"]) == 4
        assert len(frame["band_g_per_kwh"]) == 4
        assert len(frame["realized_g_per_kwh"]) == 4
        assert len(frame["served_gpu_s"]) == 4
        assert all(capacity > 0 for capacity in frame["capacity_gpu_s"])
        assert frame["queue"]["total_gpu_s"] >= 0


def test_site_carbon_decomposes_to_the_fleet_total(payload: dict) -> None:
    sites = payload["sites"]
    assert len(sites) == 4
    total = sum(row["carbon_kg"] for row in sites)
    assert total == pytest.approx(payload["summary"]["carbon_kg"], abs=0.02)
    assert sum(row["served_share_pct"] for row in sites) == pytest.approx(100.0, abs=0.05)
    assert sum(row["carbon_share_pct"] for row in sites) == pytest.approx(100.0, abs=0.05)
    assert sum(row["served_gpu_s"] for row in sites) == pytest.approx(
        payload["summary"]["served_gpu_s"], abs=1.0
    )


def test_objective_uses_the_displayed_price(payload: dict) -> None:
    summary = payload["summary"]
    expected = summary["carbon_kg"] + summary["price"] * summary["missed_gpu_hours"]
    assert summary["objective"] == pytest.approx(expected, abs=1e-3)


def test_selected_slot_has_decisions_and_a_selected_request(payload: dict) -> None:
    decision = payload["slot_decision"]
    assert decision["decisions"]
    selected = payload["selection"]["item"]
    assert selected in {row["id"] for row in decision["decisions"]}
    assert payload["selection"]["slot"] == decision["slot"]
    # The default is derived from the replay: the busiest placement.
    busiest = max(payload["frames"], key=lambda frame: (sum(frame["served_gpu_s"]), -frame["slot"]))
    assert decision["slot"] == busiest["slot"]
    selected_row = next(row for row in decision["decisions"] if row["id"] == selected)
    assert selected_row["chosen"] is not None


def test_every_decision_has_classified_alternatives(payload: dict) -> None:
    for row in payload["slot_decision"]["decisions"]:
        if row["chosen"] is None:
            # Nothing was placed, so there is no block to compare candidates in.
            assert row["alternatives"] == []
            assert row["explanation"]["code"] in {"expired", "no_capacity", "unplaceable"}
            continue
        assert len(row["alternatives"]) == 4
        assert {alt["status"] for alt in row["alternatives"]} <= {"chosen", "rejected"}
        assert any(alt["status"] == "chosen" for alt in row["alternatives"])
        for alt in row["alternatives"]:
            assert alt["code"] in {
                "chosen",
                "spill",
                "pricier",
                "full",
                "tie",
                "cheaper_unused",
                "illegal",
            }
            assert alt["reason"]
        # Every reason that is about price quotes the price the row displays;
        # "full" and "illegal" are about capacity and the window instead.
        for alt in row["alternatives"]:
            if alt["code"] in {"chosen", "spill", "pricier", "tie", "cheaper_unused"}:
                assert f"{alt['price_g_per_kwh']:.1f} g/kWh" in alt["reason"]


def test_every_block_is_inside_its_deadline_window(payload: dict) -> None:
    decisions = payload["slot_decision"]["decisions"]
    for row in decisions:
        assert row["last_legal_slot"] == row["arrival"] + row["deadline_slots"] - 1
        if row["chosen"] is not None:
            for block in row["chosen"]["blocks"]:
                assert row["arrival"] <= block["slot"] <= row["last_legal_slot"]
        now = sum(
            block["take_gpu_s"]
            for block in (row["chosen"] or {}).get("blocks", [])
            if block["slot"] == payload["slot_decision"]["slot"]
        )
        assert now == pytest.approx(row["executed_now_gpu_s"], abs=0.11)


def test_explanations_match_the_recorded_split(payload: dict) -> None:
    for row in payload["slot_decision"]["decisions"]:
        code = row["explanation"]["code"]
        split = row["split"]
        if split["expired"]:
            assert code == "expired"
        elif split["deferred"] and not split["executed_now"]:
            assert code.startswith("deferred_")
        elif split["executed_now"]:
            assert code in {"served_now", "served_now_spilled", "split_now_and_later"}
        assert row["explanation"]["detail"]
        assert row["explanation"]["headline"]


def test_deferred_requests_cite_a_later_legal_slot(payload: dict) -> None:
    deferred = [row for row in payload["slot_decision"]["decisions"] if row["split"]["deferred"]]
    assert deferred, "the default slot should include some deferral"
    for row in deferred:
        assert row["chosen"] is not None
        assert row["chosen"]["slot"] > payload["slot_decision"]["slot"]
        assert row["chosen"]["slot"] <= row["last_legal_slot"]


def test_queue_groups_the_backlog_by_deadline_class(payload: dict) -> None:
    queue = payload["slot_decision"]["queue"]
    assert len(queue["by_class"]) == 4
    assert [row["label"] for row in queue["by_class"]] == ["1 h", "2 h", "4 h", "8 h"]
    assert queue["gpu_s"] == pytest.approx(sum(row["gpu_s"] for row in queue["by_class"]), abs=0.2)
    assert queue["items"]
    for row in queue["by_class"]:
        assert all(item["class_index"] == row["class_index"] for item in row["items"])


def test_request_ids_are_derived_and_unique(payload: dict) -> None:
    ids = [row["id"] for row in payload["slot_decision"]["decisions"]]
    assert len(ids) == len(set(ids))
    for value in ids:
        assert value.startswith("class-")
        assert "/slot-" in value


def test_cache_hit_returns_the_same_trace(payload: dict) -> None:
    again = schedule.replay_raw(
        week="2024-12-23",
        fleet="capacity_bound",
        robust=0.0,
        reserve=0.2,
        reserve_gpu_s=0.0,
        arrival_forecast=0,
        price=0.1,
    )
    assert again["cache"]["hit"] is True
    assert again["summary"] == payload["summary"]


def test_calibrated_reserve_changes_the_plan(payload: dict) -> None:
    calibrated = schedule.replay(
        week="2024-12-23",
        fleet="capacity_bound",
        price=0.1,
        robust=0.0,
        reserve=0.0,
        reserve_level=0.9,
    )
    assert calibrated["knobs"]["reserve_mode"] == "calibrated"
    assert calibrated["knobs"]["reserve_source"]["exp_id"] == "exp018-arrival-reserve"
    assert calibrated["trace"]["matches_planner"] is True
    # A different reserve is a different plan, not a relabelled one.
    assert calibrated["summary"] != payload["summary"]


def test_robust_band_changes_the_price_the_planner_sees(payload: dict) -> None:
    robust = schedule.replay(
        week="2024-12-23",
        fleet="capacity_bound",
        price=0.1,
        robust=1.0,
        reserve=0.2,
        reserve_level=None,
    )
    base = schedule.replay(
        week="2024-12-23",
        fleet="capacity_bound",
        price=0.1,
        robust=0.0,
        reserve=0.2,
        reserve_level=None,
    )
    assert robust["knobs"]["robust"] == 1.0
    assert robust["frames"][0]["price_g_per_kwh"] != base["frames"][0]["price_g_per_kwh"]


def test_invalid_requests_are_rejected_with_a_reason() -> None:
    with pytest.raises(ValueError, match="held-out weeks"):
        schedule.replay(
            week="1999-01-01",
            fleet="capacity_bound",
            price=0.1,
            robust=0.0,
            reserve=0.2,
            reserve_level=None,
        )
    with pytest.raises(ValueError, match="fleet"):
        schedule.replay(
            week="2024-12-23",
            fleet="nope",
            price=0.1,
            robust=0.0,
            reserve=0.2,
            reserve_level=None,
        )
    with pytest.raises(ValueError, match="calibrated reserve"):
        schedule.replay(
            week="2024-12-23",
            fleet="capacity_bound",
            price=0.1,
            robust=0.0,
            reserve=0.2,
            reserve_level=0.77,
        )


def test_missing_demand_artifact_is_reported_not_fabricated(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(schedule, "DEMAND_ARTIFACT", tmp_path / "nope.json")
    tokens, note = schedule._load_demand()
    assert tokens is None
    assert "missing" in note.lower()
    assert "build_derived" in note


def test_replay_refuses_to_run_without_demand(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # Clear both caches: a cached trace would otherwise be served.
    monkeypatch.setattr(schedule, "_MEM", {})
    monkeypatch.setattr(schedule, "CACHE_DIR", tmp_path / "empty-cache")
    monkeypatch.setattr(
        schedule,
        "_series_and_tokens",
        lambda: (None, None, "demand artifact missing"),
    )
    payload = schedule.replay(
        week="2024-12-23",
        fleet="capacity_bound",
        price=0.1,
        robust=0.0,
        reserve=0.2,
        reserve_level=None,
    )
    assert payload["available"] is False
    assert payload["reason"] == "demand artifact missing"
    assert payload["meta"]["available"] is True
