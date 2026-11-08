#!/usr/bin/env python3
"""Build the dataset comparison workbook (deliverable 2)."""
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset-comparison.xlsx")

HDR_FILL = PatternFill("solid", fgColor="1F4E79")
HDR_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Arial", size=10)
WRAP = Alignment(wrap_text=True, vertical="top")

wb = Workbook()

# ---------------- Sheet 1: Dataset comparison ----------------
ws = wb.active
ws.title = "Dataset comparison"

cols = ["Category", "Dataset", "Publisher", "Release / coverage", "Geography identifiable?",
        "Resolution", "Key fields", "Format & size", "License", "Access model",
        "Forecast data?", "Audit status", "Role in project"]
rows = [
    # Carbon / electricity
    ["Carbon intensity", "NESO Carbon Intensity API", "National Energy System Operator (UK)", "2017-09-26 → present; 30-min",
     "YES — GB national + 14 DNO regions (regionid 1-17)", "30 min",
     "intensity.forecast, intensity.actual, index; regional generationmix[]", "JSON API; ~0.6 MB/month national",
     "CC BY 4.0", "Free, no API key", "YES — historical forecast AND actual per slot (verified)",
     "Downloaded & inspected [V]", "PRIMARY carbon signal + native uncertainty"],
    ["Carbon intensity", "Elexon BMRS Insights API (FUELHH/FUELINST)", "Elexon (GB)", "present; half-hourly/5-min",
     "YES — GB national", "30 min / 5 min", "generation by fuel type (MW)", "JSON API", "Free (BMRS terms)",
     "Free, no key", "No CO2 — compute from fuel mix", "Live-verified [S]", "Generation-mix cross-check for GB"],
    ["Carbon intensity", "EIA-930 Hourly Grid Monitor bulk CSV", "US EIA", "2015-H2 → 2026-H2; hourly",
     "YES — 64 Balancing Authorities (CISO, ERCT, PJM...)", "1 hour",
     "demand, net generation by fuel, interchange, demand forecast", "CSV; 41.7 MB per 6 months",
     "US public data", "Free, no key (API needs free key)", "Day-ahead demand forecast only; no CO2 forecast",
     "Downloaded & inspected [V]", "US candidate backbone; CI computed from fuel mix + eGRID factors"],
    ["Carbon intensity", "CAISO Today's Outlook history", "CAISO", "≥2019 → present; 5-min today, per-day history",
     "YES — California ISO footprint", "5 min (current), per-day files",
     "CO2 tonnes by fuel; fuel mix (MWh)", "CSV per day (~8 KB)", "Public (informational)",
     "Free, no key", "No CO2 forecast", "Live-verified [S]", "US single-region case study"],
    ["Carbon intensity", "EPA eGRID2023", "US EPA", "data year 2023 (rev2, 2025-06); annual",
     "YES — 27 eGRID subregions (CAMX...)", "annual", "CO2 lb/MWh & kg/MWh by subregion", "XLSX",
     "US public data", "Free", "No", "URLs verified [S]", "Static emission factors for US CI computation"],
    ["Carbon intensity", "Energy-Charts API (public_power + forecast)", "Fraunhofer ISE (DE)", "≈2000s → present; 15-min",
     "YES — DE + European bidding zones", "15 min", "generation by source; generation forecast", "JSON API",
     "Publishing notes (attribution)", "Free, no key", "Generation forecast YES; CI computed by us",
     "Live-verified [S]", "German/EU candidate"],
    ["Carbon intensity", "Fingrid emission-factor datasets 265/266/396", "Fingrid (FI)", "real-time; 3-15 min updates",
     "YES — Finland", "3-15 min", "gCO2/kWh equivalents (consumption & production)", "JSON API",
     "Fingrid open data licence", "Free API key (registration + licence approval)", "Real-time only; no archived forecast",
     "Key required; not fetched [D]", "Nordic candidate; history depth unverified"],
    ["Carbon intensity", "Waseda hourly CI, 9 TSO areas", "Waseda Univ. (Zenodo 18396311)", "FY2024 (Apr 2024-Mar 2025); hourly",
     "YES — 9 Japanese TSO areas", "1 hour", "kgCO2/kWh per TSO area", "CSV (~15 MB total)",
     "CC BY 4.0", "Free download", "No", "Record page verified [S]", "Japan candidate (1 fiscal year only)"],
    ["Carbon intensity", "OpenElectricity v4 emissions", "OpenNEM/OpenElectricity (AU)", "multi-year → present; 5-min-1y",
     "YES — NEM states (NSW1...)", "5 min → 1 d", "emissions (t), energy by fueltech", "JSON API",
     "Open (CC-style)", "Free, keyless (today)", "No forecast", "Live-verified [S]", "Australia candidate"],
    ["Carbon intensity", "Electricity Maps API/portal", "Electricity Maps", "2017-2024 historical; forecasts",
     "YES — 130+ zones", "5/15/60 min", "CI, CFE%, mix, flows", "API (paid)",
     "Commercial", "PAID — €6,000/yr per country; 14-day free trial", "YES (proprietary forecast endpoint)",
     "Pricing page verified [S]", "Fallback only — not free"],
    ["Carbon intensity", "WattTime", "WattTime", "2+ yr historical; 72 h forecasts",
     "YES — global (Pro) / CAISO_NORTH (free tier)", "5 min", "marginal & average CI", "API",
     "Commercial", "Free Basic tier = CAISO_NORTH only; research access by application", "YES (marginal)",
     "Docs verified [S]", "Marginal-emission sensitivity analysis"],
    ["Carbon intensity", "ENTSO-E Transparency Platform", "ENTSO-E", "2015 → present; 15-60 min",
     "YES — European bidding zones", "15-60 min", "generation by type per zone (NO CO2)", "XML/ZIP API",
     "Free (EU)", "Free token after registration; 400 req/min", "No", "Docs verified [S]", "EU fuel-mix backbone"],
    # Workload
    ["Workload", "Azure LLM Inference Trace 2024", "Microsoft (AzurePublicDataset)", "10-19 May 2024 (10 d); 2023 variant 7 d",
     "NO — geo-anonymous (no region field; verified in schema)", "per-request (µs timestamps)",
     "TIMESTAMP, ContextTokens, GeneratedTokens", "CSV; 692 MB (code 1-week); 16.8M rows",
     "CC BY 4.0", "Free direct download", "n/a", "Downloaded & inspected [V]",
     "PRIMARY workload (LLM inference demand model; region assumption disclosed)"],
    ["Workload", "Alibaba cluster-trace-gpu-v2020", "Alibaba Cloud", "Jul-Aug 2020; 62 d",
     "NO — README gives a UTC+8/Asia/Shanghai desensitization note (timezone hint only; no country/region named)", "per job/task/instance",
     "job/task/instance tables; plan_gpu, gpu_type (V100/A100-class)", "tar.gz; ~1.4 GB",
     "Research-use clause; cite NSDI'22", "Free direct download (OSS)", "n/a",
     "Downloaded & inspected [S]", "GPU training/batch workload; SustainCluster's workload source"],
    ["Workload", "Google cluster-data v3 (Borg 2019)", "Google", "May 2019; 30 d, 8 cells",
     "PARTIAL — official cell→timezone table (America/New_York, America/Chicago, Europe/Helsinki, Asia/Singapore, Europe/Brussels); no sites",
     "5-min usage; event-level", "instance events, priority tiers, CPU/mem requests & usage", "BigQuery + GCS JSON; ~2.4 TiB",
     "CC BY 4.0", "Free (BigQuery/GCS)", "n/a", "Spec verified [S]", "CPU-side multi-region diurnal workload"],
    ["Workload", "Bitbrains GWA-T-12", "TU Delft / Bitbrains", "Aug-Sep 2013; 1,750 VMs",
     "PARTIAL — Netherlands provenance (SPEC CCGrid'15), no per-VM site", "5 min",
     "CPU/MEM/disk/network usage per VM", "ZIP; 128 MB (fastStorage)",
     "Acknowledgement clause", "Free (mirror)", "n/a", "Downloaded & inspected [S]", "Utilization ground truth (CPU era)"],
    ["Workload", "Helios (SenseTime S-Lab)", "SenseTime", "Apr-Sep 2020; 4 published clusters",
     "NO — pseudonym clusters", "per job", "gpu_num, cpu_num, state, submit/start/end", "zip; 36.4 MB compressed",
     "CC BY 4.0", "Free", "n/a", "Repo verified [S]", "GPU job pool cross-check"],
    ["Workload", "Philly trace", "Microsoft Research", "Aug-Dec 2017; 117,325 jobs",
     "NO", "per job/attempt", "GPU/CPU per attempt, vc, preemptions", "tar.gz; ~1.06 GB",
     "none observed", "Free", "n/a", "Blob verified [S]", "Preemption dynamics"],
    ["Workload", "AcmeTrace KaLOs", "InternLM / Shanghai AI Lab", "Mar-Aug 2023; 62,413 rows (public slice)",
     "NO", "per job", "GPU counts, fail/stop times, gpu_time", "CSV",
     "CC BY 4.0", "Free (KaLOs only; SeReN missing from repo)", "n/a", "Downloaded & inspected [S]", "GPU scheduling shapes"],
    # Power
    ["Power", "NLR GenAI Workload Power Profiles", "National Laboratory of the Rockies (US DOE)", "2025-09 → 2026; ≈10 Hz",
     "YES — Kestrel HPC, Golden, Colorado, USA", "≈10 Hz",
     "RAPL CPU W (per socket), NVML GPU mW + °C (per GPU)", "ZIP; 1,021 MB (2.89 GB uncompressed)",
     "DOE work licence (cite paper)", "Free download", "n/a", "Downloaded & inspected [S]",
     "PRIMARY measured power telemetry (per-node GPU/CPU power curves)"],
    ["Power", "Harvard GPU Power & Performance Metrics", "Harvard Dataverse", "2025-09-25; kernel-level",
     "NO", "per kernel", "Power (W) per kernel, 4 NVIDIA architectures", "ZIP; 0.4 MB; 14,054 rows",
     "CC0 1.0", "Free", "n/a", "Downloaded & inspected [S]", "Power-model calibration"],
    ["Power", "GPU-DVFS-Dataset", "open source (GitHub)", "V100; 33 workloads × 13 frequencies",
     "NO", "per config", "avg GPU power W, performance", "CSV (small)",
     "open", "Free", "n/a", "Downloaded & inspected [S]", "DVFS/power-cap knob calibration"],
    ["Power / PUE", "Google region-carbon-info + PUE tables", "Google", "2019-2025 (annual CFE/CI); PUE quarterly since 2008",
     "YES — named Google cloud regions & campuses", "annual (CFE/CI); quarterly (PUE)",
     "CFE %, grid gCO2eq/kWh per region; PUE per campus", "CSV + HTML",
     "Open (CC-style)", "Free", "No", "Files verified [S]", "Region selection + PUE priors"],
    ["Power / PUE", "Ireland CSO MEC02", "CSO (IE)", "2015Q1 → present; quarterly",
     "YES — Ireland national", "quarterly", "data-centre metered GWh", "CSV",
     "CC BY 4.0 (CSO)", "Free", "No", "Endpoint verified [S]", "Facility-demand evidence (aggregate)"],
    # Network
    ["Network", "Azure inter-region RTT matrix", "Microsoft (azurespeed / MS Learn)", "continuously updated",
     "YES — 53 Azure regions", "static table", "RTT ms between regions", "HTML table",
     "published measurements", "Free", "n/a", "Fetched [S]", "Inter-DC latency matrix (incl. UK South)"],
    ["Network", "cloudping.co", "community (MIT)", "every 6 h; p10-p99",
     "YES — AWS regions", "6 h", "inter-region TCP RTT percentiles", "web/API",
     "MIT", "Free (historical API with key)", "n/a", "Verified [S]", "Latency matrix alternative"],
    ["Network", "RIPE Atlas", "RIPE NCC", "on-demand + archive",
     "YES — probe locations worldwide", "per measurement", "RTT/traceroute", "API",
     "RIPE terms", "Free account; 50k starter credits", "n/a", "Docs verified [S]", "Fresh RTT measurements near DC cities"],
    ["Network", "Cloud egress pricing pages", "AWS/Azure/GCP", "current",
     "YES — per region pairs", "static", "$/GB egress", "HTML",
     "published pricing", "Free", "n/a", "Pages verified [S]", "Transfer-cost model"],
]

for c, name in enumerate(cols, 1):
    cell = ws.cell(row=1, column=c, value=name)
    cell.fill, cell.font, cell.alignment = HDR_FILL, HDR_FONT, WRAP
for r, row in enumerate(rows, 2):
    for c, val in enumerate(row, 1):
        cell = ws.cell(row=r, column=c, value=val)
        cell.font, cell.alignment = BODY_FONT, WRAP
widths = [16, 30, 24, 26, 34, 14, 34, 22, 18, 26, 24, 20, 34]
for i, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(i)].width = w
ws.freeze_panes = "A2"

# ---------------- Sheet 2: Feasibility matrix ----------------
ws2 = wb.create_sheet("Feasibility matrix")
crit = ["Criterion", "UK (GB)", "USA (CAISO/EIA)", "Germany", "Netherlands", "Nordics (FI/SE)", "India", "Japan", "Australia (NEM)"]
rows2 = [
    ["Workload availability (public real traces)", "YES (Azure LLM trace; geo-anonymous)", "YES (Azure LLM trace; Borg cells tz-mapped)", "weak (old CPU traces)", "weak (Bitbrains 2013 CPU)", "NO", "NO", "NO", "NO"],
    ["Geographical identity of workload", "ASSUMPTION (disclosed)", "PARTIAL (Borg tz table; Azure anon)", "NO", "PARTIAL (NL provenance)", "NO", "NO", "NO", "NO"],
    ["Carbon data (historical, regional)", "STRONG — 14 DNO regions, 30-min, direct gCO2/kWh", "STRONG — BA-level hourly (computed)", "STRONG — 15-min (computed)", "GOOD — ENTSO-E zone", "GOOD — Fingrid direct EF (FI)", "WEAK — daily reports only", "MODERATE — 9 TSOs, FY2024 only", "GOOD — NEM states"],
    ["Carbon forecast-vs-actual (uncertainty)", "YES — native in API (verified)", "NO — self-constructed", "Generation forecast YES; CI derived", "NO", "NO", "NO", "NO", "NO"],
    ["Power data (measured)", "Generic measured telemetry (NLR, US) + physics model", "NLR (US, Colorado)", "generic", "generic", "generic", "NO", "NO", "generic"],
    ["PUE / facility evidence", "Google UK campuses PUE tables; UK policy data", "Google US campuses; EIA", "Google DE campus", "Google NL campus (Eemshaven 1.07)", "Google FI (Hamina)", "fact sheets only", "fact sheets only", "fact sheets only"],
    ["Time alignment", "2017→present (any window)", "2015→present", "≈2000s→present", "2015→present", "FI recent", "daily only", "FY2024 only", "multi-year"],
    ["Data accessibility (free)", "ALL free, no key", "free (bulk); API key", "free, no key", "token required", "key required", "free", "free (Zenodo)", "free"],
    ["Volume manageable", "YES", "YES", "YES", "YES", "YES", "YES", "YES", "YES"],
    ["Fields for scheduling", "carbon strong; workload schema thin (tokens only)", "same", "same", "same", "same", "weak", "weak", "same"],
    ["Multi-site within one country", "EXCELLENT — 14 DNO regions, verified 348 gCO2/kWh spread", "GOOD — multiple BAs (but multi-ISO)", "limited (one zone)", "one zone", "FI one zone; SE 4 zones", "5 RLDCs (daily)", "9 TSOs", "5 NEM states"],
    ["Reproducibility (frozen versions)", "API + chunked archives; CC BY 4.0", "bulk CSVs frozen", "API snapshots", "token-gated", "key-gated", "PDF reports", "Zenodo DOI", "API"],
    ["VERDICT", "FEASIBLE (with disclosed workload-region assumption)", "FEASIBLE (with limitations)", "FEASIBLE (with limitations)", "FEASIBLE (with limitations)", "NOT feasible alone", "NOT feasible", "NOT feasible alone", "NOT feasible alone"],
]
for c, name in enumerate(crit, 1):
    cell = ws2.cell(row=1, column=c, value=name)
    cell.fill, cell.font, cell.alignment = HDR_FILL, HDR_FONT, WRAP
for r, row in enumerate(rows2, 2):
    for c, val in enumerate(row, 1):
        cell = ws2.cell(row=r, column=c, value=val)
        cell.font, cell.alignment = BODY_FONT, WRAP
ws2.column_dimensions["A"].width = 34
for i in range(2, len(crit) + 1):
    ws2.column_dimensions[get_column_letter(i)].width = 26
ws2.freeze_panes = "B2"

# ---------------- Sheet 3: Literature ----------------
ws3 = wb.create_sheet("Literature 2024-2026")
cols3 = ["Title", "Authors", "Year", "Venue", "DOI / ID", "Status", "Method", "Data", "Relevance to our project"]
lit = [
    ["SustainCluster: Benchmarking Dynamic Workload Distribution Techniques for Sustainable Data Center Cluster", "Guillen-Perez, Naug, Gundecha, Sarkar et al. (HPE Labs)", 2025, "NeurIPS D&B", "OpenReview AgTASkryb6", "peer-reviewed",
     "Centralized top-level agent (defer-or-dispatch, 15-min), Gym env, physics DC model, modular rewards", "Alibaba GPU trace 2020 + Electricity Maps CI + GridStatus prices + Open-Meteo", "Closest platform; our delta = decentralization + uncertainty + risk"],
    ["SustainDC: Benchmarking for Sustainable Data Center Control", "Naug et al. (HPE Labs)", 2024, "NeurIPS D&B", "arXiv:2408.07841", "peer-reviewed",
     "MARL within one DC (workload/cooling/battery agents)", "real weather + grid CI traces", "intra-DC agent design reference"],
    ["Green-DCC: Hierarchical Multi-Agent Framework for Carbon-Efficient Liquid-Cooled Data Center Clusters", "Sarkar, Naug, Gundecha et al. (HPE Labs)", 2025, "AAAI", "10.1609/aaai.v39i28.35370", "peer-reviewed",
     "hierarchical RL: cluster-level distribution + DC-level cooling/time-shifting", "real weather + grid carbon", "hierarchical skeleton; still top-down, no uncertainty"],
    ["Caspian: A Carbon-aware Workload Scheduler in Multi-Cluster Kubernetes Environments", "Bahreini, Tantawi et al. (IBM)", 2024, "IEEE/ACM MASCOTS", "10.1109/MASCOTS64422.2024.10786568", "peer-reviewed",
     "optimization-driven multi-cluster scheduling", "multi-cluster sim + CI variability", "19% carbon cut; centralized, deterministic"],
    ["CarbonEdge: Leveraging Mesoscale Spatial Carbon-Intensity Variations for Low Carbon Edge Computing", "Wu, Hanafy, Souza, Nguyen, Harkes, Irwin, Satyanarayanan, Shenoy", 2025, "ACM HPDC", "10.1145/3731545.3731576", "peer-reviewed",
     "mesoscale carbon-aware placement under latency SLOs", "granular CI traces (EU/US), edge testbed", "up to 78.7% cut, <5.5 ms latency increase; centralized"],
    ["On the Limitations of Carbon-Aware Temporal and Spatial Workload Shifting in the Cloud", "Sukprasert, Souza, Bashir, Irwin, Shenoy", 2024, "ACM EuroSys", "10.1145/3627703.3650079", "peer-reviewed",
     "upper-bound analysis of spatiotemporal shifting", "production carbon traces + job distributions", "bounds our achievable savings; temporal > spatial"],
    ["Uncertainty-Aware Decarbonization for Datacenters", "Li, Liu, Zuo, Varghese", 2024, "ACM SIGENERGY Energy Informatics Review", "10.1145/3727200.3727221", "peer-reviewed",
     "conformal prediction for CI forecast uncertainty", "production power/carbon traces", "statistical tool we adopt for calibrated CI bands"],
    ["EnsembleCI: Ensemble Learning for Carbon Intensity Forecasting", "Yan, Wang, Liu, Ding (Purdue)", 2025, "ACM e-Energy", "10.1145/3679240.3734630", "peer-reviewed",
     "ensemble regional CI forecasting", "multi-zone CI data", "plug-in forecaster; point forecasts only"],
    ["LACS: Learning-Augmented Algorithms for Carbon-Aware Resource Scaling with Uncertain Demand", "Bostandoost, Lechowicz, Hanafy, Bashir, Shenoy, Hajiesmaili", 2024, "ACM e-Energy", "10.1145/3632775.3661942", "peer-reviewed",
     "learning-augmented online algorithm, robustness guarantees", "carbon + job traces", "within 1.2% of clairvoyant online; robustness template"],
    ["Carbon-aware scheduling and distributionally robust optimization for cloud systems", "Ruparel et al.", 2026, "J. Cloud Computing (SpringerOpen)", "10.1186/s13677-026-00904-7", "peer-reviewed",
     "DRO + LSTM forecasts + battery, tail-risk", "grid carbon + job traces (sim)", "only 2024-26 DRO+carbon+geo-DC work; single controller"],
    ["Multi-Agent Deep RL Framework for Renewable Energy-Aware Workflow Scheduling on Distributed Cloud Data Centers", "Jayanetti, Halgamuge et al.", 2024, "IEEE TPDS", "10.1109/tpds.2024.3360448", "peer-reviewed",
     "MADRL workflow scheduling across DCs", "trace-driven simulation", "flagship MADRL geo-DC baseline; deterministic signals"],
    ["Two-Timescale Joint Optimization of Task Scheduling and Resource Scaling in Multi-Data Center System Based on MADRL", "Chen, Li et al.", 2024, "IEEE TPDS", "10.1109/TPDS.2024.3467212", "peer-reviewed",
     "two-timescale MADRL (scheduling + scaling)", "production-like traces", "two-timescale idea reusable"],
    ["DynamoLLM: Designing LLM Inference Clusters for Performance and Energy Efficiency", "Stojkovic, Zhang, Goiri, Torrellas, Choukse", 2025, "IEEE HPCA", "10.1109/hpca61900.2025.00102", "peer-reviewed",
     "hierarchical energy control of LLM clusters", "Azure LLM Inference traces", "~52% energy / ~38% carbon savings; single-DC"],
    ["TAPAS: Thermal- and Power-Aware Scheduling for LLM Inference in Cloud Platforms", "Stojkovic et al.", 2025, "ACM ASPLOS", "10.1145/3676641.3716025", "peer-reviewed",
     "thermal/power-aware LLM scheduling", "Azure LLM traces", "thermal realism for our GPU racks"],
    ["EcoServe: Designing Carbon-Aware AI Inference Systems", "Li, Hassan, Las-Casas et al. (Microsoft)", 2025, "arXiv preprint", "arXiv:2502.05043", "preprint",
     "operational+embodied carbon accounting for GenAI serving", "production GenAI traces", "batch ≈55% of serving capacity → deferrable share"],
    ["PecSched: Preemptive and Efficient Cluster Scheduling for LLM Inference", "et al.", 2024, "arXiv preprint", "arXiv:2409.15104", "preprint",
     "preemptive LLM serving scheduling", "Azure LLM trace", "p99 queueing −92%; trace-informed latency models"],
    ["Characterizing Power Management Opportunities for LLMs in the Cloud", "Patel, Choukse, Zhang, Goiri et al. (Microsoft)", 2024, "ACM ASPLOS", "10.1145/3620666.3651329", "peer-reviewed",
     "production characterization; origin of Azure LLM trace", "Azure production", "trace provenance"],
    ["CAFE: Carbon-Aware Federated Learning in Geographically Distributed Data Centers", "Bian, Wang, Ren, Xu", 2024, "ACM e-Energy", "10.1145/3632775.3661970", "peer-reviewed",
     "CI-driven FL client scheduling", "public CI + benchmarks", "decentralized learning + CI precedent"],
    ["FedZero: Leveraging Renewable Excess Energy in Federated Learning", "Wiesner et al. (TU Berlin)", 2024, "ACM e-Energy", "10.1145/3632775.3639589", "peer-reviewed",
     "renewable-excess-aware FL scheduling", "renewable signals", "region-matched renewable scheduling precedent"],
    ["LinTS: Carbon-Aware Temporal Data Transfer Scheduling Across Cloud Datacenters", "Rodrigues et al.", 2025, "IEEE CLOUD", "10.1109/cloud67622.2025.00034", "peer-reviewed",
     "carbon-aware transfer scheduling", "cloud transfer scenarios", "network-side actor; transfer-carbon trade-off"],
    ["ML Training with Cloud GPU Shortages: Is Cross-Region the Answer?", "Strati, Elvinger, Kerimoglu, Klimovic (ETH)", 2024, "EuroMLSys @ EuroSys", "10.1145/3642970.3655843", "peer-reviewed workshop",
     "analytical cross-region GPU training model", "profiling", "justifies transfer cost/bandwidth constraints"],
    ["Data center workload flexibility for power system demand response: Evidence from Alibaba traces", "Caprara, Yu et al.", 2026, "Int. J. Electrical Power & Energy Systems", "10.1016/j.ijepes.2026.111940", "peer-reviewed",
     "flexibility quantification from Alibaba traces", "Alibaba production traces", "validates deferrability of GPU workloads"],
    ["GreenFlow: A Carbon-Efficient Scheduler for Deep Learning Workloads", "Gu, Zhao, Sun et al.", 2024, "IEEE TPDS", "10.1109/tpds.2024.3470074", "peer-reviewed",
     "carbon-budget GPU packing", "testbed + traces", "single-cluster GPU carbon scheduling"],
    ["F2S-WSS: forecast-driven two-stage workload scheduling for carbon-aware geo-distributed DCs", "Zhai, Zhu, Zhang", 2025, "Sustainable Computing: Informatics and Systems", "10.1016/j.suscom.2025.101216", "peer-reviewed",
     "wind-forecast-driven two-stage scheduling", "wind + CI data", "closest forecast+two-stage relative; no risk term"],
    ["Dissecting the Carbon-SLO Tension in Geo-Distributed LLM Serving", "Topçu et al.", 2026, "arXiv preprint", "arXiv:2610.14571", "preprint",
     "latency-centric geo-LLM simulator", "hardware-grounded engine models", "simulator fidelity warning for our evaluation"],
    ["HealthServe: A Public Health-Aware Inference Framework", "Zhou, Roy, Tiwari et al.", 2026, "ACM SIGMETRICS (POMACS)", "10.1145/3805638", "peer-reviewed",
     "carbon+health-aware geo-LLM serving", "grid + health data", "extends objective space"],
    ["Going Green for Less Green: Optimizing the Cost of Reducing Cloud Carbon Emissions", "Hanafy et al. (MIT/UMass)", 2024, "ACM ASPLOS", "10.1145/3620666.3651374", "peer-reviewed",
     "cost-optimal carbon reduction via reservations", "cloud traces", "economic envelope"],
    ["On the Implications of Choosing Average vs Marginal Carbon Intensity Signals", "Sukprasert et al.", 2024, "ACM e-Energy (notes)", "10.1145/3632775.3661953", "peer-reviewed",
     "avg vs marginal CI comparison", "US grids", "signal-choice defense needed in our evaluation"],
    ["The Green Mirage", "Maji, Bashir, Irwin, Shenoy, Sitaraman", 2024, "ACM e-Energy", "10.1145/3632775.3639587", "peer-reviewed",
     "location- vs market-based CI estimation", "US grids", "carbon-accounting caveat"],
    ["The Sunk Carbon Fallacy", "Bashir et al.", 2024, "ACM SoCC", "10.1145/3698038.3698542", "peer-reviewed",
     "footprint metric distortions", "cloud data", "accounting caveat"],
]
for c, name in enumerate(cols3, 1):
    cell = ws3.cell(row=1, column=c, value=name)
    cell.fill, cell.font, cell.alignment = HDR_FILL, HDR_FONT, WRAP
for r, row in enumerate(lit, 2):
    for c, val in enumerate(row, 1):
        cell = ws3.cell(row=r, column=c, value=val)
        cell.font, cell.alignment = BODY_FONT, WRAP
widths3 = [44, 30, 7, 22, 28, 14, 40, 28, 40]
for i, w in enumerate(widths3, 1):
    ws3.column_dimensions[get_column_letter(i)].width = w
ws3.freeze_panes = "A2"

# ---------------- Sheet 4: Sources ----------------
ws4 = wb.create_sheet("Key sources")
cols4 = ["Source", "Type", "URL", "Access", "Verified"]
srcs = [
    ["NESO Carbon Intensity API", "API", "https://api.carbonintensity.org.uk", "Free, no key, CC BY 4.0", "Yes [V]"],
    ["Carbon Intensity homepage/methodology", "Docs", "https://carbonintensity.org.uk", "Free", "Yes [V]"],
    ["Elexon BMRS Insights API", "API", "https://data.elexon.co.uk/bmrs/api/v1/", "Free, no key", "Yes [S]"],
    ["Azure LLM Inference Trace 2024", "Dataset", "https://github.com/Azure/AzurePublicDataset/blob/master/AzureLLMInferenceDataset2024.md", "Free, CC BY 4.0", "Yes [V]"],
    ["AzurePublicDataset repo", "Dataset hub", "https://github.com/Azure/AzurePublicDataset", "Free, CC BY 4.0", "Yes [S]"],
    ["Alibaba clusterdata", "Dataset", "https://github.com/alibaba/clusterdata", "Free (research clause)", "Yes [S]"],
    ["Google cluster-data v3", "Dataset", "https://github.com/google/cluster-data", "Free, CC BY 4.0", "Yes [S]"],
    ["Grid Workloads Archive (Bitbrains) mirror", "Dataset", "https://atlarge-research.com/gwa-traces/", "Free", "Yes [S]"],
    ["EIA-930 bulk CSVs", "Dataset", "https://www.eia.gov/electricity/gridmonitor/", "Free, no key", "Yes [V]"],
    ["EPA eGRID2023", "Dataset", "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx", "Free", "Yes [S]"],
    ["CAISO Today's Outlook", "API", "https://www.caiso.com/outlook/history/20200101/co2.csv", "Free, no key", "Yes [S]"],
    ["Energy-Charts API", "API", "https://api.energy-charts.info", "Free, no key", "Yes [S]"],
    ["Fingrid Open Data", "API", "https://data.fingrid.fi", "Free key (registration)", "Docs verified [S]"],
    ["ENTSO-E Transparency", "API", "https://transparency.entsoe.eu", "Free token", "Docs verified [S]"],
    ["OpenElectricity (OpenNEM)", "API", "https://api.opennem.org.au", "Free, keyless", "Yes [S]"],
    ["Waseda Japan CI dataset", "Dataset", "https://zenodo.org/records/18396311", "Free, CC BY 4.0", "Record verified [S]"],
    ["Electricity Maps pricing", "Commercial", "https://www.electricitymaps.com/pricing", "Paid (€6k/yr/country)", "Yes [S]"],
    ["WattTime data plans", "Commercial", "https://www.watttime.org/docs-dev/data-plans/", "Free tier = CAISO_NORTH", "Yes [S]"],
    ["NLR GenAI power profiles", "Dataset", "https://data.nlr.gov/submissions/312", "Free (DOE licence)", "Yes [S]"],
    ["Harvard GPU power metrics", "Dataset", "https://doi.org/10.7910/DVN/RNGJFI", "Free, CC0", "Yes [S]"],
    ["GPU-DVFS-Dataset", "Dataset", "https://github.com/zyjopensource/GPU-DVFS-Dataset", "Free", "Yes [S]"],
    ["Google region-carbon-info", "Dataset", "https://github.com/GoogleCloudPlatform/region-carbon-info", "Free", "Yes [S]"],
    ["Google DC efficiency (PUE)", "Docs", "https://www.google.com/about/datacenters/efficiency/", "Free", "Yes [S]"],
    ["Ireland CSO MEC02", "Dataset", "https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/MEC02/CSV/1.0/en", "Free", "Yes [S]"],
    ["Azure region latency", "Docs", "https://learn.microsoft.com/en-us/azure/networking/azure-network-latency", "Free", "Yes [S]"],
    ["azurespeed RTT matrix", "Tool", "https://www.azurespeed.com/Azure/RegionToRegionLatency", "Free", "Yes [S]"],
    ["cloudping.co", "Tool", "https://www.cloudping.co", "Free UI", "Yes [S]"],
    ["RIPE Atlas", "API", "https://atlas.ripe.net", "Free account + credits", "Docs verified [S]"],
    ["SustainCluster repo", "Code", "https://github.com/HewlettPackard/sustain-cluster", "Free, MIT", "Yes [V]"],
    ["SustainCluster paper", "Paper", "https://openreview.net/forum?id=AgTASkryb6", "Free", "Yes [S]"],
    ["SustainDC paper", "Paper", "https://arxiv.org/abs/2408.07841", "Free (arXiv)", "Yes [S]"],
    ["Grid-India reports", "Docs", "https://grid-india.in", "Free", "Yes [S]"],
    ["CEA CO2 Baseline Database", "Docs", "https://cea.nic.in/cdm-co2-baseline-database/", "Free", "Yes [S]"],
    ["EU EED reporting platform", "Docs", "https://policy-reporting-platform.ec.europa.eu/Reporting/web/screen/home:registration", "Free (aggregate)", "Yes [S]"],
]
for c, name in enumerate(cols4, 1):
    cell = ws4.cell(row=1, column=c, value=name)
    cell.fill, cell.font, cell.alignment = HDR_FILL, HDR_FONT, WRAP
for r, row in enumerate(srcs, 2):
    for c, val in enumerate(row, 1):
        cell = ws4.cell(row=r, column=c, value=val)
        cell.font, cell.alignment = BODY_FONT, WRAP
for i, w in enumerate([34, 14, 70, 30, 18], 1):
    ws4.column_dimensions[get_column_letter(i)].width = w
ws4.freeze_panes = "A2"

wb.save(OUT)
print("saved", OUT)
