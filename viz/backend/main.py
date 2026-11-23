"""FastAPI service: the project's experiments as JSON, for the Next.js frontend.

Run it with ``make api`` (uvicorn on :8000). The frontend's Node layer proxies
to this service, so the browser never talks to Python directly.

Design rules:
  * every number is read from a committed artifact, never computed twice;
  * a missing artifact yields ``null`` plus a note, not a fabricated value;
  * shapes are stable, so pages do not need per-experiment special cases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from viz.backend import content, repo, schedule

app = FastAPI(
    title="Carbon-aware scheduling API",
    version="0.1.0",
    description=(
        "Read-only projection of the repository's experiment artifacts for the "
        "project frontend. Nothing is recomputed here that a run record does not "
        "already state."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Cheap liveness probe that also reports which artifacts are present."""
    ids = repo.experiment_ids()
    with_runs = [exp_id for exp_id in ids if repo.latest_run(exp_id)]
    return {
        "status": "ok",
        "generated_at": _now(),
        "experiments": len(ids),
        "experiments_with_runs": len(with_runs),
        "repo_root": repo.REPO_ROOT.name,
    }


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    ids = repo.experiment_ids()
    runs = sum(len(repo.run_dirs(exp_id)) for exp_id in ids)
    return {
        "project": {
            "title": "Uncertainty-aware decentralised carbon-aware scheduling",
            "subtitle": (
                "Multi-agent RL that places GPU/LLM work across UK grid regions to cut CO2 "
                "without missing deadlines, with measured forecast uncertainty as an input."
            ),
            "phase": "2 of 4 complete",
            "generated_at": _now(),
        },
        "counts": {"experiments": len(ids), "runs": runs},
        "legend": content.LEGEND,
        "claim": content.CLAIM,
    }


@app.get("/api/experiments")
def experiments() -> dict[str, Any]:
    """Registry entries with their newest run summary."""
    out = []
    for entry in repo.registry():
        exp_id = entry["id"]
        run = repo.latest_run(exp_id)
        metrics = run["metrics"] if run else None
        out.append(
            {
                "id": exp_id,
                "title": entry.get("title"),
                "phase": entry.get("phase"),
                "status": entry.get("status"),
                "rollback_tag": entry.get("rollback_tag"),
                "description": entry.get("description"),
                "run": None
                if run is None
                else {
                    "run_dir": run["run_dir"],
                    "timestamp": run["manifest"].get("timestamp"),
                    "git_sha": run["manifest"].get("git_sha"),
                    "git_dirty": run["manifest"].get("git_dirty"),
                    "config_hash": run["manifest"].get("config_hash"),
                    "seed": run["manifest"].get("seed"),
                },
                "summary": repo.summary(exp_id, metrics),
            }
        )
    return {"experiments": out, "count": len(out)}


@app.get("/api/experiments/{exp_id}")
def experiment(exp_id: str) -> dict[str, Any]:
    try:
        entry = repo.registry_entry(exp_id)
    except repo.ArtifactError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    run = repo.latest_run(exp_id)
    try:
        config = repo.config(exp_id)
    except repo.ArtifactError:
        config = None
    return {
        "registry": entry,
        "config": config,
        "run": run,
        "runs": [
            {
                "run_dir": item["run_dir"],
                "timestamp": item["manifest"].get("timestamp"),
                "git_sha": item["manifest"].get("git_sha"),
                "git_dirty": item["manifest"].get("git_dirty"),
            }
            for item in repo.runs(exp_id)
        ],
    }


@app.get("/api/data")
def data() -> dict[str, Any]:
    """Source catalogue, the four UK sites, and the demand/energy envelopes."""
    uk = repo.latest_metrics("exp009-uk-sites")
    regions = []
    if uk:
        for site, row in uk.get("regional_intensity", {}).items():
            regions.append(
                {
                    "site": site,
                    "neso_region_id": row.get("neso_region_id"),
                    "neso_region_name": row.get("neso_region_name"),
                    "input_mean_gco2_per_kwh": row.get("input_mean_gco2_per_kwh"),
                    "simulated_gco2_per_kwh": row.get("simulated_gco2_per_kwh"),
                    "within_tolerance": row.get("within_tolerance"),
                }
            )
        regions.sort(key=lambda row: row["input_mean_gco2_per_kwh"])
    return {
        "sources": content.DATA_SOURCES,
        "gaps": content.DATA_GAPS,
        "regions": regions,
        "spread_gco2_per_kwh": uk.get("regional_spread_gco2_per_kwh") if uk else None,
        "demand": repo.latest_metrics("exp006-azure-trace-demand"),
        "energy": repo.latest_metrics("exp007-site-energy"),
    }


@app.get("/api/uncertainty")
def uncertainty() -> dict[str, Any]:
    """Band evidence: the single split (exp004/5) and the rolling design (exp010)."""
    national = repo.latest_metrics("exp004-conformal-bands")
    regional = repo.latest_metrics("exp005-regional-bands")
    rolling = repo.latest_metrics("exp010-rolling-bands")

    per_region = []
    if regional:
        for region_id, row in regional.get("per_region", {}).items():
            per_region.append(
                {
                    "regionid": int(region_id),
                    "coverage": row.get("holdout_coverage"),
                    "band_half_width_gco2_per_kwh": row.get("band_half_width_gco2_per_kwh"),
                    "slots": row.get("holdout_n_slots"),
                }
            )
        per_region.sort(key=lambda row: row["coverage"] or 0)

    by_region = []
    by_month = []
    if rolling:
        for region_id, row in rolling.get("per_region", {}).items():
            by_region.append(
                {
                    "regionid": int(region_id),
                    "shortname": row.get("shortname"),
                    "mean_coverage": row.get("relative_mean_coverage"),
                    "min_coverage": row.get("relative_min_coverage"),
                    "months_at_target": row.get("relative_months_at_target"),
                    "zero_forecast_pct": row.get("zero_forecast_slot_pct"),
                    "sim_site": row.get("sim_site"),
                }
            )
        by_month = [
            {"month": int(month), **row}
            for month, row in rolling.get("decision_relevance", {}).get("by_month", {}).items()
        ]
        by_month.sort(key=lambda row: row["month"])

    return {
        "alpha": (rolling or national or {}).get("alpha"),
        "target": (rolling or national or {}).get("target_coverage"),
        "single_split": {
            "national": national,
            "regional": {
                "mean_coverage": regional.get("mean_coverage"),
                "min_coverage": regional.get("min_coverage"),
                "n_regions_at_target": regional.get("n_regions_at_target"),
                "n_regions": regional.get("n_regions"),
            }
            if regional
            else None,
            "per_region": per_region,
        },
        "rolling": None
        if not rolling
        else {
            "scheme": rolling.get("scheme"),
            "calibration_days": rolling.get("calibration_days"),
            "n_cells": rolling.get("n_cells"),
            "n_regions": rolling.get("n_regions"),
            "n_evaluation_slots": rolling.get("n_evaluation_slots"),
            "relative": rolling.get("relative"),
            "constant": rolling.get("constant"),
            "regime_relative": rolling.get("regime_relative"),
            "regime_conditional": rolling.get("regime_conditional"),
            "residual_structure": rolling.get("residual_structure"),
            "decision_relevance": {
                key: value
                for key, value in rolling.get("decision_relevance", {}).items()
                if key != "by_month"
            },
            "pairing": rolling.get("pairing"),
            "sim_sites": rolling.get("sim_sites"),
            "by_region": sorted(by_region, key=lambda row: row["mean_coverage"] or 0),
            "by_month": by_month,
            # One row per (region, month). A mean of 90% can hide half the cells
            # being wrong, so the frontend renders the grid rather than the mean.
            "grid": [
                {
                    "month": cell.get("month"),
                    "regionid": cell.get("regionid"),
                    "shortname": cell.get("shortname"),
                    "sim_site": cell.get("is_sim_site"),
                    "relative_coverage": cell.get("relative_coverage"),
                    "constant_coverage": cell.get("constant_coverage"),
                    "regime_conditional_coverage": cell.get("regime_coverage"),
                    "regime_relative_coverage": cell.get("regime_relative_coverage"),
                    "mean_forecast_gco2_per_kwh": cell.get("mean_forecast_gco2_per_kwh"),
                    "n_eval": cell.get("n_eval"),
                }
                for cell in rolling.get("cells", [])
            ],
        },
    }


def _controllers(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise a controller map into a sorted, chartable list."""
    relative = metrics.get("carbon_vs_round_robin_pct", {})
    rows = []
    for name, row in metrics.get("controllers", {}).items():
        rows.append(
            {
                "name": name,
                "family": "SAC" if name.startswith("sac:") else "rule",
                "carbon_kg": row.get("carbon_kg"),
                "carbon_vs_round_robin_pct": relative.get(name),
                "sla_violation_rate": row.get("sla_violation_rate"),
                "energy_kwh": row.get("energy_kwh"),
                "transmission_cost_usd": row.get("transmission_cost_usd"),
                "tasks_finished": row.get("tasks_finished"),
                "per_dc": row.get("per_dc"),
            }
        )
    rows.sort(key=lambda row: row["carbon_kg"] or 0)
    return rows


@app.get("/api/simulator")
def simulator() -> dict[str, Any]:
    control = repo.latest_metrics("exp008-sustaincluster-baseline")
    uk = repo.latest_metrics("exp009-uk-sites")
    return {
        "upstream": {
            "name": "SustainCluster",
            "organisation": "HPE Labs (MIT licence)",
            "commit": (uk or control or {}).get("sustaincluster_commit"),
            "note": (
                "Third-party code is never patched. All UK behaviour is opt-in through our drivers "
                "(site list, window, reward, clock alignment), so the upstream result "
                "stays a control."
            ),
        },
        "control": None
        if not control
        else {
            "exp_id": "exp008-sustaincluster-baseline",
            "window": None,
            "days": control.get("days"),
            "seed": control.get("seed"),
            "controllers": _controllers(control),
            "best_rule_kg": control.get("rbc_best_carbon_kg"),
            "best_sac_kg": control.get("sac_best_carbon_kg"),
            "sac_min_sla_violation_rate": control.get("sac_min_sla_violation_rate"),
        },
        "uk": None
        if not uk
        else {
            "exp_id": "exp009-uk-sites",
            "window_start_utc": uk.get("carbon_window_start_utc"),
            "window_hours": uk.get("carbon_window_hours"),
            "days": uk.get("days"),
            "seed": uk.get("seed"),
            "clock_aligned_with_carbon": uk.get("clock_aligned_with_carbon"),
            "controllers": _controllers(uk),
            "regional_spread_gco2_per_kwh": uk.get("regional_spread_gco2_per_kwh"),
            "sites": uk.get("regional_intensity"),
            "exit_test": {
                "max_intensity_error_gco2_per_kwh": uk.get("max_intensity_error_gco2_per_kwh"),
                "regional_ordering_matches_input": uk.get("regional_ordering_matches_input"),
                "exit_test_passed": uk.get("exit_test_passed"),
            },
            "transmission_inoperative": all(
                (row.get("transmission_cost_usd") or 0) == 0
                for row in uk.get("controllers", {}).values()
            ),
            "price_identical_across_sites": uk.get("price_identical_across_sites"),
        },
    }


@app.get("/api/policies")
def policies() -> dict[str, Any]:
    return content.policies()


@app.get("/api/schedule")
def schedule_meta() -> dict[str, Any]:
    """The scheduler's real knobs, held-out weeks, fleets and evidence labels."""
    return schedule.meta()


@app.get("/api/schedule/replay")
def schedule_replay(
    week: str | None = Query(None, description="a held-out week from the exp017 record"),
    fleet: str | None = Query(None, description="capacity_bound or slack"),
    price: float | None = Query(None, ge=0, description="kg CO2 per missed GPU-hour"),
    robust: float | None = Query(None, ge=0, le=1, description="band multiplier"),
    reserve: float | None = Query(None, ge=0, lt=1, description="capacity held back"),
    reserve_level: float | None = Query(
        None, ge=0, le=1, description="calibrated arrival-reserve level (exp018)"
    ),
    slot: int | None = Query(None, ge=0, description="slot to explain"),
    site: str | None = Query(None, description="selected site"),
    item: str | None = Query(None, description="selected request id"),
) -> dict[str, Any]:
    """Replay one held-out week through the committed planner and explain a slot.

    Every number comes from the carbon panel, the verified demand artifact and
    the planner's own ledger. If the demand artifact is missing the payload says
    so instead of fabricating a schedule.
    """
    defaults = schedule.meta().get("defaults") or {}
    if defaults.get("week") is None:
        raise HTTPException(status_code=503, detail="no committed exp017 run record")
    try:
        return schedule.replay(
            week=week or defaults["week"],
            fleet=fleet or defaults["fleet"],
            price=defaults["price"] if price is None else price,
            robust=defaults["robust"] if robust is None else robust,
            reserve=defaults["reserve"] if reserve is None else reserve,
            reserve_level=reserve_level,
            slot=slot,
            site=site,
            item=item,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/roadmap")
def roadmap() -> dict[str, Any]:
    return content.roadmap()
