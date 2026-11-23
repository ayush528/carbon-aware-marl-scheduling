"""Experiment registry: exp_id -> experiment function.

Every new experiment must be registered here (and listed in
``experiments/registry.yaml``) before it can run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from carbon_scheduling.experiments.exp001_uk_carbon_baseline import run as exp001
from carbon_scheduling.experiments.exp002_neso_regional_pull import run as exp002
from carbon_scheduling.experiments.exp003_regional_matrix_check import run as exp003
from carbon_scheduling.experiments.exp004_conformal_bands import run as exp004
from carbon_scheduling.experiments.exp005_regional_bands import run as exp005
from carbon_scheduling.experiments.exp006_azure_trace_demand import run as exp006
from carbon_scheduling.experiments.exp007_site_energy import run as exp007
from carbon_scheduling.experiments.exp008_sustaincluster_baseline import run as exp008
from carbon_scheduling.experiments.exp009_uk_sites import run as exp009
from carbon_scheduling.experiments.exp010_rolling_bands import run as exp010
from carbon_scheduling.experiments.exp011_band_dispatch import run as exp011
from carbon_scheduling.experiments.exp012_rl_dispatch import run as exp012
from carbon_scheduling.experiments.exp013_marl_dispatch import run as exp013
from carbon_scheduling.experiments.exp014_marl_seeds import run as exp014
from carbon_scheduling.experiments.exp015_timing_headroom import run as exp015
from carbon_scheduling.experiments.exp016_queue_ownership import run as exp016
from carbon_scheduling.experiments.exp017_hybrid_scheduler import run as exp017
from carbon_scheduling.experiments.exp018_arrival_reserve import run as exp018
from carbon_scheduling.experiments.exp019_arrival_shape import run as exp019
from carbon_scheduling.experiments.exp020_selected_scheduler import run as exp020
from carbon_scheduling.experiments.exp021_service_frontier import run as exp021
from carbon_scheduling.experiments.exp022_head_to_head import run as exp022
from carbon_scheduling.experiments.exp023_controllable_share import run as exp023
from carbon_scheduling.experiments.exp026_uncertainty_cannot_reorder import run as exp026
from carbon_scheduling.experiments.exp027_regional_actuals_boundary import run as exp027
from carbon_scheduling.experiments.exp028_idle_floor_curve import run as exp028
from carbon_scheduling.experiments.exp029_rolling_origin import run as exp029
from carbon_scheduling.experiments.exp030_deferral_head_to_head import run as exp030
from carbon_scheduling.experiments.exp031_demand_robustness import run as exp031

REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "exp001-uk-carbon-baseline": exp001,
    "exp002-neso-regional-pull": exp002,
    "exp003-regional-matrix-check": exp003,
    "exp004-conformal-bands": exp004,
    "exp005-regional-bands": exp005,
    "exp006-azure-trace-demand": exp006,
    "exp007-site-energy": exp007,
    "exp008-sustaincluster-baseline": exp008,
    "exp009-uk-sites": exp009,
    "exp010-rolling-bands": exp010,
    "exp011-band-dispatch": exp011,
    "exp012-rl-dispatch": exp012,
    "exp013-marl-dispatch": exp013,
    "exp014-marl-seeds": exp014,
    "exp015-timing-headroom": exp015,
    "exp016-queue-ownership": exp016,
    "exp017-hybrid-scheduler": exp017,
    "exp018-arrival-reserve": exp018,
    "exp019-arrival-shape": exp019,
    "exp020-selected-scheduler": exp020,
    "exp021-service-frontier": exp021,
    "exp022-head-to-head": exp022,
    "exp023-controllable-share": exp023,
    "exp026-uncertainty-cannot-reorder": exp026,
    "exp027-regional-actuals-boundary": exp027,
    "exp028-idle-floor-curve": exp028,
    "exp029-rolling-origin": exp029,
    "exp030-deferral-head-to-head": exp030,
    "exp031-demand-robustness": exp031,
}
