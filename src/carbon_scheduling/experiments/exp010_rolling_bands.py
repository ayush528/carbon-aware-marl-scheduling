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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from carbon_scheduling.bands import conformal_quantile, regional_residuals
from carbon_scheduling.data.neso import load_slot_json, read_tidy_csv
from carbon_scheduling.runner import REPO_ROOT

ALPHA = 0.1
TARGET = 1 - ALPHA
CALIB_DAYS = 28

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


def _relative_coverage(
    regional: list[dict[str, Any]],
    national: list[dict[str, Any]],
    q_rel: float,
) -> float:
    """Coverage of a band whose half-width is ``forecast * q_rel``.

    Computed per region from that region's own slots (residual under national
    scaling against the slot's own band), so the "one calibration covers every
    region" claim is tested rather than assumed.
    """
    nat = {
        r["from"]: r
        for r in national
        if r.get("actual") is not None and r.get("forecast") not in (None, 0)
    }
    n = inside = 0
    for reg in regional:
        nat_row = nat.get(reg["from"])
        forecast = reg.get("forecast")
        if nat_row is None or not forecast:
            continue
        residual = abs(nat_row["actual"] - nat_row["forecast"]) * forecast / nat_row["forecast"]
        n += 1
        inside += residual <= forecast * q_rel
    if not n:
        raise ValueError("no evaluation slots")
    return inside / n


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
    for month in range(1, 13):
        eval_start, eval_end = _month_bounds(year, month)
        calib_start = eval_start - timedelta(days=CALIB_DAYS)

        calib_national = _slice(national_index, calib_start, eval_start)
        eval_national = _slice(national_index, eval_start, eval_end)
        q_rel = conformal_quantile(_relative_errors(calib_national), ALPHA)
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
                    "relative_coverage": round(
                        _relative_coverage(eval_reg, eval_national, q_rel), 4
                    ),
                    "constant_coverage": round(_coverage(eval_res, q_const), 4),
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

    def _mean(cs: list[dict[str, Any]], key: str) -> float:
        return sum(c[key] for c in cs) / len(cs)

    def _at_target(cs: list[dict[str, Any]], key: str) -> float:
        return round(100 * sum(1 for c in cs if c[key] >= TARGET) / len(cs), 2)

    per_region: dict[str, Any] = {}
    for rid in sorted({c["regionid"] for c in cells}):
        own = [c for c in cells if c["regionid"] == rid]
        per_region[str(rid)] = {
            "shortname": own[0]["shortname"],
            "sim_site": rid in SIM_SITES,
            "months": len(own),
            "relative_mean_coverage": round(_mean(own, "relative_coverage"), 4),
            "relative_min_coverage": min(c["relative_coverage"] for c in own),
            "relative_months_at_target": sum(1 for c in own if c["relative_coverage"] >= TARGET),
            "constant_mean_coverage": round(_mean(own, "constant_coverage"), 4),
            "constant_months_at_target": sum(1 for c in own if c["constant_coverage"] >= TARGET),
            "constant_half_width_pct_of_mean": round(
                100
                * _mean(own, "constant_half_width_gco2_per_kwh")
                / _mean(own, "mean_forecast_gco2_per_kwh"),
                2,
            ),
        }

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
            "mean_coverage": round(_mean(cells, "relative_coverage"), 4),
            "min_cell_coverage": min(c["relative_coverage"] for c in cells),
            "max_cell_coverage": max(c["relative_coverage"] for c in cells),
            "cells_at_target_pct": _at_target(cells, "relative_coverage"),
            "mean_half_width_pct_of_forecast": round(_mean(cells, "relative_half_width_pct"), 2),
            "coverage_identical_across_regions": spread < 1e-9,
            "max_within_month_regional_spread": round(spread, 4),
            # Binomial standard error of coverage over all evaluated slots.
            "coverage_stderr": round((TARGET * (1 - TARGET) / n_eval_total) ** 0.5, 4),
        },
        "constant": {
            "mean_coverage": round(_mean(cells, "constant_coverage"), 4),
            "min_cell_coverage": min(c["constant_coverage"] for c in cells),
            "max_cell_coverage": max(c["constant_coverage"] for c in cells),
            "cells_at_target_pct": _at_target(cells, "constant_coverage"),
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
            "mean_coverage": round(_mean(sim_cells, "relative_coverage"), 4),
            "min_coverage": min(c["relative_coverage"] for c in sim_cells),
            "cells_at_target_pct": _at_target(sim_cells, "relative_coverage"),
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
