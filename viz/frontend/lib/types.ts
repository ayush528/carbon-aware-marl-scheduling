/**
 * Shapes returned by the Python experiment service (`viz/backend`).
 *
 * Only the fields the pages read are typed. Optional marks values the service
 * may return as null when an artifact is missing: pages must render a "not
 * available" state instead of assuming a number.
 */

export type StatusKey = "verified" | "inspected" | "modelled" | "assumption" | "next";

export type Tone = "good" | "bad" | "info" | "warn" | "accent" | "muted";

export interface LegendEntry {
  key: StatusKey;
  label: string;
  tone: Tone;
  meaning: string;
}

export interface Meta {
  project: {
    title: string;
    subtitle: string;
    phase: string;
    generated_at: string;
  };
  counts: { experiments: number; runs: number };
  legend: LegendEntry[];
  claim: { title: string; body: string; rules: string[] };
}

export interface SummaryValue {
  label: string;
  value: string;
  tone?: Tone;
}

export interface ExperimentRow {
  id: string;
  title: string;
  phase: string;
  status: string;
  rollback_tag: string | null;
  description: string;
  run: {
    run_dir: string;
    timestamp: string | null;
    git_sha: string | null;
    git_dirty: boolean | null;
    config_hash: string | null;
    seed: number | null;
  } | null;
  summary: SummaryValue[];
}

export interface ExperimentsResponse {
  experiments: ExperimentRow[];
  count: number;
}

export interface RunRecord {
  run_dir: string;
  manifest: {
    timestamp: string;
    git_sha: string;
    git_dirty: boolean;
    config_hash: string;
    seed: number;
    data_hashes?: Record<string, string>;
    python?: string;
    platform?: string;
  };
  metrics: Record<string, unknown>;
}

export interface ExperimentDetail {
  registry: {
    id: string;
    title: string;
    phase: string;
    status: string;
    rollback_tag: string | null;
    description: string;
  };
  config: Record<string, unknown> | null;
  run: RunRecord | null;
  runs: {
    run_dir: string;
    timestamp: string | null;
    git_sha: string | null;
    git_dirty: boolean | null;
  }[];
}

export interface DataSource {
  name: string;
  what: string;
  granularity: string;
  role: string;
  status: StatusKey;
  evidence: string;
}

export interface DataGap {
  title: string;
  detail: string;
  status: StatusKey;
}

export interface SiteIntensity {
  site: string;
  neso_region_id: number;
  neso_region_name: string;
  /** Mean of the regional input series over the simulated window. */
  input_mean_gco2_per_kwh: number;
  /** Mean implied by the simulator's own accounting over the same window. */
  simulated_gco2_per_kwh: number;
  within_tolerance: boolean;
}

export interface DataResponse {
  sources: DataSource[];
  gaps: DataGap[];
  regions: SiteIntensity[];
  spread_gco2_per_kwh: number | null;
  demand: {
    n_requests: number;
    mean_requests_per_slot: number;
    peak_requests_per_slot: number;
    n_slots: number;
  } | null;
  energy: {
    mean_utilization: number;
    n_saturated_slots: number;
    n_slots: number;
    wh_per_request: number;
  } | null;
}

export interface CoverageBlock {
  mean_coverage_positive_forecast: number;
  min_cell_coverage?: number | null;
  max_cell_coverage?: number | null;
  cells_at_target_pct: number;
  mean_half_width_pct_of_forecast: number;
  mean_coverage_all_slots?: number;
  zero_forecast_slot_pct?: number;
  coverage_stderr?: number;
  thin_regime_fallbacks?: number;
  note?: string;
  edges_gco2_per_kwh?: number[];
}

export interface MonthRow {
  month: number;
  calibration_start_utc: string;
  calibration_slots: number;
  national_relative_q: number;
  national_coverage: number;
  threshold_ratio: number;
  sim_site_slots: number;
  band_robust_pct: number | null;
  median_best_to_second_ratio: number | null;
}

export interface RegionRow {
  regionid: number;
  shortname: string | null;
  mean_coverage: number | null;
  min_coverage: number | null;
  months_at_target: number | null;
  zero_forecast_pct: number | null;
  sim_site: boolean | null;
}

export interface BucketRow {
  lo: number;
  hi: number | null;
  n: number;
  mean_abs_error: number;
  q90_abs_error: number;
  mean_relative_error: number;
}

export interface GridCell {
  month: number;
  regionid: number;
  shortname: string | null;
  sim_site: boolean;
  relative_coverage: number;
  constant_coverage: number;
  regime_conditional_coverage: number;
  regime_relative_coverage: number;
  mean_forecast_gco2_per_kwh: number;
  n_eval: number;
}

export interface UncertaintyResponse {
  alpha: number;
  target: number;
  single_split: {
    national: {
      holdout_coverage: number;
      band_half_width_gco2_per_kwh: number;
      holdout_mae_gco2_per_kwh: number;
      n_calibration?: number;
      n_holdout?: number;
    } | null;
    regional: {
      mean_coverage: number;
      min_coverage: number;
      n_regions_at_target: number;
      n_regions: number;
    } | null;
    per_region: {
      regionid: number;
      coverage: number | null;
      band_half_width_gco2_per_kwh: number | null;
      slots: number | null;
    }[];
  };
  rolling: {
    scheme: string;
    calibration_days: number;
    n_cells: number;
    n_regions: number;
    n_evaluation_slots: number;
    relative: CoverageBlock;
    constant: CoverageBlock;
    regime_conditional: CoverageBlock;
    regime_relative: CoverageBlock;
    residual_structure: {
      note: string;
      by_bucket: BucketRow[];
      alignment: {
        by_shift_slots: Record<string, number>;
        best_shift_slots?: number;
        used_for_calibration: boolean;
        note: string;
      };
    };
    decision_relevance: {
      note: string;
      mean_national_relative_q: number;
      mean_threshold_ratio: number;
      mean_band_robust_pct: number;
    };
    pairing: {
      min_paired_pct?: number;
      duplicate_slots_dropped?: { national: number; regional: number };
      slots_per_month?: Record<string, number>;
    };
    sim_sites: {
      regions: string[];
      mean_coverage_positive_forecast: number;
      min_coverage_positive_forecast?: number;
    };
    by_region: RegionRow[];
    by_month: MonthRow[];
    grid: GridCell[];
  } | null;
}

export interface ControllerRow {
  name: string;
  family: "rule" | "SAC";
  carbon_kg: number;
  carbon_vs_round_robin_pct: number | null;
  sla_violation_rate: number;
  energy_kwh: number | null;
  transmission_cost_usd: number | null;
  tasks_finished: number | null;
  per_dc?: Record<string, { carbon_kg?: number; tasks?: number }> | null;
}

export interface SimulatorResponse {
  upstream: {
    name: string;
    organisation: string;
    commit: string | null;
    note: string;
  };
  control: {
    exp_id: string;
    window: string | null;
    days: number;
    seed: number;
    controllers: ControllerRow[];
    best_rule_kg: number;
    best_sac_kg: number;
    sac_min_sla_violation_rate: number;
  } | null;
  uk: {
    exp_id: string;
    window_start_utc: string;
    window_hours: number;
    days: number;
    seed: number;
    clock_aligned_with_carbon: boolean;
    controllers: ControllerRow[];
    regional_spread_gco2_per_kwh: number;
    sites: Record<string, SiteIntensity>;
    exit_test: {
      max_intensity_error_gco2_per_kwh: number;
      regional_ordering_matches_input: boolean;
      exit_test_passed: boolean;
    };
    transmission_inoperative: boolean;
    price_identical_across_sites: boolean;
  } | null;
}

export interface LadderRung {
  rung: number;
  name: string;
  uses: string;
  purpose: string;
  status: StatusKey;
  evidence: string;
}

export interface PoliciesResponse {
  ladder: LadderRung[];
  agent: {
    observation: string[];
    action: string[];
    objective: {
      formula: string;
      terms: { term: string; meaning: string }[];
    };
    cvar_note: string;
  };
  note: string;
}

export interface RoadmapResponse {
  phases: {
    phase: string;
    name: string;
    work: string;
    exit_test: string;
    state: "done" | "next";
  }[];
  next: { title: string; detail: string }[];
  limits: { title: string; detail: string }[];
  claim: { title: string; body: string; rules: string[] };
}

export interface HealthResponse {
  status: string;
  generated_at: string;
  experiments: number;
  experiments_with_runs: number;
  repo_root: string;
}
