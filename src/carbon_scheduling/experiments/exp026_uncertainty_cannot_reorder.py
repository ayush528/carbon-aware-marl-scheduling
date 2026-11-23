"""exp026 -- can calibrated uncertainty change a carbon decision?

exp011 ran this question on one week and reported an awkward result: a pooled
relative band changed nothing (0 of 336 slots) and a per-region absolute band
reordered 1.8-3% of slots but only ever *cost* carbon. That was reported as a
finding. It is not a finding, it is a theorem, and this experiment states it,
measures its cost over a full year, and finds the boundary where it stops
holding.

**The theorem.** Write the documented estimator for regional realized intensity:

    realized_r(t) = national_actual(t) * forecast_r(t) / national_forecast(t)

Then the forecast error is

    realized_r - forecast_r = forecast_r * (national_actual/national_forecast - 1)

and the bracket is one number per slot, identical for every region. So:

1. ``realized`` and ``forecast`` induce the *same* ranking of regions, whatever
   the national error was;
2. filling sites in forecast order is therefore the optimum of the linear
   capacity problem for that slot -- no other order can emit less;
3. any band that reorders the sites is reordering on noise, so it can only
   misprice, never improve.

Nothing in (1)-(3) depends on the band being calibrated badly. It is a property
of the *data construction*, which is the point: a regional carbon series built
by scaling a national one contains no regional ranking information, so a
spatial-uncertainty result computed on it is vacuous at best.

**What is measured.** For all 44 fully covered weeks of 2024, calibrated on the
28 days before each week: the premise (0 slots where the realized ordering
differs), three band constructions across a lambda grid, the fraction of slots
each reorders, and the carbon it costs -- mean, worst, and per week, so
"never better" is a count rather than a claim. Then the boundary: independent
per-region error injected at several magnitudes, which is the only structure
under which the band can carry information. There it is scored on both mean
carbon and the tail (CVaR-95 of per-slot emissions), because a risk-averse
choice is allowed to trade one for the other and pretending otherwise would
hide the band's only defensible role.

Everything here is deterministic: the counterfactual uses the config seed.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from carbon_scheduling import dispatch
from carbon_scheduling.cluster import Site
from carbon_scheduling.experiments.exp011_band_dispatch import (
    _evaluate,
    residuals,
    site_series,
)
from carbon_scheduling.rl.data import demand_profile
from carbon_scheduling.runner import REPO_ROOT
from carbon_scheduling.uncertainty import (
    COMMON_ADDITIVE,
    COMMON_MULTIPLICATIVE,
    REGIONAL,
    classify,
    reorders,
)

SLOT_MINUTES = 30
WEEK_SLOTS = 336


def _fleet_sites(fleet: dict[str, Any], regions: dict[str, int]) -> dict[str, Site]:
    return {
        slug: Site(
            name=slug,
            n_gpus=int(fleet["n_gpus"]),
            gpu_idle_w=float(fleet["gpu_idle_w"]),
            gpu_peak_w=float(fleet["gpu_peak_w"]),
            pue=float(fleet["pue"]),
            tokens_per_gpu_second=float(fleet["tokens_per_gpu_second"]),
        )
        for slug in regions
    }


def _week_frames(
    series: dict[str, dict[str, dict[datetime, float]]],
    start: datetime,
    regions: dict[str, int],
    tokens: np.ndarray,
) -> tuple[list[dict[str, Any]], list[dict[str, float]], list[dict[str, float]]]:
    """One week's slots as (demand rows, forecast rows, realized rows).

    A slot is kept only if every site has both a forecast and a realized value,
    so all policies are scored on exactly the same slots. Demand is the single
    real Azure week laid positionally over each carbon week (disclosed, and the
    same reuse ``rl.data`` makes).
    """
    stamps = [start + timedelta(minutes=SLOT_MINUTES * i) for i in range(WEEK_SLOTS)]
    keep = [
        i
        for i, stamp in enumerate(stamps)
        if all(
            stamp in series[slug]["forecast"] and stamp in series[slug]["realized"]
            for slug in regions
        )
    ]
    slots = [
        {
            "from": stamps[i].strftime("%Y-%m-%dT%H:%MZ"),
            "context_tokens": float(tokens[i]),
            "generated_tokens": 0.0,
        }
        for i in keep
    ]
    forecast = [{slug: series[slug]["forecast"][stamps[i]] for slug in regions} for i in keep]
    realized = [{slug: series[slug]["realized"][stamps[i]] for slug in regions} for i in keep]
    return slots, forecast, realized


def _policy_table(
    forecast: list[dict[str, float]],
    bands: dict[str, dict[str, float]],
    lams: list[float],
) -> dict[str, list[dict[str, float]]]:
    """Score tables for forecast-greedy and every (band, lambda) pair."""
    table: dict[str, list[dict[str, float]]] = {"forecast_greedy": [dict(row) for row in forecast]}
    for name, half_width in bands.items():
        for lam in lams:
            table[f"{name}_lam{lam}"] = [
                dispatch.risk_scores(row, half_width, float(lam)) for row in forecast
            ]
    return table


def _cvar(values: list[float], quantile: float) -> float:
    """Mean of the worst (1 - quantile) fraction of per-slot emissions."""
    ordered = sorted(values)
    k = max(1, int(round((1.0 - quantile) * len(ordered))))
    return sum(ordered[-k:]) / k


def _score_week(
    slots: list[dict[str, Any]],
    forecast: list[dict[str, float]],
    realized: list[dict[str, float]],
    sites: dict[str, Site],
    table: dict[str, list[dict[str, float]]],
    tail_quantile: float,
) -> dict[str, dict[str, Any]]:
    """Run every policy over one week and report carbon, tail and reordering."""
    base = _evaluate(slots, sites, table["forecast_greedy"], realized, forecast)
    base_carbon = base["carbon_kg_realized"]
    base_tail = _cvar(base["per_slot_carbon_kg"], tail_quantile)
    base_top = [picks[0] for picks in base["picks"]]

    out: dict[str, dict[str, Any]] = {}
    for name, scores in table.items():
        res = _evaluate(slots, sites, scores, realized, forecast)
        reordered = sum(1 for a, b in zip(res["picks"], base["picks"], strict=True) if a[0] != b[0])
        out[name] = {
            "carbon_kg_realized": res["carbon_kg_realized"],
            "carbon_delta_pct": (res["carbon_kg_realized"] / base_carbon - 1.0) * 100.0,
            "tail_cvar_kg": _cvar(res["per_slot_carbon_kg"], tail_quantile),
            "tail_delta_pct": (_cvar(res["per_slot_carbon_kg"], tail_quantile) / base_tail - 1.0)
            * 100.0,
            "reordered_slots": reordered,
            "reordered_pct": reordered / len(slots) * 100.0,
            "energy_kwh_total": res["energy_kwh_total"],
            "unserved_fraction": res["unserved_fraction"],
            "top_pick_changes": sum(
                1 for a, b in zip([p[0] for p in res["picks"]], base_top, strict=True) if a != b
            ),
        }
    return out


def _bands(
    series: dict[str, dict[str, dict[datetime, float]]],
    cal_start: datetime,
    cal_end: datetime,
    regions: dict[str, int],
    alpha: float,
) -> dict[str, dict[str, float]]:
    """The three band constructions, calibrated strictly before the week."""
    absolute_res, levels, relative_res = residuals(series, cal_start, cal_end)
    pooled = dispatch.relative_half_widths(
        {"all": [v for values in relative_res.values() for v in values]},
        {"all": [v for values in levels.values() for v in values]},
        alpha,
    )["all"]
    per_site_relative = dispatch.relative_half_widths(relative_res, levels, alpha)
    # Applied as a fraction of each site's forecast, so the pooled band and the
    # per-site relative band both enter the score multiplicatively.
    return {
        "absolute": dispatch.absolute_half_widths(absolute_res, alpha),
        "pooled_relative": {slug: pooled for slug in regions},
        "per_region_relative": per_site_relative,
    }


def _aggregate(weeks: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean / worst / counts per policy, so "never better" is a count."""
    names = [n for n in weeks[0]["policies"] if n != "forecast_greedy"]
    by_policy: dict[str, dict[str, Any]] = {}
    for name in names:
        rows = [week["policies"][name] for week in weeks]
        deltas = [r["carbon_delta_pct"] for r in rows]
        tails = [r["tail_delta_pct"] for r in rows]
        by_policy[name] = {
            "mean_carbon_delta_pct": round(float(np.mean(deltas)), 4),
            "best_carbon_delta_pct": round(float(min(deltas)), 4),
            "worst_carbon_delta_pct": round(float(max(deltas)), 4),
            "weeks_better": sum(1 for d in deltas if d < -1e-9),
            "weeks_worse": sum(1 for d in deltas if d > 1e-9),
            "mean_tail_delta_pct": round(float(np.mean(tails)), 4),
            "mean_reordered_pct": round(float(np.mean([r["reordered_pct"] for r in rows])), 3),
        }
    return {
        "n_weeks": len(weeks),
        "by_policy": by_policy,
        "any_band_week_better": sum(v["weeks_better"] for v in by_policy.values()),
        "any_band_week_worse": sum(v["weeks_worse"] for v in by_policy.values()),
    }


def _counterfactual_series(
    series: dict[str, dict[str, dict[datetime, float]]],
    regions: dict[str, int],
    sigma: dict[str, float],
    rng: np.random.Generator,
) -> dict[str, dict[str, dict[datetime, float]]]:
    """Real series plus per-region relative error, independently drawn.

    The real estimator has one shared factor per slot, so ``realized/forecast``
    is identical across regions. This multiplies each region's realized value by
    ``1 + N(0, sigma_r)``. When every ``sigma_r`` is equal the band widths stay
    roughly proportional to the level and the ranking barely moves; when they
    differ, the widths differ in proportion and the ranking can move. That
    difference is the point of running both.
    """
    out = {
        slug: {"forecast": dict(rows["forecast"]), "realized": dict(rows["realized"])}
        for slug, rows in series.items()
    }
    for slug in regions:
        spread = sigma[slug]
        if spread == 0.0:
            continue
        for stamp in out[slug]["realized"]:
            out[slug]["realized"][stamp] *= 1.0 + float(rng.normal(0.0, spread))
    return out


def _boundary(
    series: dict[str, dict[str, dict[datetime, float]]],
    starts: list[datetime],
    regions: dict[str, int],
    sites: dict[str, Site],
    tokens: np.ndarray,
    *,
    alpha: float,
    calibration_days: int,
    lams: list[float],
    tail_quantile: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Score the band on perturbed series, per noise profile and magnitude."""
    weeks = []
    for start in starts:
        cal_start = start - timedelta(days=calibration_days)
        bands = _bands(series, cal_start, start, regions, alpha)
        slots, forecast, realized = _week_frames(series, start, regions, tokens)
        if len(slots) < WEEK_SLOTS // 2:
            continue
        table = _policy_table(forecast, bands, lams)
        weeks.append(
            {"policies": _score_week(slots, forecast, realized, sites, table, tail_quantile)}
        )
    return _aggregate(weeks)


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {p.name: p for p in paths}

    with by_name["uk_regional_2024_tidy.csv"].open(newline="") as handle:
        regional_rows = list(csv.DictReader(handle))
    national_rows = json.loads(by_name["uk_national_2023-12_2024-12.json"].read_text())["data"]

    regions: dict[str, int] = config["regions"]
    alpha = float(config["alpha"])
    calibration_days = int(config["calibration_days"])
    lams = [float(v) for v in config["lam_grid"]]
    tail_quantile = float(config["counterfactual"]["tail_quantile"])

    series = site_series(regional_rows, national_rows, regions)
    tokens = demand_profile(by_name["AzureLLMInferenceTrace_code_1week.csv"], WEEK_SLOTS)

    # Week starts whose week *and* 28-day calibration span are fully covered.
    available = set.intersection(*(set(rows["realized"]) for rows in series.values()))
    weeks_cfg = config["weeks"]
    starts: list[datetime] = []
    cursor = datetime(int(weeks_cfg["year"]), 1, 1)
    while cursor.year == int(weeks_cfg["year"]):
        if cursor.month in weeks_cfg["months"]:
            span = [cursor + timedelta(minutes=SLOT_MINUTES * i) for i in range(WEEK_SLOTS)]
            # A week is used only if the week *and* its whole 28-day calibration
            # window are present, so no band is fitted on a hole in the series.
            cal_start = cursor - timedelta(days=calibration_days)
            cal_ok = all(
                cal_start + timedelta(minutes=SLOT_MINUTES * i) in available
                for i in range(calibration_days * 48)
            ) and all(s in available for s in span)
            if cal_ok:
                starts.append(cursor)
        cursor += timedelta(days=7)

    # --- the premise: does the realized ordering ever differ? ---
    structure: dict[str, int] = {COMMON_MULTIPLICATIVE: 0, COMMON_ADDITIVE: 0, REGIONAL: 0}
    reordering_slots = 0
    spread_max = 0.0
    checked = 0
    for stamp in sorted(available):
        row_f = {s: series[s]["forecast"].get(stamp) for s in regions}
        row_r = {s: series[s]["realized"].get(stamp) for s in regions}
        if any(v is None for v in row_f.values()) or any(v is None for v in row_r.values()):
            continue
        if any(v == 0 for v in row_f.values()):
            continue
        checked += 1
        structure[classify(row_r, row_f)] += 1
        if reorders(row_r, row_f):
            reordering_slots += 1
        ratios = [row_r[s] / row_f[s] for s in regions]
        spread_max = max(spread_max, max(ratios) - min(ratios))

    fleets: dict[str, dict[str, Any]] = {}
    for fleet in config["fleets"]:
        label = str(fleet["label"])
        sites = _fleet_sites(fleet, regions)
        weeks: list[dict[str, Any]] = []
        for start in starts:
            cal_start = start - timedelta(days=calibration_days)
            bands = _bands(series, cal_start, start, regions, alpha)
            slots, forecast, realized = _week_frames(series, start, regions, tokens)
            if len(slots) < WEEK_SLOTS // 2:
                continue
            table = _policy_table(forecast, bands, lams)
            weeks.append(
                {
                    "start_utc": start.strftime("%Y-%m-%dT%H:%MZ"),
                    "n_slots": len(slots),
                    "policies": _score_week(slots, forecast, realized, sites, table, tail_quantile),
                }
            )
        fleets[label] = _aggregate(weeks)

    # --- the boundary: independent regional error ---
    rng = np.random.default_rng(int(config["seed"]))
    cf = config["counterfactual"]
    cf_fleet = next(f for f in config["fleets"] if str(f["label"]) == str(cf["fleet"]))
    cf_sites = _fleet_sites(cf_fleet, regions)
    base_profile: dict[str, float] = cf["heteroskedastic"]["base"]

    homoskedastic: dict[str, Any] = {}
    for sigma in [float(v) for v in cf["homoskedastic"]["sigma_grid"]]:
        perturbed = _counterfactual_series(series, regions, dict.fromkeys(regions, sigma), rng)
        homoskedastic[f"{sigma:.2f}"] = _boundary(
            perturbed,
            starts,
            regions,
            cf_sites,
            tokens,
            alpha=alpha,
            calibration_days=calibration_days,
            lams=lams,
            tail_quantile=tail_quantile,
            rng=rng,
        )

    heteroskedastic: dict[str, Any] = {}
    for scale in [float(v) for v in cf["heteroskedastic"]["scale_grid"]]:
        profile = {slug: scale * float(base_profile[slug]) for slug in regions}
        perturbed = _counterfactual_series(series, regions, profile, rng)
        heteroskedastic[f"{scale:.2f}"] = _boundary(
            perturbed,
            starts,
            regions,
            cf_sites,
            tokens,
            alpha=alpha,
            calibration_days=calibration_days,
            lams=lams,
            tail_quantile=tail_quantile,
            rng=rng,
        )

    return {
        "premise": {
            "n_weeks": len(starts),
            "n_slots_checked": checked,
            "slots_with_reordered_realized": reordering_slots,
            "error_structure_counts": structure,
            "max_relative_error_spread_across_regions": spread_max,
            "statement": (
                "realized_r = national_actual * forecast_r / national_forecast implies one "
                "shared relative error per slot, so the regional ordering is the forecast's "
                "ordering. Zero reordering slots is the premise the rest of the experiment "
                "relies on, verified rather than assumed."
            ),
        },
        "fleets": fleets,
        "boundary": {
            "labelled": "Modelled",
            "fleet": str(cf["fleet"]),
            "tail_quantile": tail_quantile,
            "note": (
                "Per-region relative error added independently on top of the real series. "
                "Homoskedastic is the control: equal noise leaves widths roughly "
                "proportional, so the band stays inert. Heteroskedastic is the realistic "
                "case and the only one where the band can buy tail carbon. Magnitude 0 "
                "reproduces the measured series as an anchor."
            ),
            "homoskedastic": {
                "sigma_grid": cf["homoskedastic"]["sigma_grid"],
                "by_sigma": homoskedastic,
            },
            "heteroskedastic": {
                "base_profile": base_profile,
                "scale_grid": cf["heteroskedastic"]["scale_grid"],
                "by_scale": heteroskedastic,
            },
        },
        "disclosures": [
            "Regional actuals do not exist in the NESO API; realized is the documented "
            "national-scaling estimate, which is precisely what makes the theorem apply.",
            "Demand is the single real Azure LLM week, laid positionally over each carbon "
            "week. Carbon is the only thing that differs between weeks.",
            "The boundary experiment is synthetic (labelled Modelled); its sigma axis is a "
            "sensitivity, not a measurement of US or EU grids.",
        ],
    }
