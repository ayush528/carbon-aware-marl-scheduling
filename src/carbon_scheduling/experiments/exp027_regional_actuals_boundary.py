"""exp027 — does the band reorder on a grid whose regional actuals are measured?

exp026 proves that a regional series built by scaling a national one leaves a
calibrated band nothing to decide: the error is one shared factor per slot, so
the realized ranking is the forecast's ranking and forecast-greedy is already
the slot optimum. That is a theorem about a *construction*, and the obvious
objection is that it says nothing about grids where regional actuals exist.

This experiment removes the objection. EIA-930 publishes hourly generation by
fuel for every US balancing authority, so each region's realized intensity is
computed from its own measured mix — not borrowed from a national series. The
question is then empirical:

1. Is the error structure ``regional`` rather than ``common-multiplicative``?
2. Does the realized ordering ever differ from the forecast ordering? (On the
   UK series the answer was 0 of 18,757 slots. Here it should not be.)
3. Do the regions differ in *volatility*, not just in level? That is what makes
   band widths differ in proportion, which is what lets a band reorder at all.
4. When the band does reorder, does it buy mean carbon, tail carbon, or neither?

EIA publishes no carbon forecast, so the forecast is ours and is disclosed as
such. Two causal models are run — day-ahead persistence and the mean of the same
hour over the previous week — so the structural answer cannot be an artefact of
one naive forecaster. The emission factors are published EIA averages applied to
each authority's real mix: the mix is measured, the factor is a disclosed
assumption, and a sensitivity re-prices the unclassified "Other" fuel.

Everything is deterministic; no randomness is used at all.
"""

from __future__ import annotations

import csv
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from carbon_scheduling import dispatch
from carbon_scheduling.cluster import Site, site_energy_kwh
from carbon_scheduling.data import eia
from carbon_scheduling.demand import requests_per_slot
from carbon_scheduling.runner import REPO_ROOT
from carbon_scheduling.uncertainty import (
    COMMON_ADDITIVE,
    COMMON_MULTIPLICATIVE,
    REGIONAL,
    classify,
    reorders,
)

HOURS_PER_WEEK = 168


def forecast_series(
    realized: dict[datetime, float],
    *,
    kind: str,
    lag_hours: int = 24,
    days: int = 7,
) -> dict[datetime, float]:
    """A causal carbon forecast from the realized series alone.

    ``persistence``: the value ``lag_hours`` ago. ``same_hour_mean``: the mean of
    the same hour over the previous ``days`` days. Both use only the past, so a
    band calibrated on them cannot see the hour it is judged on.
    """
    out: dict[datetime, float] = {}
    if kind == "persistence":
        for stamp in realized:
            previous = stamp - timedelta(hours=lag_hours)
            if previous in realized:
                out[stamp] = realized[previous]
        return out
    if kind == "same_hour_mean":
        for stamp in realized:
            past = [
                realized[stamp - timedelta(days=k)]
                for k in range(1, days + 1)
                if stamp - timedelta(days=k) in realized
            ]
            if len(past) == days:
                out[stamp] = sum(past) / len(past)
        return out
    raise ValueError(f"unknown forecast kind {kind!r}")


def _sites(spec: list[dict[str, Any]], fleet: dict[str, Any]) -> dict[str, Site]:
    return {
        str(item["authority"]): Site(
            name=str(item["authority"]),
            n_gpus=int(fleet["n_gpus"]),
            gpu_idle_w=float(fleet["gpu_idle_w"]),
            gpu_peak_w=float(fleet["gpu_peak_w"]),
            pue=float(fleet["pue"]),
            tokens_per_gpu_second=float(fleet["tokens_per_gpu_second"]),
        )
        for item in spec
    }


def _aligned_hours(
    forecast: dict[str, dict[datetime, float]],
    realized: dict[str, dict[datetime, float]],
    start: datetime,
    hours: int,
) -> list[datetime]:
    stamps = [start + timedelta(hours=i) for i in range(hours)]
    return [
        stamp
        for stamp in stamps
        if all(stamp in forecast[site] and stamp in realized[site] for site in realized)
    ]


def _residuals(
    forecast: dict[str, dict[datetime, float]],
    realized: dict[str, dict[datetime, float]],
    start: datetime,
    end: datetime,
) -> tuple[dict[str, list[float]], dict[str, list[float]], dict[str, list[float]]]:
    """Absolute residuals, forecast levels and relative residuals per site."""
    absolute: dict[str, list[float]] = {}
    levels: dict[str, list[float]] = {}
    relative: dict[str, list[float]] = {}
    for site in realized:
        absv, fcs, rel = [], [], []
        for stamp, value in forecast[site].items():
            if not (start <= stamp < end) or value == 0 or stamp not in realized[site]:
                continue
            error = abs(realized[site][stamp] - value)
            absv.append(error)
            fcs.append(value)
            rel.append(error / value)
        absolute[site], levels[site], relative[site] = absv, fcs, rel
    return absolute, levels, relative


def _bands(
    forecast: dict[str, dict[datetime, float]],
    realized: dict[str, dict[datetime, float]],
    cal_start: datetime,
    cal_end: datetime,
    alpha: float,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    absolute, levels, relative = _residuals(forecast, realized, cal_start, cal_end)
    pooled = dispatch.relative_half_widths(
        {"all": [v for values in relative.values() for v in values]},
        {"all": [v for values in levels.values() for v in values]},
        alpha,
    )["all"]
    return (
        {"absolute": dispatch.absolute_half_widths(absolute, alpha)},
        {
            "pooled_relative": dict.fromkeys(realized, pooled),
            "per_region_relative": dispatch.relative_half_widths(relative, levels, alpha),
        },
    )


def _cvar(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    k = max(1, int(round((1.0 - quantile) * len(ordered))))
    return sum(ordered[-k:]) / k


def _evaluate(
    stamps: list[datetime],
    forecast: dict[str, dict[datetime, float]],
    realized: dict[str, dict[datetime, float]],
    sites: dict[str, Site],
    tokens: list[float],
    scores: dict[str, list[dict[str, float]]],
    slot_minutes: int,
    tail_quantile: float,
) -> dict[str, dict[str, Any]]:
    """Score every policy on the same hours, with the same demand and capacity."""
    capacity = {site: spec.n_gpus * slot_minutes * 60 for site, spec in sites.items()}
    demand = [
        tokens[i] / next(iter(sites.values())).tokens_per_gpu_second for i in range(len(stamps))
    ]
    real_rows = [{site: realized[site][stamp] for site in sites} for stamp in stamps]

    out: dict[str, dict[str, Any]] = {}
    base_carbon = base_tail = None
    base_top: list[str] = []
    base_order: list[tuple[str, ...]] = []
    for name, table in scores.items():
        carbon = 0.0
        per_slot: list[float] = []
        top: list[str] = []
        order: list[tuple[str, ...]] = []
        unserved = 0.0
        for i in range(len(stamps)):
            row = table[i]
            alloc, left = dispatch.allocate(row, demand[i], capacity)
            energy = {
                site: site_energy_kwh(sites[site], alloc[site], slot_minutes) for site in sites
            }
            slot_carbon = dispatch.carbon_kg(energy, real_rows[i])
            carbon += slot_carbon
            per_slot.append(slot_carbon)
            unserved += left
            ranking = dispatch.rank(row)
            top.append(ranking[0])
            order.append(tuple(ranking))
        tail = _cvar(per_slot, tail_quantile)
        if name == "forecast_greedy":
            base_carbon, base_tail, base_top, base_order = carbon, tail, top, order
        out[name] = {
            "carbon_kg": carbon,
            "tail_cvar_kg": tail,
            "unserved_gpu_seconds": unserved,
            "top": top,
            "order": order,
        }
    assert base_carbon is not None and base_tail is not None
    for row in out.values():
        row["carbon_delta_pct"] = (row["carbon_kg"] / base_carbon - 1.0) * 100.0
        row["tail_delta_pct"] = (row["tail_cvar_kg"] / base_tail - 1.0) * 100.0
        row["reordered_pct"] = (
            sum(1 for a, b in zip(row["top"], base_top, strict=True) if a != b)
            / len(stamps)
            * 100.0
        )
        row["ranking_changed_pct"] = (
            sum(1 for a, b in zip(row["order"], base_order, strict=True) if a != b)
            / len(stamps)
            * 100.0
        )
        del row["top"]
        del row["order"]
    return out


def _policy_table(
    stamps: list[datetime],
    forecast: dict[str, dict[datetime, float]],
    absolute_bands: dict[str, dict[str, float]],
    relative_bands: dict[str, dict[str, float]],
    lams: list[float],
) -> dict[str, list[dict[str, float]]]:
    """Absolute bands are added (gCO2/kWh); relative bands scale the forecast.

    Confusing the two turns a relative band into a common additive constant,
    which cannot reorder for a trivial reason -- the bug exp026's regression
    test now pins.
    """
    rows = [{site: forecast[site][stamp] for site in forecast} for stamp in stamps]
    table: dict[str, list[dict[str, float]]] = {"forecast_greedy": [dict(r) for r in rows]}
    for name, width in absolute_bands.items():
        for lam in lams:
            table[f"{name}_lam{lam}"] = [dispatch.risk_scores(row, width, lam) for row in rows]
    for name, fraction in relative_bands.items():
        for lam in lams:
            table[f"{name}_lam{lam}"] = [
                {site: value * (1.0 + lam * fraction[site]) for site, value in row.items()}
                for row in rows
            ]
    return table


def _aggregate(weeks: list[dict[str, Any]]) -> dict[str, Any]:
    names = [n for n in weeks[0] if n != "forecast_greedy"]
    by_policy: dict[str, Any] = {}
    for name in names:
        deltas = [week[name]["carbon_delta_pct"] for week in weeks]
        tails = [week[name]["tail_delta_pct"] for week in weeks]
        by_policy[name] = {
            "mean_carbon_delta_pct": round(statistics.mean(deltas), 4),
            "best_carbon_delta_pct": round(min(deltas), 4),
            "worst_carbon_delta_pct": round(max(deltas), 4),
            "weeks_better": sum(1 for d in deltas if d < -1e-9),
            "weeks_worse": sum(1 for d in deltas if d > 1e-9),
            "mean_tail_delta_pct": round(statistics.mean(tails), 4),
            "best_tail_delta_pct": round(min(tails), 4),
            "mean_reordered_pct": round(
                statistics.mean([week[name]["reordered_pct"] for week in weeks]), 3
            ),
            "mean_ranking_changed_pct": round(
                statistics.mean([week[name]["ranking_changed_pct"] for week in weeks]), 3
            ),
        }
    return {
        "n_weeks": len(weeks),
        "by_policy": by_policy,
        "any_band_week_better": sum(v["weeks_better"] for v in by_policy.values()),
    }


def _diagnostic(
    forecast: dict[str, dict[datetime, float]],
    realized: dict[str, dict[datetime, float]],
) -> dict[str, Any]:
    """The structural question, answered on every hour all sites share."""
    common = set.intersection(*(set(forecast[s]) & set(realized[s]) for s in realized))
    structure = {COMMON_MULTIPLICATIVE: 0, COMMON_ADDITIVE: 0, REGIONAL: 0}
    reordered = 0
    spread_max = 0.0
    for stamp in sorted(common):
        f = {s: forecast[s][stamp] for s in realized}
        r = {s: realized[s][stamp] for s in realized}
        if any(v == 0 for v in f.values()):
            continue
        structure[classify(r, f)] += 1
        if reorders(r, f):
            reordered += 1
        ratios = [r[s] / f[s] for s in realized]
        spread_max = max(spread_max, max(ratios) - min(ratios))
    volatility = {}
    for site in realized:
        rel = [
            (realized[site][stamp] - forecast[site][stamp]) / forecast[site][stamp]
            for stamp in common
            if forecast[site][stamp] != 0
        ]
        volatility[site] = {
            "relative_error_std": round(statistics.pstdev(rel), 4) if len(rel) > 1 else 0.0,
            "mean_realized_gco2_per_kwh": round(
                statistics.mean([realized[site][s] for s in common]), 2
            ),
        }
    return {
        "n_hours": len(common),
        "error_structure_counts": structure,
        "hours_with_reordered_realized": reordered,
        "reordered_pct": round(reordered / len(common) * 100, 3) if common else 0.0,
        "max_relative_error_spread_across_regions": round(spread_max, 4),
        "per_site": volatility,
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {p.name: p for p in paths}
    with by_name["eia930_balance_2024_janjun_sample.csv"].open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    tolerance = float(config["rounding_tolerance"])
    realized_all, stats = eia.intensity_series(rows, tolerance=tolerance)

    spec = config["sites"]
    authorities = [str(item["authority"]) for item in spec]
    min_coverage = float(config["min_site_coverage"])
    coverage = {
        a: {
            **stats[a],
            "coverage_pct": round(stats[a]["usable"] / stats[a]["total"] * 100, 2),
        }
        for a in authorities
    }
    for a in authorities:
        if coverage[a]["coverage_pct"] / 100 < min_coverage:
            raise ValueError(f"{a} covers only {coverage[a]['coverage_pct']}% of hours")
    realized = {a: realized_all[a] for a in authorities}

    slot_minutes = int(config["slot_minutes"])
    demand_slots = requests_per_slot(
        by_name["AzureLLMInferenceTrace_code_1week.csv"], slot_minutes=slot_minutes
    )
    tokens = [float(s["context_tokens"] + s["generated_tokens"]) for s in demand_slots]
    if len(tokens) < HOURS_PER_WEEK:
        raise ValueError(f"demand has {len(tokens)} hourly slots, need {HOURS_PER_WEEK}")
    tokens = tokens[:HOURS_PER_WEEK]

    alpha = float(config["alpha"])
    calibration_days = int(config["calibration_days"])
    lams = [float(v) for v in config["lam_grid"]]
    tail_quantile = float(config["tail_quantile"])

    # Week starts whose week and whole calibration window are covered.
    available = set.intersection(*(set(realized[a]) for a in authorities))
    starts: list[datetime] = []
    cursor = datetime(int(config["weeks"]["year"]), 1, 1)
    while cursor.year == int(config["weeks"]["year"]) and cursor.month in config["weeks"]["months"]:
        span = [cursor + timedelta(hours=i) for i in range(HOURS_PER_WEEK)]
        cal_start = cursor - timedelta(days=calibration_days)
        cal_ok = all(
            cal_start + timedelta(hours=i) in available for i in range(calibration_days * 24)
        )
        if cal_ok and all(s in available for s in span):
            starts.append(cursor)
        cursor += timedelta(days=7)

    models: dict[str, Any] = {}
    for model in config["forecast_models"]:
        name = str(model["name"])
        forecast = {
            a: forecast_series(
                realized[a],
                kind=str(model["kind"]),
                lag_hours=int(model.get("lag_hours", 24)),
                days=int(model.get("days", 7)),
            )
            for a in authorities
        }
        fleets: dict[str, Any] = {}
        for fleet in config["fleets"]:
            sites = _sites(spec, fleet)
            weeks = []
            for start in starts:
                cal_start = start - timedelta(days=calibration_days)
                absolute_bands, relative_bands = _bands(forecast, realized, cal_start, start, alpha)
                stamps = _aligned_hours(forecast, realized, start, HOURS_PER_WEEK)
                if len(stamps) < HOURS_PER_WEEK // 2:
                    continue
                table = _policy_table(stamps, forecast, absolute_bands, relative_bands, lams)
                weeks.append(
                    _evaluate(
                        stamps,
                        forecast,
                        realized,
                        sites,
                        tokens,
                        table,
                        slot_minutes,
                        tail_quantile,
                    )
                )
            fleets[str(fleet["label"])] = _aggregate(weeks)
        models[name] = {"diagnostic": _diagnostic(forecast, realized), "fleets": fleets}

    # Sensitivity: price the unclassified "Other" fuel at the gas factor.
    sensitivity: dict[str, Any] | None = None
    if config.get("other_factor_sensitivity"):
        original = eia.FACTORS_G_PER_KWH["Other Fuel Sources"]
        eia.FACTORS_G_PER_KWH["Other Fuel Sources"] = eia.FACTORS_G_PER_KWH["Natural Gas"]
        try:
            alt_all, _ = eia.intensity_series(rows, tolerance=tolerance)
            alt = {a: alt_all[a] for a in authorities}
            model = config["forecast_models"][0]
            forecast = {
                a: forecast_series(
                    alt[a],
                    kind=str(model["kind"]),
                    lag_hours=int(model.get("lag_hours", 24)),
                    days=int(model.get("days", 7)),
                )
                for a in authorities
            }
            sensitivity = {
                "other_factor": "natural_gas",
                "diagnostic": _diagnostic(forecast, alt),
            }
        finally:
            eia.FACTORS_G_PER_KWH["Other Fuel Sources"] = original

    # How much of each site's generation the zero-priced "Other" fuel accounts
    # for, so the reader can see what that assumption is worth.
    other_totals = dict.fromkeys(authorities, 0.0)
    net_totals = dict.fromkeys(authorities, 0.0)
    for row in rows:
        authority = row["Balancing Authority"]
        if authority not in other_totals:
            continue
        if eia.intensity(row, tolerance=tolerance) is None:
            continue
        generation = eia.fuel_generation(row)
        other_totals[authority] += generation["Other Fuel Sources"]
        net_totals[authority] += sum(generation.values())
    other_share = {
        a: round(other_totals[a] / net_totals[a] * 100, 3) if net_totals[a] else 0.0
        for a in authorities
    }

    return {
        "grid": {
            "source": "EIA-930 hourly generation by fuel per balancing authority",
            "factors": "EIA published averages (coal 2.31, gas 0.96, petroleum 2.46 lb CO2/kWh)",
            "rounding_tolerance": tolerance,
            "site_coverage": coverage,
            "other_fuel_share_pct": other_share,
            "sites": {str(i["authority"]): str(i["label"]) for i in spec},
            "n_authorities_in_file": len(stats),
            "n_authorities_priced": len(realized_all),
        },
        "n_weeks": len(starts),
        "models": models,
        "other_factor_sensitivity": sensitivity,
        "disclosures": [
            "Realized intensity is computed from each authority's own measured fuel mix, "
            "not from a national series. That is the whole point of this experiment.",
            "EIA publishes no carbon forecast, so the forecast is ours (persistence and "
            "same-hour weekly mean), disclosed and run as two models.",
            "Emission factors are national averages applied to a real mix: the mix is "
            "measured, the factor is a modelling assumption, with a sensitivity on the "
            "unclassified 'Other' fuel.",
            "Interchange is not attributed, so an authority importing clean power looks "
            "dirtier than its consumption would.",
            "Demand is the single real Azure week laid positionally over each carbon week, "
            "as in every other dispatch experiment.",
        ],
    }
