# Findings, Questions & Project Plan

**Project:** Uncertainty-Aware Decentralized Multi-Agent Reinforcement Learning for Carbon-Aware Workload Scheduling Across Geo-Distributed Data Centers
**Study type:** Real-world dataset feasibility study (B.Tech major project) → implementation plan


**Label key:** **[VERIFIED]** downloaded & inspected by us · **[VERIFIED-S]** official page/repo fetched by survey, samples where noted · **[DOCUMENTED]** official docs only · **[ASSUMPTION]** disclosed modelling assumption · **[INFERENCE]** our deduction, not the publisher's statement.

---

# Part 1 — Findings

## 1.1 The central finding

**No public workload trace on Earth is officially mapped to a real region.** Verified across 29 trace families. The strongest geographic signal any publisher ships is a *timezone hint* — and even that is disappearing over time.

| Trace | Strongest geographic signal | Status |
|---|---|---|
| Azure LLM Inference 2024 | "one geographical region" — unnamed, by design | **[VERIFIED]** (schema has no region field) |
| Alibaba GPU 2020 | UTC+8 "Asia/Shanghai" note — **a timezone hint for diurnal alignment only; no country named anywhere** | **[VERIFIED]** (README quoted verbatim) |
| Alibaba GPU 2026 (ASI) | salted-hash `cluster_id`/`server_id`, "not meant to be joined with other datasets", **no calendar dates, no timezone** | **[VERIFIED]** (schema.md quoted) |
| Alibaba v2026-maas | `site_id` + `cluster_id` anonymized (56 clusters) | **[VERIFIED-S]** |
| Qwen-Bailian | nothing — trace-relative, anonymous | **[VERIFIED-S]** |
| Google Borg 2019 | official cell→timezone table (a,c,d=America/New_York; b,f=America/Chicago; e=Europe/Helsinki; g=Asia/Singapore; h=Europe/Brussels) — country-level inference possible, **timezone ≠ grid region**, CPU-only | **[VERIFIED]** (spec PDF extracted) |
| Helios, Philly, Bitbrains, Mooncake, BurstGPT | pseudonyms / nothing / paper-level provenance | **[VERIFIED-S]** |

**Trend over time: LESS geography, not more** (Alibaba: UTC+8 hint 2020 → nothing 2023 → anonymized site IDs 2026). The strict requirement fails for every candidate region as of 4 Nov 2026, and the direction of travel is away from it.

## 1.2 Why the UK is the only complete region

The **NESO Carbon Intensity API** is the only source worldwide that ships **historical forecast-vs-actual carbon pairs out of the box**:

| Verified evidence | Value |
|---|---|
| Coverage | national + **14 DNO regions**, 30-min slots, since Sep 2017, free, no key, CC BY 4.0 |
| Jan 2025 national (actuals) | 1,489 slots; min 35 / mean 168.1 / max 293 gCO₂/kWh; zero gaps |
| **Forecast error (measured)** | **MAE 9.05 / RMSE 12.97 gCO₂/kWh** (1,463 slots with both forecast+actual = 98.3%) |
| Regional spread (15 Jan 2025, 12:00Z) | **19 (North East England) → 367 (South Wales)** = 348 gCO₂/kWh inside one country |
| London (region 13), Jan 2025 | min 22 / mean 185.3 / max 334 gCO₂/kWh |
| API quirks found | regional path is `/regional/intensity/{from}/{to}/regionid/{id}`; regional history has forecast+index but **no `actual`**; full-year single call → HTTP 400 (chunk weekly) |

Everywhere else (EIA-930, CAISO, Energy-Charts, Fingrid, OpenElectricity, Grid-India, Japan/Waseda): either no CO₂ forecast, no hourly CI, no API, or no regional depth. Full comparison: `deliverables/dataset-comparison.xlsx`.

## 1.3 Verified workload-layer numbers

| Dataset | Verified facts |
|---|---|
| **Azure LLM Inference Trace 2024** | 16,803,695 rows (full 692 MB file parsed); 7 days (2024-05-10→16); 0 nulls, 0 duplicates; ContextTokens p50 1,930 / mean 2,511 / p95 7,674 / max 7,743; GeneratedTokens p50 8 / mean 23 / p95 79 / max 5,000; arrivals 74→5,884 req/min (**80× burstiness**); CC BY 4.0 |
| **Alibaba GPU 2020** | 707,064 jobs (546,742 terminated / 108,893 failed / 48,591 running / 2,837 waiting); 1,261,050 tasks; `plan_gpu`, `gpu_type` (V100/A100-class, T4, MISC); per-instance sensor utilization; July–Aug 2020 (season documented); NSDI'22 |
| **Alibaba 2026 `job_execution_summary`** | 1.19 GB; `duration_hours`, `schedule_delay_sec`, `job_type_public` (training/online_inference/offline_inference), `model_type_public` (**genai**/rec/cv/embedding), `priority_class` (HP/LP) — ideal **validation-only** cross-check |
| **EIA-930 (US fallback)** | 266,398 hourly rows; free; but CO₂ must be computed from fuel mix and **no CO₂ forecast exists** |
| **NLR GenAI power profiles** (DOI 10.7799/3025227) | 10 Hz RAPL+NVML; CPU 100.8–355.5 W; 4-GPU array 289–2,851 W (Llama-3.1-70B); measured at Kestrel HPC, **Colorado, USA** (only geo-identified measured-power set) |

## 1.4 SustainCluster assessment (verified by code inspection)

- **MIT license**, NeurIPS 2025 D&B (OpenReview `AgTASkryb6`), HPE Labs.
- Implements: Gymnasium env, **centralized** top-level agent, defer-or-dispatch every **15 min**, physics-based per-DC model (IT+HVAC+water), transmission-aware routing (per-GB cost + empirical RTT), modular multi-objective rewards, SAC + RLlib PPO/APPO + rule baselines.
- Data: Alibaba GPU 2020 × Electricity Maps CI (incl. **GB folder 2021–2024**) × GridStatus prices × Open-Meteo.
- **Does NOT implement (our deltas):** decentralized agents · forecast uncertainty · risk measures (CVaR/DRO) · communication limits · native GB 14-region carbon.
- Its own future work names MARL extensions and "Incorporating Advanced Forecasting" — **our project is, almost verbatim, their future-work item**.

## 1.5 Literature gap (30 papers, 2024–2026, all DOIs resolved)

**No published work combines: decentralized limited-communication MARL + forecast uncertainty + region-matched real data + risk-aware deadlines.**

Nearest partials: SustainCluster (real data, centralized) · UAD/SIGENERGY 2024 (conformal uncertainty, no agents) · Jayanetti TPDS 2024 (MADRL, deterministic signals) · DRO-JCC 2026 (risk, single controller) · Green-DCC AAAI 2025 (hierarchical, no uncertainty). What the top venues actually use: Caspian = synthetic workloads; DynamoLLM/TAPAS = the same anonymized Azure trace, no grid signal; CarbonEdge = real CI + synthetic jobs. **Our data posture is at the strong end of the field, not the weak end.**

---

# Part 2 — Questions & answers 

Every question below was raised and answered during the study. The answers are evidence-backed.

**Q1. "Modelling assumption" — how can you apply another region's trace to UK carbon? How does it match?**
The trace is a **demand pattern** (when requests arrive, how big they are), not a physical record tied to a place. Carbon comes from where a job *runs*: energy (measured power curves × duration) × grid CI at the site (real UK data). The pipeline assigns trace jobs to UK sites; the "match" happens at the energy-calculation point, not at data origin. The claim defended is *relative*: all policies face identical demand, so the scheduler ranking is robust to the demand's origin. Only absolute kg-CO₂ numbers are assumption-dependent — and they are labelled as such.

**Q2. Doesn't "modelling" mean it's not real-world applicable? What do other papers use?**
Real-world applicability = findings transfer, not that data was captured at the deployment site. Verified practice: SustainCluster (NeurIPS 2025) probabilistically distributes the geo-anonymous Alibaba trace over 20+ regions; Caspian uses fully synthetic workloads; Jayanetti TPDS 2024 uses grid averages; DynamoLLM has no grid signal at all. Even Microsoft's own papers use the same anonymized Azure trace — they *have* the internal geo-located data and still cannot publish it. Our stack (real trace + 14-region real carbon + measured forecast errors + measured power) is **stronger than typical published work**.

**Q3. Even Qwen has no region info?**
Confirmed: Qwen-Bailian ships trace-relative timestamps, single anonymous cluster, no location fields at all.

**Q4. Does the Alibaba 2020 trace even mention a country?**
**No.** The README names no country, region or site. It gives a UTC+8 timezone hint so diurnal (time-of-day/day-of-week) analysis works, with explicitly faked dates. Reading it as "China" is our inference, not their statement. (We corrected our own report on this — the audit standard applies to our own claims too.)

**Q5. Why won't companies share workload data — it's just workload, not customer data?**
Workload data is quasi-identifying (timestamps + sizes + hashed user IDs re-identify customers — the Netflix Prize lesson), business-sensitive (requests/region ≈ revenue/region; `gpu_type` = hardware inventory), and legally constrained (PIPL/GDPR). Companies *do* share — but the compromise is always: hash identities, fake dates, shrink the window, **cut geography first**. Google's timezone table is the ceiling; Alibaba 2026 went backwards (anonymized site IDs, no timezone).

**Q6. What does Google's cell→timezone table mean?**
Google publishes, per anonymized cell (a–h), its timezone (America/New_York, America/Chicago, Europe/Helsinki, Asia/Singapore, Europe/Brussels). Country-level inference is possible for several cells — the strongest official signal anywhere — but a timezone is a *clock*, not a *grid*: America/New_York time spans multiple US power grids (PJM, NYISO, ISO-NE). Timezone ≠ carbon zone, so even Google's best signal cannot support strict carbon matching.

**Q7. Why Alibaba 2020 and not 2026?**
(1) 2020 is fully downloaded and verified; 2026 sample fetch timed out (unverified). (2) 2026 `pod_hourly` is 352 GB; 2020 is ~350 MB. (3) 2026 is hourly aggregates — coarser than our 15-min decision step. (4) No SustainCluster loader exists for 2026. (5) **Decisive:** 2026 has no calendar dates and no timezone → its diurnal phase cannot be anchored to a real clock, so workload time cannot be aligned with grid time — fatal for *carbon-aware* scheduling. 2020 documents both anchors (UTC+8 phase + July–Aug season).

**Q8. The 2026 trace is hourly — why can't we find where the wave sits on the 24-hour clock?**
"Hourly" ≠ "anchored." `hour=14` could be local time (of an unknown city), UTC, or hours-since-trace-start — the schema doesn't say. In principle the phase could be inferred from the wave shape, but the fleet spans 56 clusters: if labels are per-cluster local time, the aggregate wave is a smeared mixture with no recoverable phase; if UTC, we'd have to assume it. Either way it stacks undocumented guesses on top of the region assumption. 2020's documented anchor beats 2026's inferable one.

**Q9. What is a diurnal pattern and why does it matter?**
A rhythm repeating every ~24 h. Workload arrivals peak in working hours; grid carbon often bottoms overnight (wind + low demand) and peaks in the evening. The scheduler's opportunity **is** the misalignment of these two waves, across both time and regions. No diurnal alignment → no defensible time-shifting results.

**Q10. Can we do the project with only the Alibaba dataset?**
Only-Alibaba-as-workload: yes (SustainCluster does exactly that). Only-one-dataset-total: impossible — no dataset contains workload + power + carbon together. Minimum chain: workload (Alibaba 2020 or Azure) + carbon (NESO) + power model (SustainCluster's physics code — not a dataset). Leanest stack: Alibaba 2020 + SustainCluster's bundled GB carbon. **But dropping NESO drops the measured-uncertainty pillar of the title** — the one thing nobody else has.

---

# Part 3 — What we can get publicly from the UK

All free, all license-clean, all verified accessible:

| # | Layer | Source | Access | License | Status |
|---|---|---|---|---|---|
| 1 | Carbon intensity, national + 14 regions, 30-min, **forecast+actual** | NESO Carbon Intensity API (`api.carbonintensity.org.uk`) | free, no key | CC BY 4.0 | **[VERIFIED]** — downloaded |
| 2 | Generation mix (cross-check) | Elexon BMRS (`data.elexon.co.uk/bmrs/api/v1`, FUELHH/FUELINST) | free, no key | BMRS terms | **[VERIFIED-S]** |
| 3 | LLM workload demand | Azure LLM Inference Trace 2024 (692 MB, 16.8M req) | free direct download | CC BY 4.0 | **[VERIFIED]** — downloaded |
| 4 | GPU job shapes | Alibaba GPU 2020 (707k jobs) | free (OSS) | research clause, cite NSDI'22 | **[VERIFIED]** — downloaded |
| 5 | Modern-fleet validation | Alibaba 2026 `job_execution_summary` (1.19 GB) | free (OSS) | ⚠️ verify license | **[VERIFIED-S]** (schema) |
| 6 | Measured node power | NLR GenAI Power Profiles (10 Hz RAPL+NVML) | free (DOE) | cite paper | **[VERIFIED-S]** |
| 7 | Power-model calibration | Harvard GPU metrics (CC0) + GPU-DVFS-Dataset | free | CC0/open | **[VERIFIED-S]** |
| 8 | PUE priors | Google DC efficiency pages (fleet 1.09 TTM 2025) | free | published | **[VERIFIED-S]** |
| 9 | Inter-site latency | Azure RTT matrix + cloudping.co (UK South included) | free | published/MIT | **[VERIFIED-S]** |
| 10 | Transfer costs | AWS/Azure/GCP egress pricing | free | published | **[VERIFIED-S]** |
| 11 | Simulator foundation | SustainCluster (HPE Labs) | free | **MIT** | **[VERIFIED]** — cloned & inspected |

**Site mapping [RECOMMENDATION]:** London → DNO region 13 (Azure UK South is documented as London-based); South Wales (7) or South East England (14) as second site; optionally North West England (3) and South Scotland (2) for renewable-rich contrast.

---

# Part 4 — What we can do and test

## 4.1 Build (from the verified data)

1. **Uncertainty layer (the differentiator).** Calibrate conformal/quantile forecast bands per horizon from the real NESO forecast-vs-actual pairs (anchor: MAE 9.05 / RMSE 12.97). *Test: empirical coverage of the bands on held-out months — target ≈90% coverage at nominal level.*
2. **Demand model.** Azure trace → arrival process (15-min aggregation) + token-size distributions; seasonal-naive + gradient-boosted arrival forecaster. *Test: forecast skill vs seasonal-naive baseline; reproduce the 80× burstiness in replay.*
3. **Job mix.** Azure requests + Alibaba 2020 GPU-job shapes; deadlines by disclosed policy (e.g., p95 service time × slack). *Test: duration/delay distributions vs Alibaba 2026 `job_execution_summary` (modern-fleet cross-check).*
4. **Power & energy.** NLR idle→peak curves per GPU (filter counter-rollover artifact) → energy = ∫P dt × PUE (Google priors). *Test: per-request energy sanity range vs DynamoLLM/TAPAS reported magnitudes.*
5. **Simulator.** SustainCluster extended: NESO regional CI per site (replacing single-zone Electricity Maps), forecast bands in observations, 3–5 UK sites. *Test: reproduce SustainCluster baseline behavior before modifications; verify carbon accounting against GB actuals.*

## 4.2 Experiment matrix

| Baseline | Purpose |
|---|---|
| Round Robin | sanity floor |
| Earliest Deadline First | classical SLA baseline, carbon-blind |
| Carbon-greedy | places at greenest site now; ignores uncertainty & future load |
| Centralized PPO | upper bound (SustainCluster's own agent) |
| IPPO | decentralized, no communication |
| MAPPO (limited comm) | our primary |
| **Uncertainty-aware MAPPO + CVaR** | **the contribution** |

**Ablations:** uncertainty bands on/off · communication level (full / summaries / none) · CVaR level α.
**Robustness test:** double the forecast error → measure degradation of each policy (uncertainty-aware should degrade least).
**Regional-exploitation test:** how often jobs move toward low-CI regions; savings vs the 348 gCO₂/kWh spread.

## 4.3 Metrics

Total operational carbon (kg CO₂eq) · energy (kWh) · SLA violation rate & p95 latency · transfer volume/cost · robustness curves · band coverage.

## 4.4 What we can claim vs. cannot claim

| ✅ CAN claim | ❌ CANNOT claim |
|---|---|
| "Uncertainty-aware decentralized scheduling reduces carbon X% vs baselines under identical real demand" | "The traced requests were served from the UK" |
| "Uncertainty comes from measured NESO forecast errors, not simulation" | Any absolute national carbon figure as a measurement |
| "Regional spread of 348 gCO₂/kWh verified in real data" | That the workload mix represents UK demand exactly |
| Savings reported **within the EuroSys 2024 shifting-limits envelope** | Savings beyond what spatiotemporal-shifting bounds allow |

**Signal choice (decide early, defend):** average GB CI (NESO), disclosed; cite Green Mirage / avg-vs-marginal (e-Energy 2024) as the known caveat.

---

# Part 5 — Proposed plan

**Step 0 (this week): guide sign-off.** Present `report/executive-summary.md` + the disclosed-assumption framing *before* coding. Get explicit approval.

| Phase | Weeks | Work | Exit test |
|---|---|---|---|
| 1. Data freeze | 1–4 | NESO 14-region long-window pulls (chunked weekly); conformal bands; Azure demand model; NLR curves | Bands hit target coverage on held-out month |
| 2. Simulator | 5–10 | Run SustainCluster as-is → swap NESO regional carbon → 3–5 UK sites → bands in observations | Baseline reproduced; carbon accounting matches GB actuals |
| 3. Agents | 11–18 | RR/EDF/carbon-greedy → centralized PPO → IPPO → MAPPO → +CVaR | Each level beats or matches the previous before adding the next |
| 4. Evaluate & write | 19–24 | Ablations, robustness, thesis | Claims inside EuroSys-2024 envelope; assumptions table complete |

**Three rules:**
1. **The measured uncertainty is the moat** — every design decision protects it.
2. **Relative claims only** — comparisons under identical demand; absolutes labelled as illustrative.
3. **Disclose early** — the region assumption is in the abstract, not buried in a footnote.

**Risks & mitigations:**

| Risk | Mitigation |
|---|---|
| Panel rejects the region assumption | It's the field-wide practice (SustainCluster, NeurIPS 2025); documented in Ch. 7 of the report; no alternative exists |
| NESO regional `actual` missing | Use national actuals scaled by regional forecast ratio; disclose |
| MAPPO unstable | Fall back to IPPO (still novel with uncertainty+CVaR); centralized PPO is the safety net |
| 2026 license unclear | Validation role only; replaceable by Bitbrains/utilization checks |
| Savings look small | That's the honest envelope (EuroSys 2024); robustness-under-uncertainty is the value claim |

---

# Part 6 — Deliverables map

| Deliverable | Location |
|---|---|
| Full 10-chapter report (DOCX + PDF + MD) | `report/report.docx`, `report/report.pdf`, `report/report.md` |
| Executive summary (guide-ready) | `report/executive-summary.md` |
| Source list, 79 entries with DOIs | `report/sources.md` |
| Dataset comparison spreadsheet (4 sheets) | `deliverables/dataset-comparison.xlsx` |
| Data audit (702 MB raw, scripts, verification tables) | `data-audit/` |
| Research notes A–D (raw survey evidence) | `research-notes/` |
| Figures (3, from verified data) | `report/figures/` |
| **This document** | `findings-and-plan.md` |
