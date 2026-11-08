"""Experiment registry: exp_id -> experiment function.

Every new experiment must be registered here (and listed in
``experiments/registry.yaml``) before it can run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from carbon_scheduling.experiments.exp001_uk_carbon_baseline import run as exp001

REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "exp001-uk-carbon-baseline": exp001,
}
