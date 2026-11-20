"""Read-only access to the repository's experiment artifacts.

The API never invents a number: every value it returns is read from a committed
artifact (``experiments/<id>/config.yaml``, ``runs/<run>/manifest.json``,
``runs/<run>/metrics.json``, ``experiments/registry.yaml``). If an artifact is
missing the endpoint says so instead of filling the gap.

Kept dependency-free apart from PyYAML so the service can be imported by tests
without a running server.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
REGISTRY_PATH = EXPERIMENTS_DIR / "registry.yaml"


class ArtifactError(LookupError):
    """A requested artifact does not exist on disk."""


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise ArtifactError(str(path.relative_to(REPO_ROOT)))
    return yaml.safe_load(path.read_text())


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise ArtifactError(str(path.relative_to(REPO_ROOT)))
    return json.loads(path.read_text())


def registry() -> list[dict[str, Any]]:
    """Every experiment in ``registry.yaml``, in file order."""
    entries = _read_yaml(REGISTRY_PATH).get("experiments", [])
    return [entry for entry in entries if isinstance(entry, dict)]


def experiment_ids() -> list[str]:
    return [entry["id"] for entry in registry()]


def registry_entry(exp_id: str) -> dict[str, Any]:
    for entry in registry():
        if entry.get("id") == exp_id:
            return entry
    raise ArtifactError(f"experiment {exp_id!r} is not in the registry")


def config(exp_id: str) -> dict[str, Any]:
    return _read_yaml(EXPERIMENTS_DIR / exp_id / "config.yaml")


def run_dirs(exp_id: str) -> list[Path]:
    """Run directories, oldest first (the directory name starts with the UTC stamp)."""
    root = EXPERIMENTS_DIR / exp_id / "runs"
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if (path / "manifest.json").is_file())


def latest_run(exp_id: str) -> dict[str, Any] | None:
    """Newest run record, or None when the experiment has not been run yet."""
    dirs = run_dirs(exp_id)
    if not dirs:
        return None
    run = dirs[-1]
    return {
        "run_dir": run.name,
        "manifest": _read_json(run / "manifest.json"),
        "metrics": _read_json(run / "metrics.json"),
    }


def runs(exp_id: str) -> list[dict[str, Any]]:
    out = []
    for run in run_dirs(exp_id):
        out.append(
            {
                "run_dir": run.name,
                "manifest": _read_json(run / "manifest.json"),
                "metrics": _read_json(run / "metrics.json"),
            }
        )
    return out


def latest_metrics(exp_id: str) -> dict[str, Any] | None:
    run = latest_run(exp_id)
    return run["metrics"] if run else None


def metrics_of(exp_id: str) -> dict[str, Any]:
    metrics = latest_metrics(exp_id)
    if metrics is None:
        raise ArtifactError(f"experiment {exp_id!r} has no run record yet")
    return metrics


# --- headline extraction -----------------------------------------------------
# Each experiment reports different metrics. Rather than teach the frontend ten
# shapes, the API maps them to a common [label, value, note] list here, where it
# can be reviewed next to the experiment that produced it.


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _thousands(value: float) -> str:
    return f"{value:,.0f}"


def summary(exp_id: str, metrics: dict[str, Any] | None) -> list[dict[str, str]]:
    if not metrics:
        return []
    m = metrics
    if exp_id == "exp004-conformal-bands":
        return [
            {
                "label": "held-out coverage",
                "value": _pct(100 * m["holdout_coverage"]),
                "tone": "good",
            },
            {"label": "band half-width", "value": f"{m['band_half_width_gco2_per_kwh']:.1f} g/kWh"},
            {"label": "hold-out MAE", "value": f"{m['holdout_mae_gco2_per_kwh']:.2f} g/kWh"},
        ]
    if exp_id == "exp005-regional-bands":
        return [
            {"label": "mean coverage", "value": _pct(100 * m["mean_coverage"]), "tone": "good"},
            {"label": "regions at target", "value": f"{m['n_regions_at_target']}/{m['n_regions']}"},
            {"label": "worst region", "value": _pct(100 * m["min_coverage"])},
        ]
    if exp_id == "exp006-azure-trace-demand":
        return [
            {"label": "requests", "value": _thousands(m["n_requests"])},
            {"label": "mean per 30 min", "value": _thousands(m["mean_requests_per_slot"])},
            {"label": "peak slot", "value": _thousands(m["peak_requests_per_slot"])},
        ]
    if exp_id == "exp007-site-energy":
        return [
            {"label": "mean utilisation", "value": f"{m['mean_utilization']:.2f}"},
            {"label": "saturated slots", "value": f"{m['n_saturated_slots']}/{m['n_slots']}"},
            {"label": "energy per request", "value": f"{m['wh_per_request']:.2f} Wh"},
        ]
    if exp_id == "exp008-sustaincluster-baseline":
        sac_best = m.get("sac_best_carbon_kg")
        rbc_best = m.get("rbc_best_carbon_kg")
        delta = None
        if sac_best and rbc_best:
            delta = 100 * (sac_best - rbc_best) / rbc_best
        return [
            {"label": "best rule", "value": f"{_thousands(rbc_best or 0)} kg", "tone": "good"},
            {
                "label": "best SAC vs rule",
                "value": f"{delta:+.1f}%" if delta is not None else "n/a",
                "tone": "warn",
            },
            {
                "label": "SAC SLA violations",
                "value": _pct(100 * m["sac_min_sla_violation_rate"]),
                "tone": "bad",
            },
        ]
    if exp_id == "exp009-uk-sites":
        return [
            {
                "label": "best vs round-robin",
                "value": f"{m['carbon_vs_round_robin_pct']['lowest_carbon']:+.2f}%",
                "tone": "good",
            },
            {
                "label": "intensity error",
                "value": f"{m['max_intensity_error_gco2_per_kwh']:.2f} g/kWh",
            },
            {"label": "regional spread", "value": f"{m['regional_spread_gco2_per_kwh']:.0f} g/kWh"},
        ]
    if exp_id == "exp010-rolling-bands":
        rel = m.get("relative", {})
        reg = m.get("regime_conditional", {})
        return [
            {
                "label": "rolling coverage",
                "value": _pct(100 * (rel.get("mean_coverage_positive_forecast") or 0)),
                "tone": "good",
            },
            {
                "label": "regime-conditional",
                "value": _pct(100 * (reg.get("mean_coverage_positive_forecast") or 0)),
            },
            {
                "label": "cells at target",
                "value": _pct(rel.get("cells_at_target_pct") or 0),
            },
        ]
    # Fallback: the first few scalar metrics, so a new experiment still shows up.
    out = []
    for key, value in m.items():
        if isinstance(value, int | float) and not isinstance(value, bool):
            out.append({"label": key.replace("_", " "), "value": f"{value:,.3g}"})
        if len(out) == 3:
            break
    return out
