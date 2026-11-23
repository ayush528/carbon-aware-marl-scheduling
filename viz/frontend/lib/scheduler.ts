/**
 * Types for the scheduler replay endpoints.
 *
 * Shapes are read straight off ``viz/backend/schedule.py``; nothing here is
 * optional-by-guess, and every field that the backend may null is nullable here
 * so a missing value renders as "unavailable" instead of ``undefined``.
 */

export type Site = {
  name: string;
  short: string;
  region_id: number;
  lat: number;
  lon: number;
  geo_note: string;
};

export type QueueItem = {
  id: string;
  class_index: number;
  class_label: string;
  arrival: number;
  volume_gpu_s: number;
  slots_left: number;
  expired: boolean;
  selected: boolean;
};

export type QueueClass = {
  class_index: number;
  gpu_s: number;
  n_items: number;
  oldest_slots_left: number;
  deadline_hours: number;
  label: string;
  items: QueueItem[];
};

export type Alternative = {
  site: string;
  label: string;
  slot: number;
  forecast_g_per_kwh: number | null;
  band_g_per_kwh: number | null;
  price_g_per_kwh: number | null;
  realized_g_per_kwh: number | null;
  free_gpu_s: number | null;
  block_capacity_gpu_s: number | null;
  take_gpu_s: number;
  status: "chosen" | "rejected";
  code: string;
  reason: string;
};

export type Decision = {
  id: string;
  slot: number;
  class_index: number;
  class_label: string;
  deadline_slots: number;
  arrival: number;
  age_slots: number;
  slots_left: number;
  last_legal_slot: number;
  volume_gpu_s: number;
  executed_now_gpu_s: number;
  deferred_gpu_s: number;
  unassigned_gpu_s: number;
  chosen: {
    slot: number;
    at: string;
    site: string;
    site_label: string;
    price_g_per_kwh: number | null;
    blocks: { slot: number; site: string; site_label: string; take_gpu_s: number; price_g_per_kwh: number }[];
  } | null;
  predicted_emissions_kg: number | null;
  realized_emissions_kg: number | null;
  worst_feasible: {
    site: string;
    label: string;
    price_g_per_kwh: number | null;
    emissions_kg: number | null;
    fully_feasible: boolean;
  } | null;
  reduction_kg: number | null;
  reduction_pct: number | null;
  split: {
    executed_now: boolean;
    deferred: boolean;
    spilled: boolean;
    unplaced: boolean;
    expired: boolean;
    deadline_forced: boolean;
  };
  alternatives: Alternative[];
};

export type Frame = {
  slot: number;
  at: string;
  forecast_g_per_kwh: number[];
  band_g_per_kwh: number[];
  realized_g_per_kwh: (number | null)[];
  price_g_per_kwh: number[];
  capacity_gpu_s: number[];
  served_gpu_s: number[];
  offered_gpu_s: number[];
  missed_gpu_s: number;
  carbon_kg: number;
  idle_carbon_kg: number;
  queue: { total_gpu_s: number; by_class: { class_index: number; gpu_s: number; n_items: number; oldest_slots_left: number }[] };
};

export type Label = { status: "verified" | "inspected" | "modelled" | "assumption" | "next"; what: string };

export type Replay = {
  available: boolean;
  reason: string | null;
  meta: {
    exp_id: string;
    run: { run_dir: string; timestamp: string; git_sha: string; git_dirty: boolean; config_hash: string; seed: number };
    weeks: string[];
    fleets: { name: string; n_gpus_per_site: number; capacity_gpu_s_per_slot: number }[];
    deadlines: number[];
    prices: number[];
    n_slots: number;
    slot_minutes: number;
    sites: Site[];
    labels: Record<string, Label>;
    notes: Record<string, string>;
    defaults: {
      week: string;
      fleet: string;
      price: number;
      robust: number;
      reserve_mode: string;
      reserve: number;
      reserve_level: number | null;
    };
  };
  week: string;
  window_start_utc: string;
  fleet: { name: string; n_gpus_per_site: number; capacity_gpu_s_per_slot: number };
  knobs: { robust: number; reserve: number; reserve_gpu_s: number; reserve_mode: string; reserve_level: number | null };
  price: number;
  sites: Site[];
  summary: {
    carbon_kg: number;
    variable_carbon_kg: number;
    idle_carbon_kg: number;
    offered_gpu_s: number;
    served_gpu_s: number;
    missed_fraction: number;
    missed_gpu_hours: number;
    objective: number;
    price: number;
  };
  frames: Frame[];
  slot_decision: {
    slot: number;
    at: string;
    queue: { gpu_s: number; by_class: QueueClass[] };
    decisions: Decision[];
    totals: {
      forecast_g_per_kwh: number[];
      band_g_per_kwh: number[];
      realized_g_per_kwh: (number | null)[];
      served_gpu_s: number[];
      offered_gpu_s: number[];
      missed_gpu_s: number;
      carbon_kg: number;
    };
  };
  selection: { slot: number; site: string; item: string; defaulted: string[]; slot_reason: string | null; site_reason: string };
  trace: { matches_planner: boolean; mismatch_slots: number[]; n_slots: number; note: string };
  policy: {
    exp_id: string;
    deadlines_slots: number[];
    hard_constraints: { label: string; value: string; note: string }[];
    objective: { formula: string; price: number; parity_price_kg_per_gpu_hour: number; note: string };
    arms: { label: string; kind: string; robust: number; reserve: number; arrival_forecast: number }[];
    band: { evidence: { available: boolean; relative_flipped_pct: number; absolute_flipped_pct: number; n_slots: number } | null; note: string };
    note: string;
  };
};

export function fmt(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function signPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${fmt(value, digits)}%`;
}

export function slotClock(startIso: string, slot: number, slotMinutes = 30): string {
  const start = new Date(startIso);
  const at = new Date(start.getTime() + slot * slotMinutes * 60_000);
  return at.toISOString().slice(0, 16).replace("T", " ") + "Z";
}

/** Colour ramp for gCO2/kWh: green (clean) → amber → red (dirty). */
export function carbonColour(value: number, lo: number, hi: number): string {
  const span = Math.max(hi - lo, 1e-6);
  const t = Math.min(1, Math.max(0, (value - lo) / span));
  // Interpolate in HSL from 150deg (green) through 45deg (amber) to 0deg (red).
  const hue = 150 - 150 * t;
  const light = 62 - 24 * t;
  return `hsl(${hue.toFixed(0)} 70% ${light.toFixed(0)}%)`;
}
