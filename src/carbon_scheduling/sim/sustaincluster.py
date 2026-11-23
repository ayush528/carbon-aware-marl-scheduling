"""Thin adapter to an external SustainCluster checkout (MIT, HPE Labs).

SustainCluster is a large third-party simulator, so it is not vendored here:
the user clones it once (``make sc-setup``) and this module runs *our* headless
drivers (``scripts/sustaincluster/run_baseline.py`` / ``run_rl.py``) against
that checkout, parsing their JSON metrics. The drivers live in this repo
because upstream's own Table-1 script never writes its results CSV and crashes
in plotting -- see ``docs/research/findings-and-plan.md``.

The drivers must run with ``cwd`` set to the checkout: SustainCluster loads
``configs/...`` and ``data/...`` through paths relative to the working
directory.

Checkout resolution (first match wins):
    1. ``config["checkout"]``
    2. ``$SUSTAINCLUSTER_DIR``
    3. ``<repo>/external/sustain-cluster``

Interpreter resolution (first match wins):
    1. ``config["python"]``
    2. ``$SUSTAINCLUSTER_PYTHON``
    3. ``<checkout>/.venv/bin/python`` if present
    4. the current interpreter
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from carbon_scheduling.runner import REPO_ROOT

DEFAULT_CHECKOUT = REPO_ROOT / "external" / "sustain-cluster"
DRIVER_DIR = REPO_ROOT / "scripts" / "sustaincluster"
BASELINE_DRIVER = DRIVER_DIR / "run_baseline.py"
RL_DRIVER = DRIVER_DIR / "run_rl.py"
PLANNER_DRIVER = DRIVER_DIR / "run_planner.py"
CHECKOUT_MARKER = Path("envs") / "task_scheduling_env.py"


def checkout_dir(config: dict[str, Any]) -> Path:
    """Resolve and validate the SustainCluster checkout directory."""
    raw = config.get("checkout") or os.environ.get("SUSTAINCLUSTER_DIR")
    path = Path(raw) if raw else DEFAULT_CHECKOUT
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    if not (path / CHECKOUT_MARKER).is_file():
        raise FileNotFoundError(
            f"SustainCluster checkout not found: {path} (expected {CHECKOUT_MARKER}); "
            "run `make sc-setup` or set SUSTAINCLUSTER_DIR / the config's 'checkout'"
        )
    return path


def resolve_python(checkout: Path, config: dict[str, Any]) -> str:
    """Interpreter that has SustainCluster's dependencies installed."""
    configured = config.get("python") or os.environ.get("SUSTAINCLUSTER_PYTHON")
    if configured:
        return configured
    venv_python = checkout / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


def checkout_commit(checkout: Path) -> str:
    """Upstream commit SHA of the checkout (for the run manifest)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _invoke(driver: Path, checkout: Path, python: str, argv: list[str]) -> dict[str, Any]:
    """Run one driver in the checkout and return its JSON payload."""
    out_path = Path(argv[argv.index("--out") + 1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [python, str(driver), "--checkout", str(checkout), *argv]
    subprocess.run(command, cwd=checkout, check=True, capture_output=True, text=True)
    return json.loads(out_path.read_text())


def _config_flags(
    init_day_of_year: int | None,
    sim_config: str | Path | None,
    datacenters: str | Path | None,
    reward_config: str | Path | None,
    align_clock: bool = False,
) -> list[str]:
    """Only pass overrides that were asked for (keeps upstream runs untouched)."""
    flags: list[str] = []
    if init_day_of_year is not None:
        flags += ["--init-day-of-year", str(init_day_of_year)]
    if sim_config is not None:
        flags += ["--sim-config", str(sim_config)]
    if datacenters is not None:
        flags += ["--datacenters", str(datacenters)]
    if reward_config is not None:
        flags += ["--reward-config", str(reward_config)]
    if align_clock:
        flags += ["--align-clock"]
    return flags


def run_strategy(
    checkout: Path,
    python: str,
    strategy: str,
    *,
    days: float,
    seed: int,
    out_path: Path,
    init_day_of_year: int | None = None,
    sim_config: str | Path | None = None,
    datacenters: str | Path | None = None,
    reward_config: str | Path | None = None,
    align_clock: bool = False,
) -> dict[str, Any]:
    """Run one rule-based controller headless; return its metrics JSON."""
    return _invoke(
        BASELINE_DRIVER,
        checkout,
        python,
        [
            "--strategy",
            strategy,
            "--days",
            str(days),
            "--seed",
            str(seed),
            "--out",
            str(out_path),
            *_config_flags(init_day_of_year, sim_config, datacenters, reward_config, align_clock),
        ],
    )


def run_checkpoint(
    checkout: Path,
    python: str,
    checkpoint: str,
    *,
    days: float,
    seed: int,
    out_path: Path,
    device: str = "cpu",
    init_day_of_year: int | None = None,
    sim_config: str | Path | None = None,
    datacenters: str | Path | None = None,
    reward_config: str | Path | None = None,
    align_clock: bool = False,
) -> dict[str, Any]:
    """Evaluate one shipped SAC checkpoint headless; return its metrics JSON."""
    return _invoke(
        RL_DRIVER,
        checkout,
        python,
        [
            "--checkpoint",
            checkpoint,
            "--days",
            str(days),
            "--seed",
            str(seed),
            "--device",
            device,
            "--out",
            str(out_path),
            *_config_flags(init_day_of_year, sim_config, datacenters, reward_config, align_clock),
        ],
    )


def run_planner(
    checkout: Path,
    python: str,
    *,
    days: float,
    seed: int,
    out_path: Path,
    forecast_csv: str | Path,
    national_json: str | Path,
    region_map: dict[str, int],
    lam: float,
    window_hours: float | None,
    alpha: float,
    calibration_end: str,
    init_day_of_year: int | None = None,
    sim_config: str | Path | None = None,
    datacenters: str | Path | None = None,
    reward_config: str | Path | None = None,
    align_clock: bool = False,
) -> dict[str, Any]:
    """Run our carbon-aware planner inside the simulator; return its metrics JSON.

    Decisions are made from the NESO *forecast* series and a conformal band, not
    from the simulator's realized series, so the run is causal. See
    ``scripts/sustaincluster/planner_policy.py``.
    """
    mapping = ",".join(f"{slug}={rid}" for slug, rid in region_map.items())
    return _invoke(
        PLANNER_DRIVER,
        checkout,
        python,
        [
            "--forecast-csv",
            str(forecast_csv),
            "--national-json",
            str(national_json),
            "--region-map",
            mapping,
            "--lam",
            str(lam),
            *(["--window-hours", str(window_hours)] if window_hours is not None else []),
            "--alpha",
            str(alpha),
            "--calibration-end",
            str(calibration_end),
            "--days",
            str(days),
            "--seed",
            str(seed),
            "--out",
            str(out_path),
            *_config_flags(init_day_of_year, sim_config, datacenters, reward_config, align_clock),
        ],
    )
