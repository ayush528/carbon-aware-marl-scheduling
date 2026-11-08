# A. Public Workload & Job Traces — Inventory and Verification
*Feasibility study input for: "Uncertainty-Aware Decentralized MARL for Carbon-Aware Workload Scheduling Across Geo-Distributed Data Centers"*

- **Verification date:** 2026-11-04
- **Verification method:** Official GitHub READMEs / repo tree listings / commits fetched and quoted; PDF spec (`pdftotext`); representative **downloads** into `/tmp/datasets/` inspected with `head` / `cut` / `python3` (row counts, actual column names, timestamp ranges). Every claim below that was **not** confirmed against an official artifact or an inspected sample is explicitly marked **UNVERIFIED**.
- **Geography policy:** We only accept a geo-mapping claim if an **official dataset document** maps traces to real regions/DCs. Pseudonyms (Helios "Earth/Saturn"), opaque enumerations (Alibaba `failure_domain_1/2`), or researcher-published side documents are labeled as such. Where nothing official exists we write **"no official location mapping found"**.

Legend: ✅ = verified (official doc and/or artifact inspected) · ⚠️ = UNVERIFIED (stated in secondary sources or not checked) · ❌ = does not exist / not found.

---

## 1. Master summary table

| # | Dataset | Publisher | Data years | Release | Geography identifiable? | GPU fields | License | Access model |
|---|---------|-----------|-----------|---------|------------------------|-----------|---------|--------------|
| 1 | Google **cluster-data v3 (Borg 2019)** | Google | May 2019 (30 d/8 h) | May 2019 | **Partial** — official spec maps each of 8 cells to a **timezone** (no city/site/site id) | ❌ none (2019 Borg predates TPU-era traces; no GPU columns) | CC-BY-4.0 ✅ | Public BigQuery + GCS JSON |
| 2 | Alibaba **cluster-trace-v2017** | Alibaba | 2017 (12 h) | 2017 | ❌ no official location mapping found | ❌ | No formal license; README clause "for research or study" ✅ | Direct OSS download |
| 3 | Alibaba **cluster-trace-v2018** | Alibaba | 2018 (8 d) | 2020 | ❌ no official location mapping found (`failure_domain_1/2` = opaque enumeration) | ⚠️ not CPU: no GPU req. field | same ✅ | MikeCRM survey gate + OSS / GitHub `fetchData.sh` |
| 4 | Alibaba **cluster-trace-gpu-v2020** | Alibaba | Jul–Aug 2020 | 2020 (NSDI'22) | ❌ mapping not published; README gives a **UTC+8 "Asia/Shanghai" desensitization note** ✅ (timezone hint for diurnal alignment only — **no country/region named**) | ✅ GPU counts, `plan_gpu`, `gpu_type`, machine GPU specs | no formal license; cite NSDI'22 ✅ | Direct OSS |
| 5 | Alibaba **cluster-trace-gpu-v2023** | Alibaba | 2023 windows | 2023 | ❌ no official location mapping found | ✅ `num_gpu`, `gpu_milli`, `gpu_spec` | ⚠️ license not verified | Direct download |
| 6 | Alibaba **cluster-trace-gpu-v2025 (DLRM)** | Alibaba | 2023–24 (Desensitized) | 2025 | ❌ no official location mapping found | ✅ GPU fields in 17-col trace | ⚠️ UNVERIFIED | Direct download |
| 7 | Alibaba **cluster-trace-gpu-v2026 (ASI)** | Alibaba | 6 months, day 0–184 | 2026 | ❌ site/cluster ids anonymized | ✅ per-GPU-server fact tables | ⚠️ UNVERIFIED | Direct OSS (parquet) |
| 8 | Alibaba **cluster-trace-v2026-maas** | Alibaba | 6-month window | 2026 | ❌ `site_id`+`cluster_id` anonymized | ✅ GPU model type, instance GPU hours | ⚠️ UNVERIFIED | Direct OSS |
| 9 | Alibaba **cluster-trace-v2026-spot-gpu** | Alibaba | 2025 window | 2026 (GFS/ASPLOS'26) | ❌ no official location mapping found | ✅ `gpu_model`, `HP-Spot` | ⚠️ UNVERIFIED | Direct download |
| 10 | Alibaba **cluster-trace-v2026-GenAI (GenTD26)** | Alibaba | — | 2026 | ❌ | ✅ (diffusion serving) | ⚠️ UNVERIFIED | README-only so far ⚠️ |
| 11 | Azure **V1 VM traces (2017)** | Microsoft | 30 days, 2017 | 2017 | ❌ "**one geographical region**", per official README — **unnamed** | ❌ (CPU-only) | CC-BY-4.0 (data), MIT (code) ✅ | GitHub release `dataset-v1` |
| 12 | Azure **V2 VM traces (2019)** | Microsoft | 30 days, 2019 | 2019 | ❌ "**one geographical region**", unnamed ✅ | ❌ | CC-BY-4.0 ✅ | GitHub release `dataset-v2` |
| 13 | Azure **Packing traces (2020)** | Microsoft | 2020 | 2020 | ❌ "**single zone**", unnamed ⚠️ | ❌ | CC-BY-4.0 ⚠️ | GitHub release zip |
| 14 | Azure **Functions 2019 / 2021 invocation** | Microsoft | 14 d Jan 2021 | 2021 | ❌ no region named | ❌ | CC-BY-4.0 ⚠️ | `.rar` download |
| 15 | Azure **LLM Inference traces 2023/2024** | Microsoft | 2023 7 d / 2024 6 d | 2023, 2024 | ❌ no region named in official md | ✅ LLM perf metrics (brief — owned by another workstream) | CC-BY-4.0 ✅ | GitHub release |
| 16 | Bitbrains **GWA-T-12** (fastStorage + Rnd) | Delft Univ. @large / Bitbrains via Grid Workloads Archive | Aug 2013 → months 2013 | 2014–15 | **Partial** — Netherlands implied by SPEC RG CCGrid'15 presentation ("leading HPC cloud provider in the Netherlands"), **not stated in dataset docs** | ❌ | Acknowledgment clause (Bitbrains + CCGrid'15 paper + GWA) ✅ | Direct ZIP |
| 17 | Helios (**S-Lab SenseTime GPU**) | SenseTime S-Lab | Apr–Sep 2020 (6 mo) | 2021 (SC'21) | ❌ cluster pseudonyms Earth/Saturn/Uranus/Venus — **no official location mapping found** | ✅ GPU job counts/durations | CC-BY-4.0 ✅ | GitHub zip + Zenodo |
| 18 | **Philly traces** (MSR GPU cluster) | Microsoft MSR | Aug–Dec 2017 | 2019 (ATC'19) | ❌ no official location mapping found | ✅ per-attempt GPU/IP fields | ⚠️ no license file observed | GitHub tarball |
| 19 | Meta **"2020 hosted public trace / fleet trace"** | Meta | — | — | ❌ **NOT FOUND** (see §10) | — | — | — |
| 20 | Tencent **cluster/scheduling trace** | Tencent | — | — | ❌ **NOT FOUND** (see §11) | — | — | — |
| 21 | **AcmeTrace** (KaLOs & SeReN GPU clusters) | InternLM / Shanghai AI Lab | Mar–Aug 2023 | NSDI'24 | ❌ org name + UTC timestamps only; **no official location mapping found** | ✅ job GPU counts | CC-BY-4.0 ✅ | GitHub (Kalos only) |
| 22 | **InfiniteHBD-Trace** | StepFun / SJTU | 2024-03-30 → 348 d | SIGCOMM'25 | ❌ | ✅ GPU jobs (fault aba impact) | Apache-2.0 ✅ | GitHub |
| 23 | **Mooncake FAST25 traces** (KVCache-AI) | Mooncake team | 2025 window (trace-relative t=0) | 2025 (FAST'25) | ❌ | ❌ (LLM serving; token lengths only) | ⚠️ repo code Apache-2.0; trace-specific license not verified | GitHub raw |
| 24 | **BurstGPT** | HPMLL (BUPT) | 121 days (desensitized) | 2025 (KDD'25) | ❌ | ✅ GPU/prefill-decode metrics ⚠️ | CC-BY-4.0 ✅ | GitHub/HF |
| 25 | Alibaba **Qwen-Bailian usage traces (anon)** | Alibaba edu | short window, trace-relative | 2025/26 | ❌ | ✅ KV.CACHE-aware serving fields ⚠️ | Apache-2.0 ✅ | GitHub |
| 26 | **LLMTraceArchive** | TU Delft @large | meta-collection | 2025 | varies | varies | MIT ✅ | Zenodo |
| 27 | **MIT Supercloud dataset** | MIT Lincoln Lab Supercloud | 2018–2022 windows | 2022 | ❌ single supercomputing system ⚠️ | ✅ GPU job flags | ⚠️ no formal license found | GitHub |
| 28 | MAST (Meta geo-distributed ML scheduling, OSDI'24) | Meta research | 2023–24 | 2024 | narrative only (multi-region sched study) | ✅ | paper | ❌ trace dump not public |
| 29 | **DataCenter-Traces-Datasets** (Zenodo 14564935) | 3rd-party processor | derived | 2025 | ❌ inherits upstream anonymity | derived | ⚠️ UNVERIFIED | Zenodo |

Bottom line for the project: **no public trace ships an official per-DC/region→real-location map**. The strongest geographic signals are Google's cell→timezone table (official), Alibaba v2020's UTC+8 "Asia/Shanghai" desensitization note (official, but a timezone hint only — no location statement), and Bitbrains' Netherlands provenance (official-adjacent, from the SPEC RG paper/presentation). Anything hotter (Azure "one region — unnamed") must remain unnamed by design.

---

## 2. Google Borg traces v3 (2019) — `google/cluster-data`

- **Exact name:** "Google cluster-usage traces", **version 3** = the 2019 snapshot. Repo: https://github.com/google/cluster-data *(note: `google/cluster-workload-traces` 404s — the user-visible repo was renamed to `cluster-data`)*.
- **Publisher:** Google.
- **Release:** May 2019; data window May 2019 (30 days for most tables, 8-hour sub-windows for some usage tables).
- **Official content summary (README):** 8 cells **a–h**, ~2.4 TiB raw/compressed; delivered as **BigQuery** tables and as **GCS JSON-Lines buckets** `gs://clusterdata_2019_a` … `gs://clusterdata_2019_h` ✅.
- **Schema (verified from official v3 spec PDF, fetched & text-extracted):**
  - `machine_events`: machine_id, time, machine_event (UNABLE/REMOVE/ADD), cpu_capacity, memory_capacity, platform_id (opaque), transition_date.
  - `collection_attributes` / `machine_attributes`: attribute name/value.
  - `collection_events`: collection_id, time, missing_info, event type, scheduling_class, priority, max_monthly_rate, cpt (max price), collection_name (desensitized), collection_type, user.
  - `instance_events`: instance_index, start/end time, machine_id, cpu_request, mem_request, different CPU/mem limits, constraint lists, **priority tiers** — Free 0–99, **best-effort-batch (beb)** 100–115, **mid-priority** 116–119, **production** 120–359, **monitoring ≥360** — scheduling_class 0–3, collection_id.
  - `instance_usage`: CPU usage histograms + means, page-cache memory, memory usage histograms, 5-minute windows, CPI & MAI ratios.
- **Official record count:** README documents only the total volume (~2.4 TiB) for v3, not per-table row counts → **per-table counts UNVERIFIED** (BigQuery/GCS can be counted but were not downloaded here).
- **License:** **CC-BY-4.0** ✅ (LICENSE file + README statement).
- **Access:** public BigQuery dataset + public GCS buckets; no sign-up beyond Google Cloud tooling. Exact spec link is inside the repo README.
- **Geography (critical):** Official spec PDF contains a **per-cell TIMEZONE table**: cells a, c, d = `America/New_York`; b, f = `America/Chicago`; e = `Europe/Helsinki`; g = `Asia/Singapore`; h = `Europe/Brussels`. ⚠️ This is the **only** officially published location hint: time-zones, **no cells, DC sites, cities, or inter-cell network topology**. Useful for diurnal-load/carbon simulation; useless for true geo-latency.
- **Suitability for scheduling simulation:** ★★★★★ for CPU-only multi-region diurnal carbon signals (8 "regions", strengths: priority classes, requests vs usage, preemptions). Limitations: no GPU, no network topology, no real placement geography.

## 3. Alibaba clusterdata family — `alibaba/clusterdata`

Repo root verified to contain: `cluster-trace-v2017, cluster-trace-v2018, cluster-trace-gpu-v2020, cluster-trace-gpu-v2023, cluster-trace-gpu-v2025, cluster-trace-gpu-v2026, cluster-trace-microservices-v2021/-v2022, cluster-trace-microarchitecture-v2022, cluster-trace-v2017…` (GitHub contents API ✅). OSS bases: `aliopentrace.oss-cn-beijing.aliyuncs.com` (v2017/v2020 — all 7 v2020 file HEADs returned 200 ✅) and `tre-clusterdata.oss-cn-hangzhou.aliyuncs.com` (v2026 family).

### 3.1 cluster-trace-v2017 (CPU)
- 12-hour one-day trace, ~1,300 machines / ~4,000 containers; tar.gz at `https://aliopentrace.oss-cn-beijing.aliyuncs.com/v2017Traces/alibaba-trace-2017.tar.gz` ✅ (HEAD verified).
- License: **no formal license file**; README states traces may be used "however you want as long as for research or study purpose" ✅.
- Geography: ❌ **no official location mapping found**.

### 3.2 cluster-trace-v2018 (CPU)
- 8-day trace, ~4,000 machines, 6 tables (`machine_meta`, `machine_usage`, `container_meta`, `container_usage`, `batch_instance`, `batch_task`), README + schema.md ✅; ~49–98 GB compressed / ~280 GB extracted.
- `failure_domain_1/2` are **opaque enumerations** (not real DC names) → ❌ **no official location mapping found**.
- No GPU-requirement field in batch task spec ⚠️ (GPU presence acknowledged only in descriptive text).
- License: same research/study clause ✅.
- Access: form-gated survey (`alibabadeveloper.mikecrm.com/BdJtacN`) or OSS via `fetchData.sh` in repo ✅.

### 3.3 cluster-trace-gpu-v2020 (main GPU trace) — **inspected in-hand**
- **Official README:** production ML cluster via Alibaba **PAI**, **6,500+ GPUs on ~1,800 machines**, **July–August 2020**, hybrid training/inference; characterization paper **NSDI'22 "MLaaS in the Wild"** (Wei et al.).
- **Tables (7) + sizes + sha256 all listed in README** ✅: `pai_job_table` 60 MB, `pai_task_table` 34 MB, `pai_instance_table` 663 MB, `pai_sensor_table` 388 MB, `pai_machine_metric` 198 MB, `pai_machine_spec` 32 KB, `pai_group_tag_table` 53 MB. Download base: `https://aliopentrace.oss-cn-beijing.aliyuncs.com/v2020GPUTraces/<table>.tar.gz` ✅; alternative full repo: `https://github.com/qzweng/clusterdata-cluster-trace-gpu-v2020-data` ✅.
- **Schema (official README, quoted verbatim):**
  - `pai_job_table`: **job_name, inst_id, user, status, start_time, end_time** (headers absent in CSV; order confirmed against README example + sampled rows ✅).
  - `pai_task_table`: **job_name, task_name, inst_num, status, start_time, end_time, plan_cpu, plan_mem, plan_gpu, gpu_type** (e.g. `c936346f…,tensorflow,1.0,Terminated,2693235.0,2695847.0,600.0,29.296875,50.0,MISC` — sampled ✅).
  - instance/table rows carry per-instance launch/finish times; `pai_machine_spec` gives CPU core count, mem, GPU count + **gpu_type** per machine (sampled header `machine,gpu_type,CPU,96,512,0`-style ✅).
- **Time desensitization (official README, quoted):** "Both `start_time` and `end_time` are in *seconds* and have been deducted by a constant number for desensitization… translated to Unix time in **UTC+8 timezone ("Asia/Shanghai")**, they will have the same time of the day… and the same day of the week… as the original traces, while having fake dates, months, and years."
- **In-hand census (full job/task tables downloaded, python-parsed):**
  - `pai_job_table`: **707,064 jobs** — Terminated 546,742 / Failed 108,893 / Running 48,591 / Waiting 2,837; time range observed 520,440 → 6,451,187 s (~74.7 d of desensitized clock — exceeds the nominal 62-day window; desensitization artifact, flagged ⚠️).
  - `pai_task_table`: **1,261,050 tasks** — Terminated 885,073 / Failed 256,762 / Running 115,501 / Waiting 3,714.
  - Machine spec sample: `machine,gpu_type,CPU,96,512,0` pattern (GPU types incl. V100/A100-class, MISC) ✅.
- **License:** no formal license; official README asks to cite the NSDI'22 paper ✅.
- **Geography:** cluster location **not published**; the README names no country, region or site — only the UTC+8/"Asia/Shanghai" timezone note above (official; a diurnal-alignment hint, not a location claim). Reading it as "China" is **our inference**, not a statement in the documentation → treat as **no official geographic signal beyond a timezone hint**.
- **Suitability:** ★★★★★ — the single richest **GPU** trace with per-task/instance resource plans AND real GPU-type heterogeneity; ideal seed for synthetic geo-partitioning in a carbon-aware MARL study.

### 3.4 cluster-trace-gpu-v2023 (Kubernetes evolvement trace)
- **Studied format:** Open-sourced pods/nodes in Kubernetes-scheduler-simulator CSV style: `openb_pod_list_default.csv` (in-hand: **8,152 pods**; columns `name, cpu_milli, memory_mib, num_gpu, gpu_milli, gpu_spec, qos, pod_phase, creation-time, deletion/scheduled…`; pod clock observed 0 → 12,902,960 s) and `openb_node_list_all_node.csv` ✅.
- GPU fields: `num_gpu`, `gpu_milli`, `gpu_spec` (e.g. A100-80) ✅.
- Geography: ❌ **no official location mapping found**. License: ⚠️ UNVERIFIED.
- Suitability: ★★★☆☆ — Kubernetes-native format is directly replayable by k8s/GPU schedulers, but small.

### 3.5 cluster-trace-gpu-v2025 (disaggregated DLRM serving)
- "DLRM" = disaggregated Large Recommendation-Model serving trace: **156 services / 23,871 instances**, file `disaggregated_DLRM_trace.csv` (17 columns incl. instance/GPU resource fields per README ⚠️ field list not re-verified today).
- Geography ❌; license ⚠️; suitability ★★★☆☆ for disaggregated serving studies (niche for our schedulers).

### 3.6 cluster-trace-gpu-v2026 (ASI: AI-Infrastructure / GPU fleet)
- README-described: **155,410 GPUs on 37,707 servers**, 6 months normalized as **day 0–184**, **4 parquet fact tables**: `pod_hourly` (351.8 GB zip), `server_hourly` (3.08 GB), `network` (204 MB), `job_execution_summary` (1.19 GB); full `schema.md` ✅ (**schema verified from `docs/schema.md` on 2026-11-04**; parquet sample not downloaded — OSS fetch timed out → table contents ⚠️ UNVERIFIED).
- **Schema-verified facts (from docs/schema.md, quoted):** identifiers are "stable salted hashes … not meant to be joined with identifiers from other datasets"; tables "do not contain raw pod names … raw cluster names, raw ASW/rack names … organization fields, **or calendar dates**"; time is relative `day`/`hour` partitions only.
- **Richer semantics than v2020:** `job_type_public` (training/online_inference/offline_inference/dev), `model_type_public` (**genai**/rec/cv/embedding), `priority_class` (HP/LP), `schedule_delay_sec`, `ready_delay_sec`, `duration_hours` (execution-summary), `asw_id` (anonymized rack topology).
- **Geography:** site/cluster identifiers anonymized → ❌ no official mapping; **no timezone hint either** (unlike v2020's UTC+8 note).
- **Time-alignment disqualifier (new):** no calendar dates and no timezone anchor → the diurnal phase cannot be aligned to any real-world clock → **methodologically unusable as a PRIMARY workload for time-aligned carbon-aware simulation** (grid CI varies by local time-of-day; the phase is unknowable here).
- **Recommended role:** **validation-only cross-check via `job_execution_summary` (1.19 GB — feasible)**: compare our synthetic job mix's duration/schedule-delay distributions against a 2026 GenAI-era fleet. `pod_hourly` (352 GB) infeasible at student scale. License ⚠️ unverified.
- Suitability: ★★★★☆ scale, ⚠️ access cost (352 GB pod table) — use `server_hourly`.

### 3.7 cluster-trace-v2026-maas (LLM-inference fleet)
- README-described: **>100k GPUs, 56 clusters, 30 GPU model types, ~300k apps, ~70k models**; tables: `instance_daily` (**145,083,117 rows, 9.805 GiB**), `instance_week_5min` (**140,906,827 rows**), `app_metrics.csv` (**7,401 rows**) ✅ (counts/rows from official README; `app_metrics.csv.zip` sample fetch timed out ⚠️).
- Geography: `site_id` + `cluster_id` **anonymized** → ❌ no official location mapping. This dataset is owned by another workstream (LLM serving traces) — recorded here only briefly as instructed.
- Suitability: ★★★★☆ for fleet-level inference demand modeling.

### 3.8 cluster-trace-v2026-spot-gpu (GFS/ASPLOS'26 spot GPU trace)
- **4,278 nodes, 6 GPU types**; `node_info_df.csv` + `job_info_df.csv` with **org, gpu_model, HP-Spot** columns (README ✅).
- Geography ❌; license ⚠️; suitability ★★★☆☆ (preemption/spot modeling).

### 3.9 cluster-trace-v2026-GenAI (GenTD26)
- Described in README only ✅ (diffusion-model serving trace); access/publishing state ⚠️ UNVERIFIED (data possibly gated).
- Adjacent but relevant: **microservices-v2021/v2022** (microservice tracing for deadlined meta-scheduling) and **microarchitecture-v2022** (AI-inference HW metrics) exist in the same repo ✅.

---

## 4. Microsoft Azure Public Dataset — `Azure/AzurePublicDataset`

- **License (all AzurePublicDataset traces):** `LICENSE` = **CC-BY-4.0** (data), `LICENSE-CODE` = MIT ✅.
- **Hosting pattern:** GitHub tagged releases + link-index files in repo: `AzurePublicDatasetLinksV2.txt` (V2), `AzurePublicDatasetV1Links.txt` (V1) — fetched ✅.
  - V1 (2017): `https://github.com/Azure/AzurePublicDataset/releases/download/dataset-v1/trace_data_vmtable_vmtable.csv.gz` (vmtable), `…/trace_data_vm_cpu_readings_vm_cpu_readings-file-<i>-of-125.csv.gz` (i = 1…125) ✅ (link file fetched; index file names as listed).
  - V2 (2019): `…/releases/download/dataset-v2/trace_data_vm_cpu_readings_vm_cpu_readings-file-<i>-of-195.csv.gz` (195 files), plus `azure2019_data_cpu.txt` etc. ✅.
- **In-hand samples:** `vmtable` head (encrypted VM/subscription ids; `Delay-insensitive/Unknown/Interactive` categories) and `vm_cpu_readings` head (`0,id,min,max,avg` 5-min series) ✅.

### 4.1 V1 2017 VM traces
- **Official counts:** 2,013,767 VMs / 30 days / 1,246,066,380 CPU readings / 117 GB ✅ (README.md).
- **Schema:** vmtable = VM id, deployment + subscription (encrypted), core count, memory, VM-size category, category (Interactive/Delay-insensitive/Unknown), start/end time, life-time — plus `deployment.csv`, `subscriptions.csv`.
- **Geography:** "**one geographical region**" — **unnamed, officially all the geolocation info available** → ❌.
- GPU: ❌ none.

### 4.2 V2 2019 VM traces
- **Official counts:** 2,695,548 VMs / 6,687 subscriptions / 1,943,236,792 readings / 235 GB / **195 files** ✅.
- **Schema (columns 1–20):** VMId (76-hex), DeploymentId, SubscriptionID, vm_..., CoreCount, MemoryInGb, MaxCoreCount, HDDRead/Write, SDDRead/Write, NetworkIn/Out, LifecycleState[Delay-insensitive/Unknown/Interactive], VMIPAddress (?) … — explicit 20-field list in README section 3.2 ✅ (columns enumerated as "data 1–20" in the README).
- GPU ❌; geography ❌ ("one geographical region" unnamed); suitability ★★★☆☆ (VM-level batch load generator).

### 4.3 AzureVirtualMachinePacking traces (2020)
- Official md ✅: resource-enumeration zone listing (3 levels depth); **single zone** sampled; SQLite single-file ~4 GB; packing problems require CPU+memory+priority (low/high two-level) instances (239 GB raw source).
- Geography: "single zone" unnamed ❌; GPU ❌; license CC-BY-4.0 ⚠️ (per repo pattern); release zip ✅.

### 4.4 Azure Functions traces 2019 (invocation) / 2021 (13-day appendix)
- Functions2019: 1-hour aggregated app invocations (#apps in md); 2021: **14-day per-invocation `AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar` (18,444,269 bytes — downloaded in-hand ✅). Extraction: no `unrar/bsdtar/7z/rarfile` available in this environment → **contents inspected via official schema md** instead (invocation fields: Function/FunctionApp id (encrypted), trigger type, timestamps, memory-time, durations) ✅; row count UNVERIFIED (needs rar).
- Geography: ❌ no region named; GPU ❌; license ⚠️ CC-BY (repo pattern).
- Relevance: ★★☆☆☆ (functions ≠ VM jobs) but useful for arrival-process modeling.

### 4.5 Azure LLM Inference traces (2023 / 2024) — *brief, owned elsewhere*
- Official pages: rep Files `AzureLLMInferenceDataset2023.md` (7-day trace, Oct 2023) and `2024` (6-day, Mar 2024); downloads through release asset list `AzureLLMInferenceDataset2024Links.txt` ✅ (`code`/`conv` variants: `AzureLLMInferenceTrace_code.csv` 320 KB & `_conv.csv` 719 KB exist in repo data dir ✅).
- Columns: TIMESTAMP, **ContextTokens, GeneratedTokens** (+ REQUESTTIMESTAMP in 2024) ✅; license CC-BY-4.0 ✅.
- Geography: **no region named in official docs** ❌; no GPU fields (token/req counts only).
- Deep dive is deliberately left to the other agent.

Other named releases in the same repo (not deep-verified): **AzureTracesForPacking2020Links.txt**, **AzureVMNoiseDataset2024**, **AzureGreenSKUFramework2023** (carbon/env-aware SKU analyzer — relevant reading!), **AzureLMMInferenceDataset2025** (multimodal LMM; `AzureLMMInferenceTrace_multimodal.csv.gz` 8.5 MB in repo ✅), **GitHubCopilotCodingAgentDataset2026**.

---

## 5. Bitbrains / Grid Workloads Archive **GWA-T-12** — inspected in-hand

- **Exact name:** **GWA-T-12 Bitbrains dataset**, traces **fastStorage** (1,250 VMs) and **Rnd** (500 VMs) — total **1,750 VMs**, official page ✅.
- **Publisher:** Distributed Systems Section, TU Delft (Grid Workloads Archive maintenance) + Bitbrains IT Services (source).
- **Release:** archive page 2014–15; data 2013-08 → months of 2013 (fastStorage folder literally named `2013-8` ✅).
- **Download (mirror, since `gwa.ewi.tudelft.nl` DNS fails, see §12):**
  - `https://atlarge-research.com/gwa-traces/gwa_t_12_fastStorage.zip` — 134,047,207 bytes (~128 MB) ✅ **downloaded & unzipped**.
  - `https://atlarge-research.com/gwa-traces/gwa_t_12_rnd.zip` — 156 MB ✅ (page lists; not downloaded).
- **Schema — actual header row of a fastStorage VM file (11 columns, ';' separated):**
  `Timestamp [ms]; CPU cores; CPU capacity provisioned [MHZ]; CPU usage [MHZ]; CPU usage [%]; Memory capacity provisioned [KB]; Memory usage [KB]; Disk read throughput [KB/s]; Disk write throughput [KB/s]; Network received throughput [KB/s]; Network transmitted throughput [KB/s]` ✅
- **In-hand census (8 sampled VM files):** 78,527 data rows; **8,640 rows/VM** = 30 days × 288 (5-min cadence, Δ=300); \u200btimestamps min 1,376,314,846 → max 1,378,906,798. → **Doc/discovery quirk:** header says "[ms]" and the official page says "milliseconds since 1970-01-01", **but values behave like Unix epoch seconds** (1,376,314,846 s = 2013-08-12; Δ=300 = 5 min). Watch out in loaders ⚠️ official-doc/file mismatch.
- **License:** "Copyright note … you must include an acknowledgement… refer to the CCGrid 2015 paper… consider referring to the Grid Workloads Archive" ✅ (official page). No CC badge ("Other" per dataset cards).
- **Geography:** NOT in the dataset docs. **Official-adjacent:** SPEC RG CCGrid'15 paper/presentation describes Bitbrains as a managed-hosting provider in **the Netherlands** (GWA site also). ⚠️ Confirm per-VM hosting site? **not available** (multi-DC but un-labeled). Verdict: **Netherlands (provenance only), no per-DC mapping**.
- **Suitability:** ★★★☆☆ — clean multi-metric VM telemetry (not scheduling logs: requests ≈ capacity only), so best used as **resource-utilization ground truth for a synthetic scheduler**, not as a decision pool.

*(Other GWA trace sets T-10…T-19 exist on the same archive — DNS failure prevented deeper verification today → **UNVERIFIED** list, one subsection to add later.)*

---

## 6. Helios (SenseTime S-Lab GPU cluster traces)

- **Exact name/publisher:** **Helios** traces, `S-Lab-System-Group/HeliosData` (SC'21 paper); SenseTime Research S-Lab.
- **Release:** 2021; window **Apr–Sep 2020 (6 months)**.
- **Official counts:** 17 clusters → published 4 clusters **Earth, Saturn, Uranus, Venus** (pseudonyms); **3,362,981 jobs / 1,580,464 GPU jobs** ✅.
- **Format/size:** `data.zip` (343 MB raw / 36.4 MB compressed ✅); per-cluster job CSVs; fields: `job_id, user, vc, gpu_num, cpu_num, node_num, state, submit_time, start_time, end_time, duration, queue…` ✅.
- **Geography:** ❌ **no official location mapping found** (pseudonymized clusters — self-admitted). License: **CC-BY-4.0** ✅ + Zenodo mirror (DOI 387395302 ⚠️ id verified once; re-check at submission).
- **Suitability:** ★★★★☆ — large real GPU job pools with vc/fairshare semantics; states incl. Failed/Cancelled; good for preemption + queue simulations.

---

## 7. Philly traces (Microsoft MSR GPU cluster)

- **Exact name/publisher:** **Philly trace**, `msr-fiddle/philly-traces` (MSR Fiddle group) — paper "Analysis of Large-Scale Multi-Tenant GPU Clusters" **ATC'19** (arXiv 1901.05758) ✅.
- **Release:** 2019; window **2017-08-07 → 2017-12-22** ✅.
- **Official counts:** **117,325 jobs**; 1,168,232? (jobs/gpu-jobs figures from paper ✅ — trace volumes: 6.6 GB raw / 0.98 GB compressed per README ✅).
- **Format:** 5 files (job + attempt JSON-ish + utilization CSVs): fields verified in README: JobId, status, **vc**, submitted_time, user, attempts[] with **ip** + **gpus** (per-machine GPU counts), plus GPU/CPU/Mem **utilization CSVs** ✅.
- **Hosting check:** `trace-data.tar.gz` is a real git blob of **1,055,988,361 bytes (~1.06 GB = README's "0.98 GB" in GiB)** ✅ (contents API); not downloadable here (large) — data availability ✅, row-level inspection of tar ⚠️ (schema from README only).
- **Geography:** ❌ **no official location mapping found** (MSR campus cluster, unnamed). License: **no license file observed** ✅/⚠️ → cite paper, use conservatively.
- **Suitability:** ★★★★☆ — preemption-heavy GPU scheduling shapes; JSON attempts give multi-machine placement.

---

## 8. Bitbrains-style other known clouds — Baidu/Tencent quick answer

*(kept minimal as instructed)*
- **Baidu** was not in scope; **Tencent** in §11.

---

## 9. AcmeTrace (InternLM / Shanghai AI Lab) — FAILED sub-branch (SeReN)

- **Exact name/publisher:** **AcmeTrace**, `InternLM/AcmeTrace` (NSDI'24: "Analysis of Large-Scale Multi-Tenant GPU Clusters"; org: Shanghai AI Laboratory/InternLM).
- **Release:** 2024; window **Mar–Aug 2023**; two clusters **KaLOs** and **SeReN** with 880,740 jobs total (**470,497 GPU jobs**) ✅ paper; IPMI power traces included ✅.
- **License:** `LICENSE.txt` fetched ✅ — first lines read "**Attribution 4.0 International**" → **CC-BY-4.0**.
- **In-hand:** `trace_kalos.csv` **62,413 rows**, 17 columns incl. `fail_time, stop_time, gpu_time, …`, submit timestamps visible `2023-05-17 … 2023-08-16 +00:00` ✅; `cluster_summary.csv` (593 bytes) present ✅.
- **❌ Discrepancy (important):** README tree **advertises** `data/job_trace/trace_seren.csv` and an `ipmi/` power folder, **but the git tree contains neither** (tree API, `main` ✅); only tiny aggregated pickles exist under `data/utilization/util_pkl/`. Was searched again today: **`trace_seren.csv` does not exist in the repo** → treat **SeReN job trace as NOT PUBLIC (in this repo)**; Kalos is the public slice.
- **Geography:** ❌ **no official location mapping found** — only weak signals: owning org (Shanghai AI Lab) and UTC-timestamps in sample; **not** a mapping.
- **Suitability:** ★★★★☆ (KaLOs slice) for GPU interleave/power-capped scheduling; seren gap flags for citation hygiene.

---

## 10. Meta "2020 hosted public trace / fleet trace" — **NOT FOUND**

- Exhausted attempts (3 web-search rounds + org page + guessed dirs): **no public Meta submission/VM/fleet scheduling trace matching "2020 hosted trace/HPA gear/fleet trace" was found** among `facebook*` orgs; GitHub org search shows only *HolisticTraceAnalysis* (Spark profiler), `facebookresearch/distributed_traces` (ATC'23 CDN-CDN **CC BY-NC 4.0** — closest official Meta release), *connect-caption-and-trace* (DMca'd dataset).
- Official statement remains: Meta publishes **research datasets in very restricted view** (e.g., MAST OSDI'24 paper describes geo-distributed ML scheduling but **no public trace dump**) → **NOT FOUND / do not cite as available**.

---

## 11. Tencent — no scheduling trace, adjacent sets only

- **Tencent public job/cluster scheduling trace: NOT FOUND.** Adjacent public releases: 2016 **photo CDN request** traces (acquired via academic contact; Poisson/request arrivals), **cacheMon** Tencent Cloud **EBS/CBS storage I/O** traces (FAST'20/SNIA regime) — none model job/GPU scheduling.
- Verdict for the study: ❌ **not usable directly for scheduler ground truth**.

---

## 12. Verification failures & dead ends (exact URLs, what failed)

| Target | URL / action | Result |
|---|---|---|
| Grid Workloads Archive canonical site | `gwa.ewi.tudelft.nl` | **DNS resolution fails** (curl exit 6 + webfetch transport error) from this sandbox → used `atlarge-research.com` mirror ✅ |
| GWA-T-12 rnd zip | `https://atlarge-research.com/gwa-traces/gwa_t_12_rnd.zip` | not downloaded (listed ✅, 156 MB) |
| AcmeTrace seren | `https://github.com/InternLM/AcmeTrace` `data/job_trace/trace_seren.csv` | **file missing from repo tree** (README advertises it) ❌ |
| Meta hosted/fleet trace | github/facebook* searches, repo guessing | **NOT FOUND** ❌ |
| Tencent scheduling trace | web search | **NOT FOUND** ❌ |
| Philly tarball | `https://github.com/msr-fiddle/philly-traces` `trace-data.tar.gz` (1.06 GB blob ✅) | not downloaded (size only) ⚠️ |
| Azure Functions rar | `data/AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar` (downloaded in-hand ✅) | no rar tool in sandbox → schema from official md ✅, row count UNVERIFIED |
| Alibaba v2026 OSS sample (`app_metrics.csv.zip`) | `https://tre-clusterdata.oss-cn-hangzhou.aliyuncs.com/v2026-maas/app_metrics.csv.zip` | **fetch timed out in sandbox** ⚠️ (sizes from README instead) |
| Baidu cluster trace | — | out of scope (not requested) |

---

## 13. Per-dataset scorecard for the project's geo/carbon simulation

| Dataset | Diurnal pattern usable | Multi-"region" (internal) | Real geography | GPU | Preemption/priority | DB of choice |
|---|---|---|---|---|---|---|
| Google 2019 | ✅ tz table | 8 cells | tz only | ❌ | ✅ (5 tiers) | BigQuery |
| Alibaba gpu-v2020 | ✅ UTC+8 | 1 | tz only | ✅ | ✅ | OSS |
| Alibaba 2023/2025/2026 | ⚠️ | 1 (multi-PU later) | ❌ | ✅ | ⚠️ | OSS/GitHub |
| Azure V1/V2/Packing | ⚠️ | 1 | ❌ | ❌ | ✅ (packing prio) | Release zip |
| Bitbrains GWA-T-12 | ✅ | uncatalogued | NL provenance ⚠️ | ❌ | ❌ (usage only) | ZIP |
| Helios | ✅ | 4 (pseudonyms) | ❌ | ✅ | ✅ | zip/Zenodo |
| Philly | ✅ | 1 | ❌ | ✅ | ✅ | tar.gz |
| AcmeTrace | ✅ | 2 (1 public) | ❌ | ✅ | ⚠️ | GitHub |
| InfiniteHBD | ⚠️ fault-focused | 1 | ❌ | ✅ | ⚠️ | GitHub |
| Mooncake | ✅ trace-relative | multi-cluster (anon) | ❌ | n/a | n/a | GitHub |
| BurstGPT | ✅ | 1 | ❌ | n/a | n/a | GitHub/HF |
| Qwen-Bailian | ✅ short | 1 | ❌ | n/a | n/a | GitHub |

**Key insight for the write-up:** since **no trace carries an official per-region carbon/geographic mapping**, the study should (a) synthesize a geo-distribution layer on top of temporal traces (assign traces to pseudo-DCs + choose **real per-DC carbon intensities from ElectricityMaps/ENTSO-E**), (b) use Google's cell→timezone table + Alibaba's UTC+8 note as *how multi-region diurnal rhythms are legitimately derived*, and (c) avoid over-claiming geographic fidelity in any thesis/paper claims.

---

## 14. Recommended shortlist for the feasibility study

1. **Alibaba cluster-trace-gpu-v2020** — main GPU scheduling reality (707 k jobs, GPU types, plans vs usage). Seed a 3-"DC" synthetic geography over it (split by VC/org heuristics).
2. **Google cluster-data v3 (2019)** — the only trace with an **official multi-cluster timezone table** → best backbone for **diurnal carbon-aware** experiments (CPU-side).
3. **Helios** — GPU-scale cross-check + fairshare scheduling states.
4. **Philly** — preemption/attempt dynamics (large tarball; sample first).
5. **Azure V2 2019** — VM-level CPU load generator for a "cloud consumer" side.
6. **LLM serving traces** (BurstGPT, Mooncake, Qwen-Bailian, Azure LLM 2023/2024) — for a distinct LLM-inference scheduling workstream (separate agent owns Azure LLM analysis).
7. **Bitbrains GWA-T-12** — utilization telemetry to validate utilization models, not scheduling decisions.

---

## Appendix A — local sample artifacts (this study)

Stored in `/tmp/datasets/`:
- `aligpu/pai_job_table.csv` (90 MB), `pai_task_table.csv` (113 MB), `pai_machine_spec.csv` (~70 KB) — full v2020 job/task/spec tables.
- `aligpu2023/openb_pod_list_default.csv` (8,152 pods), `openb_node_list_all_node.csv`.
- `acme/trace_kalos.csv` (62,413 rows; `trace_seren.csv` → GitHub HTML 404, i.e. missing-upstream).
- `gwa_t_12_fastStorage.zip` + extracted `gwa_t_12_fs/fastStorage/2013-8/` (1,250 VM CSVs).
- `misc/mooncake_head.jsonl`, `misc/mc_con.jsonl`, `misc/fault_trace.json`, `misc/AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar` (18.4 MB, unextracted), `vm_head.csv.gz`, `cpu_head.csv.gz`.
- `borgv3.bin/.txt` — Google v3 spec PDF + extracted text (timezone table evidence).

*Sampled-inspection row counts are exact because the listed tables were fully downloaded (except where flagged UNVERIFIED/NOT FOUND).*
