# Feasibility Study Report

## Uncertainty-Aware Decentralized Multi-Agent Reinforcement Learning for Carbon-Aware Workload Scheduling Across Geo-Distributed Data Centers

**Study type:** Real-world dataset feasibility study (B.Tech major project)
**Audit date:** 4 November 2026
**Evidence base:** All dataset claims in this report were verified by direct download and programmatic inspection on this date, unless explicitly marked otherwise. Raw evidence: `data-audit/` folder. Research notes: `research-notes/` folder.

**Label key used throughout this report:**
- **[VERIFIED]** — we downloaded the data and inspected it programmatically.
- **[VERIFIED-S]** — a survey pass fetched the official page/repo and, where noted, downloaded samples.
- **[DOCUMENTED]** — official documentation confirms the claim, but we did not download data.
- **[MODELLING ASSUMPTION]** — a disclosed design assumption, not a measurement.
- **[RECOMMENDATION]** — our judgement for the project.

---

# Chapter 1 — Executive summary

**The project.** We want to build a decentralized multi-agent reinforcement learning (MARL) scheduler that places GPU/LLM workloads across several data centers in a way that reduces carbon emissions while respecting deadlines, using **real-world data only**, with workload, electricity and carbon-intensity information belonging to the **same geographical region**.

**The main finding.** After verifying 30+ datasets and APIs by actually downloading and inspecting them, the strict form of the geographical-consistency requirement — a public workload trace whose records are officially mapped to a named, real data-center region — **does not exist anywhere today**. Every public production workload trace (Azure, Alibaba, Google, Meta, SenseTime, Tencent-class) is geographically anonymized, and no publisher provides an official location mapping. We state this plainly because it shapes everything else.

**What IS fully achievable.** For one country — the United Kingdom (Great Britain) — we verified a complete, free, geographically consistent **electricity and carbon layer**:

- The **NESO Carbon Intensity API** (free, no key, CC BY 4.0) provides 30-minute carbon intensity (gCO₂/kWh) for the GB nation **and for 14 regional electricity distribution areas**, with history since September 2017. Uniquely among all sources we examined worldwide, its historical records contain **both the forecast and the actual value for every half-hour slot** — we downloaded January 2025 and measured a forecast error of **MAE 9.05 / RMSE 12.97 gCO₂/kWh** (1,463 verified slots). This is exactly the forecast-uncertainty signal our project needs, measured rather than invented.
- In one verified half-hour slot (15 Jan 2025, 12:00 UTC), regional carbon intensity ranged from **19 gCO₂/kWh (North East England) to 367 gCO₂/kWh (South Wales)** — a 348 gCO₂/kWh spread inside one country. This makes a genuinely multi-site, intra-country geo-distributed scheduler meaningful, not decorative.

**The workload layer.** The strongest real workload traces are: the **Azure LLM Inference Trace 2024** (16.8 million production LLM requests over 7 days; we downloaded all 692 MB and verified zero nulls, zero duplicates, and 80× arrival burstiness) and the **Alibaba GPU cluster trace 2020** (707,064 jobs with GPU types and plans; verified). Both are **geo-anonymous**. SustainCluster — the NeurIPS 2025 benchmark closest to our project — handles this by distributing the Alibaba trace over 20+ regions with a disclosed probabilistic model. We propose the same honest approach, **disclosed as a modelling assumption**, never claimed as a UK measurement.

**Verdict.**

| Question | Answer |
|---|---|
| Can we build a valid workload→power→carbon chain for the SAME identifiable region from public data? | **Not in the strict sense** — no public workload trace is officially geo-located. |
| Can the project still be implemented with real data and scientific honesty? | **Yes** — UK-based, with a real region-resolved carbon layer, real measured power telemetry, real network latency, and a real production workload trace used as a demand model with a disclosed region assumption. |
| Recommended region | **United Kingdom (Great Britain)** — best carbon data worldwide for this exact purpose. |
| Feasibility rating | **Feasible with one disclosed limitation** (workload geography is an assumption). |

**Recommended data stack (all free):** NESO Carbon Intensity API (national + 14 regions, forecast+actual) · Azure LLM Inference Trace 2024 (workload) · NLR Generative-AI power profiles (measured RAPL/NVML GPU+CPU power, 10 Hz) · SustainCluster (MIT-licensed simulator foundation, verified by code inspection) · Azure inter-region RTT matrix + cloud egress pricing (network layer) · Elexon BMRS (generation-mix cross-check).

**Recommended research contribution.** Extend SustainCluster's centralized scheduler to **decentralized, limited-communication MARL agents that consume calibrated forecast uncertainty (conformal/quantile bands derived from the real NESO forecast-vs-actual record) and a CVaR-style risk term on SLA violations**. Our 2024–2026 literature survey (30 papers, all DOIs verified) found **no published work combining all of: decentralized limited-communication agents + forecast uncertainty + region-matched real data + risk-aware deadlines**. The nearest works each satisfy only part of this combination (SustainCluster: real data, centralized; UAD 2024: uncertainty, no agents; Jayanetti TPDS 2024: MADRL, deterministic signals; DRO-JCC 2026: risk, single controller).

---

# Chapter 2 — Data requirements

The scheduler makes a decision every time step (we plan 15-minute steps, matching SustainCluster and grid-data granularity): for each pending job, either defer it or assign it to one of several data centers. To make those decisions carbon-aware, SLA-aware and uncertainty-aware, and to *evaluate* them credibly, the project needs six data categories.

**A. Workload and job information.** Job arrivals, sizes and deadlines drive the scheduling problem. Required fields: job/instance ID, arrival timestamp, duration/completion, workload type (training/inference/batch/interactive), CPU/GPU/memory requirements, GPU type, utilization, priority, deadline/SLA. Without real arrivals, any "scheduling improvement" claim is weak.

**B. Data-center infrastructure and capacity.** How many GPUs/CPUs each site has, and where the sites are. Needed to make placement decisions binding (a job can only go where capacity exists) and to make "geo-distributed" more than a label.

**C. Electricity consumption and power.** How much energy a job actually draws at each site. The strongest evidence is **measured** telemetry (per-node GPU/CPU power); facility-level consumption requires a PUE assumption. Prefer measured over theoretical values.

**D. Electricity carbon intensity.** gCO₂/kWh of the grid each site sits on, historically and — critically for our "uncertainty-aware" claim — **as forecasts**, so that forecast errors can be quantified from real data rather than simulated noise.

**E. Network information.** Inter-site latency and transfer costs, because moving a job or its data consumes network energy, money and time, and can break deadlines.

**F. Forecast uncertainty.** Prediction-error distributions for workload arrivals and carbon intensity. We do not need a separate uncertainty dataset: uncertainty can be **derived** from historical forecast-vs-actual pairs (carbon) and from arrival-process residuals (workload).

**Which fields are actually available in public traces (verified):**

| Required field | Azure LLM trace 2024 | Alibaba GPU 2020 | Google Borg 2019 | Bitbrains 2013 |
|---|---|---|---|---|
| Job/instance ID | implicit (rows are requests) | Yes | Yes | per-VM files |
| Arrival timestamp | Yes (µs) | Yes (desensitized) | Yes | Yes |
| Completion/duration | No | Yes | Yes | No (usage only) |
| Workload type | inference (LLM) | training+inference | mixed | VM service |
| CPU requirement | No | Yes (plan_cpu) | Yes | capacity+usage |
| GPU requirement | No (token counts only) | **Yes (plan_gpu, gpu_type)** | No | No |
| Memory | No | Yes (plan_mem) | Yes | Yes |
| Utilization | No | Yes (sensor tables) | Yes (5-min) | Yes (5-min) |
| Priority | No | No | **Yes (5 tiers)** | No |
| Deadline/SLA | No | No | No | No |
| **Region identified** | **No** | **No (UTC+8 note only)** | **Timezones only** | **NL provenance only** |

Two structural gaps exist in *every* public trace: **no deadlines** and **no region IDs**. Deadlines must be assigned by a disclosed policy (standard practice — e.g., SustainCluster assigns SLA deadlines in its scenario generator). Region identity is the finding of this study (Chapter 7).

---

# Chapter 3 — Geographical dataset search

We searched by **location first**, then matched sources within each location. Summary; full per-source detail is in `research-notes/` and `deliverables/dataset-comparison.xlsx`.

## 3.1 United Kingdom (Great Britain)

| Layer | Source | Status |
|---|---|---|
| Carbon intensity (national + 14 regions) | NESO Carbon Intensity API — free, no key, CC BY 4.0, 30-min, since 2017-09-26, **forecast AND actual per slot** | **[VERIFIED]** |
| Generation mix | Elexon BMRS Insights API (FUELHH/FUELINST) — free, no key | **[VERIFIED-S]** |
| Workload | Azure LLM Inference Trace 2024 (16.8M requests, CC BY 4.0) — geo-anonymous | **[VERIFIED]** |
| Power telemetry | NLR GenAI power profiles (measured, 10 Hz) — measured in USA; used as hardware-level power curves, not UK facility data | **[VERIFIED-S]** |
| PUE / facility | Google publishes per-campus PUE (fleet TTM 1.09 in 2025) and per-region CFE/grid-CI CSVs 2019–2025; UK policy data exists (subnational electricity statistics) | **[VERIFIED-S]** |
| Network | Azure inter-region RTT matrix (includes UK South), cloudping.co, RIPE Atlas for fresh measurements, egress pricing pages | **[VERIFIED-S]** |
| Simulator | SustainCluster (MIT) — includes a **GB carbon-intensity dataset folder** (Electricity Maps format, 2021–2024) we inspected | **[VERIFIED]** |

## 3.2 United States

| Layer | Source | Status |
|---|---|---|
| Carbon intensity | EIA-930 bulk CSVs (hourly, 64 Balancing Authorities, 2015→2026, free no key) + per-BA CO₂ Excel (from 2018-07) + EPA eGRID2023 subregion factors (CAMX etc.) | **[VERIFIED]** (EIA-930 downloaded) / **[VERIFIED-S]** |
| Carbon (single region) | CAISO Today's Outlook: per-day `co2.csv` + `fuelsource.csv` back to ≥2019, free, keyless | **[VERIFIED-S]** |
| Workload | Azure LLM trace (geo-anonymous); Google Borg cells a/b/d officially in America/New_York & America/Chicago timezones (CPU-only) | **[VERIFIED]** / **[VERIFIED-S]** |
| Power | **NLR GenAI power profiles — measured at Kestrel HPC, Golden, Colorado** (geographically identifiable!) | **[VERIFIED-S]** |
| Forecast uncertainty | No CO₂ forecast published by EIA/CAISO → must self-train a forecaster | **[VERIFIED-S]** |

## 3.3 Other candidates (brief)

- **Germany:** Fraunhofer Energy-Charts API — free, no key, 15-min generation actuals **and forecasts** (verified live). No CO₂ endpoint (apply factors). No German workload trace.
- **Netherlands:** ENTSO-E (free token) for NL generation; Bitbrains GWA-T-12 traces (2013, CPU-only, NL provenance via SPEC paper). Old workload.
- **Nordics:** Fingrid (Finland) publishes **direct emission-factor datasets (IDs 265/266/396)** — free API key required; history depth unverified. Sweden has no direct CI source. No regional workload.
- **India:** Grid-India publishes daily reports (generation by source, per regional grid) and CEA publishes annual CO₂ baseline factors — **no hourly CI, no API, no forecasts**. No workload trace. **Not feasible** for the full stack.
- **Japan:** No official hourly CI; excellent academic fallback — Waseda University's Zenodo dataset (18396311, CC BY 4.0, published Jan 2026) with **hourly CI for all 9 TSO areas for FY2024 only**. One year, no forecasts, no workload.
- **Australia:** OpenElectricity (OpenNEM) v4 API — free, keyless, per-state emissions + fuel mix (verified live). No CO₂ forecast; no workload trace.

**Cross-cutting finding.** The only source worldwide that ships **historical forecast-vs-actual carbon pairs out of the box** is the UK NESO API. Everywhere else, forecast uncertainty must be constructed by training our own forecaster — doable, but it weakens the "real uncertainty" claim.

---

# Chapter 4 — Actual downloaded dataset analysis

All files are in `data-audit/downloads/`; scripts in `data-audit/scripts/`; machine-readable results in `data-audit/analysis/`. The full verification table is `data-audit/analysis/VERIFICATION_TABLE.md`.

## 4.1 NESO Carbon Intensity API (UK) — [VERIFIED]

**What we did:** 8 successful API calls (after correcting two wrong path/window attempts — both recorded). Downloaded: 1-day national, full-month national (January 2025), all-regions 1-day snapshot, London (regionid 13) week + month, national generation mix.

**Schema (verbatim from files):** `from`, `to`, `intensity.forecast`, `intensity.actual`, `intensity.index`; regional records add `generationmix[]` (biomass, coal, imports, gas, nuclear, other, hydro, wind, solar) per region per half hour.

Sample rows (national, 1 Jan 2025, verbatim JSON):
```json
{"from":"2025-01-01T00:00Z","to":"2025-01-01T00:30Z","intensity":{"forecast":62,"actual":68,"index":"low"}}
{"from":"2025-01-01T00:30Z","to":"2025-01-01T01:00Z","intensity":{"forecast":68,"actual":66,"index":"low"}}
```

**Measured statistics (January 2025, national, actual values):** 1,489 unique half-hour slots; **min 35, mean 168.1, max 293 gCO₂/kWh**; zero unexpected gaps in the 30-minute series; 1,463 slots (98.3%) carry **both** forecast and actual.

**Forecast-vs-actual error (the uncertainty layer):** **MAE 9.05, RMSE 12.97 gCO₂/kWh** over the month. This is a real, measured error distribution we can feed to conformal/quantile band construction — no synthetic noise needed.

**Regional evidence:** the API returns 14 DNO regions by name (regionid 13 = London; 1 = North Scotland … 14 = South East England) plus England/Scotland/Wales/GB aggregates. In one verified half-hour (15 Jan 2025 12:00–12:30Z) regional intensity spanned **19 → 367 gCO₂/kWh**. London (region 13) January 2025 forecast values: min 22, mean 185.3, max 334 gCO₂/kWh.

**Limitations found:** regional historical records contain `forecast` + `index` but **no `actual`** field (national has both); a single API call is window-capped (full-year regional call → HTTP 400; chunked weekly calls work); no published rate-limit number was found in accessible docs — we kept to ~1 request/second and recommend the same.

**Figures produced from this data:** `report/figures/uk_carbon_forecast_vs_actual_jan2025.png` (forecast vs actual series), `uk_regional_spread_sample_slot.png` (14-region bar chart).

## 4.2 Azure LLM Inference Trace 2024 — [VERIFIED]

**What we did:** downloaded the official `AzureLLMInferenceTrace_code_1week.csv` release asset (691,989,454 bytes) and parsed **the entire file** with pandas.

| Test | Finding |
|---|---|
| Records inspected | **16,803,695 rows** (full file, not a sample) |
| Columns | `TIMESTAMP` (µs), `ContextTokens`, `GeneratedTokens` — matches official schema exactly |
| Time range | 2024-05-10 00:00:00.009930+00:00 → 2024-05-16 23:59:59.929501+00:00 (7 days) |
| Nulls / duplicates | **0 / 0** |
| ContextTokens | p50 1,930 · mean 2,511 · p95 7,674 · max 7,743 |
| GeneratedTokens | p50 8 · mean 23 · p95 79 · max 5,000 |
| Arrival burstiness | 74 → 5,884 requests/min (80×); 9,086 → 301,105 requests/hour |
| Region field | **None exists** — geo-anonymous by design (customer privacy, per official page) |
| License / access | CC BY 4.0; free direct download; citation: DynamoLLM (HPCA 2025) |

Sample rows (verbatim, first three):
```
TIMESTAMP,ContextTokens,GeneratedTokens
2024-05-10 00:00:00.009930+00:00,2162,5
2024-05-10 00:00:00.017335+00:00,2399,6
```

Figure: `report/figures/azure_llm_trace_arrivals.png`. **Use in project:** real production LLM demand model (arrival process + token-size distributions feed GPU-hours and energy per request); the 80× burstiness is direct evidence for workload-forecast uncertainty.

## 4.3 EIA-930 bulk CSV (US) — [VERIFIED]

Downloaded `EIA930_BALANCE_2024_Jan_Jun.csv` (41,742,812 bytes; **266,398 hourly rows**; all Balancing Authorities). Verified columns: demand, demand forecast, net generation by fuel (coal/gas/nuclear/hydro/solar/wind/petroleum), interchange, imputed/adjusted flags. Free, no key. Confirms the US candidate's backbone and its limitation: **CO₂ must be computed from fuel mix** (per-BA Excel CO₂ exists from 2018-07; no CO₂ forecast anywhere).

## 4.4 Datasets verified by survey passes with in-hand samples — [VERIFIED-S]

- **Alibaba cluster-trace-gpu-v2020:** full job/task/spec tables downloaded and parsed — **707,064 jobs, 1,261,050 tasks**; GPU fields (`plan_gpu`, `gpu_type` incl. V100/A100-class); official README gives a **UTC+8 "Asia/Shanghai" desensitization note** — a timezone hint for diurnal alignment only; **no country, region or site is named anywhere in the documentation**. This is SustainCluster's workload source.
- **NLR Generative-AI Workload Power Profiles** (DOI 10.7799/3025227; 1,021 MB zip): raw **RAPL + NVML** logs at ≈10 Hz; for Llama-3.1-70B offline inference we verified 504,570 CPU rows and 504,711 GPU rows over 14 hours; CPU 100.8–355.5 W; GPU array 289–2,851 W. Measured on **Kestrel HPC, Golden, Colorado, USA** — the only geographically identifiable measured-power dataset we found. (A counter-rollover artifact in a few dozen rows must be filtered.)
- **Bitbrains GWA-T-12 fastStorage:** 128 MB zip, 1,250 VM files × 8,640 rows (30 days @ 5-min); 11 metric columns; timestamps 2013-08-12→09-11; **doc/file mismatch found** (header says "[ms]", values behave as epoch seconds). Netherlands provenance only (via the SPEC CCGrid'15 paper), not per-VM.
- **Harvard GPU power metrics** (CC0, 14,054 kernel-level rows, 4 architectures) and **GPU-DVFS-Dataset** (V100, 33 workloads × 13 frequencies, 46.5–242.5 W): power-model calibration data.
- **Live API verifications:** Elexon FUELHH/FUELINST (free, no key), CAISO `/outlook/history/{date}/co2.csv` (≥2019), Energy-Charts `/v2/public_power` + `_forecast` (DE), OpenElectricity v4 emissions (NEM/NSW1), Fingrid 401-without-key, EIA API 403-without-key, Google region-carbon-info CSVs, Ireland CSO MEC02, Azure RTT matrix.

## 4.5 Honest failures (exact)

`gwa.ewi.tudelft.nl` DNS failure (mirror used) · AcmeTrace `trace_seren.csv` advertised but **absent from repo** · Meta and Tencent scheduling traces **not found** · Azure Functions `.rar` downloaded but unextractable in sandbox · Alibaba v2026 OSS sample timed out · UK CI API full-year single call → HTTP 400 (window cap). Full list in `VERIFICATION_TABLE.md` §D.

---

# Chapter 5 — Research literature survey (2024–2026)

Method: Semantic Scholar API (rate-limited during the session; OpenAlex/Crossref/arXiv used as verified fallbacks). Every DOI below was resolved against a real record; none invented. Full details: `research-notes/C-literature-2024-2026.md` (37 entries) and `deliverables/dataset-comparison.xlsx` sheet "Literature 2024-2026".

## 5.1 Benchmarks and simulators with real workload + carbon data

- **SustainCluster** (Guillén-Perez, Naug, Gundecha, Sarkar et al., HPE Labs; **NeurIPS 2025 Datasets & Benchmarks**; OpenReview `AgTASkryb6`; no DOI/arXiv yet). Centralized top-level agent; defer-or-dispatch every 15 min; physics-based per-DC model (IT + HVAC + water); transmission-aware routing (per-GB cost + empirical RTT from Persico et al., GLOBECOM 2016; transfer energy 0.06 kWh/GB from Aslan et al. 2017); modular multi-objective rewards. Data: **Alibaba GPU trace 2020 × Electricity Maps CI × GridStatus prices × Open-Meteo**, 20+ regions. **Limitations:** single centralized agent; no forecast-uncertainty module; no limited-communication setting; no risk measures. This is the closest platform to our project.
- **SustainDC** (Naug et al., **NeurIPS 2024 D&B**, arXiv:2408.07841): MARL **within one DC** (workload/cooling/battery agents). Intra-DC design reference.
- **Green-DCC** (Sarkar et al., **AAAI 2025**, DOI 10.1609/aaai.v39i28.35370): hierarchical RL for DC clusters with liquid cooling — cluster-level distribution + DC-level control. Still top-down; no uncertainty.

## 5.2 Carbon-aware geo-distributed scheduling (non-RL competitors)

- **Caspian** (IBM, **MASCOTS 2024**, 10.1109/MASCOTS64422.2024.10786568): multi-cluster K8s carbon scheduler; **19% carbon reduction**; centralized, deterministic.
- **CarbonEdge** (UMass/CMU/UCSC, **HPDC 2025**, 10.1145/3731545.3731576): mesoscale spatial CI variation for edge placement; **up to 78.7% reductions with <5.5 ms added latency**; centralized.
- **Sukprasert et al., "On the Limitations of Carbon-Aware Temporal and Spatial Workload Shifting"** (**EuroSys 2024**, 10.1145/3627703.3650079): quantifies upper bounds — temporal shifting beats spatial in most regions; realistic job distributions shrink joint savings. Our results must be interpreted inside this envelope.
- **IAS** (Chien group, **SoCC 2025**, 10.1145/3772052.3772250): VM scheduling when DCs flex capacity for the grid; interval-aware scheduler removes up to 92% of terminations.
- **LinTS** (**IEEE CLOUD 2025**, 10.1109/cloud67622.2025.00034): carbon-aware *transfer* scheduling — the network-side actor our reward must price.

## 5.3 Forecast uncertainty and risk

- **Uncertainty-Aware Decarbonization for Datacenters (UAD)** (Li, Liu, Zuo, Varghese; **ACM SIGENERGY Energy Informatics Review 2024**, 10.1145/3727200.3727221): **conformal prediction** for CI-forecast uncertainty; case studies, no control agents. This is the statistical tool we adopt.
- **EnsembleCI** (Purdue, **e-Energy 2025**, 10.1145/3679240.3734630): ensemble CI forecasting beating CarbonCast; point forecasts only.
- **LACS** (**e-Energy 2024**, 10.1145/3632775.3661942): learning-augmented carbon-aware scaling with unknown job lengths; within 1.2% of a clairvoyant online baseline — a robustness template.
- **DRO carbon scheduling** (**J. Cloud Computing 2026**, 10.1186/s13677-026-00904-7): the only 2024–26 work combining DRO + carbon + geo-distributed DCs — but a **single controller**, simulation only.
- **Tail-risk Bit-Watt** (**IJEPES 2026**, 10.1016/j.ijepes.2026.112227): CVaR-style tail risk with cumulative SLA constraints in DC energy systems — the risk formulation we transfer to placement.
- **Probabilistic guarantees for carbon-aware computing** (**IEEE TPWRS 2025**, 10.1109/tpwrs.2025.3630499): risk-aware load shaping with probabilistic bounds.

## 5.4 Multi-agent / decentralized scheduling

- **Jayanetti et al., MADRL renewable-aware workflow scheduling across DCs** (**IEEE TPDS 2024**, 10.1109/tpds.2024.3360448): the flagship MADRL geo-DC baseline — but deterministic renewable/cost signals, communication not a design variable.
- **Two-timescale MADRL** (**IEEE TPDS 2024**, 10.1109/TPDS.2024.3467212): fast task scheduling + slow resource scaling across DCs; reusable idea.
- **CAFE** (**e-Energy 2024**, 10.1145/3632775.3661970) and **FedZero** (**e-Energy 2024**, 10.1145/3632775.3639589): decentralized carbon/renewable-aware federated learning — precedents for region-matched signals driving decentralized decisions, but FL semantics, not placement.

## 5.5 GPU/LLM workloads

- **Azure LLM trace origin:** Patel et al., **ASPLOS 2024** (10.1145/3620666.3651329).
- **DynamoLLM** (**HPCA 2025**, 10.1109/hpca61900.2025.00102): LLM inference cluster energy control on the Azure trace; **~52% energy / ~38% operational carbon savings**; single-DC, no grid signal.
- **TAPAS** (**ASPLOS 2025**, 10.1145/3676641.3716025): thermal/power-aware LLM scheduling on the same trace.
- **PecSched** (arXiv:2409.15104): preemptive LLM scheduling on the trace; p99 queueing −92%.
- **EcoServe** (arXiv:2502.05043): production GenAI serving carbon accounting; **batch ≈55% of serving capacity** — strong evidence that a large deferrable share exists (the raw material of carbon-aware scheduling).
- **SPROUT** (**EMNLP 2024**, 10.18653/v1/2024.emnlp-main.1215): >40% carbon cut via generation directives — an orthogonal, request-level lever.

## 5.6 Carbon accounting cautions (cite in any evaluation)

**Green Mirage** (e-Energy 2024, 10.1145/3632775.3639587), **Sunk Carbon Fallacy** (SoCC 2024, 10.1145/3698038.3698542), **average-vs-marginal CI** (e-Energy 2024 notes, 10.1145/3632775.3661953), and **the Carbon-SLO tension study** (arXiv:2610.14571, 2026) which shows carbon savings can evaporate under realistic SLO/queueing dynamics — our simulator fidelity and signal choice (average GB CI, disclosed) must answer these.

---

# Chapter 6 — SustainCluster assessment

Verified by cloning `github.com/HewlettPackard/sustain-cluster` (MIT license, © 2025 HPE) and reading the README, configs and data tree. Paper: NeurIPS 2025 D&B (OpenReview `AgTASkryb6`).

**What it implements (verified in repo):**

1. **Gymnasium environment** (`TaskSchedulingEnv`) with a **centralized top-level agent** deciding, every **15 minutes**, defer-or-assign for each pending task across N data centers.
2. **Real data integration:** workload = **Alibaba Cluster Trace 2020 GPU** (preprocessed to a full-year DataFrame, `data/workload/alibaba_2020_dataset/`); carbon intensity = **Electricity Maps** zone CSVs for 15+ zones — including a **GB folder (2021–2024, hourly, direct + LCA gCO₂eq/kWh)** we inspected; electricity prices = Electricity Maps + GridStatus; weather = Open-Meteo; transfer costs = AWS/GCP/Azure per-GB pricing.
3. **Physics-informed DC model:** CPU/GPU/memory power curves, thermal response, HVAC proxy (chiller COP, cooling-tower model) inherited from SustainDC; per-DC configs (racks, CPUs/GPU per rack, supply/return temperatures).
4. **Transmission-aware routing:** monetary per-GB cost + delay formula `delay(s) = size_GB×8000/throughput_Mbps + RTT_ms/1000` using empirical inter-macro-region values (Persico et al. 2016); tasks held "in transit" before enqueueing.
5. **Reward engine:** modular multi-objective (energy cost, carbon, SLA violations, transfer overhead) with configurable weights.
6. **Agents included:** custom SAC (multi-action, masked padding for variable task counts), RLlib PPO/APPO/IMPALA (single-action aggregated mode), rule-based baselines (lowest carbon / lowest price / most available), plus a trained HVAC PPO agent per DC.

**What it does NOT implement (our deltas):**

- **Decentralized agents** — the scheduler is one global agent with full system visibility. Its own "Future Work" (§12.2) proposes hierarchical/MARL extensions and lists **"Incorporating Advanced Forecasting"** (price/carbon/workload forecasts in the observation) as future work. Our project is, almost verbatim, their future-work item — a strong, citable motivation.
- **Forecast uncertainty** — observations include *current* carbon intensity and price, not forecast distributions; no prediction intervals anywhere.
- **Risk measures** — rewards are expectation-based; no CVaR/DRO term.
- **Communication limits** — no model of what agents may share.
- **Native GB regional carbon** — its GB file is a single national zone (Electricity Maps GB), not the 14 DNO regions the NESO API provides.

**Reuse plan [RECOMMENDATION]:** keep the Gym env, per-DC physics model, transmission model, reward engine and Alibaba/Azure workload loaders; **replace** the single-zone carbon input with NESO national+regional series (and add its forecast field); **replace** the centralized agent with K decentralized agents (one per site) with a configurable communication graph; **add** uncertainty inputs (conformal bands) and a CVaR penalty; **add** baselines (Round Robin, EDF, carbon-greedy) and the centralized-PPO upper bound.

**Suitability verdict:** **suitable as the simulation foundation**, with the modifications above. MIT license permits this.

---

# Chapter 7 — Feasibility study

**The most important question first:** *Can we create a valid workload-to-power-to-carbon relationship for the SAME identifiable geographical region using publicly available real-world data?*

**Answer: not in the strict sense — and we can prove why.** After verifying 29 workload trace families (note A), we found that **no public workload trace ships an official mapping from its records to a real region or facility**. Azure traces explicitly say "one geographical region" (unnamed); Alibaba's only official signal is a UTC+8 desensitization note; Google publishes cell→timezone but no sites; Bitbrains' Netherlands provenance comes from a conference paper, not the dataset docs; Helios uses pseudonyms; Meta and Tencent traces are not public at all. Per the study's own rule ("if no mapping exists, do not assume or invent the location"), the strict requirement **fails for every candidate region on Earth as of 4 Nov 2026**.

What remains genuinely possible — and what the recent literature itself does — is a **disclosed-assumption design**: real production workload dynamics (arrivals, sizes, burstiness) + real region-resolved carbon + real measured hardware power + real network latency, with the workload→region assignment explicitly labelled as a modelling assumption. SustainCluster makes exactly this kind of assumption (probabilistic distribution of the Alibaba trace over 20+ regions). We adopt the same honesty and go further: we ground the carbon layer in one country with measured forecast uncertainty.

## 7.1 Candidate feasibility ratings

| Criterion | UK (GB) | USA (CAISO/EIA) | Germany | Netherlands | Nordics | India | Japan | Australia |
|---|---|---|---|---|---|---|---|---|
| Workload availability | Yes (Azure LLM; geo-anon) | Yes (Azure LLM; Borg tz-partial) | weak (no recent GPU trace) | weak (Bitbrains 2013, CPU) | No | No | No | No |
| Geographical identity of workload | Assumption (disclosed) | Partial (Borg timezones only) | No | Partial (NL provenance) | No | No | No | No |
| Carbon data (regional, historical) | **Strong** — 14 DNO regions, 30-min, direct gCO₂/kWh, since 2017 | Strong — BA-level hourly (computed from fuel) | Strong — 15-min (computed) | Good (ENTSO-E zone) | Good (FI direct EF; key needed) | Weak (daily reports) | Moderate (9 TSOs, FY2024 only) | Good (NEM states) |
| **Forecast-vs-actual uncertainty** | **Yes — native in API (verified)** | No (self-construct) | Generation forecast yes; CI derived | No | No | No | No | No |
| Measured power data | Generic (NLR, US) + physics model | **NLR is US-based (Colorado)** | generic | generic | generic | none | none | generic |
| PUE/facility evidence | Google UK campuses; policy stats | Google US campuses; EIA | Google DE campus | Google NL campus | Google FI | fact sheets | fact sheets | fact sheets |
| Time alignment | 2017→present | 2015→present | ≈2000s→present | 2015→present | recent | daily | FY2024 | multi-year |
| Accessibility (free) | All free, no key | Free (bulk); API key | Free, no key | Token required | Key required | Free | Free (Zenodo) | Free |
| Multi-site within one country | **Excellent** — 14 DNO regions; verified 348 gCO₂/kWh spread | Good (multi-BA; but multi-ISO) | One zone | One zone | FI one zone | 5 RLDCs (daily) | 9 TSOs | 5 states |
| Reproducibility | API + frozen archives; CC BY 4.0 | Frozen bulk CSVs | API snapshots | Token-gated | Key-gated | PDFs | DOI'd dataset | API |
| **Verdict** | **Feasible (with disclosed workload-region assumption)** | Feasible with limitations | Feasible with limitations | Feasible with limitations | Not feasible alone | **Not feasible** | Not feasible alone | Not feasible alone |

**Why the UK wins for THIS project specifically:**
1. It is the only region where **forecast uncertainty is measured, not simulated** (forecast+actual per slot, verified).
2. It offers **genuine intra-country multi-site structure**: 14 distribution regions with verified extreme spread (19→367 gCO₂/kWh in one half-hour), letting us model 3–5 sites inside one country and one regulatory regime — exactly the "geo-distributed within one country" design the project asks for.
3. Every layer is free and license-clean (CC BY 4.0 / MIT / CC0 / DOE), downloadable without registration.
4. The SustainCluster foundation already ships a GB carbon file and is MIT-licensed for modification.
5. Hyperscaler presence is documented (Azure UK South in London; Google London campus PUE published), supporting credible site placement.

**India and Japan fail** the full stack (no hourly CI + no workload + no measured power). **Nordics/Germany/NL** are viable carbon-wise but lack workload and (for FI/SE) ease of access. The **US** is the strongest runner-up (NLR power data is US-located; EIA-930 is excellent) but loses on forecast uncertainty (must self-train) and on intra-country regional granularity for a student-scale study.

## 7.2 What "feasible" means here — stated honestly

- **Verified facts:** all carbon, network, power-telemetry and workload-statistics numbers in Chapters 3–4.
- **Directly inspected dataset observations:** everything in Chapter 4.
- **Modelled estimates:** PUE priors (Google fleet 1.09 TTM 2025, campus tables), transfer energy factor (0.06 kWh/GB, Aslan et al. 2017 — also used by SustainCluster), GPU-hours per request (derived from token counts + measured power curves).
- **Simulation assumptions:** workload→region assignment; deadline assignment policy; site capacities.
- **Research recommendations:** Chapters 9–10.

---

# Chapter 8 — Research gap and novelty

**What has been done (A):** centralized carbon-aware scheduling with real data (SustainCluster, Caspian, CarbonEdge); single-DC MARL (SustainDC); hierarchical MARL (Green-DCC); MADRL across DCs with deterministic signals (Jayanetti TPDS 2024); CI-forecast *uncertainty quantification* without control (UAD 2024); ensemble CI forecasting (EnsembleCI 2025); DRO/CVaR formulations in energy-system contexts (IJEPES 2026, TPWRS 2025) and one single-controller cloud DRO (JCC 2026); LLM-cluster energy control (DynamoLLM, TAPAS); transfer scheduling (LinTS).

**Done separately but never combined (B):** real region-matched data ∙ forecast uncertainty ∙ decentralized agents ∙ limited communication ∙ risk-aware deadlines.

**Insufficiently investigated (C):** no published scheduler consumes **calibrated CI forecast distributions** at dispatch time; no cross-DC carbon-aware system models an **explicit communication budget/graph**; no GPU/LLM placement work prices **transfer carbon + deadline risk jointly**; no evaluation couples the Azure LLM trace (or any real trace) with **region-resolved real CI under uncertainty-aware decentralized control**.

**Realistic student contribution (D) [RECOMMENDATION]:** a decentralized, limited-communication MARL scheduler (IPPO/MAPPO family) over a SustainCluster-derived, UK-grounded simulator in which (i) carbon forecasts carry **measured** uncertainty (conformal bands from the NESO forecast-vs-actual record), (ii) the reward carries a **CVaR penalty on SLA violations**, and (iii) ablations isolate the value of uncertainty awareness and of communication. This is defensible novelty: each ingredient exists in the literature; the combination and the measured-uncertainty evaluation do not.

**Novelty caution:** SustainCluster's future-work list naming forecasting/MARL does **not** prove nobody else did it — we checked the literature instead (survey §5, special check (d): no peer-reviewed combination found as of 4 Nov 2026).

---

# Chapter 9 — Proposed system and implementation plan

**Pipeline:** real workload data → data-center resource model → workload forecasting → carbon-intensity forecasting → forecast-uncertainty estimation → multi-data-center simulator → decentralized MARL → risk-aware scheduling → evaluation.

## 9.1 Forecasting

- **Carbon:** baseline = the **NESO forecast as issued** (already in the data; zero leakage by construction, since historical forecasts were produced before the actuals). Comparison forecaster = gradient-boosted trees / small LSTM on history (time, generation mix, interconnector flows). Uncertainty = **conformal/quantile bands** calibrated on the measured forecast-error distribution (MAE 9.05, RMSE 12.97 gCO₂/kWh for Jan 2025 as the anchor; calibrate per horizon).
- **Workload:** arrival-rate forecasting (seasonal-naive baseline + gradient boosting on the trace's 15-min aggregation); token-size distributions from the verified trace statistics; prediction intervals from empirical residuals. Sudden spikes are already present in the data (74→5,884 req/min).
- **Leakage prevention:** strictly time-ordered splits (train → validation → test in chronology); forecasts aligned to their issue time (use the API's as-issued forecast field, not recomputed hindsight values); walk-forward evaluation; no future covariates.

## 9.2 Simulator

- **Sites:** 3–5 UK sites mapped to DNO regions (e.g., London=13, South Wales=7, North West England=3, South Scotland=2) — real regional carbon per site, verified spread.
- **Capacity:** GPU-node counts per site [MODELLING ASSUMPTION]; per-node power from the **NLR measured profiles** (idle→peak curves per GPU/CPU); PUE priors from Google's published tables (fleet 1.09 TTM 2025) [MODELLING ESTIMATE].
- **Jobs:** replayed/synthesized from the Azure LLM trace (requests/hour, token sizes) and optionally Alibaba GPU 2020 (GPU-job shapes); deadlines assigned by disclosed policy (e.g., p95 of historical service times × slack factor).
- **Energy & carbon:** energy = ∫ node power dt × PUE; carbon = Σ site energy × site CI(t) + transfer energy (0.06 kWh/GB) × origin CI; **directly measured** inputs: CI (both forecast and actual), node power curves, RTT matrix; **derived**: GPU-hours/request; **simulated**: queueing, deferral, migration.
- **Time step:** 15 minutes (matches carbon data and SustainCluster).

## 9.3 MARL design

- **Why multi-agent:** the project thesis is decentralized operation — sites cannot assume a global oracle; communication is costly/limited; each site has private state (queue, thermal, local CI).
- **Algorithm choice:** **MAPPO** as the primary algorithm (stable, CTDE — centralized critic during training only, decentralized actors at execution, which matches limited runtime communication); **IPPO** as the strict no-communication ablation. QMIX is a poor fit because the action space is per-job assignment, not a monotonic joint-value decomposition.
- **Agent observation (per site):** local queue (job sizes, deadlines), local capacity/utilization, local CI + **forecast band** (upper/lower quantiles), neighbor CI summaries, time features.
- **Actions:** accept-and-run locally, defer (time-shifting within deadline), or offer/accept transfer to a neighbor (with transfer cost/energy/latency applied).
- **Communication:** a configurable graph — full exchange (MAPPO upper regime), summary vectors only (limited regime), or none (IPPO). The communication-cost term in the reward prices each message.
- **Reward:** `−α·operational_carbon − β·energy_cost − γ·SLA_violations − δ·transfer_cost − ε·CVaR_α(SLA_violation_distribution) − ζ·communication_cost`, with weights ablated. CVaR at level α on the deadline-miss distribution implements risk-awareness under forecast error.

## 9.4 Evaluation

| Baseline | Purpose |
|---|---|
| Round Robin | sanity floor; proves the problem is non-trivial |
| Earliest Deadline First | classical SLA-aware baseline; ignores carbon |
| Carbon-aware greedy | places each job at the currently-greenest site with capacity; ignores uncertainty and future load |
| Centralized PPO | upper bound of learned control with full information |
| Independent PPO (IPPO) | decentralized, no communication |
| MAPPO | decentralized with limited communication (our primary) |
| **Uncertainty-aware MAPPO** | our contribution: consumes forecast bands + CVaR penalty |

**Metrics:** total operational carbon (kg CO₂eq), energy (kWh), SLA violation rate & p95 latency, transfer volume/cost, and **robustness**: performance degradation when forecast error is doubled, and per-region carbon-spread exploitation (how often jobs move toward low-CI regions). Ablations: uncertainty on/off; communication level; risk level α. Expected claims are bounded by the EuroSys 2024 shifting-limits paper — we will report savings relative to that envelope, not absolute hype.

---

# Chapter 10 — Final recommendation

**Recommended region: United Kingdom (Great Britain).**

**Exact dataset/API combination (all free, all verified):**

| Layer | Source | Access | License | Verified |
|---|---|---|---|---|
| Carbon intensity (national + 14 regions, 30-min, **forecast+actual**) | NESO Carbon Intensity API — `api.carbonintensity.org.uk` | Free, no key | CC BY 4.0 | Yes [V] |
| Generation mix cross-check | Elexon BMRS Insights API — `data.elexon.co.uk/bmrs/api/v1` (FUELHH/FUELINST) | Free, no key | BMRS terms | Yes [S] |
| Workload (LLM inference demand) | Azure LLM Inference Trace 2024 (`AzureLLMInferenceTrace_code_1week.csv`, 692 MB, 16.8M rows) | Free direct download | CC BY 4.0 | Yes [V] |
| Workload (GPU jobs, optional) | Alibaba cluster-trace-gpu-v2020 (707k jobs) | Free (OSS) | research clause; cite NSDI'22 | Yes [S] |
| Measured node power | NLR GenAI Workload Power Profiles (RAPL+NVML, 10 Hz), DOI 10.7799/3025227 | Free (DOE licence) | cite paper | Yes [S] |
| Power-model calibration | Harvard GPU power metrics (CC0); GPU-DVFS-Dataset | Free | CC0 / open | Yes [S] |
| PUE priors | Google DC efficiency pages (fleet 1.09 TTM 2025; per-campus tables) | Free | published | Yes [S] |
| Network latency | Azure inter-region RTT matrix (azurespeed / MS Learn) + cloudping.co; RIPE Atlas for fresh measurements | Free | published / MIT | Yes [S] |
| Transfer costs | AWS/Azure/GCP egress pricing pages | Free | published | Yes [S] |
| Simulator foundation | SustainCluster (HPE Labs), MIT | Free | MIT | Yes [V] |

**Site mapping [RECOMMENDATION]:** London → DNO region 13 (Azure UK South is documented as London-based); a second UK site → South Wales (region 7) or South East England (region 14); optionally North West England (region 3) and South Scotland (region 2) for renewable-rich contrast.

**The compromise, stated plainly:** the workload trace is geo-anonymous; assigning it to UK sites is a **disclosed modelling assumption**, consistent with current research practice (SustainCluster does the same with the Alibaba trace). No claim in the thesis may state that the traced requests were served from the UK. The carbon, power-curve, PUE and network layers are real and region-matched; the workload layer is real but region-agnostic. If the panel requires strict region-matching with zero assumptions, then **no public dataset today satisfies it**, and the project cannot be implemented as specified without either (a) this disclosed assumption, or (b) waiting for a geo-located public trace.

**Smallest scientifically defensible compromise (adopted):** UK carbon + measured power + real trace demand model + disclosed assumption + uncertainty measured from real forecast errors.

**Data-freezing plan (reproducibility):** archive all API pulls as dated JSON/CSV in `data-audit/downloads/` (already begun); pin dataset versions (Azure release tag `dataset-llm-2024`; SustainCluster v1.1; Zenodo DOIs); record fetch scripts and hashes.

---

## Appendix A — Deliverables map

| Deliverable | Location |
|---|---|
| This report (DOCX + Markdown) | `report/report.docx`, `report/report.md` |
| Dataset comparison spreadsheet | `deliverables/dataset-comparison.xlsx` (4 sheets) |
| Data audit folder (samples, scripts, analysis) | `data-audit/` |
| Source/reference list with URLs & DOIs | `report/sources.md` |
| Guide-ready executive summary | `report/executive-summary.md` |
| Figures | `report/figures/` (3 PNGs from verified data) |
| Research notes (raw survey evidence) | `research-notes/A–D*.md` |
