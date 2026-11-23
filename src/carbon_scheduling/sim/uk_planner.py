"""A carbon-aware planner that runs inside SustainCluster as a controller.

This is the head-to-head arm: **our** scheduling rule, expressed in upstream's
own action space (per pending task: defer, or route to one of the sites), scored
by upstream's own carbon/energy/SLA accounting. The point is to compare against
the published rule-based controllers on identical terms rather than across
papers.

Where the information comes from (this matters):

* **Decisions** use the NESO *forecast* series (``data/uk_regional_2024_tidy.csv``)
  plus a conformal band calibrated on the national forecast residuals of the
  month before the run. A planner that read the simulator's installed series
  would have perfect foresight, which would make the comparison meaningless.
* **Accounting** is upstream's: the simulator consumes the derived regional
  series, so the carbon it reports is the realized one.

The band is applied exactly as the project's estimator defines it:

    band_region(t) = q_national * forecast_region(t) / forecast_national(t)

Because the scaling factor is common to all sites at a given slot, the band
cannot reorder sites -- it can only change *when* work is worth doing. That is
the same structural property exp011/exp016/exp017 measured, and it is pinned by
a test here rather than assumed.

Stdlib only: this module is imported by a driver that runs with the upstream
checkout's interpreter, which has no dependency on ``carbon_scheduling``.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TIMESTEP = timedelta(minutes=15)


# --------------------------------------------------------------------------- #
# Series loading
# --------------------------------------------------------------------------- #


def _parse_utc(text: str) -> datetime:
    """Parse ``2024-01-01T00:00Z`` or ``2024-01-01 00:00:00+00:00`` into naive UTC."""
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is not None:
        stamp = (stamp - stamp.utcoffset()).replace(tzinfo=None)
    return stamp.replace(minute=0, second=0, microsecond=0)


def load_regional_forecast(
    path: str | Path, region_ids: dict[str, int]
) -> dict[str, dict[datetime, float]]:
    """Hourly mean NESO forecast per region slug (``{slug: {hour: g/kWh}}``).

    The regional API is half-hourly; a slot's hour value is the mean of the two
    half-hour slots that fall in it. Missing half-hours are skipped, so an hour
    is present only if at least one half-hour is.
    """
    by_id = {int(rid): slug for slug, rid in region_ids.items()}
    acc: dict[str, dict[datetime, list[float]]] = {slug: {} for slug in region_ids}
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            rid = int(row["regionid"])
            slug = by_id.get(rid)
            if slug is None or row["forecast"] in ("", None):
                continue
            stamp = _parse_utc(row["from"])
            acc[slug].setdefault(stamp, []).append(float(row["forecast"]))
    return {
        slug: {hour: sum(values) / len(values) for hour, values in per_hour.items()}
        for slug, per_hour in acc.items()
    }


def load_national(path: str | Path) -> dict[datetime, dict[str, float]]:
    """Hourly national forecast/actual from the pulled JSON (mean of half-hours)."""
    payload = json.loads(Path(path).read_text())
    records = payload["data"] if isinstance(payload, dict) else payload
    acc: dict[datetime, dict[str, list[float]]] = {}
    for row in records:
        hour = _parse_utc(row["from"])
        bucket = acc.setdefault(hour, {"forecast": [], "actual": []})
        if row.get("forecast") is not None:
            bucket["forecast"].append(float(row["forecast"]))
        if row.get("actual") is not None:
            bucket["actual"].append(float(row["actual"]))
    out: dict[datetime, dict[str, float]] = {}
    for hour, bucket in acc.items():
        record: dict[str, float] = {}
        if bucket["forecast"]:
            record["forecast"] = sum(bucket["forecast"]) / len(bucket["forecast"])
        if bucket["actual"]:
            record["actual"] = sum(bucket["actual"]) / len(bucket["actual"])
        out[hour] = record
    return out


# --------------------------------------------------------------------------- #
# Conformal band
# --------------------------------------------------------------------------- #


def conformal_quantile(residuals: Iterable[float], alpha: float) -> float:
    """Finite-sample-corrected split-conformal half-width (same rule as bands.py)."""
    values = sorted(abs(float(r)) for r in residuals)
    if not values:
        raise ValueError("no residuals to calibrate on")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    k = math.ceil((len(values) + 1) * (1.0 - alpha))
    if k > len(values):
        return math.inf
    return values[k - 1]


def calibrate_band(
    national: dict[datetime, dict[str, float]], before: datetime, alpha: float
) -> float:
    """National band half-width from residuals strictly before ``before``.

    Strictly-before is the leakage guard: the run's window is never used to size
    the band that decides inside it.
    """
    residuals = [
        abs(record["actual"] - record["forecast"])
        for hour, record in national.items()
        if hour < before and "actual" in record and "forecast" in record
    ]
    return conformal_quantile(residuals, alpha)


def site_band(forecast_site: float, forecast_national: float, q_national: float) -> float:
    """Regional band under the national-scaling estimator (see module docstring)."""
    if forecast_national <= 0.0:
        return 0.0
    return q_national * forecast_site / forecast_national


def risk(forecast_site: float, forecast_national: float, q_national: float, lam: float) -> float:
    """Risk-qualified intensity: forecast plus ``lam`` bands."""
    return forecast_site + lam * site_band(forecast_site, forecast_national, q_national)


# --------------------------------------------------------------------------- #
# The policy
# --------------------------------------------------------------------------- #


def _hour(stamp: datetime) -> datetime:
    return stamp.replace(minute=0, second=0, microsecond=0)


def _capacity_ok(dc: Any, task: Any, committed: dict[int, float]) -> bool:
    spare_cores = getattr(dc, "available_cores", math.inf) - committed.get(-dc.dc_id, 0.0)
    return (
        dc.available_gpus - committed.get(dc.dc_id, 0.0) >= task.gpu_req
        and spare_cores >= task.cores_req
        and getattr(dc, "available_mem", math.inf) >= task.mem_req
    )


def _window_risk(
    forecast: dict[datetime, float],
    national: dict[datetime, dict[str, float]],
    now: datetime,
    duration_minutes: float,
    q_national: float,
    lam: float,
) -> float | None:
    """Mean risk-qualified intensity over a task's execution window.

    ``lowest_carbon`` prices a task at the intensity of the single 15-minute
    slot it arrives in. A task runs for tens of minutes, so what matters is the
    intensity over the slots it will occupy. Integrating over the window is the
    placement rule this project argues for; the band enters the same integral.
    """
    slots = max(1, math.ceil(duration_minutes / 60.0))
    values: list[float] = []
    for offset in range(slots):
        hour = _hour(now + timedelta(hours=offset))
        site_forecast = forecast.get(hour)
        nat = national.get(hour, {}).get("forecast")
        if site_forecast is None or nat is None or nat <= 0.0:
            continue
        values.append(risk(site_forecast, nat, q_national, lam))
    if not values:
        return None
    return sum(values) / len(values)


class DurationAwareStrategy:
    """Our placement rule, shaped like one of upstream's RBC strategies.

    Injecting it into the cluster manager's strategy map means tasks travel the
    *same* assignment path as the published controllers: no transit step, no
    action-space translation, identical accounting. That is what makes the
    comparison a comparison and not a measurement of the harness.

    ``lam = 0`` is duration-aware placement on the point forecast; ``lam = 1``
    adds one calibrated band, which can reorder sites only by weighting hours
    differently -- at a single slot the band scales every site equally and
    cannot reorder (pinned by a test).
    """

    def __init__(
        self,
        *,
        forecast: dict[str, dict[datetime, float]],
        national: dict[datetime, dict[str, float]],
        q_national: float,
        lam: float,
        window_hours: float | None = None,
    ) -> None:
        self.forecast = forecast
        self.national = national
        self.q_national = q_national
        self.lam = lam
        # ``None`` = integrate over the task's own duration; ``0`` = one slot
        # (the published controller's view), which is the sanity-check arm.
        self.window_hours = window_hours

    def reset(self) -> None:
        return None

    def _score(self, dc: Any, now: datetime, duration_minutes: float) -> float | None:
        slug = getattr(dc, "location", "")
        hours = (
            duration_minutes if self.window_hours is None else max(1.0, self.window_hours * 60.0)
        )
        return _window_risk(
            self.forecast.get(slug, {}),
            self.national,
            now,
            hours,
            self.q_national,
            self.lam,
        )

    def __call__(self, task: Any, datacenters: dict[str, Any], logger: Any = None) -> int | None:
        if not datacenters:
            return None
        now = next(iter(datacenters.values())).current_time_task
        candidates: list[tuple[float, int]] = []
        for dc in datacenters.values():
            if hasattr(dc, "can_schedule") and not dc.can_schedule(task):
                continue
            score = self._score(dc, now, float(task.duration))
            if score is None:
                # No forecast for this site/hour: fall back to the simulator's
                # own instantaneous signal rather than dropping the task.
                score = float(dc.get_current_carbon_intensity())
            candidates.append((score, int(dc.dc_id)))
        if not candidates:
            return None
        # Ties break on dc_id so the run is deterministic.
        return min(candidates)[1]
