"""Tests for the reproducible experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from carbon_scheduling import runner
from carbon_scheduling.experiments import REGISTRY

EXP001 = "exp001-uk-carbon-baseline"


def test_sha256_config_is_order_independent() -> None:
    assert runner.sha256_config({"a": 1, "b": 2}) == runner.sha256_config({"b": 2, "a": 1})


def test_sha256_config_changes_with_content() -> None:
    assert runner.sha256_config({"a": 1}) != runner.sha256_config({"a": 2})


def test_load_config_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        runner.load_config("exp999-does-not-exist")


def test_load_config_missing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exp_dir = tmp_path / "experiments" / "exp001-x"
    exp_dir.mkdir(parents=True)
    (exp_dir / "config.yaml").write_text("id: exp001-x\n")
    monkeypatch.setattr(runner, "EXPERIMENTS_DIR", tmp_path / "experiments")
    with pytest.raises(ValueError, match="missing required keys"):
        runner.load_config("exp001-x")


def test_load_config_validates_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exp_dir = tmp_path / "experiments" / "exp001-x"
    exp_dir.mkdir(parents=True)
    (exp_dir / "config.yaml").write_text("id: wrong-id\ntitle: t\nseed: 1\ndata: []\n")
    monkeypatch.setattr(runner, "EXPERIMENTS_DIR", tmp_path / "experiments")
    with pytest.raises(ValueError, match="config id"):
        runner.load_config("exp001-x")


def test_registered_experiments_exist_on_disk() -> None:
    for exp_id in REGISTRY:
        config, _ = runner.load_config(exp_id)
        assert config["id"] == exp_id
        assert isinstance(config["seed"], int)


def test_exp001_run_is_reproducible(tmp_path: Path) -> None:
    """Two runs of the same config on the same tree must produce identical
    metrics and identical config/data hashes."""
    first = runner.run(EXP001, runs_root=tmp_path)
    second = runner.run(EXP001, runs_root=tmp_path)

    assert first["metrics"] == second["metrics"]
    assert first["config_hash"] == second["config_hash"]
    assert first["data_hashes"] == second["data_hashes"]
    assert first["git_sha"] == second["git_sha"]
    assert first["run_dir"] != second["run_dir"]  # append-only records


def test_exp001_run_record_files(tmp_path: Path) -> None:
    record = runner.run(EXP001, runs_root=tmp_path)
    run_dir = tmp_path / record["run_dir"]
    manifest = json.loads((run_dir / "manifest.json").read_text())
    metrics = json.loads((run_dir / "metrics.json").read_text())

    assert manifest["config_hash"] == record["config_hash"]
    assert manifest["exp_id"] == EXP001
    assert manifest["data_hashes"]  # input data was hashed into the record
    assert metrics["n_slots"] > 0
