# Executive Summary — Guide-Ready

**Project:** Uncertainty-Aware Decentralized Multi-Agent Reinforcement Learning for Carbon-Aware Workload Scheduling Across Geo-Distributed Data Centers.
**Question studied:** Can this project be built on free, real-world, geographically consistent datasets?

## Answer in one paragraph

Yes — with one honestly disclosed limitation. After downloading and programmatically inspecting the key datasets (not just reading their websites), we found that **no public workload trace in the world is officially mapped to a real data-center location** — every publisher anonymizes geography. However, for the **United Kingdom** we verified a complete, free, real-data stack for everything else: 30-minute **carbon intensity for the whole country and for 14 regional electricity areas** including **historical forecasts paired with actuals** (the uncertainty signal our project needs, measured rather than invented), a **real production LLM workload trace of 16.8 million requests**, **measured GPU/CPU power telemetry at 10 Hz**, real **inter-data-center latency** tables, and an **MIT-licensed simulator (SustainCluster, NeurIPS 2025)** we can extend. The single compromise — assigning the geo-anonymous workload trace to UK sites — is disclosed as a modelling assumption, exactly as the closest published benchmark already does.

## Key verified numbers (from our own downloads, 4 Nov 2026)

| Evidence | Value |
|---|---|
| UK carbon data | 30-min gCO₂/kWh, national + 14 regions, since Sep 2017, free, no API key, CC BY 4.0 |
| Forecast uncertainty (Jan 2025, national) | 1,463 slots with forecast+actual; MAE 9.05, RMSE 12.97 gCO₂/kWh |
| Regional spread in one half-hour (15 Jan 2025) | 19 → 367 gCO₂/kWh across 14 regions (348 gCO₂/kWh) |
| Azure LLM trace | 16,803,695 requests, 7 days (May 2024), 0 nulls, 0 duplicates; 74→5,884 requests/min burstiness; no region field |
| Measured power (NLR, Colorado, DOI 10.7799/3025227) | 10 Hz RAPL+NVML; CPU 100.8–355.5 W; 4-GPU array 289–2,851 W (Llama-3.1-70B inference) |
| Alibaba GPU trace 2020 (verified by download) | 707,064 jobs / 1,261,050 tasks; GPU types; UTC+8 note only |
| EIA-930 (US alternative) | 266,398 hourly rows verified; free; but no CO₂ forecast → uncertainty must be self-trained |

## Why the UK wins

Only source worldwide with **native forecast-vs-actual carbon pairs**; genuine multi-site structure inside one country (14 regions, verified 348 gCO₂/kWh spread); all layers free and license-clean (CC BY 4.0 / MIT / CC0); SustainCluster already ships GB carbon data and is MIT-licensed for extension. India and Japan fail the full stack (no hourly carbon + no workload + no measured power). The US is the runner-up but loses on measured forecast uncertainty.

## The research gap (checked against 30 papers, 2024–2026, DOIs verified)

No published work combines **decentralized limited-communication MARL + forecast uncertainty + region-matched real data + risk-aware deadlines**. SustainCluster has the real data but one centralized agent and lists forecasting/MARL as *future work*; the conformal-uncertainty paper (SIGENERGY 2024) has no control agents; the MADRL papers use deterministic signals; the DRO/CVaR papers have single controllers. Our contribution — uncertainty-aware, risk-penalized, communication-limited decentralized scheduling evaluated on the UK stack — is a defensible novelty.

## Recommended build

NESO Carbon Intensity API (carbon + uncertainty) → SustainCluster simulator extended with 3–5 UK sites (London/South Wales/North England/Scotland) → MAPPO agents (limited communication) with IPPO ablation and centralized-PPO upper bound → CVaR penalty on SLA violations → baselines: Round Robin, EDF, carbon-greedy, centralized PPO, IPPO, MAPPO, uncertainty-aware MAPPO.

## Deliverables produced by this study

1. Full report (10 chapters): `report/report.md` / `report/report.docx`
2. Dataset comparison spreadsheet (28 datasets, feasibility matrix, 30 papers, 34 sources): `deliverables/dataset-comparison.xlsx`
3. Data audit folder — raw samples (715 MB incl. the full Azure trace), fetch/inspection scripts, verification tables: `data-audit/`
4. Source/reference list with URLs and DOIs: `report/sources.md`
5. This executive summary: `report/executive-summary.md`
