# Data Audit — Verification Table & Findings

**Study:** Feasibility of real-world, geographically consistent datasets for
"Uncertainty-Aware Decentralized MARL for Carbon-Aware Workload Scheduling Across Geo-Distributed Data Centers".
**Audit date:** 2026-11-04. All "inspected" rows below were downloaded and read programmatically during this audit.
Raw samples: `data-audit/downloads/`. Fetch/inspect scripts: `data-audit/scripts/`.

Legend: **[V]** = directly inspected by us this session · **[S]** = verified by a survey agent this session (official pages/READMEs fetched; some with in-hand sample downloads) · **[D]** = documented only (not downloaded; treat as unverified).

---

## A. Sources directly downloaded and inspected in this audit [V]

### A1. UK Carbon Intensity API (NESO) — api.carbonintensity.org.uk

| Test | Finding |
|---|---|
| Download successful | **Yes** (5 successful API calls; 2 earlier calls returned HTTP 400 due to wrong path/window, corrected per official docs) |
| Actual records inspected | 1-day national: 49 half-hour slots · January 2025 national: 1,493 slots (1,489 unique after de-duplicating chunk overlaps) · London (regionid 13) January 2025: 1,476 slots · all-regions snapshot: 18 region entries |
| File format | JSON over HTTPS (also XML supported per docs) |
| Fields identified | `from`, `to`, `intensity.forecast`, `intensity.actual`, `intensity.index`; regional adds `generationmix[]` (biomass, coal, imports, gas, nuclear, other, hydro, wind, solar) per region per slot |
| Time range | Historical from 2017-09-26 (per homepage); verified working window: Jan 2025. Single-call window cap exists (full-year regional call → HTTP 400); 30-day national call succeeded |
| Region identified | **Yes** — 14 DNO regions with names (regionid 13 = London; 1 = North Scotland … 14 = South East England) + 4 aggregate regions (England/Scotland/Wales/GB) |
| Missing values | National Jan-2025: 1,463/1,489 unique slots have **both** forecast and actual (98.3%); regional intensity provides forecast+index only (no `actual` field) |
| Duplicate records | 4 boundary duplicates from chunked download (removed in analysis); no intra-call duplicates |
| Units confirmed | gCO₂/kWh (intensity); % (generation mix) — confirmed against official methodology page |
| Geographical match | Yes — same source provides national + regional; matches GB grid (Elexon/NESO footprint) |
| Suitable for project | **Yes — conditional on disclosed workload-region assumption (see report Ch. 7/10)** |
| Statistics (Jan 2025 national, actual) | min 35 · mean 168.1 · max 293 gCO₂/kWh |
| Forecast-vs-actual error (Jan 2025 national) | MAE 9.05 · RMSE 12.97 gCO₂/kWh (n=1,467 row-pairs incl. 4 dupes; 1,463 unique) |
| Regional spread (2025-01-15 12:00–12:30Z) | 19 (North East England) → 367 (South Wales) gCO₂/kWh — **span 348 gCO₂/kWh in one half-hour** |
| License / access | CC BY 4.0; free, **no API key**; terms at terms.carbonintensity.org.uk |
| Files | `uk_national_2025-01-01_to_2025-01-02.json`, `uk_national_2025-01_full_month.json`, `uk_regional_all_2025-01-01_to_2025-01-02.json`, `uk_region13_london_2025-01-01_to_2025-01-08.json`, `uk_region13_london_2025-01_full_month.json`, `uk_generation_2025-01-01_to_2025-01-02.json` |

Sample rows (national, 2025-01-01, verbatim):
```json
{"from":"2025-01-01T00:00Z","to":"2025-01-01T00:30Z","intensity":{"forecast":62,"actual":68,"index":"low"}}
{"from":"2025-01-01T00:30Z","to":"2025-01-01T01:00Z","intensity":{"forecast":68,"actual":66,"index":"low"}}
```

### A2. Azure LLM Inference Trace 2024 (Microsoft, AzurePublicDataset)

| Test | Finding |
|---|---|
| Download successful | **Yes** — GitHub release asset, 691,989,454 bytes |
| Actual records inspected | **16,803,695 rows** (full file parsed with pandas; not a sample) |
| File format | CSV |
| Fields identified | `TIMESTAMP` (µs precision), `ContextTokens`, `GeneratedTokens` — schema matches official dataset page exactly |
| Time range | 2024-05-10 00:00:00.009930+00:00 → 2024-05-16 23:59:59.929501+00:00 (7 days) |
| Region identified | **No** — no region/cluster/GPU field exists in the schema; official docs name no location |
| Missing values | 0 nulls in all three columns |
| Duplicate records | 0 duplicate rows |
| Units confirmed | Token counts (integers); timestamps ISO with tz |
| Geographical match | N/A — geo-anonymous by design (customer privacy) |
| Suitable for project | **Yes, as a real production LLM demand model, with disclosed region assumption** |
| Statistics | ContextTokens: p50 1,930 · mean 2,511 · p95 7,674 · max 7,743. GeneratedTokens: p50 8 · mean 23 · p95 79 · max 5,000. Requests/min: min 74 · p50 998 · mean 1,667 · p95 4,625 · max 5,884. Requests/hour: 9,086 → 301,105 |
| License / access | CC-BY 4.0 (AzurePublicDataset LICENSE); free direct download; cite DynamoLLM (HPCA 2025) |
| Files | `AzureLLMInferenceTrace_code_1week.csv` (692 MB) |

Sample rows (verbatim, first 3):
```
TIMESTAMP,ContextTokens,GeneratedTokens
2024-05-10 00:00:00.009930+00:00,2162,5
2024-05-10 00:00:00.017335+00:00,2399,6
```

### A3. EIA-930 Hourly Grid Monitor bulk CSV (US EIA)

| Test | Finding |
|---|---|
| Download successful | **Yes** — 41,742,812 bytes |
| Actual records inspected | **266,398 rows** (Jan–Jun 2024, all BAs, hourly) |
| File format | CSV (quoted headers) |
| Fields identified | Balancing Authority, Data Date, Hour Number, Local/UTC time, Demand Forecast (MW), Demand (MW), Net Generation (MW), Total Interchange (MW), imputed/adjusted variants, net generation by fuel (coal, natural gas, nuclear, petroleum, hydro, solar, wind, other) |
| Time range | 2024-01-01 → 2024-06-30 (file covers six months; archive list runs 2015-H2 → 2026-H2) |
| Region identified | **Yes** — per Balancing Authority (CISO, ERCT, PJM, NEWE, …) |
| Missing values | Present as empty fields (imputed/adjusted columns exist precisely to flag them) |
| Duplicate records | Not detected in header scan; full dedup pass deferred |
| Units confirmed | MW; CO₂ available separately in per-BA Excel files (from 2018-07) |
| Geographical match | US grid regions (BAs) — matches CAISO/ERCOT/PJM footprint |
| Suitable for project | **Yes** — US candidate backbone; carbon intensity must be computed from fuel mix (+ eGRID factors); no CO₂ forecast |
| License / access | Free, no key (bulk files); API v2 requires free key |
| Files | `eia930_balance_2024_janjun_sample.csv` |

---

## B. Sources verified by survey agents with in-hand downloads [S]

| Source | What was actually inspected | Key findings |
|---|---|---|
| **Alibaba cluster-trace-gpu-v2020** | Full `pai_job_table.csv` (90 MB), `pai_task_table.csv` (113 MB), `pai_machine_spec.csv` downloaded & parsed | **707,064 jobs / 1,261,050 tasks**; GPU fields (`plan_gpu`, `gpu_type` incl. V100/A100-class); README gives a UTC+8 ("Asia/Shanghai") desensitization note — **timezone hint for diurnal alignment only; no country/region/site named anywhere** |
| **Bitbrains GWA-T-12 (fastStorage)** | 128 MB ZIP downloaded & unzipped; 8 VM files censused | 1,250 VMs × 8,640 rows (30 days @ 5-min); 11 columns (CPU MHz/%, memory, disk, network); timestamps 2013-08-12→09-11; header says "[ms]" but values are epoch **seconds** (doc/file mismatch flagged); geography = Netherlands via SPEC CCGrid'15 provenance only |
| **AcmeTrace (KaLOs)** | `trace_kalos.csv` 62,413 rows sampled; LICENSE.txt read | CC-BY-4.0; Mar–Aug 2023; GPU job fields; **SeReN trace advertised in README but missing from repo tree**; no location mapping |
| **Azure VM traces V1/V2** | vmtable + cpu_readings headers sampled | CC-BY-4.0; "one geographical region" — officially **unnamed**; no GPU |
| **NLR Generative AI Workload Power Profiles** | 1,021 MB zip downloaded; raw RAPL + NVML logs parsed | **504,570 RAPL rows @ ≈10 Hz** (14 h, Llama-3.1-70B inference); CPU 100.8/248.3/355.5 W (min/mean/max); GPU array 289/2,378/2,851 W; measured on Kestrel HPC, **Golden, Colorado, USA** (geographically identifiable); DOI 10.7799/3025227 |
| **Harvard Dataverse GPU Power & Performance** | PowerDatasets.zip (0.4 MB) downloaded; 4 CSVs parsed | 14,054 kernel-level rows with Power (W) across K80/Tesla/Ampere/AdaLovelace; **CC0**; aggregates, no time series |
| **GPU-DVFS-Dataset** | 3 CSVs downloaded | V100, 33 workloads × 13 frequencies, 46.5–242.5 W averages; DVFS-knob calibration data |
| **Elexon BMRS Insights API** | Live FUELHH + FUELINST calls | Free, no key; half-hourly GB generation by fuel; no CO₂ (compute ourselves) |
| **CAISO Today's Outlook** | Live `/outlook/current/co2.csv`, `/outlook/history/{YYYYMMDD}/co2.csv` + `fuelsource.csv` for 2019/2020 dates | Free, keyless; 5-min CO₂ tonnes by fuel today/yesterday; **day-level history back to ≥2019** (2017/2018 → 404); no CO₂ forecast |
| **Energy-Charts (Fraunhofer ISE, DE)** | Live `/v2/public_power` + `/v2/public_power_forecast` | Free, no key; 15-min generation actuals **and forecasts**; no CO₂ endpoint (apply own factors) |
| **OpenElectricity/OpenNEM (AU)** | Live v4 emissions metric (NEM/NSW1) | Free, keyless (today); per-state emissions (t) + fuel-tech energy; no CO₂ forecast |
| **Fingrid (FI)** | `/api/datasets` → 401 without key (confirmed key required); rate limits from official docs | Free key after registration+license approval; **direct emission-factor datasets 265/266/396**; 10k req/24h |
| **EIA API v2** | Live call without key → 403 `API_KEY_MISSING` | Confirms key required for API (bulk CSVs remain keyless) |
| **Google region-carbon-info** | GitHub CSVs 2019–2025 parsed | Per-Google-cloud-region annual CFE % + grid gCO₂eq/kWh (e.g. 2025: 47 regions) |
| **Ireland CSO MEC02** | CSV endpoint fetched | Quarterly data-centre electricity GWh since 2015Q1 (132 rows) — national aggregate |
| **Azure inter-region RTT matrix** | azurespeed 53-region table fetched | Microsoft-published RTTs (e.g. West US 2→West Europe 142 ms) |

## C. Documented but not downloaded [D] (treat as unverified)

- Electricity Maps portal/API — **paid** (€6,000/yr per country; 14-day free trial) — verified from pricing page.
- WattTime — free Basic tier limited to CAISO_NORTH + CO₂ percentile elsewhere; research access by application.
- ENTSO-E Transparency Platform — free token after registration; 400 req/min; **no CO₂ values** (compute from generation mix).
- Grid-India (POSOCO) daily/VRE reports + CEA CO₂ Baseline Database v20/v21 — free downloads, daily/annual granularity, no hourly CI.
- Japan — no official hourly CI; **Zenodo 18396311** (Waseda, 2026-01-28, CC-BY-4.0): hourly CI for 9 TSO areas, FY2024 only.
- EU EED datacentre reporting database — aggregate dashboard only; per-facility data not openly downloadable.
- Meta/Tencent scheduling traces — **not found** (verified by exhaustive search).

## D. Failed downloads / dead ends (exact)

| Target | Result |
|---|---|
| `gwa.ewi.tudelft.nl` | DNS failure from sandbox → used `atlarge-research.com` mirror |
| `github.com/InternLM/AcmeTrace` `trace_seren.csv` | Advertised in README, **absent from git tree** |
| Meta hosted/fleet trace | Not found (3 search rounds + org page) |
| Tencent scheduling trace | Not found |
| `AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar` | Downloaded (18,444,269 B) but no rar tool in sandbox → schema from official md only |
| Alibaba v2026 `app_metrics.csv.zip` | OSS fetch timed out → sizes from README only |
| UK CI API full-year regional single call | HTTP 400 (window cap) — chunked weekly downloads used instead |
