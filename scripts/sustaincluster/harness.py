"""Shared harness for driving an external SustainCluster checkout headless.

Both entrypoints (``run_baseline.py`` for rule-based controllers,
``run_rl.py`` for shipped SAC checkpoints) build the environment the same way
upstream's ``evaluate_sustaincluster_agent.py`` does and accumulate the same
metrics, so their rows are directly comparable.

Why this exists: upstream's own Table-1 script is a notebook export that never
writes its results CSV and crashes in plotting, so it cannot produce numbers.
This harness drives the same classes with the same flags and returns JSON.

Faithfulness notes (all mirrored from upstream ``make_eval_env``):
    * ``init_day = int(month * 30.5 + init_day)``
    * ``shuffle_datacenter_order = False`` in evaluation mode
    * ``CompositeReward(..., normalize=False)``
    * env ``single_action_mode`` / ``disable_defer_action`` follow the
      checkpoint's own ``extra_info`` for RL, and ``sim_config.yaml`` for RBCs.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def add_checkout_to_path(checkout: Path) -> None:
    """Make the checkout's ``envs``/``simulation``/``rewards`` importable."""
    checkout = Path(checkout).resolve()
    if not (checkout / "envs" / "task_scheduling_env.py").is_file():
        raise FileNotFoundError(f"not a SustainCluster checkout: {checkout}")
    if str(checkout) not in sys.path:
        sys.path.insert(0, str(checkout))


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def checkout_commit(checkout: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def base_configs(checkout: Path) -> tuple[dict, dict, dict]:
    config_dir = Path(checkout) / "configs" / "env"
    return (
        load_yaml(config_dir / "sim_config.yaml"),
        load_yaml(config_dir / "datacenters.yaml"),
        load_yaml(config_dir / "reward_config.yaml"),
    )


_REGION_MAPS = {
    "aws": "location_to_aws_region",
    "gcp": "location_to_gcp_region",
    "azure": "location_to_azure_region",
}


def apply_location_regions(provider: str, mapping: dict[str, str]) -> None:
    """Teach the transmission mapper about locations upstream doesn't ship.

    Upstream hardcodes a location->cloud-region table and raises on anything
    else (fuzzy matching only rescues near-misses). Our UK sites are not in it,
    so the experiment's sim config carries the mapping; all four map to
    ``eu-west-2`` (AWS London), i.e. cross-site transfer is priced as
    intra-region -- a disclosed approximation.
    """
    from utils import transmission_region_mapper as mapper

    attribute = _REGION_MAPS.get(provider.lower())
    if attribute is None:
        raise ValueError(f"no region map for provider {provider!r}")
    getattr(mapper, attribute).update(mapping)


def build_env(
    checkout: Path,
    *,
    strategy: str,
    days: float,
    single_action: bool,
    disable_defer: bool,
    init_day_of_year: int | None = None,
    sim_config_path: Path | None = None,
    datacenters_path: Path | None = None,
    reward_config_path: Path | None = None,
    seed: int | None = None,
    align_clock: bool = False,
    inject_strategy: tuple[str, object] | None = None,
):
    """Environment configured exactly as upstream's evaluation path.

    The three ``*_path`` overrides let an experiment supply its own site list,
    window and reward (the UK variant does); omitting them reproduces upstream.
    """
    from envs.task_scheduling_env import TaskSchedulingEnv
    from rewards.predefined.composite_reward import CompositeReward
    from simulation.cluster_manager import DatacenterClusterManager

    sim_cfg, dc_cfg, reward_cfg = base_configs(checkout)
    if sim_config_path is not None:
        sim_cfg = load_yaml(sim_config_path)
    if datacenters_path is not None:
        dc_cfg = load_yaml(datacenters_path)
    if reward_config_path is not None:
        reward_cfg = load_yaml(reward_config_path)

    sim = sim_cfg["simulation"]
    sim["strategy"] = strategy
    sim["duration_days"] = days
    sim["single_action_mode"] = single_action
    sim["disable_defer_action"] = disable_defer
    sim["use_tensorboard"] = False

    # Optional: locations upstream's transmission table doesn't know (UK sites).
    if sim.get("location_regions"):
        apply_location_regions(sim["cloud_provider"], sim["location_regions"])

    start = pd.Timestamp(
        dt.datetime(
            sim["year"],
            sim["month"],
            sim["init_day"],
            sim["init_hour"],
            0,
            tzinfo=dt.UTC,
        )
    )

    cluster = DatacenterClusterManager(
        config_list=dc_cfg["datacenters"],
        simulation_year=sim["year"],
        # Upstream indexes carbon/price/workload by
        # ``int(month * 30.5 + init_day)``, which lands ~1 month *after* the
        # timestamp it also builds from the same fields (month=8, day=1 reads
        # 2 Sep data while the clock says 1 Aug). Passing the index directly
        # keeps data and timestamps on the same date; omit it to stay
        # bit-faithful to upstream.
        init_day=(
            int(sim["month"] * 30.5 + sim["init_day"])
            if init_day_of_year is None
            else int(init_day_of_year)
        ),
        init_hour=sim["init_hour"],
        strategy=strategy,
        tasks_file_path=sim["workload_path"],
        shuffle_datacenter_order=False,  # evaluation mode
        cloud_provider=sim["cloud_provider"],
        logger=None,
    )

    if inject_strategy is not None:
        # Upstream keeps its controllers in a strategy map keyed by name; adding
        # an entry here means our rule is dispatched by the same code path as
        # theirs, with identical capacity checks and no action translation.
        name, instance = inject_strategy
        cluster.strategy_map[name] = instance

    if align_clock:
        if seed is None:
            raise ValueError("align_clock needs the episode seed")
        # The cluster reset jitters the *data* window (+/-7 days, random hour)
        # but the env clock stays on the configured date, so the workload would
        # be dispatched against a different week than the carbon it sees. The
        # jitter is a seeded draw that depends only on (seed, init_day), so
        # probing it here and putting the clock on the same window is exact;
        # the env's own reset reproduces the identical draw.
        cluster.reset(seed=seed)
        start = pd.Timestamp(dt.datetime(sim["year"], 1, 1, tzinfo=dt.UTC)) + dt.timedelta(
            days=int(cluster.random_init_day),
            hours=int(cluster.random_init_hour),
        )

    end = start + dt.timedelta(days=sim["duration_days"])
    reward_fn = CompositeReward(
        components=reward_cfg["reward"]["components"],
        normalize=False,  # no reward normalization during eval
    )
    return TaskSchedulingEnv(
        cluster_manager=cluster,
        start_time=start,
        end_time=end,
        reward_fn=reward_fn,
        writer=None,
        sim_config=sim,
    )


class Metrics:
    """Accumulates the same fields as upstream's Table-1 ``results`` dict."""

    def __init__(self) -> None:
        self.energy_kwh = 0.0
        self.carbon_kg = 0.0
        self.energy_cost_usd = 0.0
        self.transmission_cost_usd = 0.0
        self.sla_met = 0
        self.sla_violated = 0
        self.tasks_finished = 0
        self._cpu: list[float] = []
        self._gpu: list[float] = []
        self._mem: list[float] = []
        self.per_dc: dict[str, dict[str, float]] = {}
        # The window the simulator *actually* read. Upstream's cluster reset
        # jitters the start day by +/-7 and picks a random hour, so this is
        # not the configured date and has to be reported for carbon to be
        # verifiable against the input series.
        self.window: dict[str, int] | None = None
        # The wall clock the workload was dispatched against (equal to the data
        # window only when the caller asked for alignment).
        self.clock_start_utc: str | None = None

    def add(self, info: dict[str, Any]) -> None:
        self.transmission_cost_usd += float(info.get("transmission_cost_total_usd", 0.0))
        for dc_name, dc_info in info.get("datacenter_infos", {}).items():
            common = dc_info.get("__common__", {})
            energy = float(common.get("energy_consumption_kwh", 0.0))
            carbon = float(common.get("carbon_emissions_kg", 0.0))
            cost = float(common.get("energy_cost_USD", 0.0))
            self.energy_kwh += energy
            self.carbon_kg += carbon
            self.energy_cost_usd += cost

            sla = common.get("__sla__", {})
            self.sla_met += int(sla.get("met", 0))
            self.sla_violated += int(sla.get("violated", 0))
            self.tasks_finished += int(common.get("finished_tasks_count", 0))

            self._cpu.append(float(common.get("cpu_util_percent", 0.0)))
            self._gpu.append(float(common.get("gpu_util_percent", 0.0)))
            self._mem.append(float(common.get("mem_util_percent", 0.0)))

            dc_bucket = self.per_dc.setdefault(
                dc_name, {"energy_kwh": 0.0, "carbon_kg": 0.0, "energy_cost_usd": 0.0}
            )
            dc_bucket["energy_kwh"] += energy
            dc_bucket["carbon_kg"] += carbon
            dc_bucket["energy_cost_usd"] += cost

    def summary(self) -> dict[str, Any]:
        def mean(xs: list[float]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        sla_total = self.sla_met + self.sla_violated
        return {
            "energy_kwh": self.energy_kwh,
            "carbon_kg": self.carbon_kg,
            "energy_cost_usd": self.energy_cost_usd,
            "transmission_cost_usd": self.transmission_cost_usd,
            "sla_met": self.sla_met,
            "sla_violated": self.sla_violated,
            "sla_violation_rate": (self.sla_violated / sla_total) if sla_total else 0.0,
            "tasks_finished": self.tasks_finished,
            "mean_cpu_util_percent": mean(self._cpu),
            "mean_gpu_util_percent": mean(self._gpu),
            "mean_mem_util_percent": mean(self._mem),
            "window": self.window,
            "clock_start_utc": self.clock_start_utc,
            "per_dc": self.per_dc,
        }


def run_episode(env, *, days: float, seed: int, policy) -> Metrics:
    """Drive one episode; ``policy(obs) -> int | list[int]`` or ``None`` for RBCs."""
    obs, _ = env.reset(seed=seed)
    metrics = Metrics()

    # Capture the jittered data window the cluster manager settled on. Carbon,
    # price and weather all index off it, so this is the window to verify.
    cluster = getattr(env, "cluster_manager", None)
    start_day = getattr(cluster, "random_init_day", None)
    if start_day is not None:
        metrics.window = {
            "start_day_index": int(start_day),
            "start_hour_utc": int(getattr(cluster, "random_init_hour", 0)),
            "year": int(getattr(cluster, "random_year", 0)),
        }
    start_time = getattr(env, "start_time", None)
    if start_time is not None:
        metrics.clock_start_utc = pd.Timestamp(start_time).strftime("%Y-%m-%dT%H:%MZ")
    for _ in range(int(days * 24 * 4)):
        actions = [] if policy is None else policy(obs)
        obs, _reward, done, truncated, info = env.step(actions)
        metrics.add(info)
        if done or truncated:
            break
    return metrics


def load_actor(checkout: Path, checkpoint: Path, device: str):
    """Load a shipped SAC actor; returns (actor, extra_info, step, device)."""
    import torch
    from rl_components.agent_net import ActorNet

    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    data = torch.load(Path(checkpoint), map_location="cpu", weights_only=False)
    extra = data["extra_info"]
    actor = ActorNet(
        extra["obs_dim"],
        extra["act_dim"],
        extra.get("hidden_dim", 256),
        extra.get("use_layer_norm", False),
    ).to(device)
    actor.load_state_dict(data["actor_state_dict"])
    actor.eval()
    return actor, extra, int(data.get("step", 0)), device


def greedy_policy(actor, single_action: bool, device: str):
    """Argmax action selection, shaped exactly like upstream's eval loop."""
    import torch

    def policy(obs):
        if single_action:
            tensor = torch.as_tensor(np.asarray(obs, dtype=np.float32), device=device).unsqueeze(0)
            with torch.no_grad():
                return int(torch.argmax(actor(tensor), dim=-1).item())
        if len(obs) == 0:
            return []
        tensor = torch.as_tensor(np.asarray(obs, dtype=np.float32), device=device)
        with torch.no_grad():
            return torch.argmax(actor(tensor), dim=-1).cpu().numpy().tolist()

    return policy
