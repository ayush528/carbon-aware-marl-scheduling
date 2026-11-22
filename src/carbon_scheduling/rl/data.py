"""Episode assembly for the Phase 3 agents (ours; no upstream code).

Turns the validated data into the arrays one episode needs:

    forecast / realized / band   (T, N) gCO2/kWh
    demand_tokens                (T,)    tokens offered per slot

The **band for an episode is calibrated on the 28 days before that episode's
week**, exactly the rolling-origin rule exp010 uses, so an agent never sees a
band fitted on its own week. The demand trace is the one Azure week (the only
real LLM arrival stream we have) and is reused across episodes -- disclosed,
and harmless for the comparison, because every policy in an experiment sees
the identical demand and only the carbon week changes.
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
from carbon_scheduling.demand import requests_per_slot
from carbon_scheduling.runner import REPO_ROOT

SLOT_MINUTES = 30


def _parse(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%dT%H:%MZ")


def panel(
    paths: dict[str, Path],
    regions: dict[str, int],
) -> dict[str, dict[str, dict[datetime, float]]]:
    """Per-site forecast/realized series for the whole year, keyed by slot."""
    regional_rows: list[dict[str, Any]] = []
    with Path(paths["regional"]).open(newline="") as handle:
        regional_rows = list(csv.DictReader(handle))
    national_rows = json.loads(Path(paths["national"]).read_text())["data"]

    national: dict[datetime, tuple[float, float]] = {}
    for row in national_rows:
        forecast = row.get("forecast")
        actual = row.get("actual")
        if forecast is None or actual is None:
            continue
        national[_parse(row["from"])] = (float(forecast), float(actual))

    wanted = {rid: slug for slug, rid in regions.items()}
    out: dict[str, dict[str, dict[datetime, float]]] = {
        slug: {"forecast": {}, "realized": {}} for slug in regions
    }
    for row in regional_rows:
        try:
            slug = wanted[int(row["regionid"])]
        except (KeyError, TypeError, ValueError):
            continue
        try:
            forecast = float(row["forecast"])
        except (TypeError, ValueError):
            continue
        stamp = _parse(row["from"])
        out[slug]["forecast"][stamp] = forecast
        pair = national.get(stamp)
        if pair is None or pair[0] == 0:
            continue
        out[slug]["realized"][stamp] = pair[1] * forecast / pair[0]
    return out


def demand_tokens(path: Path) -> dict[datetime, float]:
    """Tokens offered per half-hour slot, keyed by slot start."""
    return {
        _parse(slot["from"]): float(slot["context_tokens"] + slot["generated_tokens"])
        for slot in requests_per_slot(path)
    }


def week_band(
    series: dict[str, dict[str, dict[datetime, float]]],
    start: datetime,
    *,
    days: int = 28,
    alpha: float = 0.1,
) -> dict[str, float]:
    """Per-site absolute conformal half-width from the ``days`` before ``start``."""
    cal_start = start - timedelta(days=days)
    residuals: dict[str, list[float]] = {}
    for slug, rows in series.items():
        values = []
        for stamp, forecast in rows["forecast"].items():
            realized = rows["realized"].get(stamp)
            if realized is None or not (cal_start <= stamp < start) or forecast == 0:
                continue
            values.append(abs(realized - forecast))
        residuals[slug] = values
    if any(not v for v in residuals.values()):
        raise ValueError(f"no calibration residuals before {start:%Y-%m-%d} for some site")
    return dispatch.absolute_half_widths(residuals, alpha)


def episode_arrays(
    series: dict[str, dict[str, dict[datetime, float]]],
    demand: dict[datetime, float],
    start: datetime,
    n_slots: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Forecast, realized and demand arrays for one episode window.

    A slot is kept only if every site has both carbon values and the demand
    trace covers it; partial slots would silently mix truths. The window is
    contiguous, so a gap raises rather than shifts the week.
    """
    sites = list(series)
    forecast = np.zeros((n_slots, len(sites)))
    realized = np.zeros((n_slots, len(sites)))
    tokens = np.zeros(n_slots)
    for i in range(n_slots):
        stamp = start + timedelta(minutes=SLOT_MINUTES * i)
        if stamp not in demand:
            raise ValueError(f"demand trace does not cover {stamp:%Y-%m-%dT%H:%MZ}")
        tokens[i] = demand[stamp]
        for j, slug in enumerate(sites):
            fc = series[slug]["forecast"].get(stamp)
            rc = series[slug]["realized"].get(stamp)
            if fc is None or rc is None:
                raise ValueError(f"{slug} carbon missing at {stamp:%Y-%m-%dT%H:%MZ}")
            forecast[i, j] = fc
            realized[i, j] = rc
    return forecast, realized, tokens


def weekly_windows(
    series: dict[str, dict[str, dict[datetime, float]]],
    demand: dict[datetime, float],
    *,
    months: list[int],
    year: int,
    n_slots: int = 336,
) -> list[datetime]:
    """Every week start inside ``months`` that the data fully covers."""
    available = set.intersection(*(set(rows["realized"]) for rows in series.values()))
    available &= set(demand)
    starts: list[datetime] = []
    cursor = datetime(year, 1, 1, tzinfo=None)
    while cursor.year == year:
        if cursor.month in months:
            span = [
                cursor + timedelta(minutes=SLOT_MINUTES * i) for i in range(n_slots)
            ]
            previous = cursor - timedelta(days=28)
            cal_ok = previous in available and all(
                previous + timedelta(minutes=SLOT_MINUTES * i) in available
                for i in range(0, 28 * 48, 97)
            )
            if cal_ok and all(s in available for s in span):
                starts.append(cursor)
        cursor += timedelta(days=7)
    return starts


def make_sites(spec: dict[str, Any], names: list[str]) -> list[Site]:
    return [
        Site(
            name=name,
            n_gpus=int(spec["n_gpus"]),
            gpu_idle_w=float(spec["gpu_idle_w"]),
            gpu_peak_w=float(spec["gpu_peak_w"]),
            pue=float(spec["pue"]),
            tokens_per_gpu_second=float(spec["tokens_per_gpu_second"]),
        )
        for name in names
    ]


def resolve(paths: list[str]) -> dict[str, Path]:
    """Map the config's ``data:`` list onto the three files the loader needs."""
    out: dict[str, Path] = {}
    for rel in paths:
        path = Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel
        name = path.name
        if name == "uk_regional_2024_tidy.csv":
            out["regional"] = path
        elif name == "uk_national_2023-12_2024-12.json":
            out["national"] = path
        elif name.startswith("AzureLLMInferenceTrace"):
            out["demand"] = path
    missing = {"regional", "national", "demand"} - set(out)
    if missing:
        raise FileNotFoundError(f"config data list is missing {sorted(missing)}")
    return out
