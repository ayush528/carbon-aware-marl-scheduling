"""Tests for the read-only experiment API.

The API is a projection of committed artifacts, so the tests assert two things:
the shapes the frontend depends on, and that the numbers equal the run records
(rather than something recomputed differently here).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api import content, repo
from services.api.main import app

client = TestClient(app)


def test_health_reports_experiments_and_runs() -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["experiments"] == len(repo.experiment_ids())
    assert body["experiments_with_runs"] >= 1


def test_meta_serves_the_legend_the_frontend_renders() -> None:
    body = client.get("/api/meta").json()
    assert [item["key"] for item in body["legend"]] == [
        "verified",
        "inspected",
        "modelled",
        "assumption",
        "next",
    ]
    assert body["project"]["title"]
    assert body["claim"]["rules"]


def test_experiments_list_every_registry_entry_in_order() -> None:
    body = client.get("/api/experiments").json()
    ids = [row["id"] for row in body["experiments"]]
    assert ids == repo.experiment_ids()
    assert body["count"] == len(ids)
    ran = [row for row in body["experiments"] if row["run"]]
    assert ran, "at least one experiment should have a run record"


def test_experiments_summary_numbers_match_the_run_record() -> None:
    rows = {row["id"]: row for row in client.get("/api/experiments").json()["experiments"]}
    uk = rows["exp009-uk-sites"]
    metrics = repo.metrics_of("exp009-uk-sites")
    delta = metrics["carbon_vs_round_robin_pct"]["lowest_carbon"]
    assert any(value["value"] == f"{delta:+.2f}%" for value in uk["summary"])
    # Run metadata is the record's, not the clock's.
    assert uk["run"]["git_sha"] == repo.latest_run("exp009-uk-sites")["manifest"]["git_sha"]


def test_single_experiment_includes_config_manifest_and_history() -> None:
    body = client.get("/api/experiments/exp009-uk-sites").json()
    assert body["config"]["sites"][0]["location"] == "GB-London"
    assert body["run"]["manifest"]["seed"] == 42
    assert isinstance(body["runs"], list) and body["runs"]


def test_unknown_experiment_is_404() -> None:
    response = client.get("/api/experiments/exp999-nope")
    assert response.status_code == 404


def test_data_sorts_regions_by_intensity_and_reports_the_spread() -> None:
    body = client.get("/api/data").json()
    assert body["sources"] and body["gaps"]
    values = [row["input_mean_gco2_per_kwh"] for row in body["regions"]]
    assert values == sorted(values)
    assert body["regions"][0]["site"] == "GB-SouthScotland"
    assert body["regions"][-1]["site"] == "GB-SouthWales"
    assert body["spread_gco2_per_kwh"] > 200


def test_data_marks_the_region_mapping_as_an_assumption() -> None:
    body = client.get("/api/data").json()
    mapping = [row for row in body["sources"] if "mapping" in row["name"]]
    assert mapping and mapping[0]["status"] == "assumption"


def test_uncertainty_exposes_both_designs() -> None:
    body = client.get("/api/uncertainty").json()
    assert body["target"] == 0.9
    assert body["single_split"]["national"]["holdout_coverage"] > 0.9
    rolling = body["rolling"]
    assert rolling["n_cells"] == rolling["n_regions"] * 12
    assert rolling["calibration_days"] == 28
    assert rolling["relative"]["mean_coverage_positive_forecast"] == pytest.approx(0.9, abs=0.05)
    # The three constructions must all be present: that comparison is the point.
    for key in ("relative", "constant", "regime_conditional"):
        assert rolling[key]["mean_coverage_positive_forecast"] is not None
    assert rolling["residual_structure"]["by_bucket"]
    assert rolling["residual_structure"]["alignment"]["used_for_calibration"] is False


def test_uncertainty_by_month_is_ordered_and_complete() -> None:
    rolling = client.get("/api/uncertainty").json()["rolling"]
    months = [row["month"] for row in rolling["by_month"]]
    assert months == list(range(1, 13))
    for row in rolling["by_month"]:
        assert 0 <= row["band_robust_pct"] <= 100


def test_uncertainty_reports_zero_forecast_slots() -> None:
    rolling = client.get("/api/uncertainty").json()["rolling"]
    share = rolling["relative"]["zero_forecast_slot_pct"]
    assert 0 < share < 20
    assert (
        rolling["relative"]["mean_coverage_all_slots"]
        >= rolling["relative"]["mean_coverage_positive_forecast"]
    )


def test_simulator_control_run_matches_its_record() -> None:
    body = client.get("/api/simulator").json()
    control = body["control"]
    metrics = repo.metrics_of("exp008-sustaincluster-baseline")
    assert len(control["controllers"]) == len(metrics["controllers"])
    assert control["best_rule_kg"] == metrics["rbc_best_carbon_kg"]
    families = {row["family"] for row in control["controllers"]}
    assert families == {"rule", "SAC"}
    # Sorted by carbon, ascending.
    carbons = [row["carbon_kg"] for row in control["controllers"]]
    assert carbons == sorted(carbons)


def test_simulator_uk_run_passes_its_exit_test_and_has_no_transmission_cost() -> None:
    uk = client.get("/api/simulator").json()["uk"]
    assert uk["exit_test"]["exit_test_passed"] is True
    assert uk["exit_test"]["max_intensity_error_gco2_per_kwh"] < 1.0
    assert uk["transmission_inoperative"] is True
    assert uk["price_identical_across_sites"] is True
    assert len(uk["sites"]) == 4


def test_uk_controller_delta_is_quoted_against_round_robin() -> None:
    uk = client.get("/api/simulator").json()["uk"]
    best = uk["controllers"][0]
    assert best["carbon_vs_round_robin_pct"] is not None
    assert best["carbon_vs_round_robin_pct"] < 0


def test_policies_ladder_is_ordered_and_marks_work_as_next() -> None:
    body = client.get("/api/policies").json()
    assert [row["rung"] for row in body["ladder"]] == list(range(1, 8))
    assert body["ladder"][0]["status"] == "verified"
    assert body["ladder"][-1]["status"] == "next"
    assert "CVaR" in body["agent"]["objective"]["formula"]


def test_roadmap_has_five_phases_and_declared_limits() -> None:
    body = client.get("/api/roadmap").json()
    assert [row["phase"] for row in body["phases"]] == ["0", "1", "2", "3", "4"]
    assert len(body["limits"]) >= 5
    assert body["next"]


def test_every_status_used_in_content_is_in_the_legend() -> None:
    keys = {item["key"] for item in content.LEGEND}
    used = {row["status"] for row in content.DATA_SOURCES}
    used |= {row["status"] for row in content.DATA_GAPS}
    used |= {row["status"] for row in content.POLICY_LADDER}
    assert used <= keys, used - keys


def test_missing_run_yields_no_summary_instead_of_a_guess() -> None:
    """A registered experiment with no run must not invent metrics."""
    assert repo.summary("exp001-uk-carbon-baseline", None) == []


def test_uncertainty_exposes_the_per_cell_grid() -> None:
    """The heatmap needs one row per (region, month), not just the averages.

    A mean coverage of 90% can hide half the cells being wrong, which is the
    whole point of showing the grid.
    """
    rolling = client.get("/api/uncertainty").json()["rolling"]
    grid = rolling["grid"]
    assert len(grid) == rolling["n_cells"]
    months = sorted({row["month"] for row in grid})
    regions = {row["regionid"] for row in grid}
    assert months == list(range(1, 13))
    assert len(regions) == rolling["n_regions"]
    assert len(grid) == len(months) * len(regions)
    for row in grid:
        assert 0 <= row["relative_coverage"] <= 1
        # The four constructions must exist per cell, or the comparison is partial.
        for key in (
            "relative_coverage",
            "constant_coverage",
            "regime_conditional_coverage",
            "regime_relative_coverage",
        ):
            assert row[key] is not None
    sim = [row for row in grid if row["sim_site"]]
    assert len(sim) == 4 * 12


def test_uncertainty_carries_all_four_constructions() -> None:
    """The comparison table is the finding; a missing block would silently drop it."""
    rolling = client.get("/api/uncertainty").json()["rolling"]
    for key in ("relative", "constant", "regime_conditional", "regime_relative"):
        assert rolling[key] is not None, key
    # Verdict the numbers support: the pooled relative band wins.
    assert (
        rolling["relative"]["mean_coverage_positive_forecast"]
        > rolling["regime_conditional"]["mean_coverage_positive_forecast"]
    )
    assert (
        rolling["regime_conditional"]["mean_half_width_pct_of_forecast"]
        > rolling["regime_relative"]["mean_half_width_pct_of_forecast"]
    )
