"""Deterministic replay of the committed hybrid scheduler, with its reasons.

exp017's ``BlockPlanner`` is causal: at each slot it prices every (slot, site)
block in its horizon as ``forecast + robust * band``, assigns the live backlog
to the cheapest blocks that can legally hold it under each site's per-slot
capacity, executes the current slot, and replans. This module runs that planner
on one of its own held-out weeks and records enough of each decision to answer
*why*: the queue, the block ledger, every candidate's price and residual
capacity, what was placed, and what was deferred, spilled or left unplaceable.

Two rules keep the explanation honest:

1. **Decisions come from the real planner.** ``RecordingPlanner`` calls
   ``BlockPlanner.plan`` for the offer volume and *separately* replays the same
   ledger with instrumentation. If the two disagree on any slot the payload says
   so (``trace.mismatch_slots``) and tests fail on it. The trace never chooses.
2. **Nothing is invented.** Carbon comes from the committed 2024 NESO series
   laid out by ``rl/data.py``; demand is the verified Azure trace, read from a
   small derived artifact whose SHA-256 is checked against the exp017 run
   manifest. If an artifact is missing the payload carries ``null`` and a note.

The replay is ~0.1 s once the carbon panel and the demand profile are loaded and
the resulting trace is cached under ``viz/backend/cache/`` keyed by the config
hash and the knobs.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from carbon_scheduling.cluster import Site, site_energy_kwh
from carbon_scheduling.experiments.exp017_hybrid_scheduler import PLANNERS
from carbon_scheduling.rl import data
from carbon_scheduling.rl.hybrid import BlockPlanner, HybridEnv
from viz.backend import content, explain, repo

EXP_ID = "exp017-hybrid-scheduler"
RESERVE_EXP_ID = "exp018-arrival-reserve"
BAND_EXP_ID = "exp011-band-dispatch"
PARITY_EXP_ID = "exp013-marl-dispatch"
SOURCE = "docs/datasets/data-audit/downloads/AzureLLMInferenceTrace_code_1week.csv"

HERE = Path(__file__).resolve().parent
DERIVED_DIR = HERE / "derived"
CACHE_DIR = HERE / "cache"
DEMAND_ARTIFACT = DERIVED_DIR / "demand_tokens.json"

# Bump when the trace/explanation shape changes; it is part of the cache key.
REPLAY_VERSION = 1
SLOT_MINUTES = 30

_LOCK = threading.Lock()
_MEM: dict[str, dict[str, Any]] = {}


# --- artifacts ---------------------------------------------------------------


def _optional_metrics(exp_id: str) -> dict[str, Any] | None:
    try:
        return repo.latest_metrics(exp_id)
    except Exception:  # noqa: BLE001 - a missing artifact is a normal state here
        return None


def _optional_config(exp_id: str) -> dict[str, Any] | None:
    try:
        return repo.config(exp_id)
    except Exception:  # noqa: BLE001
        return None


def config() -> dict[str, Any]:
    return repo.config(EXP_ID)


def _config_hash() -> str | None:
    run = repo.latest_run(EXP_ID)
    return run["manifest"].get("config_hash") if run else None


def _latest_run_meta() -> dict[str, Any] | None:
    run = repo.latest_run(EXP_ID)
    if not run:
        return None
    return {
        "run_dir": run["run_dir"],
        "timestamp": run["manifest"].get("timestamp"),
        "git_sha": run["manifest"].get("git_sha"),
        "git_dirty": run["manifest"].get("git_dirty"),
        "config_hash": run["manifest"].get("config_hash"),
        "seed": run["manifest"].get("seed"),
    }


def _trace_source_hash() -> str | None:
    run = repo.latest_run(EXP_ID)
    if not run:
        return None
    return (run["manifest"].get("data_hashes") or {}).get(SOURCE)


def _load_demand() -> tuple[np.ndarray | None, str | None]:
    """Tokens per slot, from the committed derived artifact, hash-checked."""
    if not DEMAND_ARTIFACT.is_file():
        return None, (
            "The derived demand artifact is missing "
            "(viz/backend/derived/demand_tokens.json); regenerate it with "
            "`python -m viz.backend.build_derived`."
        )
    try:
        payload = json.loads(DEMAND_ARTIFACT.read_text())
    except json.JSONDecodeError as exc:
        return None, f"The derived demand artifact is not valid JSON ({exc})."
    expected = _trace_source_hash()
    if expected and payload.get("source_sha256") != expected:
        return None, (
            "The derived demand artifact's recorded trace hash does not match the "
            "exp017 run record, so it is not used."
        )
    tokens = payload.get("tokens")
    if not isinstance(tokens, list) or not tokens:
        return None, "The derived demand artifact carries no per-slot tokens."
    return np.asarray(tokens, dtype=np.float64), None


_DATA_CACHE: dict[str, Any] = {}


def _series_and_tokens() -> tuple[dict[str, Any] | None, np.ndarray | None, str | None]:
    """Carbon panel + demand, loaded once per process (the panel is ~17 MB)."""
    if "series" in _DATA_CACHE:
        return _DATA_CACHE["series"], _DATA_CACHE["tokens"], _DATA_CACHE["note"]
    cfg = config()
    paths = data.resolve(cfg["data"])
    series = data.panel(paths, cfg["regions"])
    tokens, note = _load_demand()
    if tokens is not None and len(tokens) < int(cfg["n_slots"]):
        note = (
            f"The derived demand artifact has {len(tokens)} slots but the config "
            f"needs {cfg['n_slots']}."
        )
        tokens = None
    _DATA_CACHE.update({"series": series, "tokens": tokens, "note": note})
    return series, tokens, note


def _file_signature(paths: list[str]) -> str:
    parts = []
    for rel in paths:
        path = repo.REPO_ROOT / rel
        if path.is_file():
            stat = path.stat()
            parts.append(f"{rel}:{stat.st_size}:{int(stat.st_mtime)}")
        else:
            parts.append(f"{rel}:missing")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


# --- policy metadata ---------------------------------------------------------


def _deadline_label(slots: int) -> str:
    hours = slots * SLOT_MINUTES / 60.0
    return f"{hours:g} h"


def _fleet(config_payload: dict[str, Any], name: str) -> dict[str, Any]:
    for fleet in config_payload.get("fleets", []):
        if fleet.get("name") == name:
            return fleet
    raise KeyError(name)


def _calibrated_reserves(fleet_name: str) -> dict[str, Any]:
    """exp018's per-site-slot reserve at each calibrated level, per fleet."""
    metrics = _optional_metrics(RESERVE_EXP_ID)
    cfg = _optional_config(RESERVE_EXP_ID)
    if not metrics or not cfg:
        return {
            "available": False,
            "reason": f"no run record for {RESERVE_EXP_ID}",
            "window_slots": None,
            "levels": [],
            "note": None,
        }
    fleet = (metrics.get("fleets") or {}).get(fleet_name) or {}
    per_level = fleet.get("reserve_gpu_s_per_site_slot") or {}
    levels = []
    for level, row in sorted(
        (metrics.get("calibration") or {}).items(), key=lambda item: float(item[0])
    ):
        levels.append(
            {
                "level": float(level),
                "quantile_gpu_s": row.get("quantile_gpu_s"),
                "quantile_reverse_gpu_s": row.get("quantile_reverse_gpu_s"),
                "coverage_forward": row.get("coverage_forward"),
                "coverage_reverse": row.get("coverage_reverse"),
                "n_held_out_slots": row.get("n_held_out_slots"),
                "reserve_gpu_s_per_site_slot": per_level.get(level),
            }
        )
    return {
        "available": bool(levels),
        "reason": None if levels else "exp018 record carries no levels for this fleet",
        "exp_id": RESERVE_EXP_ID,
        "window_slots": metrics.get("arrival_window"),
        "levels": levels,
        "note": (
            "Split-conformal upper quantile of arrival exceedance, calibrated on the "
            "first half of the one Azure week and scored on the second half. This is "
            "the uncertainty input that changes the plan; the carbon band cannot."
        ),
    }


def _parity_price() -> float | None:
    metrics = _optional_metrics(PARITY_EXP_ID)
    if not metrics:
        return None
    return (metrics.get("window") or {}).get("parity_price_kg_per_gpu_hour")


def _band_evidence() -> dict[str, Any]:
    metrics = _optional_metrics(BAND_EXP_ID)
    if not metrics:
        return {
            "available": False,
            "reason": f"no run record for {BAND_EXP_ID}",
            "relative_flipped_slots": None,
            "absolute_flipped_slots": None,
            "n_slots": None,
        }
    fleet = (metrics.get("fleets") or {}).get("capacity_bound") or {}
    policies = fleet.get("policies") or {}
    relative = policies.get("band_relative_lam1.0") or {}
    absolute = policies.get("band_absolute_lam1.0") or {}
    return {
        "available": True,
        "reason": None,
        "relative_flipped_slots": relative.get("flipped_slots"),
        "relative_flipped_pct": relative.get("flipped_slots_pct"),
        "absolute_flipped_slots": absolute.get("flipped_slots"),
        "absolute_flipped_pct": absolute.get("flipped_slots_pct"),
        "n_slots": (metrics.get("window") or {}).get("n_slots"),
    }


def meta() -> dict[str, Any]:
    """The scheduler's actual knobs, and the artifacts behind them."""
    cfg = config()
    run = _latest_run_meta()
    metrics = _optional_metrics(EXP_ID)
    weeks = list((metrics or {}).get("weeks") or [])
    fleets = [
        {
            "name": fleet.get("name"),
            "n_gpus_per_site": int(fleet.get("n_gpus") or 0),
            "capacity_gpu_s_per_slot": int(fleet.get("n_gpus") or 0) * SLOT_MINUTES * 60,
        }
        for fleet in cfg.get("fleets", [])
    ]
    deadlines = [
        {
            "slots": int(slots),
            "hours": int(slots) * SLOT_MINUTES / 60.0,
            "label": _deadline_label(int(slots)),
        }
        for slots in cfg.get("deadlines", [])
    ]
    arms = [
        {
            "label": label,
            "kind": spec.get("kind"),
            "robust": float(spec.get("robust", 0.0)),
            "reserve": float(spec.get("reserve", 0.0)),
            "arrival_forecast": int(spec.get("arrival_forecast", 0)),
        }
        for label, spec in PLANNERS.items()
    ]
    default_fleet = fleets[0]["name"] if fleets else None
    reserve_cfg = _optional_config(RESERVE_EXP_ID) or {}
    return {
        "available": bool(weeks) and run is not None,
        "reason": None
        if weeks and run
        else "the committed exp017 run record (its held-out week list) is missing",
        "exp_id": EXP_ID,
        "run": run,
        "weeks": weeks,
        "fleets": fleets,
        "deadlines": deadlines,
        "prices": [float(price) for price in cfg.get("prices", [])],
        "n_slots": int(cfg.get("n_slots", 0)),
        "slot_minutes": SLOT_MINUTES,
        "calibration_days": int(cfg.get("calibration_days", 0)),
        "sites": content.scheduler_sites(cfg.get("regions", {})),
        "arms": arms,
        "reserve_options": {
            "fractions": sorted({float(spec.get("reserve", 0.0)) for spec in PLANNERS.values()}),
            "calibrated": _calibrated_reserves(default_fleet) if default_fleet else None,
            "default_fraction": float(reserve_cfg.get("fixed_reserve", 0.2)),
        },
        "objective": {
            "formula": "carbon_kg + price * missed_gpu_hours",
            "prices": [float(price) for price in cfg.get("prices", [])],
            "parity_price_kg_per_gpu_hour": _parity_price(),
            "note": (
                "The price is the only scalar weight in the objective. Deadlines and "
                "per-slot capacity are hard constraints, not weighted terms."
            ),
        },
        "band": {
            "robust_options": sorted(
                {float(spec.get("robust", 0.0)) for spec in PLANNERS.values()}
            ),
            "evidence": _band_evidence(),
            "note": content.BAND_NOTE,
        },
        "defaults": {
            "week": weeks[-1] if weeks else None,
            "fleet": default_fleet,
            "price": float((cfg.get("prices") or [0.1])[0]),
            "robust": 0.0,
            "reserve_mode": "fraction",
            "reserve": float(reserve_cfg.get("fixed_reserve", 0.2)),
            "reserve_level": None,
        },
        "labels": content.SCHEDULER_LABELS,
        "notes": content.SCHEDULER_NOTES,
        "generated_from": {
            "config_hash": _config_hash(),
            "demand_artifact": DEMAND_ARTIFACT.name,
        },
    }


# --- the recording planner ---------------------------------------------------


class RecordingPlanner(BlockPlanner):
    """``BlockPlanner`` plus a read-only ledger trace of every decision.

    The offer volume returned to the environment is always the parent planner's.
    The trace is built by replaying the same ledger arithmetic with recording; if
    it disagrees with the decision on a slot, that slot is listed and the payload
    reports it. It is never allowed to silently replace the decision.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.traces: list[dict[str, Any]] = []
        self.mismatch_slots: list[int] = []

    def plan(self, env: HybridEnv, t: int) -> dict[int, float]:  # type: ignore[override]
        decision = super().plan(env, t)
        trace = _trace_blocks(env, t, self)
        drifted = [
            i
            for i in range(env.n_agents)
            if abs(trace["offer_now"][i] - float(decision[i]))
            > 1e-6 * max(1.0, abs(float(decision[i])))
        ]
        if drifted:
            self.mismatch_slots.append(t)
        trace["slot"] = t
        trace["match"] = not drifted
        self.traces.append(trace)
        return decision


def _trace_blocks(env: HybridEnv, t: int, planner: BlockPlanner) -> dict[str, Any]:
    """The planner's ledger with recording. Mirrors ``BlockPlanner.plan`` exactly."""
    horizon = planner.max_slots_ahead or max(env.deadlines)
    last = min(t + horizon, env.n_slots)
    n_sites = len(env.sites)

    keep = max(0.0, 1.0 - planner.reserve)
    free = {
        (slot, site): float(env.capacity_gpu_s[site]) * keep
        for slot in range(t, last)
        for site in range(n_sites)
    }
    if planner.arrival_forecast > 0:
        window = max(1, int(planner.arrival_forecast))
        past = env.demand_tokens[max(0, t - window) : t] / env.throughput
        rate = float(past.mean()) if past.size else 0.0
        tightest = min(env.deadlines)
        held = rate / env.n_agents * tightest / len(env.sites)
        for key in free:
            free[key] = max(0.0, free[key] - held)
    if planner.reserve_gpu_s > 0.0:
        for key in free:
            free[key] = max(0.0, free[key] - planner.reserve_gpu_s)
    # ``arrival_model`` is newer than the committed exp017 arms (exp019). Mirror
    # it when the planner has it, so the recording cannot drift from the parent.
    holds = getattr(planner, "holds", None)
    if holds is not None:
        for key, held in holds(env, t, last).items():
            free[key] = max(0.0, free[key] - held)
    price = {
        key: float(env.forecast[key[0], key[1]]) + planner.robust * float(env.band[key[0], key[1]])
        for key in free
    }
    initial = dict(free)

    items: list[tuple[int, int, int, float]] = []
    for i in range(env.n_agents):
        for arrival in sorted(env.queues[i]):
            items.append(
                (arrival + env.deadlines[i] - 1, i, arrival, float(env.queues[i][arrival]))
            )
    items.sort(key=lambda item: (item[0], item[2], item[1]))

    offer_now = {i: 0.0 for i in range(env.n_agents)}
    records: list[dict[str, Any]] = []
    for last_legal, i, arrival, volume in items:
        first_legal = max(t, arrival)
        snapshot = {
            slot: [free[(slot, site)] for site in range(n_sites)]
            for slot in range(first_legal, last_legal + 1)
            if (slot, 0) in free
        }
        slot_options = [
            {
                "slot": slot,
                "free_gpu_s": float(sum(row)),
                "min_price_g_per_kwh": min(
                    price[(slot, site)] for site in range(n_sites) if (slot, site) in price
                ),
                "min_price_site_index": min(
                    (site for site in range(n_sites) if (slot, site) in price),
                    key=lambda site: price[(slot, site)],
                ),
            }
            for slot, row in snapshot.items()
        ]
        record: dict[str, Any] = {
            "class_index": i,
            "arrival": arrival,
            "volume_gpu_s": volume,
            "first_legal_slot": first_legal,
            "last_legal_slot": last_legal,
            "slot_options": slot_options,
            "free_at_now": snapshot.get(t),
            "blocks": [],
            "chosen_slot": None,
            "chosen_site_index": None,
        }
        feasible = [
            key
            for key in price
            if free[key] > 1e-9 and key[0] >= first_legal and key[0] <= last_legal
        ]
        if not feasible:
            offer_now[i] += volume
            record["unassigned_gpu_s"] = volume
            records.append(record)
            continue
        for key in sorted(feasible, key=lambda k: (price[k], k[0])):
            if volume <= 1e-9:
                break
            take = min(volume, free[key])
            free[key] -= take
            volume -= take
            record["blocks"].append({"slot": key[0], "site_index": key[1], "take_gpu_s": take})
            if record["chosen_slot"] is None:
                record["chosen_slot"] = key[0]
                record["chosen_site_index"] = key[1]
            if key[0] == t:
                offer_now[i] += take
        record["unassigned_gpu_s"] = volume
        record["free_at_chosen"] = (
            snapshot.get(record["chosen_slot"]) if record["chosen_slot"] is not None else None
        )
        records.append(record)

    return {
        "offer_now": [offer_now[i] for i in range(env.n_agents)],
        "items": records,
        "initial_capacity_gpu_s": [float(initial[(t, site)]) for site in range(n_sites)],
    }


# --- replay ------------------------------------------------------------------


def _parse_week(week: str) -> datetime:
    return datetime.strptime(week, "%Y-%m-%d")


def _iso(start: datetime, slot: int) -> str:
    return (start + timedelta(minutes=SLOT_MINUTES * slot)).strftime("%Y-%m-%dT%H:%MZ")


def _replay_key(
    week: str,
    fleet: str,
    robust: float,
    reserve: float,
    reserve_gpu_s: float,
    arrival_forecast: int,
) -> str:
    cfg = config()
    payload = {
        "version": REPLAY_VERSION,
        "week": week,
        "fleet": fleet,
        "robust": round(robust, 6),
        "reserve": round(reserve, 6),
        "reserve_gpu_s": round(reserve_gpu_s, 3),
        "arrival_forecast": arrival_forecast,
        "deadlines": cfg.get("deadlines"),
        "sites": cfg.get("sites"),
        "regions": cfg.get("regions"),
        "n_slots": cfg.get("n_slots"),
        "calibration_days": cfg.get("calibration_days"),
        "config_hash": _config_hash(),
        "data": _file_signature(list(cfg.get("data", []))),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def _trace_week(
    week: str,
    fleet_name: str,
    robust: float,
    reserve: float,
    reserve_gpu_s: float,
    arrival_forecast: int,
    price: float,
) -> dict[str, Any]:
    cfg = config()
    series, tokens, demand_note = _series_and_tokens()
    if series is None or tokens is None:
        return {"available": False, "reason": demand_note}
    names = list(cfg["regions"])
    start = _parse_week(week)
    fleet = _fleet(cfg, fleet_name)
    n_gpus = int(fleet["n_gpus"])
    sites = data.make_sites({**cfg["sites"], "n_gpus": n_gpus}, names)
    forecast, realized, _ = data.episode_arrays(series, tokens, start)
    band = data.week_band(series, start, days=int(cfg["calibration_days"]))
    band_array = np.tile(np.array([band[name] for name in names]), (len(tokens), 1))
    env = HybridEnv(
        forecast=forecast,
        realized=realized,
        band=band_array,
        demand_tokens=tokens,
        sites=sites,
        deadlines=[int(d) for d in cfg["deadlines"]],
        sla_penalty_kg_per_gpu_hour=0.0,
        communicate=False,
        include_band_in_obs=False,
    )
    planner = RecordingPlanner(
        robust=robust,
        reserve=reserve,
        reserve_gpu_s=reserve_gpu_s,
        arrival_forecast=arrival_forecast,
    )

    env.reset()
    frames: list[dict[str, Any]] = []
    served_by_slot = np.zeros((env.n_slots, len(sites)))
    while True:
        t = env.t
        queued = _queue_snapshot(env, t)
        amounts = planner.plan(env, t)
        trace = planner.traces[-1]
        served_before = env.served_by_site.copy()
        _obs, _rewards, done, _truncated, _info = env.step_offers(
            [amounts[i] for i in range(env.n_agents)]
        )
        served = env.served_by_site - served_before
        served_by_slot[t] = served
        missed = float(env.slot_violations[-1])
        frames.append(_frame(env, t, start, served, missed, trace, queued, robust))
        if done:
            break

    summary = env.summary()
    return {
        "available": True,
        "reason": None,
        "week": week,
        "window_start_utc": _iso(start, 0),
        "window_end_utc": _iso(start, env.n_slots - 1),
        "n_slots": env.n_slots,
        "fleet": {
            "name": fleet_name,
            "n_gpus_per_site": n_gpus,
            "capacity_gpu_s_per_slot": float(env.capacity_gpu_s[0]),
        },
        "knobs": {
            "robust": robust,
            "reserve": reserve,
            "reserve_gpu_s": reserve_gpu_s,
            "arrival_forecast": arrival_forecast,
        },
        "price_grid_g_per_kwh": [
            [
                round(float(forecast[t, j]) + robust * float(band_array[t, j]), 4)
                for j in range(len(sites))
            ]
            for t in range(env.n_slots)
        ],
        "sites": _site_stats(
            env, names, sites, forecast, realized, band_array, served_by_slot, cfg["regions"]
        ),
        "frames": frames,
        "items": [
            {"slot": trace["slot"], **record}
            for trace in planner.traces
            for record in trace["items"]
        ],
        "summary": {
            **summary,
            "missed_gpu_hours": round(
                (summary["missed_fraction"] * summary["offered_gpu_s"]) / 3600.0, 3
            ),
            "objective": round(
                summary["carbon_kg"]
                + price * (summary["missed_fraction"] * summary["offered_gpu_s"]) / 3600.0,
                3,
            ),
            "price": price,
            "carbon_g_per_served_kwh": round(
                summary["variable_carbon_kg"] / summary["served_gpu_s"] * 1000.0, 1
            )
            if summary["served_gpu_s"]
            else None,
        },
        "trace": {
            "matches_planner": not planner.mismatch_slots,
            "mismatch_slots": planner.mismatch_slots,
            "n_slots": len(planner.traces),
            "note": (
                "The explanation is a recorded replay of the same ledger. Any slot "
                "where the recording disagrees with the real planner is listed here; "
                "the plan itself always comes from BlockPlanner."
            ),
        },
        "demand_note": demand_note,
    }


def _queue_snapshot(env: HybridEnv, t: int) -> dict[str, Any]:
    by_class = []
    total = 0.0
    for i, deadline in enumerate(env.deadlines):
        items = []
        for arrival, volume in sorted(env.queues[i].items()):
            if volume <= 1e-9:
                continue
            last_legal = arrival + deadline - 1
            items.append(
                {
                    "arrival": arrival,
                    "volume_gpu_s": float(volume),
                    "last_legal_slot": last_legal,
                    "slots_left": last_legal - t + 1,
                    "expired": last_legal < t,
                }
            )
            total += float(volume)
        by_class.append(
            {
                "class_index": i,
                "deadline_slots": deadline,
                "deadline_hours": deadline * SLOT_MINUTES / 60.0,
                "label": _deadline_label(deadline),
                "gpu_s": float(sum(item["volume_gpu_s"] for item in items)),
                "n_items": len(items),
                "items": items,
            }
        )
    return {"total_gpu_s": total, "by_class": by_class}


def _frame(
    env: HybridEnv,
    t: int,
    start: datetime,
    served: np.ndarray,
    missed: float,
    trace: dict[str, Any],
    queued: dict[str, Any],
    robust: float,
) -> dict[str, Any]:
    served_list = [float(value) for value in served]
    variable = 0.0
    for j, site in enumerate(env.sites):
        marginal = site_energy_kwh(site, served_list[j], SLOT_MINUTES) - site_energy_kwh(
            site, 0.0, SLOT_MINUTES
        )
        variable += marginal * float(env.realized[t, j]) / 1000.0
    idle = sum(
        site_energy_kwh(site, 0.0, SLOT_MINUTES) * float(env.realized[t, j]) / 1000.0
        for j, site in enumerate(env.sites)
    )
    return {
        "slot": t,
        "at": _iso(start, t),
        "forecast_g_per_kwh": [round(float(value), 2) for value in env.forecast[t]],
        "band_g_per_kwh": [round(float(value), 2) for value in env.band[t]],
        "realized_g_per_kwh": [round(float(value), 2) for value in env.realized[t]],
        "price_g_per_kwh": [
            round(float(env.forecast[t, j]) + robust * float(env.band[t, j]), 3)
            for j in range(len(env.sites))
        ],
        "capacity_gpu_s": [float(value) for value in env.capacity_gpu_s],
        "served_gpu_s": [round(value, 1) for value in served_list],
        "offered_gpu_s": [round(value, 1) for value in trace["offer_now"]],
        "missed_gpu_s": round(missed, 1),
        "carbon_kg": round(variable, 6),
        "idle_carbon_kg": round(idle, 6),
        "queue": {
            "total_gpu_s": round(queued["total_gpu_s"], 1),
            "by_class": [
                {
                    "class_index": row["class_index"],
                    "gpu_s": round(row["gpu_s"], 1),
                    "n_items": row["n_items"],
                    "oldest_slots_left": min(
                        (item["slots_left"] for item in row["items"]), default=None
                    ),
                }
                for row in queued["by_class"]
            ],
        },
    }


def _site_stats(
    env: HybridEnv,
    names: list[str],
    sites: list[Site],
    forecast: np.ndarray,
    realized: np.ndarray,
    band: np.ndarray,
    served_by_slot: np.ndarray,
    regions: dict[str, int],
) -> list[dict[str, Any]]:
    n_slots = env.n_slots
    total_served = float(env.served_by_site.sum())
    variable = np.zeros(len(sites))
    idle = np.zeros(len(sites))
    for j, site in enumerate(sites):
        for t in range(n_slots):
            amount = served_by_slot[t, j]
            marginal = site_energy_kwh(site, amount, SLOT_MINUTES) - site_energy_kwh(
                site, 0.0, SLOT_MINUTES
            )
            variable[j] += marginal * float(realized[t, j]) / 1000.0
            idle[j] += site_energy_kwh(site, 0.0, SLOT_MINUTES) * float(realized[t, j]) / 1000.0
    total_carbon = float(variable.sum() + idle.sum())
    rows = []
    for j, name in enumerate(names):
        rows.append(
            {
                **content.scheduler_site(name, regions.get(name)),
                "capacity_gpu_s_per_slot": float(env.capacity_gpu_s[j]),
                "served_gpu_s": float(env.served_by_site[j]),
                "served_share_pct": round(100.0 * float(env.served_by_site[j]) / total_served, 3)
                if total_served
                else None,
                "mean_served_gpu_s_per_slot": round(float(env.served_by_site[j]) / n_slots, 1),
                "utilisation_pct": round(
                    100.0 * float(env.served_by_site[j]) / n_slots / float(env.capacity_gpu_s[j]),
                    3,
                ),
                "variable_carbon_kg": round(float(variable[j]), 3),
                "idle_carbon_kg": round(float(idle[j]), 3),
                "carbon_kg": round(float(variable[j] + idle[j]), 3),
                "carbon_share_pct": round(100.0 * float(variable[j] + idle[j]) / total_carbon, 3)
                if total_carbon
                else None,
                "mean_forecast_g_per_kwh": round(float(forecast[:, j].mean()), 2),
                "mean_realized_g_per_kwh": round(float(realized[:, j].mean()), 2),
                "band_g_per_kwh": round(float(band[:, j].mean()), 2),
            }
        )
    return rows


# --- decisions ---------------------------------------------------------------


def _item_id(class_index: int, arrival: int, deadline_slots: int) -> str:
    return f"class-{_deadline_label(deadline_slots).replace(' ', '')}/slot-{arrival}"


def _decision(
    item: dict[str, Any],
    *,
    slot: int,
    frames: list[dict[str, Any]],
    price_grid: list[list[float]],
    site_names: list[str],
    sites: list[Site],
    deadlines: list[int],
    block_capacity_gpu_s: list[float],
) -> dict[str, Any]:
    class_index = int(item["class_index"])
    deadline = deadlines[class_index]
    chosen_slot = item.get("chosen_slot")
    volume = float(item["volume_gpu_s"])
    blocks = item.get("blocks") or []
    chosen_site_index = item.get("chosen_site_index")

    chosen_price = None
    chosen_name = None
    if chosen_slot is not None and chosen_site_index is not None:
        chosen_price = float(price_grid[int(chosen_slot)][int(chosen_site_index)])
        chosen_name = site_names[int(chosen_site_index)]

    alternatives: list[dict[str, Any]] = []
    if chosen_slot is not None:
        frame = frames[int(chosen_slot)]
        free = item.get("free_at_chosen") or [None] * len(sites)
        for j, site in enumerate(sites):
            price = float(price_grid[int(chosen_slot)][j])
            take = sum(
                float(block["take_gpu_s"])
                for block in blocks
                if int(block["slot"]) == int(chosen_slot) and int(block["site_index"]) == j
            )
            verdict = explain.candidate_verdict(
                site=content.site_label(site.name),
                price=price,
                chosen_site=content.site_label(chosen_name or ""),
                chosen_price=chosen_price if chosen_price is not None else price,
                take_gpu_s=take,
                volume_gpu_s=volume,
                free_gpu_s=float(free[j]) if free and free[j] is not None else 0.0,
                capacity_gpu_s=float(block_capacity_gpu_s[j]),
            )
            alternatives.append(
                {
                    "site": site.name,
                    "label": content.site_label(site.name),
                    "slot": int(chosen_slot),
                    "forecast_g_per_kwh": frame["forecast_g_per_kwh"][j],
                    "band_g_per_kwh": frame["band_g_per_kwh"][j],
                    "price_g_per_kwh": round(price, 3),
                    "realized_g_per_kwh": frame["realized_g_per_kwh"][j],
                    "free_gpu_s": float(free[j]) if free and free[j] is not None else None,
                    "block_capacity_gpu_s": float(block_capacity_gpu_s[j]),
                    "take_gpu_s": take,
                    "status": verdict["status"],
                    "code": verdict["code"],
                    "reason": verdict["text"],
                }
            )
    status_rank = {"chosen": 0, "rejected": 1}
    alternatives.sort(
        key=lambda row: (
            status_rank[row["status"]],
            -row["take_gpu_s"],
            row["price_g_per_kwh"],
        )
    )

    predicted = 0.0
    realized_emissions = 0.0
    for block in blocks:
        block_slot = int(block["slot"])
        site_index = int(block["site_index"])
        take = float(block["take_gpu_s"])
        marginal = site_energy_kwh(sites[site_index], take, SLOT_MINUTES) - site_energy_kwh(
            sites[site_index], 0.0, SLOT_MINUTES
        )
        predicted += marginal * float(price_grid[block_slot][site_index]) / 1000.0
        realized_emissions += (
            marginal * float(frames[block_slot]["realized_g_per_kwh"][site_index]) / 1000.0
        )

    feasible = [
        row
        for row in alternatives
        if row["free_gpu_s"] is not None and row["free_gpu_s"] >= volume - 1e-6
    ]
    fully_feasible = bool(feasible)
    if not feasible:
        feasible = [
            row for row in alternatives if row["free_gpu_s"] is not None and row["free_gpu_s"] > 0
        ]
    worst = max(feasible, key=lambda row: row["price_g_per_kwh"]) if feasible else None
    reference_site = sites[int(chosen_site_index)] if chosen_site_index is not None else sites[0]
    marginal_volume = site_energy_kwh(reference_site, volume, SLOT_MINUTES) - site_energy_kwh(
        reference_site, 0.0, SLOT_MINUTES
    )
    worst_emissions = (
        marginal_volume * float(worst["price_g_per_kwh"]) / 1000.0 if worst is not None else None
    )
    reduction_kg = worst_emissions - predicted if worst_emissions is not None else None
    reduction_pct = (
        100.0 * reduction_kg / worst_emissions
        if reduction_kg is not None and worst_emissions > 1e-12
        else None
    )

    executed_now = sum(float(block["take_gpu_s"]) for block in blocks if int(block["slot"]) == slot)
    deferred = sum(float(block["take_gpu_s"]) for block in blocks if int(block["slot"]) > slot)
    unassigned = float(item.get("unassigned_gpu_s") or 0.0)
    spilled = (
        len(
            {
                int(block["site_index"])
                for block in blocks
                if chosen_slot is not None and int(block["slot"]) == int(chosen_slot)
            }
        )
        > 1
    )
    now_price = (
        float(price_grid[slot][int(chosen_site_index)])
        if chosen_slot == slot and chosen_site_index is not None
        else min(price_grid[slot])
    )
    chosen_label = content.site_label(chosen_name or "") if chosen_name else None
    slot_options = [
        {
            **option,
            "is_now": option["slot"] == slot,
            "is_chosen": option["slot"] == chosen_slot,
            "is_last_legal": option["slot"] == int(item["last_legal_slot"]),
        }
        for option in item.get("slot_options", [])
    ]
    explanation = explain.item_explanation(
        item_id=_item_id(class_index, int(item["arrival"]), deadline),
        class_label=_deadline_label(deadline),
        volume_gpu_s=volume,
        slot=slot,
        arrival=int(item["arrival"]),
        last_legal_slot=int(item["last_legal_slot"]),
        chosen_slot=int(chosen_slot) if chosen_slot is not None else None,
        chosen_site=chosen_label,
        chosen_price=chosen_price,
        now_price=now_price,
        executed_now_gpu_s=executed_now,
        deferred_gpu_s=deferred,
        unassigned_gpu_s=unassigned,
        spilled=spilled,
        alternatives=alternatives,
        slot_options=slot_options,
        slot_label=lambda value: f"slot {value}",
    )

    return {
        "id": _item_id(class_index, int(item["arrival"]), deadline),
        "slot": slot,
        "class_index": class_index,
        "class_label": _deadline_label(deadline),
        "deadline_slots": deadline,
        "arrival": int(item["arrival"]),
        "age_slots": slot - int(item["arrival"]),
        "slots_left": int(item["last_legal_slot"]) - slot + 1,
        "last_legal_slot": int(item["last_legal_slot"]),
        "volume_gpu_s": round(volume, 1),
        "executed_now_gpu_s": round(executed_now, 1),
        "deferred_gpu_s": round(deferred, 1),
        "unassigned_gpu_s": round(unassigned, 1),
        "chosen": None
        if chosen_slot is None
        else {
            "slot": int(chosen_slot),
            "at": frames[int(chosen_slot)]["at"],
            "site": chosen_name,
            "site_label": chosen_label,
            "price_g_per_kwh": round(chosen_price, 3) if chosen_price is not None else None,
            "blocks": [
                {
                    "slot": int(block["slot"]),
                    "site": site_names[int(block["site_index"])],
                    "site_label": content.site_label(site_names[int(block["site_index"])]),
                    "take_gpu_s": round(float(block["take_gpu_s"]), 1),
                    "price_g_per_kwh": round(
                        float(price_grid[int(block["slot"])][int(block["site_index"])]), 3
                    ),
                }
                for block in blocks
            ],
        },
        "predicted_emissions_kg": round(predicted, 4),
        "realized_emissions_kg": round(realized_emissions, 4),
        "worst_feasible": None
        if worst is None
        else {
            "site": worst["site"],
            "label": worst["label"],
            "price_g_per_kwh": worst["price_g_per_kwh"],
            "emissions_kg": round(worst_emissions, 4),
            "fully_feasible": fully_feasible,
        },
        "reduction_kg": round(reduction_kg, 4) if reduction_kg is not None else None,
        "reduction_pct": round(reduction_pct, 2) if reduction_pct is not None else None,
        "split": {
            "executed_now": executed_now > 1e-9,
            "deferred": deferred > 1e-9,
            "spilled": spilled,
            "unplaced": unassigned > 1e-9,
            "expired": int(item["last_legal_slot"]) < slot,
            "deadline_forced": chosen_slot is not None
            and int(chosen_slot) >= int(item["last_legal_slot"]),
        },
        "alternatives": alternatives,
        "slot_options": slot_options,
        "explanation": explanation,
    }


# --- public API --------------------------------------------------------------


def _default_slot(frames: list[dict[str, Any]]) -> int:
    """The week's busiest placement, derived from the replay (not hand-picked).

    Backlog alone is a poor default: a slot can hold a large backlog of work
    whose deadline has already passed, where the planner places nothing. The
    decision to explain is the slot where the planner actually places the most
    work, falling back to the largest backlog only if nothing was ever placed.
    """
    placed = max(frames, key=lambda frame: (sum(frame["served_gpu_s"]), -frame["slot"]))
    if sum(placed["served_gpu_s"]) > 0:
        return int(placed["slot"])
    backlog = max(frames, key=lambda frame: (frame["queue"]["total_gpu_s"], -frame["slot"]))
    return int(backlog["slot"])


def _read_cache(key: str) -> dict[str, Any] | None:
    path = CACHE_DIR / f"replay-{key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"replay-{key}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def replay_raw(
    *,
    week: str,
    fleet: str,
    robust: float,
    reserve: float,
    reserve_gpu_s: float,
    arrival_forecast: int,
    price: float,
) -> dict[str, Any]:
    """One week of the real planner, cached on disk and in process."""
    key = _replay_key(week, fleet, robust, reserve, reserve_gpu_s, arrival_forecast)
    with _LOCK:
        if key in _MEM:
            return {**_MEM[key], "cache": {"hit": True, "source": "memory", "key": key}}
    cached = _read_cache(key)
    if cached is not None:
        with _LOCK:
            _MEM[key] = cached
        return {**cached, "cache": {"hit": True, "source": "disk", "key": key}}
    payload = _trace_week(week, fleet, robust, reserve, reserve_gpu_s, arrival_forecast, price)
    payload["cache"] = {"hit": False, "source": "replay", "key": key}
    if payload.get("available"):
        _write_cache(key, payload)
        with _LOCK:
            _MEM[key] = payload
    return payload


def assemble(
    payload: dict[str, Any],
    *,
    week: str,
    fleet: str,
    price: float,
    slot: int | None,
    site: str | None,
    item_id: str | None,
) -> dict[str, Any]:
    """Add the selected slot's decisions and the choice state to a replay."""
    if not payload.get("available"):
        return {
            "available": False,
            "reason": payload.get("reason"),
            "meta": meta(),
        }
    frames = payload["frames"]
    selected_slot = (
        _default_slot(frames) if slot is None else max(0, min(int(slot), len(frames) - 1))
    )
    defaulted: list[str] = []
    if slot is None:
        defaulted.append("slot")
    elif int(slot) != selected_slot:
        defaulted.append("slot")

    site_names = [row["name"] for row in payload["sites"]]
    if site is None or site not in site_names:
        busiest = max(payload["sites"], key=lambda row: row["served_gpu_s"])
        selected_site = busiest["name"]
        defaulted.append("site")
    else:
        selected_site = site

    cfg = config()
    deadlines = [int(value) for value in cfg["deadlines"]]
    make_names = list(cfg["regions"])
    sites = data.make_sites(
        {**cfg["sites"], "n_gpus": payload["fleet"]["n_gpus_per_site"]}, make_names
    )
    knobs = payload["knobs"]
    block_capacity = [
        max(
            0.0,
            float(capacity) * (1.0 - float(knobs["reserve"])) - float(knobs["reserve_gpu_s"]),
        )
        for capacity in frames[selected_slot]["capacity_gpu_s"]
    ]
    items = [item for item in payload.get("items", []) if int(item["slot"]) == selected_slot]
    items.sort(
        key=lambda item: (
            int(item["last_legal_slot"]),
            int(item["arrival"]),
            int(item["class_index"]),
        )
    )
    decisions = [
        _decision(
            item,
            slot=selected_slot,
            frames=frames,
            price_grid=payload["price_grid_g_per_kwh"],
            site_names=site_names,
            sites=sites,
            deadlines=deadlines,
            block_capacity_gpu_s=block_capacity,
        )
        for item in items
    ]
    selected_item = next(
        (decision["id"] for decision in decisions if decision["chosen"] is not None),
        decisions[0]["id"] if decisions else None,
    )
    if item_id is not None:
        if any(row["id"] == item_id for row in decisions):
            selected_item = item_id
        else:
            defaulted.append("item")

    frame = frames[selected_slot]
    queue = {
        "gpu_s": frame["queue"]["total_gpu_s"],
        "by_class": [
            {
                **row,
                "deadline_hours": deadlines[row["class_index"]] * SLOT_MINUTES / 60.0,
                "label": _deadline_label(deadlines[row["class_index"]]),
            }
            for row in frame["queue"]["by_class"]
        ],
        "items": [
            {
                "id": decision["id"],
                "class_index": decision["class_index"],
                "class_label": decision["class_label"],
                "arrival": decision["arrival"],
                "volume_gpu_s": decision["volume_gpu_s"],
                "slots_left": decision["slots_left"],
                "expired": decision["split"]["expired"],
                "selected": decision["id"] == selected_item,
            }
            for decision in decisions
        ],
    }
    for row in queue["by_class"]:
        row["items"] = [
            item for item in queue["items"] if item["class_index"] == row["class_index"]
        ]

    return {
        "available": True,
        "reason": None,
        "meta": meta(),
        "week": week,
        "window_start_utc": payload["window_start_utc"],
        "window_end_utc": payload["window_end_utc"],
        "n_slots": len(frames),
        "slot_minutes": SLOT_MINUTES,
        "fleet": payload["fleet"],
        "knobs": knobs,
        "price": price,
        "sites": payload["sites"],
        "summary": payload["summary"],
        "frames": frames,
        "slot_decision": {
            "slot": selected_slot,
            "at": frame["at"],
            "queue": queue,
            "decisions": decisions,
            "totals": {
                "forecast_g_per_kwh": frame["forecast_g_per_kwh"],
                "band_g_per_kwh": frame["band_g_per_kwh"],
                "realized_g_per_kwh": frame["realized_g_per_kwh"],
                "served_gpu_s": frame["served_gpu_s"],
                "offered_gpu_s": frame["offered_gpu_s"],
                "missed_gpu_s": frame["missed_gpu_s"],
                "carbon_kg": frame["carbon_kg"],
            },
        },
        "selection": {
            "slot": selected_slot,
            "site": selected_site,
            "item": selected_item,
            "defaulted": defaulted,
            "slot_reason": (
                "the week's largest placement in the replay, derived from served GPU-seconds"
                if "slot" in defaulted
                else None
            ),
            "site_reason": (
                "the site with the largest served share in this replay"
                if "site" in defaulted
                else None
            ),
        },
        "trace": payload["trace"],
        "cache": payload.get("cache"),
        "demand_note": payload.get("demand_note"),
    }


def replay(
    *,
    week: str,
    fleet: str,
    price: float,
    robust: float,
    reserve: float,
    reserve_level: float | None,
    slot: int | None = None,
    site: str | None = None,
    item: str | None = None,
) -> dict[str, Any]:
    """Validate the request, replay (or read the cache), and assemble the view."""
    meta_rows = meta()
    weeks = meta_rows.get("weeks") or []
    if week not in weeks:
        raise ValueError(
            f"week {week!r} is not one of the held-out weeks in the exp017 record: {weeks}"
        )
    fleets = {row["name"] for row in meta_rows.get("fleets", [])}
    if fleet not in fleets:
        raise ValueError(f"fleet {fleet!r} is not in the exp017 config: {sorted(fleets)}")
    if not 0.0 <= robust <= 1.0:
        raise ValueError("robust must be in [0, 1] (0 = point forecast, 1 = whole band)")
    if not 0.0 <= reserve < 1.0:
        raise ValueError("reserve must be in [0, 1)")

    reserve_gpu_s = 0.0
    reserve_source = None
    if reserve_level is not None:
        calibrated = _calibrated_reserves(fleet)
        row = next(
            (
                entry
                for entry in calibrated.get("levels", [])
                if abs(entry["level"] - reserve_level) < 1e-9
            ),
            None,
        )
        if row is None or row.get("reserve_gpu_s_per_site_slot") is None:
            raise ValueError(
                f"no calibrated reserve at level {reserve_level} for {fleet} in the "
                f"{RESERVE_EXP_ID} record"
            )
        reserve_gpu_s = float(row["reserve_gpu_s_per_site_slot"])
        reserve = 0.0
        reserve_source = {
            "exp_id": RESERVE_EXP_ID,
            "level": reserve_level,
            "window_slots": calibrated.get("window_slots"),
            "coverage_forward": row.get("coverage_forward"),
            "coverage_reverse": row.get("coverage_reverse"),
            "reserve_gpu_s_per_site_slot": reserve_gpu_s,
        }

    raw = replay_raw(
        week=week,
        fleet=fleet,
        robust=robust,
        reserve=reserve,
        reserve_gpu_s=reserve_gpu_s,
        arrival_forecast=0,
        price=price,
    )
    if not raw.get("available"):
        return {"available": False, "reason": raw.get("reason"), "meta": meta_rows}
    payload = assemble(raw, week=week, fleet=fleet, price=price, slot=slot, site=site, item_id=item)
    payload["knobs"] = {
        **payload["knobs"],
        "reserve_mode": "calibrated" if reserve_level is not None else "fraction",
        "reserve_level": reserve_level,
        "reserve_source": reserve_source,
    }
    payload["policy"] = policy_context(fleet=payload["fleet"]["name"], price=price)
    return payload


def policy_context(*, fleet: str, price: float) -> dict[str, Any]:
    """The knobs, the exact objective, and the committed arms they were tested against."""
    cfg = config()
    metrics = _optional_metrics(EXP_ID)
    arms = []
    if metrics:
        fleet_row = (metrics.get("fleets") or {}).get(fleet) or {}
        for label, row in (fleet_row.get("arms") or {}).items():
            spec = PLANNERS.get(label, {})
            arms.append(
                {
                    "label": label,
                    "kind": spec.get("kind"),
                    "robust": spec.get("robust"),
                    "reserve": spec.get("reserve"),
                    "carbon_kg": row.get("carbon_kg"),
                    "missed_fraction": row.get("missed_fraction"),
                    "carbon_g_per_served_kwh": row.get("carbon_g_per_served_kwh"),
                    "objective_at_this_price": (row.get("objective_at_price") or {}).get(
                        str(price)
                    ),
                    "paired_vs_run_now": row.get("paired_vs_run_now"),
                    "gap_to_own_bound_pct": row.get("gap_to_own_bound_pct"),
                }
            )
        arms.sort(key=lambda row: row["objective_at_this_price"] or float("inf"))
    return {
        "exp_id": EXP_ID,
        "run": _latest_run_meta(),
        "fleets": [row["name"] for row in meta()["fleets"]],
        "deadlines_slots": [int(value) for value in cfg.get("deadlines", [])],
        "hard_constraints": [
            {
                "label": "Per-site, per-slot capacity",
                "value": "capacity_gpu_s per block",
                "note": "Hard: the plan may never place more than the block holds.",
            },
            {
                "label": "Per-class deadline window",
                "value": " / ".join(_deadline_label(int(d)) for d in cfg.get("deadlines", [])),
                "note": "Hard: work cannot run after arrival + deadline - 1.",
            },
        ],
        "objective": {
            "formula": "carbon_kg + price * missed_gpu_hours",
            "price": price,
            "parity_price_kg_per_gpu_hour": _parity_price(),
            "note": (
                "A miss is priced per GPU-hour, exactly as exp017 ranks its arms. "
                "The price is not a slider inside the planner: the planner is "
                "deadline-feasible first and cheapest-block second."
            ),
        },
        "arms": arms,
        "band": {"evidence": _band_evidence(), "note": content.BAND_NOTE},
        "reserve": _calibrated_reserves(fleet),
        "note": content.SCHEDULER_NOTES["objective"],
    }
