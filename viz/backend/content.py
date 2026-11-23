"""Narrative content the API serves: data catalogue, policy ladder, roadmap.

Everything here is either a disclosed fact about the repo (checked by tests) or
a label the project uses consistently. Numbers that come from an experiment are
read from its run record elsewhere -- this module holds only the framing.
"""

from __future__ import annotations

from typing import Any

# The five labels the project uses everywhere. Kept in one place so the frontend
# renders them identically on every page.
LEGEND = [
    {
        "key": "verified",
        "label": "Verified",
        "tone": "good",
        "meaning": "Reproduced from data or a run record; re-runnable.",
    },
    {
        "key": "inspected",
        "label": "Inspected",
        "tone": "info",
        "meaning": "Checked by hand against a source; not automated.",
    },
    {
        "key": "modelled",
        "label": "Modelled",
        "tone": "warn",
        "meaning": "Produced by our own model or simulator, not measured.",
    },
    {
        "key": "assumption",
        "label": "Assumption",
        "tone": "accent",
        "meaning": "Declared, not derived; disclosed in the paper.",
    },
    {
        "key": "next",
        "label": "Next",
        "tone": "muted",
        "meaning": "Planned work; nothing claimed yet.",
    },
]

DATA_SOURCES = [
    {
        "name": "NESO regional carbon intensity",
        "what": "Half-hourly carbon forecast per DNO region, plus national actuals",
        "granularity": "30 min · 14 regions · 2024",
        "role": "Ground truth for placement and for band calibration",
        "status": "verified",
        "evidence": "exp002, exp003, exp010",
    },
    {
        "name": "Azure LLM inference trace",
        "what": "Per-request arrivals and token counts for a production LLM service",
        "granularity": "16.8M requests · 336 half-hour slots",
        "role": "LLM demand stream (arrivals + tokens)",
        "status": "verified",
        "evidence": "exp006",
    },
    {
        "name": "Alibaba GPU cluster trace 2020",
        "what": "Event-level task arrivals with resource requests",
        "granularity": "1 year · simulator-native schema",
        "role": "Workload inside SustainCluster",
        "status": "verified",
        "evidence": "exp008, exp009",
    },
    {
        "name": "Elexon MID wholesale price",
        "what": "GB half-hourly wholesale electricity price (APXMIDP)",
        "granularity": "30 min → hourly · GBP/MWh",
        "role": "Real cost signal, not a synthetic price",
        "status": "verified",
        "evidence": "exp009",
    },
    {
        "name": "NLR GPU power profiles",
        "what": "Idle and peak power per accelerator model",
        "granularity": "per-GPU watts, PUE applied",
        "role": "Energy model behind the demand envelope",
        "status": "inspected",
        "evidence": "exp007",
    },
    {
        "name": "Region-to-workload mapping",
        "what": "Which grid region each simulated site sits in",
        "granularity": "4 UK sites → NESO region ids",
        "role": "Links demand to carbon",
        "status": "assumption",
        "evidence": "No public trace names its grid region",
    },
]

DATA_GAPS = [
    {
        "title": "Regional actuals do not exist",
        "detail": (
            "NESO's regional endpoint ships forecasts only: zero actuals across the whole matrix, "
            "re-verified for 2024 on both the single-region and all-regions endpoints. Regional "
            "actuals are estimated as national_actual x regional_forecast / national_forecast."
        ),
        "status": "assumption",
    },
    {
        "title": "A real 15-hour outage",
        "detail": (
            "NESO is missing 15 hourly slots on 11-12 June 2024 in every region (8769 of "
            "8784 rows). "
            "The simulator indexes carbon positionally, so the installer forward-fills "
            "exactly those "
            "and records the count in a manifest. Nothing else is interpolated."
        ),
        "status": "verified",
    },
    {
        "title": "The price is national, not regional",
        "detail": (
            "GB wholesale price does not vary by region, so the lowest-price controller "
            "has nothing "
            "to differentiate and is degenerate. Its +3.1% carbon is tie-breaking, not a "
            "price effect."
        ),
        "status": "verified",
    },
    {
        "title": "One AWS region for GB",
        "detail": (
            "SustainCluster prices inter-site transfer through an AWS region matrix. GB "
            "has exactly "
            "one (eu-west-2), so the transmission-cost term is 0 and inoperative for a UK-only run."
        ),
        "status": "verified",
    },
]

POLICY_LADDER = [
    {
        "rung": 1,
        "name": "Round-robin",
        "uses": "Nothing",
        "purpose": "Demand and energy reference",
        "status": "verified",
        "evidence": "exp008, exp009",
    },
    {
        "rung": 2,
        "name": "Least-pending / most-available",
        "uses": "Queue state",
        "purpose": "Throughput-first control",
        "status": "verified",
        "evidence": "exp008, exp009",
    },
    {
        "rung": 3,
        "name": "Lowest-carbon / lowest-price",
        "uses": "Point forecast",
        "purpose": "The strong heuristic any learned policy must beat",
        "status": "verified",
        "evidence": "exp008, exp009",
    },
    {
        "rung": 4,
        "name": "Risk-aware rule",
        "uses": "Forecast + conformal band",
        "purpose": "Isolates the value of uncertainty alone, before any RL",
        "status": "next",
        "evidence": "exp010 supplies the band",
    },
    {
        "rung": 5,
        "name": "Centralised PPO",
        "uses": "Full global state",
        "purpose": "Learning ceiling and upper bound",
        "status": "next",
        "evidence": "",
    },
    {
        "rung": 6,
        "name": "IPPO",
        "uses": "Local observation + scalar messages",
        "purpose": "Decentralised execution with limited communication",
        "status": "next",
        "evidence": "",
    },
    {
        "rung": 7,
        "name": "MAPPO + CVaR",
        "uses": "Local observation + band + risk term",
        "purpose": "The proposed contribution",
        "status": "next",
        "evidence": "",
    },
]

AGENT_DESIGN = {
    "observation": [
        "Own queue depth, running tasks, GPU utilisation",
        "Own carbon forecast and its calibrated band (g/kWh)",
        "Own electricity price",
        "Deadline slack of queued work (min / mean / count at risk)",
        "One scalar per neighbouring site: its marginal carbon and queue pressure",
    ],
    "action": [
        "Route an arriving task to a site (including local)",
        "Defer when the deadline allows and the forecast is poor",
        "Admit or hold when the local queue is saturated",
    ],
    "objective": {
        "formula": "min  E[CO2] + lambda * E[cost] + mu * CVaR_alpha(SLA violation)",
        "terms": [
            {"term": "E[CO2]", "meaning": "Expected emissions from real regional intensity"},
            {
                "term": "CVaR_alpha",
                "meaning": "Mean of the worst alpha tail of deadline misses, not the mean miss",
            },
            {
                "term": "bands",
                "meaning": "Feed the observation, so the agent sees how much the "
                "forecast can be trusted",
            },
        ],
    },
    "cvar_note": (
        "A carbon-aware scheduler faces a fat tail: one bad forecast during a ramp can "
        "strand work. "
        "A mean penalty happily trades a rare catastrophic miss for a small average "
        "gain. CVaR prices "
        "that tail, so the policy becomes conservative exactly where the band is wide."
    ),
}

PHASES = [
    {
        "phase": "0",
        "name": "Infrastructure",
        "work": "Repo, CI, Docker, experiment framework",
        "exit_test": "CI green; an experiment reproduces in Docker",
        "state": "done",
    },
    {
        "phase": "1",
        "name": "Data freeze",
        "work": "NESO 14-region puller, conformal bands, Azure demand",
        "exit_test": "Bands hit target coverage on held-out data",
        "state": "done",
    },
    {
        "phase": "2",
        "name": "Simulator",
        "work": "SustainCluster on 4 UK sites, real carbon and price",
        "exit_test": "Baseline reproduced; carbon matches the input series",
        "state": "done",
    },
    {
        "phase": "3",
        "name": "Agents",
        "work": "Risk-aware rule, PPO, IPPO, MAPPO + CVaR",
        "exit_test": "Each rung beats or matches the one below at equal SLA",
        "state": "next",
    },
    {
        "phase": "4",
        "name": "Evaluate and write",
        "work": "Ablations, robustness, multi-window, thesis",
        "exit_test": "Claims inside the EuroSys-2024 envelope",
        "state": "next",
    },
]

NEXT_STEPS = [
    {
        "title": "Finish exp010",
        "detail": "Rolling-origin bands on 2024 with regime-conditional calibration; "
        "results from the committed run record.",
    },
    {"title": "Land the UK baseline", "detail": "exp008 + exp009 through CI, then tag on merge."},
    {
        "title": "Rung 4: risk-aware rule",
        "detail": "Same rule with and without the band — the uncertainty ablation, before any RL.",
    },
    {
        "title": "Bands into observations",
        "detail": "Retrain the shipped SAC as a sanity check that the feature helps.",
    },
    {
        "title": "PPO → IPPO → MAPPO",
        "detail": "Each with CVaR; multi-seed, multi-window evaluation.",
    },
]

LIMITS = [
    {
        "title": "Regional actuals are estimated",
        "detail": "NESO ships none; the national-scaling identity is used everywhere and "
        "can be recomputed exactly.",
    },
    {
        "title": "The 7-day window is short",
        "detail": "One week cannot support variance claims; multi-window, multi-seed "
        "runs come before any headline number.",
    },
    {
        "title": "Transmission cost is inoperative for GB",
        "detail": "One AWS region means a diagonal matrix and zero cost. Not a finding "
        "about transfer cost.",
    },
    {
        "title": "Price is national",
        "detail": "The price-only controller is degenerate by construction.",
    },
    {
        "title": "Zero-forecast slots exist",
        "detail": "About 4.6% of 2024 regional slots. Under national scaling they are "
        "trivially covered, so exp010 reports that share and the informative "
        "(positive-forecast) coverage separately.",
    },
    {
        "title": "The region mapping is an assumption",
        "detail": "No public trace names its grid region; the four-site mapping is "
        "declared, not derived.",
    },
    {
        "title": "Deadlines are the simulator's model",
        "detail": "They are not measured from a real LLM serving fleet.",
    },
]

CLAIM = {
    "title": "What the paper claims",
    "body": (
        "First demonstrated combination of four parts that each exist separately: "
        "decentralised MARL "
        "with limited communication, calibrated forecast uncertainty, real "
        "region-matched UK carbon, "
        "and risk-aware deadlines. Evaluated on region-matched ground truth with uncertainty as a "
        "measured input rather than an assumed noise term."
    ),
    "rules": [
        "All savings are relative to identical demand.",
        "Absolute numbers are labelled illustrative.",
        "The region-mapping assumption is disclosed in the abstract.",
        "Claims stay inside the EuroSys-2024 envelope.",
    ],
}


# --- scheduler dashboard -----------------------------------------------------

# Representative city coordinates for the four DNO regions. A map needs a point;
# the coordinates are the region's principal city, not a measured data-centre
# location. The mapping from workload to region is the project's disclosed
# assumption.
SITE_GEO = {
    "GB-London": (51.5074, -0.1278, "London"),
    "GB-SouthWales": (51.4816, -3.1791, "Cardiff"),
    "GB-NorthWestEngland": (53.4808, -2.2426, "Manchester"),
    "GB-SouthScotland": (55.8642, -4.2518, "Glasgow"),
}


def site_label(name: str | None) -> str:
    """Short display name for a site, from the one mapping."""
    if not name:
        return "—"
    return SITE_GEO.get(name, (0.0, 0.0, name))[2]


def scheduler_site(name: str, region_id: int | None = None) -> dict[str, Any]:
    lat, lon, short = SITE_GEO.get(name, (0.0, 0.0, name))
    return {
        "name": name,
        "short": short,
        "region_id": region_id,
        "lat": lat,
        "lon": lon,
        "geo_note": "principal city of the DNO region; representative, not measured",
    }


def scheduler_sites(regions: dict[str, int]) -> list[dict[str, Any]]:
    return [scheduler_site(name, regions.get(name)) for name in regions]


BAND_NOTE = (
    "The calibrated carbon band cannot change a placement decision here, and the "
    "dashboard does not imply it does. Under the national-scaling estimator the "
    "realized regional intensity is the forecast times one common factor per slot, "
    "so the forecast's ordering across sites is exact: exp011 measured 0 of 336 "
    "slots reordered by the pooled relative band. The band enters the planner only "
    "as a price level (forecast + robust x band), and exp017 found it changed no "
    "decision for the third independent time. The uncertainty input with real "
    "decision value is the calibrated arrival reserve (exp018), which withholds "
    "capacity for work that has not arrived yet."
)

SCHEDULER_LABELS = {
    "decision": {
        "status": "modelled",
        "what": "The chosen site, slot and predicted emissions: the planner's own output.",
    },
    "queue": {
        "status": "modelled",
        "what": "The backlog the planner sees at this slot, replayed from verified demand.",
    },
    "carbon_forecast": {
        "status": "verified",
        "what": "NESO half-hourly regional forecast for the held-out week.",
    },
    "carbon_realized": {
        "status": "assumption",
        "what": (
            "Regional actuals are estimated as national_actual x regional_forecast / "
            "national_forecast; NESO ships no regional actuals."
        ),
    },
    "demand": {
        "status": "verified",
        "what": "Azure LLM inference trace week; exp006 validated 16.8M requests.",
    },
    "mapping": {
        "status": "assumption",
        "what": (
            "Which grid region each data centre sits in. No public workload trace "
            "names its region, so the four-site mapping is declared, not derived."
        ),
    },
    "explanation": {
        "status": "modelled",
        "what": (
            "Generated from the replayed ledger: candidate prices, residual capacity "
            "and the assignment the planner made. Not authored per run."
        ),
    },
    "measured_arms": {
        "status": "verified",
        "what": "Means over 12 held-out Oct-Dec 2024 weeks, from the exp017 run record.",
    },
    "reserve": {
        "status": "verified",
        "what": "exp018's calibrated arrival reserve, re-runnable from its run record.",
    },
}

SCHEDULER_NOTES = {
    "objective": (
        "The objective is exactly the one exp017 ranks its arms on: "
        "carbon_kg + price * missed_gpu_hours. Price is the only scalar weight. "
        "Deadlines and per-site per-slot capacity are hard constraints: the planner "
        "never trades them away, so there is no weighted-sum slider for them."
    ),
    "relative": (
        "Comparisons are relative, under the identical demand stream. Absolute kg "
        "values are illustrative of this workload and fleet size, not a general "
        "claim."
    ),
    "execution": (
        "Only the current slot is executed; the rest of the plan is a reservation "
        "that is recomputed next slot with the arrivals that actually happened. The "
        "request IDs are derived (class + arrival slot), because the trace has no "
        "per-request identifiers."
    ),
    "classes": (
        "Arrivals are split equally across four deadline classes (1, 2, 4 and 8 "
        "hours). The Azure trace carries no latency labels, so the split is a "
        "disclosed modelling choice, identical for every policy."
    ),
    "band": BAND_NOTE,
    "site_map": (
        "Sites are placed at their region's principal city. Carbon intensity and "
        "capacity are the model's; the mapping from workload to region is the "
        "project's disclosed assumption."
    ),
}


def policies() -> dict[str, Any]:
    return {
        "ladder": POLICY_LADDER,
        "agent": AGENT_DESIGN,
        "note": (
            "Each rung must beat or match the one below it under identical demand. A "
            "rung that does "
            "not is reported as such: the machinery is not justified by intent."
        ),
    }


def roadmap() -> dict[str, Any]:
    return {
        "phases": PHASES,
        "next": NEXT_STEPS,
        "limits": LIMITS,
        "claim": CLAIM,
    }
