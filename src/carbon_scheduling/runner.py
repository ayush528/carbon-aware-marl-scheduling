"""Reproducible, versioned experiment runner.

Protocol:

1. Every experiment lives in ``experiments/<exp_id>/`` and is defined by a
   committed ``config.yaml`` -- configs are committed *before* they are run.
2. ``run()`` executes the callable registered for ``exp_id`` and writes an
   append-only record to ``experiments/<exp_id>/runs/`` containing the git
   SHA, the SHA-256 of the canonical config, the SHA-256 of every input data
   file, the seed, and the resulting metrics.
3. Reproducibility contract: same git commit + same config + same data files
   => same metrics (experiments are seeded and deterministic).
4. When a config and its results are merged to ``main`` the merge is tagged
   ``exp/<exp_id>``; ``scripts/rollback.sh`` checks that tag out in an
   isolated worktree to reproduce or continue from any past experiment.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import subprocess
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
REQUIRED_CONFIG_KEYS = ("id", "title", "seed", "data")

# exp_id -> experiment function.  The mapping lives in
# carbon_scheduling.experiments to keep runner import-light.
ExperimentFn = Callable[[dict[str, Any]], dict[str, Any]]


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, streamed (handles files of any size)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_config(config: dict[str, Any]) -> str:
    """Hash the canonical JSON form of a config (key-order independent)."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def git_is_dirty() -> bool:
    """True when uncommitted changes exist (a run made on such a tree is
    *not* guaranteed reproducible -- the manifest says so)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def load_config(exp_id: str) -> tuple[dict[str, Any], Path]:
    """Load and validate ``experiments/<exp_id>/config.yaml``."""
    cfg_path = EXPERIMENTS_DIR / exp_id / "config.yaml"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"config not found: {cfg_path}")
    config = yaml.safe_load(cfg_path.read_text())
    if not isinstance(config, dict):
        raise ValueError(f"{cfg_path}: config must be a YAML mapping")
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ValueError(f"{cfg_path}: missing required keys {missing}")
    if config["id"] != exp_id:
        raise ValueError(f"{cfg_path}: config id {config['id']!r} != directory {exp_id!r}")
    return config, cfg_path


def run(exp_id: str, runs_root: Path | None = None) -> dict[str, Any]:
    """Run experiment ``exp_id`` and write an append-only run record.

    ``runs_root`` overrides where run records are written (tests use this to
    avoid touching the working tree); default is
    ``experiments/<exp_id>/runs/``.
    """
    # Imported here so importing runner does not import every experiment.
    from carbon_scheduling.experiments import REGISTRY

    if exp_id not in REGISTRY:
        raise KeyError(f"no experiment function registered for {exp_id!r}")

    config, _ = load_config(exp_id)
    config_hash = sha256_config(config)

    data_hashes: dict[str, str] = {}
    for rel in config["data"]:
        path = REPO_ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(f"data file missing: {path}")
        data_hashes[rel] = sha256_file(path)

    random.seed(config["seed"])
    metrics = REGISTRY[exp_id](config)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{config_hash[:8]}-{uuid.uuid4().hex[:4]}"
    run_dir = (runs_root or EXPERIMENTS_DIR / exp_id / "runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "exp_id": exp_id,
        "git_sha": git_sha(),
        "git_dirty": git_is_dirty(),
        "config_hash": config_hash,
        "seed": config["seed"],
        "data_hashes": data_hashes,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "timestamp": stamp,
        "run_dir": run_dir.name,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    return {**manifest, "metrics": metrics}
