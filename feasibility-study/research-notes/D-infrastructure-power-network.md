# D — Data-center infrastructure evidence: measured power, PUE/energy, inter-DC network
Research date: 2026-11-04 · For: B.Tech major project feasibility study on carbon-aware geo-distributed data-center scheduling
Method note: every claim below was checked live unless marked otherwise. Items marked **[VERIFIED ON DISK]** were downloaded to `/tmp/dl/` and inspected with Python (row counts and min/mean/max are computed from the actual files, not quoted).

---

## (A) Measured GPU / server power telemetry — 5 best candidates

### A1. Dataset of Generative AI Workload Power Profiles (NLR / ex-NREL) — ★ best fit, **[VERIFIED ON DISK]**
- Publisher: National Laboratory of the Rockies (US DOE national lab; NLR Data Catalog). Fully **geographically identifiable**: measured on the Kestrel HPC system at NLR, Golden, Colorado, USA.
- DOI / paper: DOI 10.7799/3025227 · NLR/OT-2C00-99122 · arXiv:2604.07345 (Vercellino et al., "Measurement of Generative AI Workload Power Profiles for Whole-Facility Data Center Infrastructure Planning", 2026). Contact: gustavo.campos@nlr.gov.
- Dates: catalog entry 2026-01-30, updated 2026-07-17; measurements **2025-09 → 2026** (the raw log we inspected starts `2025-09-18 16:22:44`).
- Where: https://data.nlr.gov/submissions/312 · download https://data.nlr.gov/system/files/312/1775845072-dataset.zip (1,021 MB zip, 2.89 GB uncompressed, 3,191 files).
- Contents: `00_raw_datasets/` — **WattAMeter** raw logs per node for 5 workloads: `inference_offline_llama3_70b`, `inference_online_finite_llama3_70b`, `inference_online_rate_llama3_70b`, `training_llama2_70b_lora`, `training_stable_diffusion`. Per-node files: `rapl_wattameter_<hostname>.log` (CPU sockets, RAPL: µJ counters + W per socket + per-core) and `nvml_wattameter_<hostname>.log` (4 GPUs per node: mW + °C per GPU). `01_aggregated_datasets/` resampled to 0.1/0.2 s; `03_whole-facility_profiles/` — *simulated* facility profiles (DIPLOEE, 1MW/283 nodes) — synthetic, usable as ground-truth-like demand curves for a scheduler sim.
- License: "View License: (/node/312/license)" (DOE work; cite the paper).
- What I actually inspected (`inference_offline_llama3_70b`, node `x3115c0s33b0n0`, Llama-3.1-70B-Instruct across 4 GPUs):
  - RAPL log: **504,570 rows**; columns `timestamp  reading-time[ns]  cpu-0[uJ] cpu-0-core[uJ] cpu-1[uJ] cpu-1-core[uJ]  cpu-0[W] cpu-0-core[W] cpu-1[W] cpu-1-core[W]`; span 2025-09-18 16:22:44 → 2025-09-19 06:24:51 (≈14.0 h) ⇒ **≈10 Hz**. CPU power (both sockets, excluding 192 rollover-artifact rows): **min 100.8 W, mean 248.3 W, median 248.5 W, max 355.5 W**.
  - NVML log: **504,711 rows**; columns `timestamp  reading-time[ns]  gpu-0[mW] … gpu-3[mW]  gpu-0[C] … gpu-3[C]`; GPU array total: **min 289 W, mean 2,378 W, median 2,514 W, max 2,851 W** (∼713 W/GPU peak).
  - Caveat found by inspection: a few dozen cpu-0[W] readings carry a counter-rollover artifact (~6.55×10¹⁰ "W"); filter |W|>1000.
- Verdict: REAL timestamped RAPL+NVML power telemetry in the exact format hinted ("RAPL/RPM" style); obvious anchor dataset for the project's per-node power model.

### A2. amodo current corpus — NVIDIA H200 NVL (Zenodo) — real but 41 GB
- Zenodo record 23521636, DOI 10.5281/zenodo.23521636, v1.0.0, published **2026-10-21**, author Tom Kimpson, CC-BY-4.0.
- Content: 415 captures / 26.8 h (2026-09-17 → 25), oscilloscope AC current of one H200 NVL's PCIe aux power (Rogowski probe, 199,808 samples/s), plus a separate **`nvml_power_w`** telemetry channel on the host clock; 1,724 labelled step events. Captures 1 s → 4 h.
- Honest limitation (stated in the record itself): the Rogowski coil kills DC — **no power/energy is derivable from the current channel**; only the NVML channel carries watts. Single GPU, single box; no explicit geographic identifier.
- Files: `dataset.tar` (1.1 MB index) + `results-*.tar` parts (≈65 GB total). Not student-friendly to download fully; README/EXTRACT confirm structure. Download: https://zenodo.org/api/records/23521636/files/…
- Verdict: excellent *supplementary* evidence (events vs NVML power); too heavy for full download.

### A3. Watt Counts (LLM inference energy, 14M+ NVML samples) — pending public release
- Paper: arXiv:2604.09048 (Aug 2026) — F. Argerich (UPM) & J. Fürst (ZHAW), "Watt Counts: Energy-Aware Benchmark for Sustainable LLM Inference on Heterogeneous GPU Architectures", cited 14×.
- Content per paper: **14M+ power-draw samples @ 10 Hz NVML**, 5,000+ experiments, 50 LLMs × 10 GPUs spanning 5 NVIDIA architectures (V100 SXM2, T4, A100 SXM4, RTX 3090/A30, RTX 4090/L40S/L4, H100 NVL, H200 NVL), batch + server (Poisson) scenarios, plus CPU/DRAM RAPL validation runs (RTX 4090 bare-metal). Energy-per-token and mean-power metrics, TTFT/throughput included.
- Availability: author-stated MIT-licensed GitHub release "upon acceptance"; as of 2026-11-04 **not found on GitHub/Hugging Face by search** (preprint supplementary zip is the fallback). VERDICT: strong future dataset; do not plan the project around it yet.
- Companion datasets mapped in its Table 1: "LLM Energy Consumption Dataset" (3 GPUs, 6 LLMs, per-run energy), "AI Energy Score" (121 model results), ML.ENERGY (HF: `ml-energy/benchmark-v3`), MLPerf Power (system-level aggregate energy only, no GPU-level traces).

### A4. GPU Power and Performance Metrics for Multiple NVIDIA Architectures (Harvard Dataverse) — **[VERIFIED ON DISK]**
- Publisher: Harvard Dataverse, DOI 10.7910/DVN/RNGJFI, published **2025-09-25**, license **CC0 1.0** (public domain; NLM Dataset Catalog record 0000109190).
- Download: https://dataverse.harvard.edu/api/access/datafile/12100366 → `PowerDatasets.zip` (0.4 MB) → 4 CSVs: `all_merge_df_K80/Tesla/Ampere/AdaLovelace.csv` (one NVIDIA generation each).
- Schema (verified): `KernelName, GridSize, BlockSize, Comp_inst_kernel, avg_comp_lat, glob_inst_kernel, avg_glob_lat, avg_shar_lat, block_size, misc_inst_kernel, branch, glob_load_sm, glob_store_sm, inst_issue_cycles, cache_penalty, Power, Time, Regs` — one row per kernel measurement with **Power (W)** and Time.
- Verified stats: **K80: 3,671 rows, Power min 26 / mean 85.8 / max 143 W · Tesla: 4,028 rows, 46/102.4/263 W · Ampere: 3,988 rows, 10/56.3/137 W · AdaLovelace: 3,367 rows, 3/25.8/80 W** (total 14,054 rows).
- Verdict: real measured GPU power, but **kernel-level aggregates** (no time series, no timestamps, no site info). Good for power model calibration, not for scheduling traces.

### A5. GPU-DVFS-Dataset (V100 frequency-scaling) — **[VERIFIED ON DISK]**
- GitHub https://github.com/zyjopensource/GPU-DVFS-Dataset (small CSVs: `dataset_power.csv`, `dataset_performance.csv`, `dataset_efficiency.csv`). Companion paper: "Improving GPU Energy Efficiency through an Application-transparent Frequency Scaling Policy with Performance Assurance".
- Verified: 33 workloads (3MM, FDTD, Schmidt, BiCG, Walsh, BScholes, CFD, …) × 13 core frequencies (757→1530 MHz) on **V100 (TDP 300 W)**; `dataset_power.csv` = 34 lines (header + 33 rows), values are **average GPU power in W across ≥5 runs**, e.g. 3MM: 91.0 W @757 MHz → 205.8 W @1530 MHz; range observed 46.5–242.5 W.
- Verdict: real measured power but **per-configuration averages, not time series**; ideal for the DVFS/power-cap knob of a carbon-aware scheduler simulation.

### Honorable mentions / supporting evidence (not top-5)
- **AzurePublicDataset — AzureGreenSKUFramework2023** (paper "Designing Cloud Servers for Lower Carbon", ISCA'24): SKU-level server power/carbon characteristics from Azure (not time series) — https://github.com/Azure/AzurePublicDataset/blob/master/AzureGreenSKUFramework2023.md
- **Azure LLM Inference Traces 2024** (DynamoLLM, HPCA'25): CC-BY, 1-week May 2024, CSVs `TIMESTAMP, ContextTokens, GeneratedTokens` only — **no power fields** (schema verified from the dataset md). Useful as *workload* input, not power telemetry.
- **WEDISTRICT Luleå demosite** (Zenodo 14163174, CC-BY): micro data-center server/fuel-cell/utility meter data (`ServerData_v2.xlsx` etc.) — real facility time series, EU demo site; niche.
- **Green500 / TOP500 lists**: measured rank energy efficiency (MFLOPS/W) — static per-run values, no traces.
- Uptime Institute / SPECpower / MLCommons result tables: aggregate only or paid; noted as such.

---

## (B) Data-center PUE / facility electricity evidence

### B1. Google — strongest public picture
- **Hourly CFE % + grid carbon intensity per cloud region, machine-readable, one CSV per year, CC-BY-style open repo [VERIFIED]**: https://github.com/GoogleCloudPlatform/region-carbon-info — `data/yearly/2019.csv … 2025.csv`. Header verified: `Google Cloud Region,Location,Google CFE,Grid carbon intensity (gCO2eq / kWh)`; 2025 file has 47 region rows (e.g. `africa-south1,Johannesburg,0.15,641.42`). Same data rendered at https://cloud.google.com/sustainability/region-carbon. Caveat: one **annual-average** CFE % per region per year (not the hourly time series Google's internal 24/7 CFE heatmaps use); still the single most actionable hyperscaler dataset for region selection.
- **PUE disclosures [VERIFIED page]**: https://www.google.com/about/datacenters/efficiency/ — 2025 fleet-wide TTM PUE **1.09** (quarterly 1.08–1.11) and **per-campus quarterly + TTM PUE tables back to 2008** by named facility (Dublin 1.08, Eemshaven 1.07, Council Bluffs 1.07–1.11, Singapore 1.12, etc.). HTML tables (scrapable), no CSV.

### B2. Microsoft
- Per-region **sustainability fact sheets** (PUE, renewable %, water %) at https://datacenters.microsoft.com/globe/ — JS app; alternate link https://datacenters.microsoft.com/en-us/globe/ (fact sheets confirmed via the cloud-carbon-footprint discussion https://github.com/cloud-carbon-footprint/cloud-carbon-footprint/discussions/1299, which also carries regional PUE/carbon coefficients).
- **No public hourly Azure region carbon-intensity/electricity dataset found.** Azure "Carbon Optimization" dashboards/exports are tenant-scoped (https://learn.microsoft.com/en-us/azure/carbon-optimization/). The open *cloud-carbon-footprint* project publishes grid-intensity coefficients and Azure regional PUE estimates as CSVs — a reasonable stand-in.
- AzurePublicDataset gives workload traces but **zero facility-power data** (verified schema above).
- Verdict: reported (fact sheets + ESG reports), not bulk-downloadable time series.

### B3. Meta
- https://datacenters.atmeta.com/sustainability/ and annual ESG reports: aggregate renewable matching and water claims; no per-facility electricity time series. A pending US FOI case (Aug 2026) ended with Meta keeping data-center details private (Louisiana PSC) — evidence that facility-level data is *deliberately* not public. Academic estimate source: de Vries-Gao et al., "The carbon and water footprints of data centers…" (PMC12827721) + AGU AGU2025AV002140 for disclosure-gap framing.

### B4. EU EED data-centre reporting database — biggest emerging source
- Reporting obligation under Directive (EU) 2023/1791 + **Delegated Regulation (EU) 2024/1364** (PUE, energy consumption by source, water, waste heat, *annual data traffic in/out*). European database: https://policy-reporting-platform.ec.europa.eu/Reporting/web/screen/home:registration
- **Aggregate dashboard exists [VERIFIED URL resolves]**: https://link.europa.eu/q7x39t → Qlik Sense app `940a61c3-…` on dashboard.tech.ec.europa.eu — interactive aggregate KPIs. **Per-facility bulk CSV is NOT openly downloadable** (secrecy vs statistics debate documented in an asktheeu access request, 2025-07).
- First Commission analysis of 2024 reports (July 2025): https://op.europa.eu/en/publication-detail/-/publication/83be4c3e-5c79-11f0-a9d0-01aa75ed71a1/language-en ; 2025-period report "under preparation". National guide PDFs (reporter guide/FAQ) linked from the EC page.
- **Ireland (national, verified CSV)**: CSO StatBank table **MEC02 "Metered Electricity Consumption"** — quarterly **Data centres GWh since 2015Q1** (verified 132 rows, `2015Q1 Data centres 291 GWh`), CSV endpoint: `https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/MEC02/CSV/1.0/en`. 2025 share ≈23.2% of national metered electricity (highest in EU). National-aggregate only — not per facility.
- Germany: new federal data-centre register (2025 report pattern, see stackpath.ie write-ups) — per-facility reports emerging; Sweden: energimyndigheten reporting portal (aggregate). Uptime Institute Global Survey: paid, note as such.

---

## (C) Inter-data-center network latency / transfer evidence

### C1. Microsoft-published Azure region RTTs — **[VERIFIED, full 53-region table fetched]**
- https://www.azurespeed.com/Azure/RegionToRegionLatency (and per-source URLs like `/Azure/RegionToRegionLatency/WestCentralUS`) — "Microsoft-published round-trip measurements between Azure regions"; HTML table (no raw CSV endpoint found; trivially scrapable). Sample verified: **West US 2 → West US 24 ms, East US 73 ms, Japan East 101 ms, West Europe 142 ms, Australia East 161 ms, Brazil South 177 ms, UAE North 240 ms, South Africa North 279 ms**.
- Canonical source: https://learn.microsoft.com/en-us/azure/networking/azure-network-latency (round-trip statistics between Azure regions; docs page with the same matrix).
- azurespeed.com/Azure/Latency (client-side test page: "export the measurements to CSV" — your own vantage, not inter-DC).

### C2. Community/inter-cloud monitoring
- **cloudping.co** (https://github.com/mda590/cloudping.co, MIT): continuously-updated **AWS inter-region TCP latency, every region, every 6 h**, p10–p99 percentiles, daily/weekly/monthly/annual views; free UI, historical API with key. Strong, architecture documented (Lambda↔Lambda, DynamoDB).
- **cloudpingtest.com** (AWS/Azure/GCP/DO, browser Lambdas; regular snapshots as JSON — check `cloudpingtest.com/data/*` snapshots when using).
- **gcping.com** (repo github.com/gcping/gcping): user↔GCP-GCP region pings from the client only.
- **webping.cloud** (github.com/goenning/webping.cloud): browser→regions across 7 providers; useful for edge/user-side latency, not DC↔DC.
- **Kentik Cloud Latency Map** (2024-10): latencies among **100+ cloud city regions across AWS/Azure/GCP**, free tool + blog with methodology — https://www.kentik.com/blog/announcing-the-cloud-latency-map/
- **databricks/cloud-latency-map** (github.com/databricks/cloud-latency-map): measured latencies from world locations to AWS/GCP datacenters, geojson data files in repo.
- **uofa-rzhu3/NetLatency-Data**: RTT matrices (99×99) collected in Seattle ISP network — academic matrices example.

### C3. RIPE Atlas — the honest way for a student to *measure* real RTTs near DC cities
- Verified docs: registration free (RIPE NCC account); **new users get a one-time 50,000-credit grant**; credits accrue (~21,600/day) by hosting a probe or from sponsor credits. Ping measurements are cheap; **querying everyone's archived/public measurement results is free** (API at https://atlas.ripe.net/api/v2/measurements/?type=ping). Students can (a) query public ping results already recording toward data-center-facing IPs in the major DC cities (large probe density exists near Amsterdam/Frankfurt/Dublin/Ashburn/Singapore), or (b) create their own ping/traceroute measurements to colo IPs. Probe list: https://atlas.ripe.net/probes/. A ping measurement across ~50 probes costs hundreds of credits — feasible inside the free grant.
- Docs: https://atlas.ripe.net/docs/getting-started/credits/

### C4. Cloudflare Radar — traffic + latency aggregates, free API
- https://radar.cloudflare.com/ + docs https://developers.cloudflare.com/radar/ — "Radar's API is free" (account token required): traffic, AS-level **Internet Quality/latency** (median RTT to Cloudflare edge, e.g. https://radar.cloudflare.com/quality) — edge-facing, not DC↔DC; traffic volume by AS/country. https://speed.cloudflare.com gives per-run measurements.

### C5. Transfer volume / egress cost data
- **Egress prices (documented cost, not volume)**: https://aws.amazon.com/ec2/pricing/on-demand/ (Data Transfer table, first 100 GB free then $0.09/GB from us-east-1 varies by destination), https://azure.microsoft.com/pricing/details/bandwidth/ (e.g. first 5 GB/month free, then tiered by geo), https://cloud.google.com/network/pricing (premium/standard tier egress tables). Well-known published price pages — include as cost inputs.
- **Volume**: EU EED delegated regulation requires annual *incoming/outgoing data traffic* per facility → will appear via the EU database/dashboard as reporting matures; today only aggregate. Academic cloud traces (Azure functions/blob traces above) give workload transfer patterns. Radars' AS-level traffic is coarse.

---

## Recommended composition for the project
1. **Power model**: NLR GenAI power profiles (A1) as the measured per-node GPU+CPU trace source (10 Hz RAPL+NVML, real 14-h continuum), calibrated by A4 (kernel-level per-architecture power) and A5 (DVFS knob); long-horizon/high-frequency optional evidence via A2.
2. **Facility layer / PUE & grid**: Google region-carbon CSVs (B1) as the only machine-readable per-region CFE + grid intensity; Google PUE tables as PUE priors; CSO MEC02 and EU EED aggregate dashboard as facility-side demand evidence; assume Microsoft/Meta only from fact sheets.
3. **Network layer**: Azure RTT matrix (C1) + cloudping.co (C2) as static inter-DC latency matrices; RIPE Atlas (C3) for fresh, citeable RTT measurements to candidate DC regions; Cloudflare Radar for traffic context.
4. Carbon-aware scheduler simulation = NLR traces × PUE priors × CFE CSVs × RTT matrix — all from verified, downloadable, mostly license-compatible sources (Licenses: NLR/DOE work, CC0, CC-BY, MIT).

## Files kept for the record (in `/tmp/dl/`)
- `nlr-power-profiles.zip` (1,021,3 MB, NLR dataset, sha-able), extracted sample at `nlr_x/00_raw_datasets/inference_offline_llama3_70b/` (rapl 82 MB + nvml 38 MB logs).
- `harvard_gpu/` (PowerDatasets.zip contents, 4 CSVs, 14,054 rows).
- `dvfs_power.csv` / `dvfs_perf.csv` / `dvfs_eff.csv` (33×13 V100 sweeps).
