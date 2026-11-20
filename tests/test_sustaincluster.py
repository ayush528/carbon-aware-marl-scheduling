"""Tests for the SustainCluster adapter (drivers in-repo, checkout external)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from carbon_scheduling.sim import sustaincluster

STUB = """\
import argparse, json, pathlib, sys
p = argparse.ArgumentParser()
for flag in (
    "--checkout",
    "--strategy",
    "--checkpoint",
    "--device",
    "--datacenters",
    "--sim-config",
    "--reward-config",
    "--out",
):
    p.add_argument(flag)
p.add_argument("--days", type=float)
p.add_argument("--seed", type=int)
p.add_argument("--init-day-of-year", dest="init_day_of_year", type=int)
a = p.parse_args()
payload = {"argv": sys.argv[1:], "cwd": str(pathlib.Path.cwd())}
payload.update({k: v for k, v in vars(a).items() if k not in ("out",)})
out = pathlib.Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload))
"""


def _checkout(tmp_path: Path) -> Path:
    """Minimal checkout: the adapter only checks for the marker module."""
    checkout = tmp_path / "checkout"
    (checkout / "envs").mkdir(parents=True)
    (checkout / "envs" / "task_scheduling_env.py").write_text("# marker\n")
    return checkout


@pytest.fixture
def stub_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("BASELINE_DRIVER", "RL_DRIVER"):
        driver = tmp_path / f"{name.lower()}.py"
        driver.write_text(STUB)
        monkeypatch.setattr(sustaincluster, name, driver)
    return tmp_path


def test_checkout_dir_uses_config_path(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    assert sustaincluster.checkout_dir({"checkout": str(checkout)}) == checkout


def test_checkout_dir_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = _checkout(tmp_path)
    monkeypatch.setenv("SUSTAINCLUSTER_DIR", str(checkout))
    assert sustaincluster.checkout_dir({}) == checkout


def test_checkout_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="SustainCluster checkout"):
        sustaincluster.checkout_dir({"checkout": str(tmp_path / "nope")})


def test_resolve_python_prefers_config(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    assert sustaincluster.resolve_python(checkout, {"python": "/opt/py/bin/python"}) == (
        "/opt/py/bin/python"
    )


def test_resolve_python_prefers_checkout_venv(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    venv_python = checkout / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    assert sustaincluster.resolve_python(checkout, {}) == str(venv_python)


def test_resolve_python_falls_back_to_current(tmp_path: Path) -> None:
    assert sustaincluster.resolve_python(_checkout(tmp_path), {}) == sys.executable


def test_checkout_commit_reads_git_sha(tmp_path: Path) -> None:
    repo = _checkout(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=a@b",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        cwd=repo,
        check=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert sustaincluster.checkout_commit(repo) == sha


def test_checkout_commit_unknown_outside_git(tmp_path: Path) -> None:
    assert sustaincluster.checkout_commit(_checkout(tmp_path)) == "unknown"


def test_run_strategy_passes_args_and_runs_in_checkout(tmp_path: Path, stub_driver: Path) -> None:
    checkout = _checkout(tmp_path)
    out = tmp_path / "runs" / "rr.json"

    payload = sustaincluster.run_strategy(
        checkout, sys.executable, "round_robin", days=1.0, seed=7, out_path=out
    )

    assert payload["strategy"] == "round_robin"
    assert payload["days"] == 1.0
    assert payload["seed"] == 7
    # cwd must be the checkout: upstream reads configs/ and data/ relatively.
    assert Path(payload["cwd"]).resolve() == checkout.resolve()
    assert json.loads(out.read_text())["strategy"] == "round_robin"


def test_run_checkpoint_passes_checkpoint_and_device(tmp_path: Path, stub_driver: Path) -> None:
    checkout = _checkout(tmp_path)
    out = tmp_path / "runs" / "sac.json"

    payload = sustaincluster.run_checkpoint(
        checkout,
        sys.executable,
        "checkpoints/x/best.pth",
        days=2.0,
        seed=3,
        out_path=out,
        device="cuda",
    )

    assert payload["checkpoint"] == "checkpoints/x/best.pth"
    assert payload["device"] == "cuda"
    assert payload["days"] == 2.0


def test_driver_failure_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = _checkout(tmp_path)
    driver = tmp_path / "boom.py"
    driver.write_text("raise SystemExit(3)\n")
    monkeypatch.setattr(sustaincluster, "BASELINE_DRIVER", driver)

    with pytest.raises(subprocess.CalledProcessError):
        sustaincluster.run_strategy(
            checkout,
            sys.executable,
            "round_robin",
            days=1.0,
            seed=7,
            out_path=tmp_path / "out.json",
        )


def test_default_run_passes_no_overrides(tmp_path: Path, stub_driver: Path) -> None:
    checkout = _checkout(tmp_path)
    payload = sustaincluster.run_strategy(
        checkout,
        sys.executable,
        "round_robin",
        days=1.0,
        seed=7,
        out_path=tmp_path / "a.json",
    )
    for flag in ("--init-day-of-year", "--sim-config", "--datacenters", "--reward-config"):
        assert flag not in payload["argv"]


def test_strategy_forwards_config_overrides(tmp_path: Path, stub_driver: Path) -> None:
    checkout = _checkout(tmp_path)
    payload = sustaincluster.run_strategy(
        checkout,
        sys.executable,
        "lowest_carbon",
        days=2.0,
        seed=1,
        out_path=tmp_path / "b.json",
        init_day_of_year=14,
        sim_config="sim.yaml",
        datacenters="dcs.yaml",
        reward_config="reward.yaml",
    )
    assert payload["init_day_of_year"] == 14
    assert payload["sim_config"] == "sim.yaml"
    assert payload["datacenters"] == "dcs.yaml"
    assert payload["reward_config"] == "reward.yaml"


def test_checkpoint_forwards_config_overrides(tmp_path: Path, stub_driver: Path) -> None:
    checkout = _checkout(tmp_path)
    payload = sustaincluster.run_checkpoint(
        checkout,
        sys.executable,
        "checkpoints/x/best.pth",
        days=1.0,
        seed=2,
        out_path=tmp_path / "c.json",
        init_day_of_year=32,
        datacenters="dcs.yaml",
    )
    assert payload["init_day_of_year"] == 32
    assert payload["datacenters"] == "dcs.yaml"
    assert payload["sim_config"] is None
