"""exp011 -- does the calibrated band change dispatch, and does it help?

Phase 3, rung 4: the first experiment where the band is an *input to a
decision* rather than a coverage statistic. It runs a capacity-aware
carbon-greedy dispatcher over the real Azure LLM week (2024-05-10..17) on four
real UK regions, driven by NESO's *forecast*, and scores the resulting dispatch
against the *realized* intensity.

Why the forecast/realized split matters: inside the upstream simulator a site
sees one series, so a forecast error cannot exist and a band cannot do
anything. The split has to come from our own data. Here:

    forecast_i(t) = NESO regional forecast for region i
    realized_i(t) = national_actual(t) x forecast_i(t) / national_forecast(t)

The realized column is the documented national-scaling estimate (NESO ships no
regional actuals), so the *error* being banded is national forecast error
propagated to each region -- real, measured, and disclosed.

Band constructions (calibrated on the 28 days before the evaluation week, so
no leakage):

  * ``absolute``: per-region conformal half-width of |realized - forecast|.
    Widths differ across regions, so this band can reorder sites.
  * ``relative``: pooled conformal quantile of |error| / forecast, applied as a
    fraction of each site's forecast. This is exp010's best-calibrated
    construction. It scales every score by the same ``(1 + lam*q)``, so it
    provably *cannot* reorder sites: the run checks the dispatch is identical
    to forecast-greedy, which is the honest way to report that "add the band
    to the objective" is not by itself a contribution.

Policies: forecast-greedy (lam=0), the two band variants over a lam grid, and
an oracle that knows the realized intensity (a lower bound, not achievable).
All share one capacity model, so differences are the decision and nothing else.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from carbon_scheduling import dispatch
from carbon_scheduling.cluster import Site, site_energy_kwh
from carbon_scheduling.demand import requests_per_slot
from carbon_scheduling.runner import REPO_ROOT

SLOT_MINUTES = 30


def _parse(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%dT%H:%MZ")


def _num(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def site_series(
    regional_rows: list[dict[str, Any]],
    national_rows: list[dict[str, Any]],
    regions: dict[str, int],
) -> dict[str, dict[str, dict[datetime, float]]]:
    """Per-site ``{"forecast": {...}, "realized": {...}}`` on a shared timeline.

    ``realized = national_actual x regional_forecast / national_forecast``
    (the documented estimator). Slots missing any input are dropped rather than
    guessed, and the counters make that visible.
    """
    national: dict[datetime, tuple[float, float]] = {}
    for row in national_rows:
        forecast, actual = _num(row.get("forecast")), _num(row.get("actual"))
        if forecast is None or actual is None:
            continue
        national[_parse(row["from"])] = (forecast, actual)

    wanted = {rid: slug for slug, rid in regions.items()}
    out: dict[str, dict[str, dict[datetime, float]]] = {
        slug: {"forecast": {}, "realized": {}} for slug in regions
    }
    for row in regional_rows:
        rid = row.get("regionid")
        slug = wanted.get(int(rid)) if rid is not None else None
        if slug is None:
            continue
        forecast = _num(row.get("forecast"))
        if forecast is None:
            continue
        stamp = _parse(row["from"])
        out[slug]["forecast"][stamp] = forecast
        pair = national.get(stamp)
        if pair is None or pair[0] == 0:
            continue
        out[slug]["realized"][stamp] = pair[1] * forecast / pair[0]
    return out


def residuals(
    series: dict[str, dict[str, dict[datetime, float]]],
    start: datetime,
    end: datetime,
) -> tuple[dict[str, list[float]], dict[str, list[float]], dict[str, list[float]]]:
    """Absolute residuals, forecast levels, and relative residuals per site.

    Only slots where both forecast and realized exist inside ``[start, end)``
    contribute -- the calibration set can never borrow from the evaluation
    week.
    """
    absolute: dict[str, list[float]] = {}
    levels: dict[str, list[float]] = {}
    relative: dict[str, list[float]] = {}
    for slug, rows in series.items():
        absv, fcs, rel = [], [], []
        for stamp, forecast in rows["forecast"].items():
            realized = rows["realized"].get(stamp)
            if realized is None or not (start <= stamp < end) or forecast == 0:
                continue
            absv.append(abs(realized - forecast))
            fcs.append(forecast)
            rel.append(abs(realized - forecast) / forecast)
        absolute[slug], levels[slug], relative[slug] = absv, fcs, rel
    return absolute, levels, relative


def _evaluate(
    slots: list[dict[str, Any]],
    sites: dict[str, Site],
    score_table: list[dict[str, float]],
    realized: list[dict[str, float]],
    forecast: list[dict[str, float]],
) -> dict[str, Any]:
    """Run one policy over every slot and account for what it emitted.

    Per slot: demand -> GPU-seconds, then a capacity-aware greedy allocation
    by score, then energy per site through the cluster model, then carbon twice
    (against realized and against forecast). Unserved demand is reported, since
    the model has no queue and a slot the fleet cannot absorb is a deadline
    risk.
    """
    capacity = {
        slug: site.n_gpus * SLOT_MINUTES * 60 for slug, site in sites.items()
    }
    carbon_realized = 0.0
    carbon_forecast = 0.0
    energy_total = 0.0
    unserved = 0.0
    demand_total = 0.0
    picks: list[tuple[str, ...]] = []
    per_slot_carbon: list[float] = []
    for slot, scores, real, fc in zip(slots, score_table, realized, forecast, strict=True):
        tokens = slot["context_tokens"] + slot["generated_tokens"]
        demand_gpu_seconds = tokens / next(iter(sites.values())).tokens_per_gpu_second
        alloc, left = dispatch.allocate(scores, demand_gpu_seconds, capacity)
        energy = {slug: site_energy_kwh(sites[slug], alloc[slug]) for slug in sites}
        slot_carbon = dispatch.carbon_kg(energy, real)
        carbon_realized += slot_carbon
        carbon_forecast += dispatch.carbon_kg(energy, fc)
        per_slot_carbon.append(slot_carbon)
        energy_total += sum(energy.values())
        unserved += left
        demand_total += demand_gpu_seconds
        picks.append(tuple(slug for slug in dispatch.rank(scores)))
    return {
        "carbon_kg_realized": carbon_realized,
        "carbon_kg_forecast": carbon_forecast,
        "energy_kwh_total": energy_total,
        "unserved_gpu_seconds": unserved,
        "unserved_fraction": (unserved / demand_total) if demand_total else 0.0,
        "per_slot_carbon_kg": per_slot_carbon,
        "picks": picks,
    }


def _quantile(values: list[float], q: float) -> float:
    """Nearest-rank quantile; deterministic and dependency-free."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def summarise_fleet(
    results: dict[str, dict[str, Any]],
    *,
    n_gpus: int,
    n_slots: int,
) -> dict[str, Any]:
    """Turn one fleet's raw runs into the experiment's reported rows.

    Carbon is reported three ways because a risk-averse rule trades the middle
    of the distribution for the tail: the total (mean behaviour), the 95th
    percentile slot, and the CVaR-95 of per-slot emissions (the mean of the
    worst 5% of slots). A band that leaves the mean identical but lowers the
    tail is a real effect; one that leaves everything identical is a real
    non-effect, and both are reported.
    """
    base = results["forecast_greedy"]
    oracle_carbon = results["oracle_realized"]["carbon_kg_realized"]

    def flips(picks: list[tuple[str, ...]]) -> int:
        """Slots whose top-ranked site differs from forecast-greedy."""
        return sum(1 for a, b in zip(picks, base["picks"], strict=True) if a[0] != b[0])

    rows: dict[str, dict[str, Any]] = {}
    for name, res in results.items():
        per_slot = res["per_slot_carbon_kg"]
        worst = sorted(per_slot)[-max(1, len(per_slot) // 20) :]
        rows[name] = {
            "carbon_kg_realized": round(res["carbon_kg_realized"], 1),
            "carbon_kg_forecast": round(res["carbon_kg_forecast"], 1),
            "carbon_vs_forecast_greedy_pct": round(
                (res["carbon_kg_realized"] / base["carbon_kg_realized"] - 1) * 100, 3
            ),
            "regret_vs_oracle_pct": round(
                (res["carbon_kg_realized"] / oracle_carbon - 1) * 100, 3
            ),
            "carbon_kg_slot_mean": round(res["carbon_kg_realized"] / n_slots, 3),
            "carbon_kg_slot_p95": round(_quantile(per_slot, 0.95), 3),
            "carbon_kg_slot_max": round(max(per_slot), 3),
            "carbon_cvar95_kg": round(sum(worst) / len(worst), 3),
            "energy_kwh_total": round(res["energy_kwh_total"], 1),
            "unserved_fraction_pct": round(res["unserved_fraction"] * 100, 3),
            "flipped_slots": flips(res["picks"]),
            "flipped_slots_pct": round(flips(res["picks"]) / n_slots * 100, 2),
        }

    # The theorem exp010 predicted: a proportional band cannot reorder sites,
    # so its dispatch is identical to forecast-greedy. Checked, not assumed.
    relative_names = [n for n in rows if n.startswith("band_relative")]
    relative_invariant = all(
        rows[n]["flipped_slots"] == 0
        and rows[n]["carbon_kg_realized"] == rows["forecast_greedy"]["carbon_kg_realized"]
        and rows[n]["carbon_cvar95_kg"] == rows["forecast_greedy"]["carbon_cvar95_kg"]
        for n in relative_names
    )
    band_names = [n for n in rows if n.startswith("band_")]
    best_band = min(band_names, key=lambda n: rows[n]["carbon_kg_realized"])
    best_band_tail = min(band_names, key=lambda n: rows[n]["carbon_cvar95_kg"])

    return {
        "n_gpus_per_site": n_gpus,
        "policies": rows,
        "relative_band_decision_invariant": relative_invariant,
        "oracle_reduction_vs_forecast_greedy_pct": round(
            (oracle_carbon / base["carbon_kg_realized"] - 1) * 100, 3
        ),
        "best_band_policy_by_total_carbon": best_band,
        "best_band_policy_by_tail_carbon": best_band_tail,
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel for rel in config["data"]]
    by_name = {p.name: p for p in paths}

    regional_rows: list[dict[str, Any]] = []
    with by_name["uk_regional_2024_tidy.csv"].open(newline="") as handle:
        import csv

        regional_rows = list(csv.DictReader(handle))
    national_rows = json.loads(by_name["uk_national_2023-12_2024-12.json"].read_text())["data"]

    regions: dict[str, int] = config["regions"]
    window = config["window"]
    start = _parse(window["start"])
    end = _parse(window["end"])
    calibration_days = int(config["calibration_days"])
    cal_start = start - timedelta(days=calibration_days)
    alpha = float(config["alpha"])

    series = site_series(regional_rows, national_rows, regions)
    abs_res, levels, rel_res = residuals(series, cal_start, start)

    # --- calibration (28 days *before* the evaluation week) ---
    absolute = dispatch.absolute_half_widths(abs_res, alpha)
    pooled = dispatch.relative_half_widths(
        {"all": [v for values in rel_res.values() for v in values]},
        {"all": [v for values in levels.values() for v in values]},
        alpha,
    )["all"]
    per_site_relative = dispatch.relative_half_widths(rel_res, levels, alpha)

    # --- evaluation week: demand, forecast, realized ---
    demand_slots = requests_per_slot(by_name["AzureLLMInferenceTrace_code_1week.csv"])
    slots = [s for s in demand_slots if start <= _parse(s["from"]) < end]
    if not slots:
        raise ValueError(f"no demand slots inside {window['start']}..{window['end']}")

    stamps = [_parse(s["from"]) for s in slots]
    # Align demand, forecast and realized slot by slot: a slot missing either
    # carbon value is dropped from *all* policies and counted, so every policy
    # is scored on exactly the same slots.
    aligned_slots, forecast, realized = [], [], []
    for slot, stamp in zip(slots, stamps, strict=True):
        if not all(stamp in series[s]["forecast"] for s in regions):
            continue
        if not all(stamp in series[s]["realized"] for s in regions):
            continue
        aligned_slots.append(slot)
        forecast.append({slug: series[slug]["forecast"][stamp] for slug in regions})
        realized.append({slug: series[slug]["realized"][stamp] for slug in regions})
    dropped = len(slots) - len(aligned_slots)
    if not aligned_slots:
        raise ValueError("no slot inside the window has both forecast and realized carbon")
    slots = aligned_slots

    # --- policies (built once: they do not depend on the fleet size) ---
    policies: dict[str, list[dict[str, float]]] = {
        "forecast_greedy": [dict(fc) for fc in forecast],
        "oracle_realized": [dict(real) for real in realized],
    }
    for lam in config["lam_grid"]:
        policies[f"band_absolute_lam{lam}"] = [
            dispatch.risk_scores(fc, absolute, float(lam)) for fc in forecast
        ]
    for lam in config["relative_lam_grid"]:
        policies[f"band_relative_lam{lam}"] = [
            dispatch.risk_scores(fc, {s: pooled * fc[s] for s in fc}, float(lam))
            for fc in forecast
        ]

    fleets: dict[str, dict[str, Any]] = {}
    for fleet in config["fleets"]:
        label = str(fleet["label"])
        sites = {
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
        results = {
            name: _evaluate(slots, sites, table, realized, forecast)
            for name, table in policies.items()
        }
        fleets[label] = summarise_fleet(results, n_gpus=int(fleet["n_gpus"]), n_slots=len(slots))

    return {
        "window": {
            "start_utc": window["start"],
            "end_utc": window["end"],
            "n_slots": len(slots),
            "dropped_slots": dropped,
            "slot_minutes": SLOT_MINUTES,
        },
        "calibration": {
            "start_utc": cal_start.strftime("%Y-%m-%dT%H:%MZ"),
            "end_utc": window["start"],
            "days": calibration_days,
            "alpha": alpha,
            "sites_with_residuals": {s: len(v) for s, v in abs_res.items()},
            "absolute_half_width_gco2_per_kwh": {s: round(v, 3) for s, v in absolute.items()},
            "pooled_relative_fraction": round(pooled, 4),
            "per_site_relative_fraction": {s: round(v, 4) for s, v in per_site_relative.items()},
        },
        "forecast_error_in_window": {
            "mean_abs_error_gco2_per_kwh": {
                s: round(
                    sum(abs(realized[i][s] - forecast[i][s]) for i in range(len(slots)))
                    / len(slots),
                    3,
                )
                for s in regions
            },
            "mean_realized_gco2_per_kwh": {
                s: round(sum(r[s] for r in realized) / len(realized), 2) for s in regions
            },
            "regional_spread_gco2_per_kwh": round(
                max(sum(r[s] for r in realized) / len(realized) for s in regions)
                - min(sum(r[s] for r in realized) / len(realized) for s in regions),
                2,
            ),
        },
        "sites": {slug: {"neso_region_id": rid} for slug, rid in regions.items()},
        "fleets": fleets,
    }
