"""exp010 -- rolling-origin (walk-forward) conformal bands over 2024.

exp004/exp005 validated bands on a single Jan->Feb split. That shows bands can
hit target once; it does not show that a scheduler which can only look backwards
gets calibrated bands, and one held-out month is a noisy coverage estimate. This
experiment is the defensible version:

    for every month M of 2024:
        calibrate on the 28 days immediately BEFORE M
        evaluate coverage on M

No evaluation month contributes to its own calibration, so the numbers are what
an online scheduler could actually achieve. Twelve months x 14 DNO regions gives
168 (region, month) cells instead of one, so both the mean and the spread are
visible.

Two constructions are compared, because the choice is not obvious:

  national_relative    one relative half-width q from national residuals; each
                       region's band is f_it * q, i.e. it tracks that slot's
                       forecast. Under the national-scaling estimator every
                       region shares the same *relative* error, so coverage is
                       identical for all of them -- asserted, not assumed.
  per_region_constant  exp005's construction: a constant absolute half-width per
                       region per month, from that region's own scaled
                       residuals. Conformal validity means it should also reach
                       ~90% coverage; what it cannot do is track a slot's
                       forecast, so where intensity swings within a month it
                       must be wider to keep the same coverage. The experiment
                       reports both coverage and width, so "same guarantee,
                       less sharp" is measured rather than asserted.

Decision relevance -- the number that matters for the paper. A proportional band
cannot reorder regions, so uncertainty does not change *which* region looks
cleanest. What it changes is how often the ranking is *certain*: with bands
f*(1 +- q), the cleanest site is confidently cleaner than the runner-up only
when f_best/f_second < (1-q)/(1+q). The `decision_relevance` block reports that
threshold and the share of slots that clear it, so uncertainty's effect on
decisions is measured rather than asserted.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from carbon_scheduling.bands import conformal_quantile, regional_residuals
from carbon_scheduling.data.neso import load_slot_json, read_tidy_csv
from carbon_scheduling.runner import REPO_ROOT

ALPHA = 0.1
TARGET = 1 - ALPHA
CALIB_DAYS = 28

# Intensity regimes for regime-conditional (Mondrian) calibration, in
# gCO2/kWh. Measured on 2024, |error| grows with intensity up to ~150 and
# |error|/forecast falls from ~12% at 30 g/kWh to ~3% at 250, so a band that
# scales with the forecast is too tight at low intensity (where work moves) and
# too wide at high intensity. Calibrating per regime keeps both ends honest.
INTENSITY_EDGES = (50.0, 100.0, 150.0, 200.0, 300.0)  # upper bounds

# The four regions the simulator schedules on (exp009), by NESO region id.
SIM_SITES = {13: "GB-London", 7: "GB-SouthWales", 3: "GB-NorthWestEngland", 2: "GB-SouthScotland"}


def _ts(value: str) -> datetime:
    """Slot start as naive UTC (the series are all UTC; comparison only)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def _resolve(paths: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for rel in paths:
        path = Path(rel)
        out[path.name] = path if path.is_absolute() else REPO_ROOT / path
    return out


def _dedupe(
    records: list[dict[str, Any]], key_fields: tuple[str, ...] = ("from",)
) -> tuple[list[dict[str, Any]], int]:
    """Keep the first row per key; return (rows, dropped).

    NESO repeats the boundary slot between adjacent weekly windows, so a
    multi-window pull carries a handful of duplicates. Counting them twice
    would weight those slots twice. Regional rows need (slot, region) as the
    key, otherwise the 14 regions collapse into one.
    """
    seen: set[tuple[Any, ...]] = set()
    kept: list[dict[str, Any]] = []
    for row in records:
        key = tuple(row.get(field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept, len(records) - len(kept)


def _index(records: list[dict[str, Any]]) -> tuple[list[datetime], list[dict[str, Any]]]:
    """Sort once by slot start; windows then slice with bisect."""
    # Key on the timestamp only: a duplicated slot would otherwise make Python
    # compare records as tie-breakers and raise TypeError.
    ordered = sorted(((_ts(r["from"]), r) for r in records), key=lambda pair: pair[0])
    return [ts for ts, _ in ordered], [r for _, r in ordered]


def _slice(
    index: tuple[list[datetime], list[dict[str, Any]]], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    stamps, records = index
    return records[bisect_left(stamps, start) : bisect_left(stamps, end)]


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _coverage(residuals: list[float], q: float) -> float:
    if not residuals:
        raise ValueError("no evaluation residuals")
    return sum(1 for e in residuals if e <= q) / len(residuals)


def _relative_errors(records: list[dict[str, Any]]) -> list[float]:
    return [
        abs(r["actual"] - r["forecast"]) / r["forecast"]
        for r in records
        if r.get("forecast") not in (None, 0) and r.get("actual") is not None
    ]


def _band_coverage(
    regional: list[dict[str, Any]],
    national: list[dict[str, Any]],
    half_width: Callable[[float | None], float],
) -> dict[str, Any]:
    """Coverage of a band of the given half-width over the national-scaled residual.

    The residual for a regional slot is the national one scaled by the forecast
    ratio (see ``bands.regional_residuals``), i.e. exactly what
    ``regional_residuals`` returns. Two figures come back:

    ``all``       every slot that pairs with a national actual.
    ``positive``  only slots whose regional forecast is > 0.

    The second is the informative one. A forecast of 0 makes the scaled residual
    0 no matter what the national error was, so such a slot is inside any band
    (a zero-width one included). That is an artefact of the estimator, not
    evidence of calibration, and 2024 has 4.9% of them.
    """
    nat = {
        r["from"]: r
        for r in national
        if r.get("actual") is not None and r.get("forecast") not in (None, 0)
    }
    n_all = n_zero = inside_all = n_pos = inside_pos = 0
    widths: list[float] = []
    for reg in regional:
        nat_row = nat.get(reg["from"])
        forecast = reg.get("forecast")
        if nat_row is None or forecast is None:
            continue
        residual = abs(nat_row["actual"] - nat_row["forecast"]) * forecast / nat_row["forecast"]
        width = half_width(forecast)
        widths.append(width)
        covered = residual <= width
        n_all += 1
        inside_all += covered
        if forecast > 0:
            n_pos += 1
            inside_pos += covered
        else:
            n_zero += 1
    if not n_all:
        raise ValueError("no evaluation slots")
    return {
        "all": inside_all / n_all,
        "positive": (inside_pos / n_pos) if n_pos else None,
        "n_all": n_all,
        "n_zero_forecast": n_zero,
        "zero_forecast_pct": 100 * n_zero / n_all,
        "mean_half_width": sum(widths) / len(widths) if widths else None,
    }


def _ranking_certainty(
    site_index: dict[int, tuple[list[datetime], list[dict[str, Any]]]],
    start: datetime,
    end: datetime,
    q_rel: float,
) -> tuple[int, int, list[float]]:
    """Slots, band-robust slots, and best/runner-up forecast ratios.

    A proportional band is f*(1 +- q). The cleanest site is *confidently*
    cleaner than the runner-up only when

        f_best * (1 + q) < f_second * (1 - q)   <=>   f_best/f_second < (1-q)/(1+q)

    Everything a point estimate does is "always route to the minimum", which is
    free but can be wrong. This measures how often the data supports that
    choice, and by how much the gap misses.
    """
    by_slot: dict[datetime, dict[int, float]] = defaultdict(dict)
    for rid, index in site_index.items():
        for row in _slice(index, start, end):
            if row.get("forecast") is not None:
                by_slot[_ts(row["from"])][rid] = float(row["forecast"])

    threshold = (1.0 - q_rel) / (1.0 + q_rel)
    slots = robust = 0
    ratios: list[float] = []
    for values in by_slot.values():
        if len(values) < 2:
            continue
        ranked = sorted(values.values())
        best, second = ranked[0], ranked[1]
        if second <= 0:
            continue
        slots += 1
        ratio = best / second
        ratios.append(ratio)
        robust += ratio < threshold
    return slots, robust, ratios


def _bucket(forecast: float) -> int:
    """Regime index: first edge strictly above the forecast, else the last one."""
    for index, edge in enumerate(INTENSITY_EDGES):
        if forecast < edge:
            return index
    return len(INTENSITY_EDGES)


def _regime_quantiles(
    scores: list[tuple[float, float]], alpha: float, fallback: float
) -> tuple[dict[int, float], int]:
    """One conformal quantile per intensity regime, falling back when thin.

    ``scores`` is (forecast, |error|) pairs. A regime with fewer than
    ``1/alpha + 1`` calibration points cannot support its own finite-sample
    quantile, so it borrows the global one and the fallback count says how often
    that happened -- a silent zero-width band would be worse.
    """
    by_bucket: dict[int, list[float]] = defaultdict(list)
    for forecast, residual in scores:
        by_bucket[_bucket(forecast)].append(residual)
    minimum = int(1.0 / alpha) + 1
    quantiles: dict[int, float] = {}
    fallbacks = 0
    for bucket in range(len(INTENSITY_EDGES) + 1):
        values = by_bucket.get(bucket, [])
        if len(values) >= minimum:
            quantiles[bucket] = conformal_quantile(values, alpha)
        else:
            quantiles[bucket] = fallback
            fallbacks += 1
    return quantiles, fallbacks


def _scores(records: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """(forecast, |actual - forecast|) for every slot with both."""
    return [
        (r["forecast"], abs(r["actual"] - r["forecast"]))
        for r in records
        if r.get("forecast") not in (None, 0) and r.get("actual") is not None
    ]


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def run(config: dict[str, Any]) -> dict[str, Any]:
    paths = _resolve(config["data"])
    national = load_slot_json(next(p for n, p in paths.items() if n.endswith(".json")))
    regional_rows = read_tidy_csv(next(p for n, p in paths.items() if n.endswith(".csv")))
    year = int(config["year"])

    national, national_dupes = _dedupe(national)
    regional_rows, regional_dupes = _dedupe(regional_rows, ("from", "regionid"))
    national_index = _index([r for r in national if r.get("actual") is not None])
    by_region: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in regional_rows:
        if row.get("forecast") is not None:
            by_region[row["regionid"]].append(row)
    region_index = {rid: _index(rows) for rid, rows in by_region.items()}
    site_index = {rid: region_index[rid] for rid in SIM_SITES if rid in region_index}

    cells: list[dict[str, Any]] = []
    monthly: dict[str, Any] = {}
    regime_fallbacks_total = 0
    for month in range(1, 13):
        eval_start, eval_end = _month_bounds(year, month)
        calib_start = eval_start - timedelta(days=CALIB_DAYS)

        calib_national = _slice(national_index, calib_start, eval_start)
        eval_national = _slice(national_index, eval_start, eval_end)
        q_rel = conformal_quantile(_relative_errors(calib_national), ALPHA)
        calib_scores = _scores(calib_national)
        q_abs = conformal_quantile([e for _, e in calib_scores], ALPHA)
        regime_q, regime_fallbacks = _regime_quantiles(calib_scores, ALPHA, q_abs)
        regime_fallbacks_total += regime_fallbacks
        # Under national scaling a region's relative error equals the national
        # one, so the relative construction's coverage is the national coverage.
        coverage_from_national = _coverage(_relative_errors(eval_national), q_rel)

        slots, robust, ratios = _ranking_certainty(site_index, eval_start, eval_end, q_rel)
        monthly[str(month)] = {
            "calibration_start_utc": calib_start.strftime("%Y-%m-%dT%H:%MZ"),
            "calibration_slots": len(calib_national),
            "national_relative_q": round(q_rel, 4),
            "national_coverage": round(coverage_from_national, 4),
            "threshold_ratio": round((1.0 - q_rel) / (1.0 + q_rel), 4),
            "sim_site_slots": slots,
            "band_robust_pct": round(100 * robust / slots, 2) if slots else None,
            "median_best_to_second_ratio": (round(_median(ratios), 4) if ratios else None),
        }

        for rid, index in sorted(region_index.items()):
            calib_reg = _slice(index, calib_start, eval_start)
            eval_reg = _slice(index, eval_start, eval_end)
            calib_res = regional_residuals(calib_reg, calib_national)
            eval_res = regional_residuals(eval_reg, eval_national)
            if not calib_res or not eval_res:
                continue
            q_const = conformal_quantile(calib_res, ALPHA)
            mean_fc = sum(r["forecast"] for r in eval_reg) / len(eval_reg)
            rel = _band_coverage(eval_reg, eval_national, lambda f, q=q_rel: q * f)
            con = _band_coverage(eval_reg, eval_national, lambda _f, q=q_const: q)
            reg = _band_coverage(eval_reg, eval_national, lambda f, q=regime_q: q[_bucket(f)])
            cells.append(
                {
                    "month": month,
                    "regionid": rid,
                    "shortname": by_region[rid][0]["shortname"],
                    "is_sim_site": rid in SIM_SITES,
                    "n_calibration": len(calib_res),
                    "n_regional_slots": len(eval_reg),
                    "n_eval": len(eval_res),
                    "paired_pct": round(100 * len(eval_res) / len(eval_reg), 2),
                    "zero_forecast_pct": round(rel["zero_forecast_pct"], 2),
                    "relative_coverage": _rounded(rel["positive"]),
                    "relative_coverage_positive": _rounded(rel["positive"]),
                    "relative_coverage_all_slots": round(rel["all"], 4),
                    "constant_coverage": _rounded(con["positive"]),
                    "constant_coverage_all_slots": round(con["all"], 4),
                    "regime_coverage": _rounded(reg["positive"]),
                    "regime_coverage_all_slots": round(reg["all"], 4),
                    "regime_half_width_gco2_per_kwh": round(reg["mean_half_width"] or 0, 2),
                    "constant_half_width_gco2_per_kwh": round(q_const, 2),
                    "relative_half_width_pct": round(100 * q_rel, 2),
                    "mean_forecast_gco2_per_kwh": round(mean_fc, 1),
                }
            )

    if not cells:
        raise ValueError("no (region, month) cells could be evaluated")

    # The relative construction must give every region the same coverage *within
    # a month*, because national scaling gives them all the same relative error
    # for that month's calibration. Coverage may (and should) differ between
    # months: a harder month gets a wider band from a harder calibration window.
    # If the within-month spread ever stops being zero, the estimator changed
    # and the "one calibration covers all regions" claim no longer holds.
    spread = max(
        max(c["relative_coverage"] for c in cells if c["month"] == month)
        - min(c["relative_coverage"] for c in cells if c["month"] == month)
        for month in {c["month"] for c in cells}
    )

    def _values(cs: list[dict[str, Any]], key: str) -> list[float]:
        return [c[key] for c in cs if c.get(key) is not None]

    def _mean(cs: list[dict[str, Any]], key: str) -> float | None:
        vals = _values(cs, key)
        return sum(vals) / len(vals) if vals else None

    def _at_target(cs: list[dict[str, Any]], key: str) -> float | None:
        vals = _values(cs, key)
        if not vals:
            return None
        return round(100 * sum(1 for v in vals if v >= TARGET) / len(vals), 2)

    per_region: dict[str, Any] = {}
    for rid in sorted({c["regionid"] for c in cells}):
        own = [c for c in cells if c["regionid"] == rid]
        per_region[str(rid)] = {
            "shortname": own[0]["shortname"],
            "sim_site": rid in SIM_SITES,
            "months": len(own),
            "relative_mean_coverage": _rounded(_mean(own, "relative_coverage")),
            "relative_min_coverage": _rounded(min(_values(own, "relative_coverage"), default=0)),
            "relative_months_at_target": sum(
                1 for c in own if (c["relative_coverage"] or 0) >= TARGET
            ),
            "zero_forecast_slot_pct": _rounded(_mean(own, "zero_forecast_pct")),
            "constant_mean_coverage": _rounded(_mean(own, "constant_coverage")),
            "constant_months_at_target": sum(
                1 for c in own if (c["constant_coverage"] or 0) >= TARGET
            ),
            "constant_half_width_pct_of_mean": _rounded(
                100
                * _mean(own, "constant_half_width_gco2_per_kwh")
                / _mean(own, "mean_forecast_gco2_per_kwh")
            ),
        }

    # --- residual structure: is the error proportional to the level? --------
    # If it were, a relative band would be right. Measured 2024 says it is not:
    # absolute error grows with intensity while relative error falls, so a
    # relative band over-covers high-intensity slots and under-covers low ones.
    year_scores = _scores(national)
    structure: list[dict[str, Any]] = []
    for bucket in range(len(INTENSITY_EDGES) + 1):
        lo = 0.0 if bucket == 0 else INTENSITY_EDGES[bucket - 1]
        hi = INTENSITY_EDGES[bucket] if bucket < len(INTENSITY_EDGES) else None
        own = [(f, e) for f, e in year_scores if _bucket(f) == bucket]
        if not own:
            continue
        errors = sorted(e for _, e in own)
        structure.append(
            {
                "lo": lo,
                "hi": hi,
                "n": len(own),
                "mean_abs_error": round(sum(errors) / len(errors), 2),
                "q90_abs_error": round(errors[int(0.9 * (len(errors) - 1))], 2),
                "mean_relative_error": round(sum(e / f for f, e in own) / len(own), 4),
            }
        )

    # Alignment diagnostic: how much of the residual is pairing, not forecast
    # skill? The documented pairing is same-slot (shift 0); this only reports
    # whether a lead/lag would look better, and is never used for calibration.
    ordered = sorted(national, key=lambda r: _ts(r["from"]))
    alignment: dict[str, Any] = {"by_shift_slots": {}}
    for shift in (-3, -2, -1, 0, 1, 2, 3):
        pairs = []
        for i in range(max(0, -shift), min(len(ordered), len(ordered) - shift)):
            a, b = ordered[i], ordered[i + shift]
            if a.get("forecast") and b.get("actual") is not None:
                pairs.append(abs(b["actual"] - a["forecast"]))
        if pairs:
            alignment["by_shift_slots"][str(shift)] = round(sum(pairs) / len(pairs), 2)
    if alignment["by_shift_slots"]:
        best = min(alignment["by_shift_slots"].items(), key=lambda kv: kv[1])
        alignment["best_shift_slots"] = int(best[0])
        alignment["used_for_calibration"] = False
        alignment["note"] = (
            "Same-slot pairing (shift 0) is the documented one and is what every "
            "number here uses. The best-shift column only shows how much of the "
            "residual could be a timestamp convention rather than forecast error; "
            "the optimum was not stable across windows, so no shift is applied."
        )

    sim_cells = [c for c in cells if c["is_sim_site"]]
    n_eval_total = sum(c["n_eval"] for c in cells)
    pairing_min = min(c["paired_pct"] for c in cells)
    slots_per_month: dict[str, int] = {}
    for c in cells:
        # Every region shares the month's slot count; take the max so a
        # partially-paired region cannot mask it.
        slots_per_month[str(c["month"])] = max(
            slots_per_month.get(str(c["month"]), 0), c["n_regional_slots"]
        )
    return {
        "year": year,
        "alpha": ALPHA,
        "target_coverage": TARGET,
        "calibration_days": CALIB_DAYS,
        "scheme": "rolling-origin: calibrate on the 28 days before each month",
        "n_cells": len(cells),
        "n_regions": len(per_region),
        "n_evaluation_slots": n_eval_total,
        "pairing": {
            "note": (
                "Regional and national series join on the slot timestamp. If a "
                "source is reformatted, pairs drop silently and coverage would "
                "be measured on fewer slots; this block makes that visible."
            ),
            "min_paired_pct": pairing_min,
            "duplicate_slots_dropped": {
                "national": national_dupes,
                "regional": regional_dupes,
            },
            "slots_per_month": slots_per_month,
        },
        "relative": {
            # Headline: coverage on slots with a positive forecast, i.e. slots
            # the band can actually fail on. See _band_coverage.
            "mean_coverage_positive_forecast": _rounded(_mean(cells, "relative_coverage")),
            "min_cell_coverage": _rounded(min(_values(cells, "relative_coverage"), default=0)),
            "max_cell_coverage": _rounded(max(_values(cells, "relative_coverage"), default=0)),
            "cells_at_target_pct": _at_target(cells, "relative_coverage"),
            # Continuity with exp004/exp005, which counted every paired slot.
            "mean_coverage_all_slots": round(_mean(cells, "relative_coverage_all_slots"), 4),
            "zero_forecast_slot_pct": round(
                100
                * sum(c["zero_forecast_pct"] * c["n_eval"] for c in cells)
                / 100
                / sum(c["n_eval"] for c in cells),
                2,
            ),
            "mean_half_width_pct_of_forecast": round(_mean(cells, "relative_half_width_pct"), 2),
            "coverage_identical_across_regions": spread < 1e-9,
            "max_within_month_regional_spread": round(spread, 4),
            # Binomial standard error of coverage over all evaluated slots.
            "coverage_stderr": round((TARGET * (1 - TARGET) / n_eval_total) ** 0.5, 4),
        },
        "constant": {
            "mean_coverage_positive_forecast": _rounded(_mean(cells, "constant_coverage")),
            "min_cell_coverage": _rounded(min(_values(cells, "constant_coverage"), default=0)),
            "max_cell_coverage": _rounded(max(_values(cells, "constant_coverage"), default=0)),
            "cells_at_target_pct": _at_target(cells, "constant_coverage"),
            "mean_coverage_all_slots": round(_mean(cells, "constant_coverage_all_slots"), 4),
            "mean_half_width_pct_of_forecast": round(
                sum(
                    100 * c["constant_half_width_gco2_per_kwh"] / c["mean_forecast_gco2_per_kwh"]
                    for c in cells
                )
                / len(cells),
                2,
            ),
        },
        "sim_sites": {
            "regions": [SIM_SITES[r] for r in sorted(SIM_SITES) if str(r) in per_region],
            "mean_coverage_positive_forecast": _rounded(_mean(sim_cells, "relative_coverage")),
            "min_coverage_positive_forecast": _rounded(
                min(_values(sim_cells, "relative_coverage"), default=0)
            ),
            "cells_at_target_pct": _at_target(sim_cells, "relative_coverage"),
        },
        "regime_conditional": {
            "note": (
                "Conformal on the absolute residual, one quantile per intensity "
                "regime (edges in INTENSITY_EDGES). Keeps the guarantee inside "
                "each regime instead of averaging over all of them."
            ),
            "edges_gco2_per_kwh": list(INTENSITY_EDGES),
            "mean_coverage_positive_forecast": _rounded(_mean(cells, "regime_coverage")),
            "min_cell_coverage": _rounded(min(_values(cells, "regime_coverage"), default=0)),
            "cells_at_target_pct": _at_target(cells, "regime_coverage"),
            "mean_half_width_pct_of_forecast": round(
                sum(
                    100 * c["regime_half_width_gco2_per_kwh"] / c["mean_forecast_gco2_per_kwh"]
                    for c in cells
                )
                / len(cells),
                2,
            ),
            "thin_regime_fallbacks": regime_fallbacks_total,
        },
        "residual_structure": {
            "note": (
                "Error is not proportional to intensity: |error| grows with the "
                "level while |error|/forecast falls. That is why a single "
                "relative band misallocates width."
            ),
            "by_bucket": structure,
            "alignment": alignment,
        },
        "decision_relevance": {
            "note": (
                "A proportional band cannot reorder regions; it sets how large a "
                "carbon gap must be before routing is defensible. "
                "threshold_ratio is (1-q)/(1+q); band_robust_pct is the share of "
                "slots where the best site's upper bound is below the runner-up's "
                "lower bound."
            ),
            "mean_national_relative_q": round(
                sum(m["national_relative_q"] for m in monthly.values()) / len(monthly), 4
            ),
            "mean_threshold_ratio": round(
                sum(m["threshold_ratio"] for m in monthly.values()) / len(monthly), 4
            ),
            "mean_band_robust_pct": round(
                sum(m["band_robust_pct"] or 0.0 for m in monthly.values()) / len(monthly),
                2,
            ),
            "by_month": monthly,
        },
        "per_region": per_region,
        "cells": cells,
    }
