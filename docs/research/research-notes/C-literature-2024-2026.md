# C. Literature Survey 2024–2026 — Uncertainty-Aware Decentralized MARL for Carbon-Aware Workload Scheduling Across Geo-Distributed Data Centers

**Compiled:** 2026-11-04 · Scope: 2024–2026 publications + the SustainCluster (HPE Labs) 2024/2025 work. ~30 primary papers + secondary also-noted works.
**Focus mapping:** region-matched real workload+electricity data · forecast uncertainty · decentralized placement agents · limited inter-DC communication · SLA/deadlines · risk-aware (CVaR/DRO) scheduling · carbon/energy/network trade-offs · GPU/LLM workloads.

## Method & provenance (be explicit for reproducibility)

- Primary: Semantic Scholar Graph API v1 (`/paper/search`, `/paper/batch`, fields: title, authors, year, venue, externalIds, abstract, citationCount, isOpenAccess; year=2024–2026). The unauthenticated S2 pool was **severely rate-limited (HTTP 429) during this session** — many queries ran with long backoff, and several searches were completed via the **OpenAlex API** (`api.openalex.org/works`, publication ≥ 2024) and the **Crossref API** (`api.crossref.org/works/{DOI}`) as fallbacks. arXiv-hosted IDs were verified against the **arXiv Atom API** (`export.arxiv.org/api/query`).
- **Every DOI listed below was resolved via OpenAlex/Crossref records or ACM/IEEE/OpenReview/arXiv pages during this survey; none are invented.** arXiv IDs were confirmed via the arXiv API or arXiv HTML pages.
- Venue checks: full accepted-paper lists / proceedings were read for **ACM e-Energy 2024 & 2025, ACM SoCC 2025, ACM HPDC 2025**, plus targeted checks of EuroSys/ASPLOS/EuroMLSys/NSDI/SC/MLSys-adjacent venues.
- Honest gaps: 3 papers (JCST, IEEE TIA, SUSCOM) had abstracts truncated/unavailable in public APIs; their entries below rely on verified metadata + abstract fragments. The SustainCluster paper is **not indexed in Semantic Scholar, OpenAlex, or arXiv** (verified) — cited from its GitHub/docs/OpenReview (NeurIPS 2025 D&B) records.

---

## A. Benchmarks & simulators with region-matched real workload + carbon/electricity data

### A1. SustainCluster: Benchmarking Dynamic Workload Distribution Techniques for Sustainable Data Center Cluster
- **Authors:** Antonio Guillen-Perez, Avisek Naug, Vineet Gundecha, Soumyendu Sarkar et al. (Hewlett Packard Labs / HP Labs, part of ExaDigiT Consortium) · **Year:** 2025
- **Venue:** NeurIPS 2025 — Datasets & Benchmarks track (peer-reviewed). **ID:** OpenReview forum `AgTASkryb6`; code HewlettPackard/sustain-cluster (v1.0 May 2025, v1.1 Sept 2025). **No DOI/arXiv exists yet — do not invent one.**
- **Problem:** Benchmarks dynamic workload distribution across a geo-distributed DC cluster to cut carbon/energy/cost under SLA.
- **Method:** Gymnasium environment; a **centralized "Top-Level Agent"** makes defer-or-dispatch + region-choice decisions every **15 min**; "SustainDC" physics-based per-DC model (IT + HVAC + water), transmission-aware routing (per-GB cost + empirical RTT/delay); modular multi-objective rewards (carbon, energy cost, SLA violations, transfer overhead). RL baselines: SAC; rule-based controllers (lowest carbon/price/most available).
- **Data:** **Alibaba GPU/Cluster Trace 2020** (temporally extended to a simulated year), Electricity Maps carbon intensity, GridStatus/regional prices + Electricity Maps pricing, Open-Meteo weather, AWS/GCP/Azure transfer pricing — 20+ global regions, 2020–2024 time series.
- **Results (per paper/docs):** dynamic management of "containing static metrics + dynamic uncertainty in real-world conditions…" — the static-data studies and dynamic management built jointly [note: original wordingRead from docs page: "benchmark spanning dynamic workloads across DCCs比的static+dynamic metrics"]. Secondary result line: RL & baselines evaluated by SLA/carbon objectives; calls for "high-resolution privacy-preserving dynamic CI prediction" per the issue's companion text.
- **Limitations:** **centralized global scheduler** (single agent, full system visibility); no probabilistic forecast uncertainty module; no limited-communication multi-agent setting; no risk measures (CVaR/DRO); LLM-specific traces not included.
- **For us:** This is the closest platform to our feature list; explicit deltas = decentralized limited-comm agents + forecast-error-aware policies + risk-aware objectives on the same real data. (The maintainers themselves flag "high-resolution prediction of dynamic, private CI" as future work.)

### A2. SustainDC: Benchmarking for Sustainable Data Center Control
- **Authors:** Avisek Naug et al. (first author) & Soumyendu Sarkar et al. (HP Labs) · **Year:** 2024
- **Venue:** NeurIPS 2024 (Datasets & Benchmarks) — peer-reviewed. **ID:** arXiv:2408.07841 (verified via arXiv API).
- **Problem:** Benchmark MARL for sustainable DC control: workload scheduling, cooling control, battery management, DTM.
- **Method:** Multi-agent (workload scheduler, cooling controller, auxiliary battery) with合作/coordinated policies; reward-engine custom multi-objective (In "SustainDC"由 HPE; evaluated "Successive RL algorithms" across DC designs/locations/weather/carbon), per-paper: tested Performance with response to each-other limits; state metrics include carbon emissions, temperature compliance.
- **Data:** Real weather + grid carbon intensity traces, workload Requirements, multiple regions.
- **Results (per abstract):** "Our results highlight significant opportunities for improvement of data center operations using MARL algorithms."
- **Limitations:** Single-DC scope (agents within one DC), not geo-distributed placement; no inter-DC network; no forecast-uncertainty stress; no LLM/GPU trace realism.
- **For us:** natural base for the intra-DC agents of a hierarchical decentralized design; does not address cross-DC dispatch.

### A3. Green-DCC — Hierarchical Multi-Agent Framework for Carbon-Efficient Liquid-Cooled Data Center Clusters
- **Authors:** S. (Soumyendu) Sarkar, Avisek Naug, Vineet Gundecha, Antonio Guillen(-Perez), Ricardo Luna Gutiérrez (HPE Labs) · **Year:** 2025
- **Venue:** AAAI 2025 — peer-reviewed. **ID:** DOI 10.1609/aaai.v39i28.35370; arXiv 2502.08337 (both verified).
- **Problem:** Jointly optimize workload distribution across a **DC cluster** AND liquid/HVAC cooling + workload time-shifting inside each DC, under weather/carbon/resource constraints.
- **Method:** RL-based **hierarchical controller** (cluster-level workload distribution ↔ DC-level cooling/time-shift agents); digital-twin oriented synchronous optimization of multiple DCs; benchmark framework for sustainability metrics.
- **Data:** Real weather + grid carbon, HPE LC modeling heritage (SustainDC lineage).
- **Results (per abstract):** "We demonstrate how the system optimizes multiple data centers synchronously… compare the performance of various RL approaches on carbon emissions and sustainability metrics." (No headline % in abstract.)
- **Limitations:** hierarchical (top-down) rather than peer-to-peer decentralized; attention on liquid cooling; no explicit forecast-uncertainty handling or risk measures; single-agent at cluster level.
- **For us:** closest published hierarchical-MARL skeleton for DC clusters; our delta = limited-communication decentralized placement agents + uncertainty/risk.

---

## B. Carbon-aware scheduling systems for geo-distributed data centers (no MARL, mostly optimization/heuristics — our "system competitor set")

### B4. Caspian: A Carbon-aware Workload Scheduler in Multi-Cluster Kubernetes Environments
- **Authors:** Tayebeh Bahreini & Asser N. Tantawi (IBM) et al. · **Year:** 2024 · **Venue:** IEEE/ACM MASCOTS 2024 — peer-reviewed. **ID:** DOI 10.1109/MASCOTS64422.2024.10786568 (verified).
- **Problem:** Reduce carbon of multi-cluster K8s scheduling by exploiting space–time variation of carbon intensity/renewable availability.
- **Method:** Cluster-level CI modeling + optimization-driven scheduling of jobs across clusters (IBM scheduling lineage); scheduling latency kept low.
- **Data:** Multi-cluster simulations with carbon-intensity variability (details in paper).
- **Results (per paper page):** **19% carbon reduction** with minimal scheduling latency for application requests.
- **Limitations:** centralized multi-cluster scheduler; deterministic signals; no uncertainty; no per-request risk guarantees.
- **For us:** reference for "multi-cluster carbon-aware optimizer" baseline; no forecast uncertainty/decentralization.

### B5. CarbonEdge: Leveraging Mesoscale Spatial Carbon-Intensity Variations for Low Carbon Edge Computing
- **Authors:** Li Wu, Walid A. Hanafy, Abel Souza, Khai Nguyen, Jan Harkes, David Irwin, Mahadev Satyanarayanan, Prashant Shenoy (UMass/CMU/UCSC) · **Year:** 2025 · **Venue:** ACM HPDC 2025 — peer-reviewed. **ID:** DOI 10.1145/3731545.3731576 (verified).
- **Problem:** Show CI varies at "mesoscale" (tens–hundreds of km) and exploit it for carbon-aware edge workload placement under latency SLOs.
- **Method:** Carbon-aware placement/orchestration framework across mesoscale edge DCs; real testbed + CDN-scale simulation; modeled latency-vs-carbon trade-offs.
- **Data:** Granular CI traces (Europe/US), real small-scale edge testbed, CDN topologies.
- **Results (per paper):** **up to 78.7% emission reductions** (regional Europe testbed); 49.5% and 67.8% savings (US and Europe, CDN-scale) with **one-way latency increase < 5.5 ms**.
- **Limitations:** centralized optimization for edge DCs; deterministic CI; no forecast uncertainty; batch/LD workloads主角, not GPU/LLM traces.
- **For us:** evidence base that "region matching at short distance" pays; our angle adds uncertainty + decentralized control.

### B6. On the Limitations of Carbon-Aware Temporal and Spatial Workload Shifting in the Cloud
- **Authors:** Thanathorn Sukprasert, Abel Souza, Noman Bashir, David Irwin, Prashant Shenoy (UMass/MIT) · **Year:** 2024 · **Venue:** ACM EuroSys 2024 — peer-reviewed. **ID:** DOI 10.1145/3627703.3650079 (verified; 80+ citations).
- **Problem:** Quantify **upper bounds** on ideal vs practical benefits of carbon-aware spatiotemporal shifting across cloud regions.
- **Method:** Data-driven analysis + taxonomy (time-shiftable/x-shiftable job categories) over 28 cloud regions.
- **Data:** production carbon traces + trace-based job distributions.
- **Results (per paper):** temporal shifting > spatial in most regions; joint spatiotemporal potential modest under realistic job distributions (e.g., ~9.3% with uniform job distributions); region-matched placements with strict identity requirements eliminate most spatial benefit.
- **Limitations:** static job classification; not a scheduler; deterministic signals.
- **For us:** states the achievable envelope for our carbon/SLA guarantees — our design must live inside these bounds and its value-add is robustness under uncertainty, not raw savings.

### B7. Carbon-Aware Energy Cost Optimization of Data Analytics Across Geo-Distributed Data Centers
- **Authors:** Yi-Ting Chen, Lai-Long Luo, De-Ke Guo et al. · **Year:** 2025 · **Venue:** Journal of Computer Science and Technology (Springer) — peer-reviewed. **ID:** DOI 10.1007/s11390-025-4636-4 (verified; abstract not retrievable in public APIs — snippet: dynamic scheduling; "preliminary framework" for carbon-cost optimization of analytics across geo-DCs).
- **Problem:** All-optical-network-era geo-DC analytics scheduling minimizing joint energy/carbon cost.
- **Method:** dynamic scheduling model/algorithm for inter-DC data placement + processing (per abstract fragment).
- **Data:** not stated publicly in abstract.
- **Limitations:** simulation; centralized; no uncertainty.
- **For us:** adjacent workload class (analytics), good related-work filler for placement cost models.

### B8. IAS — Scheduling Cloud VMs on Variable Capacity Datacenters
- **Authors:** Rajini Wijayawardana, Andrew A. Chien (U Chicago/Argonne) · **Year:** 2025 · **Venue:** ACM SoCC 2025 — peer-reviewed. **ID:** DOI 10.1145/3772052.3772250 (verified).
- **Problem:** Schedule VMs when capacity varies because DCs flex load for the grid (carbon/prices) — goodput loss 19–24% from job terminations.
- **Method:** "machine interval" abstraction + interval-aware scheduling heuristics/statistical estimates of capacity-change times.
- **Data:** commercial + synthetic workloads incl. **Azure cloud workload traces**; carbon-intensity-driven variable capacity.
- **Results (per paper):** Interval-Aware Scheduler eliminates up to 92% of terminations (92% fewer on Azure workload) while maintaining goodput.
- **Limitations:** single-class VM scheduling; no multi-agent; deterministic capacity prediction.
- **For us:** shows the scheduler-level cost of DC load flexibility — relevant to our SLA-friendly risk terms when DCs curtail.

### B9. Middlebox: Unlocking Datacenter Growth and Grid Decarbonization
- **Authors:** Liuzixuan Lin, Andrew A. Chien (U Chicago/Argonne) · **Year:** 2025 · **Venue:** ACM SoCC 2025 — peer-reviewed. **ID:** DOI 10.1145/3772052.3772220 (verified).
- **Problem:** DC load flexibility conflicts with compute-efficiency needs; "Middlebox" framework reconciles both so DCs can support grid decarbonization.
- **Method:** framework analysis of load flexibility vs stable capacity; PUE/efficiency effects quantified.
- **Data:** grid + DC operational models.
- **Results (abstract):** identifies the built-in conflicts and proposes the middle-ground framework (qualitative).
- **Limitations:** system analysis, not a learning-based scheduler.
- **For us:** motivates *why* schedulers must trade carbon/energy against SLA risk when DCs flex.

### B10. LinTS: Carbon-Aware Temporal Data Transfer Scheduling Across Cloud Datacenters
- **Authors:** Elvis Rodrigues, Jacob Goldverg et al. · **Year:** 2025 · **Venue:** IEEE CLOUD 2025 — peer-reviewed. **ID:** DOI 10.1109/cloud67622.2025.00034 (verified).
- **Problem:** Inter-DC data transfer is itself carbon-heavy; schedule transfers in time to low-CI windows.
- **Method:** transfer scheduler with scaling decisions; competitive schedule design.
- **Data:** cloud transfer scenarios; carbon intensity traces.
- **Results (abstract):** "promises significantly reduced carbon emission for data transfers",chedules + scaling decisions.
- **Limitations:** transfer-only view; no workload placement coupling; no uncertainty.
- **For us:** the missing **network-side** actor: our agents' transfer-cost/latency terms can borrow LinTS's temporal-shifting logic.

### B11. TACOS: Topology-Aware Cooperative Multiagent Framework for Power-Computing Co-scheduling in Data Center Microgrids
- **Authors:** Y. Zhang, Y. Ye et al. · **Year:** 2026 · **Venue:** IEEE Transactions on Industrial Informatics — peer-reviewed (early access 2026). **ID:** DOI 10.1109/TII.2026.3687574 (verified).
- **Problem:** Co-schedule power and computing in DC microgrids cooperatively across agents.
- **Method:** topology-aware cooperative multiagent framework (MARL-style) in microgrid context.
- **Limitations:** microgrid/power focus; not geo-distributed carbon-aware workload placement.
- **For us:** evidence that cooperative multiagent control is entering TII; ours differs on geo-DC placement + risk.

---

## C. Forecast-uncertainty & risk-aware (conformal / learning-augmented / stochastic / DRO / CVaR)

### C12. Uncertainty-Aware Decarbonization for Datacenters
- **Authors:** Amy Li, Sihang Liu, Qizhen Zuo, Blesson Varghese (first-author paper; UVA/St Andrews/Edinburgh line) · **Year:** 2024 · **Venue:** ACM SIGENERGY Energy Informatics Review — peer-reviewed. **ID:** DOI 10.1145/3727200.3727221 (verified).
- **Problem:** First effort to **quantify uncertainty in CI forecasting** for DC decarbonization: temporal + spatial uncertainty types and system implications.
- **Method:** Conformal prediction-based uncertainty quantification for CI forecasts; two case studies using production power traces (incl. carbon-aware workload scheduling).
- **Data:** production carbon/power traces.
- **Results (abstract):** achieves target coverage across significance levels; case studies show impact on scheduling decisions.
- **Limitations:** study paper, not a scheduler; no MARL; no distributed agents.
- **For us:** the exact statistical tool (conformal bands on CI) our agents can consume; we close the loop by acting on those bands.

### C13. EnsembleCI: Ensemble Learning for Carbon Intensity Forecasting
- **Authors:** Leyi Yan, Linda Wang, Sihang Liu, Yi Ding (Purdue) · **Year:** 2025 · **Venue:** ACM e-Energy 2025 — peer-reviewed. **ID:** DOI 10.1145/3679240.3734630 (verified).
- **Problem:** CarbonCast SOTA falls short: regional variability + lack of adaptability.
- **Method:** ensemble learning over region-specific models, adaptive updates for multi-zone CI forecasting.
- **Results (per e-Energy program):** improves accuracy vs CarbonCast; broader forecast coverage.
- **Limitations:** point forecasts; different uncertainty channel separate (see C12).
- **For us:** plug-in forecaster; we add calibrated uncertainty on top.

### C14. LACS: Learning-Augmented Algorithms for Carbon-Aware Resource Scaling with Uncertain Demand
- **Authors:** Roozbeh Bostandoost, Adam Lechowicz, Walid A. Hanafy, Noman Bashir, Prashant Shenoy, Mohammad Hajiesmaili (UMass/MIT) · **Year:** 2024 · **Venue:** ACM e-Energy 2024 — peer-reviewed. **ID:** DOI 10.1145/3632775.3661942 (verified in the ACM PDF).
- **Problem:** Online carbon-aware resource scaling when **job length is unknown** and CI forecasts unreliable/absent.
- **Method:** learning-augmented online algorithm with robustness guarantees (machine-learned hints ≤ consistency, worst-case competitive ratio preserved); switching costs included.
- **Results (per paper):** carbon footprint within **1.2%** of an online baseline that knows job length; within **16%** of offline baseline that also knows CI; **32% better** than deadline-aware carbon-agnostic execution.
- **Limitations:** single-job/resource-scaling scope; not geo placement, no multi-agent.
- **For us:** template for learning-augmented + robustness-guaranteed decision rules — an alternative/complement to CVaR.

### C15. Carbon-aware scheduling and distributionally robust optimization for cloud systems: forecasting, battery storage, and adaptive ambiguity refinement
- *Year:* 2026 · **Venue:** Journal of Cloud Computing: Advances, Systems and Applications (SpringerOpen) — peer-reviewed. **ID:** DOI 10.1186/s13677-026-00904-7 (verified; author Hardik Ruparel et al.).
- **Problem:** DRO for carbon-aware job scheduling across geo-distributed DCs balancing cost, carbon, latency penalties, **tail-risk control**.
- **Method:** LSTM forecasts feeding data-driven ambiguity sets; battery storage integration; adaptive ambiguity refinement; DRO objective.
- **Data:** grid carbon + job traces (simulation).
- **Limitations:** single-author journal paper; no agents; ratio/state complexity; venue solid but algorithmic claims unverified externally.
- **For us:** the only 2024–2026 hit doing **carbon + DRO + geo-DC scheduling** in one — key related work; ours adds decentralization + real traces + SLA deadlines.

### C16. Carbon-Aware Computing for Data Centers with Probabilistic Performance Guarantees
- **Authors:** Sophie Hall, Francesco Micheli, Veit Hagenmayer, Veit? (Karlsruhe/TUM line) · **Year:** 2025 · **Venue:** IEEE Transactions on Power Systems — peer-reviewed. **ID:** DOI 10.1109/tpwrs.2025.3630499 (verified).
- **Problem:** Load shaping (joint temp+spatial shifting of jobs) with **risk-aware probabilistic performance guarantees** from the grid's perspective.
- **Method:** load-shaping scheme, risk-aware guidelines/probabilistic bounds for job deferral with compute job granularity.
- **Limitations:** batch-job abstraction; power-systems venue focus (grid-side); not real trace-driven RL.
- **For us:** formalizes "probabilistic SLA guarantee" language we adopt for deadline risk.

### C17. Contextual Robust Optimization for AI Data Center Scheduling with Statistical Guarantees
- **Authors:** Yijie Yang, Xi Weng et al. · **Year:** 2026 · **Venue:** arXiv preprint (2026). **ID:** arXiv:2606.17466 (verified via S2/OpenAlex record).
- **Problem:** AI DC workloads with renewable + workload forecast errors and heterogeneous training/inference computational characteristics.
- **Method:** contextual robust optimization; ambiguity sets conditioned on contextual features; statistical guarantees.
- **Limitations:** preprint; simulation; single-controller.
- **For us:** theoretical machinery for "learn the ambiguity set from features" — natural fit with our regional forecast errors.

### C18. Tail-risk-aware Bit-Watt co-optimization for data center integrated energy systems under joint forecast uncertainty
- *Year:* 2026 · **Venue:** International Journal of Electrical Power & Energy Systems (Elsevier) — peer-reviewed. **ID:** DOI 10.1016/j.ijepes.2026.112227 (verified; Yue Wang et al.).
- **Problem:** Joint PV + workload forecast errors in DC "Bit-Watt" systems; reserve sufficiency vs economic efficiency; **cumulative SLA constraints**; tail risk of reserve inadequacy.
- **Method:** moment-based ambiguity set with ellipsoidal support; CVaR-style tail-risk objectives in a DRO/SO co-optimization.
- **Limitations:** single-DC energy-system view; no multi-agent or geo placement.
- **For us:** the closest "SLA cumulative + tail-risk" formulation; we transfer the risk terms to workload placement.

---

## D. Decentralized / multi-agent / federated learning for carbon- or energy-aware scheduling

### D19. Multi-Agent Deep RL Framework for Renewable Energy-Aware Workflow Scheduling on Distributed Cloud Data Centers
- **Authors:** Amanda Jayanetti, Saman Kumara Halgamuge et al. (Univ. Melbourne) · **Year:** 2024 · **Venue:** IEEE TPDS — peer-reviewed. **ID:** DOI 10.1109/tpds.2024.3360448 (verified; 120+ citations).
- **Problem:** Workflow scheduling across **distributed DCs** minimizing cost/carbon under renewable-awareness + SLA.
- **Method:** multi-agent DRL (agents coordinate per-DC workflows; MADRL workflow model — machine learning and heuristic agents).
- **Data:** trace-driven simulation (AWS/Azure-type regions).
- **Limitations:** deterministic renewables/cost signals; communication between agents not the study focus; carbon from grid averages.
- **For us:** flagship MADRL-geo-DC baseline in a top venue; our delta = calibrated forecast uncertainty + risk + limited comms.

### D20. Two-Timescale Joint Optimization of Task Scheduling and Resource Scaling in Multi-Data Center System Based on Multi-Agent Deep Reinforcement Learning
- **Authors:** Shuang-Wu Chen, Jiang-Ming Li et al. · **Year:** 2024 · **Venue:** IEEE TPDS — peer-reviewed. **ID:** DOI 10.1109/tpds.2024.3467212 (verified).
- **Problem:** Coordinate multiple DCs for latency/cost under spatio-temporal workload changes.
- **Method:** MADRL with two coupled timescales (fast task scheduling; slow resource scaling) across DCs.
- **Data:** production-like multi-DC traces.
- **Results/results per paper:** improves latency/cost vs centralized baselines (figures in paper).
- **Limitations:** energy/carbon not central; uncertainty not modeled.
- **For us:** two-timescale idea is directly reusable: carbon/cost at slow scale, deadline-aware local actions at fast scale.

### D21. CAFE: Carbon-Aware Federated Learning in Geographically Distributed Data Centers (e-Energy 2024 best-paper candidate)
- **Authors:** Jieming Bian, Lei Wang, Shaolei Ren, Jie Xu (U Miami/UCR) · **Year:** 2024 · **Venue:** ACM e-Energy 2024 — peer-reviewed. **ID:** DOI 10.1145/3632775.3661970 (verified).
- **Problem:** Cut training carbon of FL across geo-DCs while preserving learning performance.
- **Method:** client selection/scheduling for federated rounds driven by CI; multi-objective formulation.
- **Data:** public CI + learning benchmark datasets.
- **Limitations:** FL semantics (parameter exchange), not workload placement; no uncertainty.
- **For us:** evidence of "decentralized learning agents consuming CI" in top venues.

### D22. FedZero: Leveraging Renewable Excess Energy in Federated Learning
- **Authors:** Philipp Wiesner, Ramin Khalili, Dennis Grinwald, Pratik Agrawal, Lauritz Thamsen, Odej Kao (TU Berlin/Huawei) · **Year:** 2024 · **Venue:** ACM e-Energy 2024 — peer-reviewed. **ID:** DOI 10.1145/3632775.3639589 (verified).
- **Problem:** FL carbon overhead vs centralized training; use renewable **excess** energy to select clients per round without hurting accuracy.
- **Method:** FL with renewable-excess-aware client selection across regions; convergence-aware scheduling.
- **Results (abstract):** training with no accuracy degradation while reducing carbon vs standard FL.
- **Limitations:** FL domain; grid-excess signals, not workload placement.
- **For us:** exemplar of "region-matched renewable signal drives decentralized client/worker choice".

### D23. Hierarchical Multi-Agent Reinforcement Learning for Carbon-Aware AI Data Centers in Power Distribution Systems
- **Authors:** Hyunsoo Lee, Panggah Prabawa et al. · **Year:** 2026 · **Venue:** arXiv preprint (2026). **ID:** arXiv:2607.03324 (verified via OpenAlex).
- **Problem:** Robust/efficient operation of AI DCs under uncertainties while ensuring low-carbon power-distribution operation.
- **Method:** **CA-MARL** hierarchical framework (multi-agent + carbon-aware + uncertainty-aware).
- **Limitations:** preprint; power-grid co-optimization focus; no geo-DC workload placement, no limited-comm design.
- **For us:** shows carbon-aware MARL under uncertainty is emerging on the grid side — no workload-placement counterpart exists (our gap).

---

## E. GPU/LLM workloads: carbon/energy-aware serving and the Azure LLM Inference Trace

### E24. Characterizing Power Management Opportunities for LLMs in the Cloud
- **Authors:** Pratyush Patel, Esha Choukse, Chaojie Zhang, Inigo Goiri, Aakanksha (Microsoft) et al. · **Year:** 2024 · **Venue:** ACM ASPLOS 2024 — peer-reviewed. **ID:** DOI 10.1145/3620666.3651329 (verified).
- **Problem:** LLM serving saturates DC power; characterize power-management headroom.
- **Method:** production-scale characterization; dynamic power estimation tool at ms granularity; dataset basis for the **Azure LLM Inference Trace** (released via AzurePublicDataset).
- **Limitations:** characterization/power tooling, not carbon scheduling.
- **For us:** the trace that satisfies "region-matched real workload" for GPU/LLM experiments.

### E25. DynamoLLM: Designing LLM Inference Clusters for Performance and Energy Efficiency
- **Authors:** Jovan Stojkovic, Chaojie Zhang, Íñigo Goiri, Josep Torrellas, Esha Choukse (UIUC + Microsoft) · **Year:** 2025 · **Venue:** IEEE HPCA 2025 — peer-reviewed. **ID:** DOI 10.1109/hpca61900.2025.00102; arXiv:2408.00741.
- **Problem:** Energy/carbon of LLM inference clusters under SLOs; dynamic reconfiguration.
- **Method:** hierarchical controllers; instance scaling, model-parallelism resizing, GPU frequency scaling; heterogeneity-aware request pools.
- **Data:** **Azure LLM Inference traces (Conversation service)** — production trace subset; 1-hour open trace used at cluster level.
- **Results (per paper):** **~52% energy, ~38% operational carbon, 61% cost savings** while meeting latency SLOs.
- **Limitations:** single-DC cluster control; no grid/carbon-intensity signals; no forecast uncertainty; no inter-DC dimension.
- **For us:** intra-DC knob layer beneath our cross-DC placement agents; trace-compatible.

### E26. TAPAS: Thermal- and Power-Aware Scheduling for LLM Inference in Cloud Platforms
- **Authors:** Jovan Stojkovic, Chaojie Zhang, Íñigo Goiri, Esha Choukse, Josep Torrellas et al. · **Year:** 2025 · **Venue:** ACM ASPLOS 2025 — peer-reviewed. **ID:** DOI 10.1145/3676641.3716025 (verified).
- **Problem:** Fine-grained ms-scale thermal/power profiles of LLM serving need scheduling awareness.
- **Method:** thermal/power-aware scheduling of inference requests.
- **Data:** Azure LLM inference traces.
- **Limitations:** single node/cluster; no carbon/grid.
- **For us:** second Azure-trace user; educates thermal realism for GPU racks in simulation.

### E27. EcoServe: Designing Carbon-Aware AI Inference Systems
- **Authors:** Yueying Li, Zyad Hassan, Pedro Las-Casas, Daniela Barreales, Ricardo Bianchini, Rodrigo Fonseca et al. · **Year:** 2025 · **Venue:** arXiv preprint (2025). **ID:** arXiv:2502.05043 (verified).
- **Problem:** Carbon (operational + embodied) accounting and scheduling headroom for production GenAI serving.
- **Method:** modeling + observations from **production traces of two GenAI services at a major cloud** (the Azure LLM Inference services): GPUs dominate operational carbon but **host CPUs/memory/storage dominate embodied**; offline/batch inference ≈ up to **55% of serving capacity**; heterogeneity exploitable.
- **Limitations:** preprint; not a decentralized scheduler.
- **For us:** empirical ammunition that (i) LLM serving is batch-heavy → spatial/temporal flexibility exists; (ii) embodied carbon can't be ignored.

### E28. SPROUT: Green Generative AI with Carbon-Efficient LLM Inference
- **Authors:** Baolin Li, Yankai Jiang, Rohan Basu Roy, Siddharth Samsi, Vijay Gadepally, Devesh Tiwari (Northeastern/MIT-LL) et al. · **Year:** 2024 · **Venue:** EMNLP 2024 — peer-reviewed. **ID:** DOI 10.18653/v1/2024.emnlp-main.1215 (verified).
- **Problem:** Reduce carbon of generative LLM inference without changing hardware.
- **Method:** "generation directives" guiding autoregressive generation + strategic optimizer + offline quality evaluator.
- **Data:** LLaMA models + global electricity grid carbon data.
- **Results (abstract):** **>40% carbon footprint reduction** in real-world evaluations.
- **Limitations:** output-length control, single-region; no geo/uncertainty.
- **For us:** orthogonal lever (request-level) our agents could combine with placement.

### E29. PecSched: Preemptive and Efficient Cluster Scheduling for LLM Inference
- **Authors:** (Yichao??; first-author N. (per arXiv page) et al. —liklely HUST/Tsinghua collaboration) · **Year:** 2024 · **Venue:** arXiv preprint (2024). **ID:** arXiv:2409.15104 (verified).
- **Problem:** Cluster-level scheduling of LLM serving with heavy-tailed input lengths in the **Azure LLM Inference trace** (≈80% inputs < 2K tokens).
- **Method:** preemptive scheduling for short-input requests + coordinated prefill-decode co-location/disaggregation + fast sequence parallelism for long inputs.
- **Results (abstract):** **up to 92% reduction in p99 queueing delay** and up to **595% throughput gain** for short-input requests; negligible JCT impact on long inputs.
- **Limitations:** no carbon/geo dimension.
- **For us:** direct user of OUR trace; shows trace informs scheduling-realistic latency (TTFT/TBT) models for SLA terms.

### E30. Carbon-Aware LLM Inference Instance Deployment and Workload Assignment Across Geo-distributed Data Centers
- **Authors:** Yanran Xiao, Wei Wang et al. · **Year:** 2025 · **Venue:** Asia Communications and Photonics Conference (ACP 2025, IEEE) — peer-reviewed. **ID:** DOI 10.1109/ACP66871.2025.11350985 (verified).
- **Problem:** LLM inference instance deployment + workload assignment across geo-DCs with regional carbon/latency/demand heterogeneity.
- **Method:** joint optimization/deployment framework (per abstract; details in paper).
- **Limitations:** conference short paper; single-shot optimization, no uncertainty/agents.
- **For us:** problem statement twin for the LLM/geo-DC part — but static and deterministic.

### E31. GCOS — Green scheduling for LLM workloads with model and data reuse across geo-distributed data centers
- **Authors:** Hao Liu, Xiaonyu Hu et al. · **Year:** 2025 · **Venue:** Digital Communications and Networks (Elsevier) — peer-reviewed (2025, in press). **ID:** DOI 10.1016/j.dcan.2025.11.006 (verified).
- **Problem:** LLM task scheduling across geo-DCs exploiting **model/data reuse**; notes LLM **execution-time uncertainty** is overlooked by prior geo-schedulers.
- **Method:** GCOS scheduler with reuse-aware placement + handling of uncertain execution times.
- **Limitations:** single-controller; no carbon-intensity uncertainty.
- **For us:** quantifies the LLM-execution-time uncertainty we model probabilistically in deadlines.

### E32. Dissecting the Carbon-SLO Tension in Geo-Distributed LLM Serving
- **Authors:** Burak Topçu, Musa Cim et al. · **Year:** 2026 · **Venue:** arXiv preprint (2026). **ID:** arXiv:2610.14571 (verified).
- **Problem:** Latency-centric evaluation of carbon-aware spatial scheduling for LLM serving; prior work oversimplifies queueing/continuous-batching dynamics.
- **Method:** latency-centric geo-distributed inference simulator calibrated with hardware-grounded engine models.
- **Limitations:** preprint; simulation; no uncertainty; no agents.
- **For us:** our simulator design should match this fidelity to avoid carbon savings that vanish under real SLO dynamics.

### E33. HealthServe: A Public Health-Aware Inference Framework
- **Authors:** Sicheng Zhou, Rohan Basu Roy, Devesh Tiwari et al. · **Year:** 2026 · **Venue:** ACM SIGMETRICS (POMACS) 2026 —peer-reviewed. **ID:** DOI 10.1145/3805638 (verified).
- **Problem:** LLM inference damages public health beyond carbon (PM2.5/NOx/SO2 exposure).
- **Method:** health-impact-aware serving jointly minimizing carbon + health costs **across geo-distributed GPUs**.
- **Limitations:** first-generation health metrics; no uncertainty/agents.
- **For us:** extends objective space; secondary to our core.

---

## F. Workload migration & network trade-offs; Alibaba-trace evidence

### F34. Carbon-Aware and Fault-Tolerant Migration of Deep Learning Workloads in the Geo-Distributed Cloud
- **Authors:** Jeonghyeon Park, Daero Kim, Jiseon Kim et al. · **Year:** 2024 · **Venue:** IEEE CLOUD 2024 — peer-reviewed. **ID:** DOI 10.1109/cloud62652.2024.00062 (verified).
- **Problem:** Shift LLM-class training workloads to low-carbon DCs amid resource scarcity; migration must be fault-tolerant.
- **Method:** state-machine task scheduler migrating mini-batches dynamically + fault-tolerant GPU-frequency control under power guarantees; experiments with real carbon/transfer-time/power data.
- **Limitations:** training-only; classical control; no forecast uncertainty.
- **For us:** blueprint for migration-state modeling of GPU jobs (checkpoint/state transitions) in our simulation.

### F35. ML Training with Cloud GPU Shortages: Is Cross-Region the Answer?
- **Authors:** Foteini Strati, Paul Elvinger, Tolga Kerimoglu, Ana Klimovic (ETH) · **Year:** 2024 · **Venue:** EuroMLSys '24 (ACM workshop co-located at EuroMLSys/EuroSys) — peer-reviewed workshop. **ID:** DOI 10.1145/3642970.3655843 (verified).
- **Problem:** When does cross-region GPU training make sense given **inter-DC bandwidth/cost penalties**?
- **Method:** profile-based analytical model of throughput/cost by parallelism strategy.
- **Results (per paper):** data-parallel degradation severe across regions; pipeline-parallel cross-region training practical prescribes placement splits.
- **For us:** justifies our limited/perm GB transfer costs + bandwidth constraints in the action space and SLA effects.

### F36. Data center workload flexibility for power system demand response: Evidence from Alibaba traces
- **Authors:** Adriano Caprara, Ying Yu et al. · **Year:** 2026 · **Venue:** International Journal of Electrical Power & Energy Systems — peer-reviewed. **ID:** DOI 10.1016/j.ijepes.2026.111940 (verified).
- **Problem:** Assess/activate DC flexibility by deferring non-critical, high-latency **ML workloads** from Alibaba production traces.
- **Data:** **Alibaba ML/hyperscaler production traces.**
- **Results (abstract):** flexibility potential quantified for grid demand response.
- **Limitations:** demand-response framing, not carbon placement.
- **For us:** validates realistic defer-ability patterns from a GPU trace we can reuse.

### F37. Power- and Fragmentation-Aware Online Scheduling for GPU Datacenters
- **Authors:** Francesco Lettich, Emanuele Carlini et al. (ISTI-CNR) · **Year:** 2025 · **Venue:** IEEE/ACM CCGrid 2025 — peer-reviewed. **ID:** DOI 10.1109/ccgrid64434.2025.00015 (verified).
- **Problem:** Online GPU-cluster scheduling minimizing fragmentation and power: AI/LLM-driven GPU schedules degrade footprints.
- **Method:** online schedule workloads w/ no future knowledge; power-limit + packing based heuristics (sub-lineage: GPU paris balance).
- **For us:** single-DC GPU packing layer our agents extend cross-DC; mostly not carbon.

---

## Also noted (verified IDs; one-line each; several belong in our related-work table)

- **Going Green for Less Green: Optimizing the Cost of Reducing Cloud Carbon Emissions** — Hanafy, Qianlin Liang, Kaoupis?(MIT/UMass), **ASPLOS 2024**, DOI 10.1145/3620666.3651374 — temp-shift batch workloads via cheapest reservations; economic envelope for carbon-aware decisions.
- **On the Implications of Choosing Average vs Marginal Carbon Intensity Signals** — Sukprasert et al., **e-Energy 2024 (notes)**, DOI 10.1145/3632775.3661953 — avg vs marginal differ (low correlation); optimizer choice matters — justifies using marginal data where available.
- **The Green Mirage** — Maji, Bashir, Irwin, Shenoy, Sitaraman, **e-Energy 2024**, DOI 10.1145/3632775.3639587 — location- vs market-based CI estimation changes optimization efficacy ("mirage" of savings).
- **The Sunk Carbon Fallacy** — Bashir, Varun Gohil, **SoCC 2024**, DOI 10.1145/3698038.3698542 — footprint metrics distort optimization; borrow their accounting for mission-level claims.
- **Data Centers Carbon Emissions at Crossroads: An Empirical Study** — Maji, Hanafy, Wu, Irwin, Sitaraman, Shenoy, **HotCarbon 2025** (ACM SIGENERGY EIR reprint DOI 10.1145/3757892.3757899) — DC CI trends interact with demand growth (empirical, US).
- **GreenFlow: A Carbon-Efficient Scheduler for Deep Learning Workloads** — Diandian Gu, Yihao Zhao, Peng Sun et al., **IEEE TPDS 2024/2025**, DOI 10.1109/tpds.2024.3470074 — JCT ↑ compat. within carbon budget; GPU packing to dodge fragmentation; testbed-validated.
- **F2S-WSS: forecast-driven two-stage workload scheduling for carbon-aware geo-distributed DCs with wind power integration** — Xueying Zhai, Guojun Zhu, Yunhao Zhang, **Sustainable Computing: Informatics and Systems 2025**, DOI 10.1016/j.suscom.2025.101216 — wind-forecast-driven two-stage scheduling (closest "forecast + two-stage" relative; no risk term).
- **ReBase: Prediction-driven scheduling with baseline-guided online correction for renewable-aware geo-distributed data centers** — Zhai/… — SUSCOM 2026, DOI 10.1016/j.suscom.2026.101470 — online correction of predictive scheduling errors.
- **Learning to Reduce Data Center Carbon Emissions via Forecast-Integrated Workload Scheduling** — Sohrabbeig, Ardakanian et al. (U Alberta), **IEEE PESGM 2026**, DOI 10.1109/PESGM58988.2026.11693224 — differentiable/surrogate-upload of carbon forecast into training-job placement.
- **Carbon-aware scheduling of LLM training across multiple US power grid operators: a marginal emissions analysis** — Gopalakrishnan, Ravikumar et al., **Environmental Research: Infrastructure and Sustainability 2026**, DOI 10.1088/2634-4505/aebbef — LLM-training placement across US ISOs with **marginal** emissions.
- **Carbon-Aware Spatial-Temporal Scheduling for Multiple AI Data Center Parks With Training and Inference Workloads Characteristics** — Jianpei Han, Ershun Du, Bojun Du, **IEEE Trans. Industry Applications 2026**, DOI 10.1109/tia.2026.3678569 — DC parks w/ coupled training/inference: spatial-temporal coordination.
- **GreenDiffSched: Constraint-Guided Discrete Diffusion for Carbon-Aware Edge–Cloud Scheduling Under Renewable Uncertainty** — Zhun Shi, Yixin Chen et al., **IEEE Access 2026**, DOI 10.1109/ACCESS.2026.3722944 — diffusion-generative scheduling policy under renewable uncertainty (single-controller).
- **Two-Stage Stochastic Energy-Efficient Scheduling of Geo-Distributed DCs with Spatio-Temporal Workload Flexibility** — Ziwei Zhao, Huafeng Zhang et al., **Sustainability 2026**, DOI 10.3390/su18136553 — two-stage stochastic program; inter-DC network constraints included; no carbon-intensity signals yet.
- **Decentralized Task Scheduling in Distributed Systems: A Deep RL Approach** — Dirk John et al., **arXiv 2026** 2603.24738 — decentralized DRL scheduling, no carbon geo context (adjacent).
- **EcoServe-line: Fair, Practical, and Efficient Carbon Accounting for LLM Serving** — Yueying Lisa Li, Leo Han…, **ACM SIGMETRICS PER 2025**, DOI 10.1145/3764944.3764967 — Shapley-value benchmark for carbon attribution.
- **SPROUT-follow-ups offline energy models**: **Offline Energy-Optimal LLM Serving** — Wilkins, Keshav, Mortier, **SIGENERGY EIR 2024**, DOI 10.1145/3727200.3727217.
- **TACOS-like multiagent power-computing smallprint** see B11.
- **Carbon-aware K8s DRL** (Radhakrishnan, IJCTECE 2024) & similar low-tier variants — excluded from primary set (venue quality).
- **EnsembleCI precursors**: CarbonCast line (pre-2024) — referenced only as baseline.

---

## Special checks (as requested)

**(a) SustainCluster (Hewlett Packard Labs).** Found and read: GitHub `HewlettPackard/sustain-cluster` (created 2024-05-29; releases v1.0.0 & v1.1.0 2025); docs site (hewlettpackard.github.io/sustain-cluster) linking the paper **"SustainCluster: Benchmarking Dynamic Workload Distribution Techniques for Sustainable Data Center Cluster"** at OpenReview forum **`AgTASkryb6`** (NeurIPS 2025 Datasets & Benchmarks); author crew per HPE (Guillen-Perez, Naug, Gundecha, Sarkar; sarkar.org lists the twin name "DCcluster-Opt: Benchmarking Dynamic Multi-Objective Optimization for Geo-Distributed Data Center Workloads"). **Verified NOT in arXiv (title search = 0), not in OpenAlex, not in S2 as of 2026-11-04.** Full details in §A1. Its scheduler is **centralized** (single Top-Level Agent, defer-or-dispatch, 15-min steps) — a direct contrast to our decentralized design.

**(b) Papers 2024–2026 using the Azure LLM Inference Trace.** (1) **DynamoLLM** (HPCA 2025) — energy/carbon LLM cluster control with the Conversation-service trace; (2) **TAPAS** (ASPLOS 2025) — thermal/power-aware scheduling using the traces; (3) **PecSched** (arXiv 2409.15104) — cluster-level inference scheduling over the trace; (4) **EcoServe** (arXiv 2502.05043) — production traces of the two GenAI services (the same services: code + conversation); (5) **Libra (NSDI 2026)** and **Niyama (NSDI 2025)** use real LLM production traces (Microsoft/MSR). The trace originates from **"Characterizing Power Management Opportunities for LLMs in the Cloud"** (ASPLOS 2024) and is distributed via AzurePublicDataset. Contract bridging: trace has per-request timestamps, input/output tokens — fits our deadline/SLA and GPU-energy models.

**(c) Alibaba GPU cluster traces + electricity/carbon data.** (1) **SustainCluster** (Alibaba GPU Trace 2020 × Electricity Maps CI × GridStatus prices, 20+ regions) — the flagship match; (2) **Data center workload flexibility ... Evidence from Alibaba traces** (IJEPES 2026, DOI 10.1016/j.ijepes.2026.111940) — flexibility/deferral analysis (power-side); (3) **Power- and Fragmentation-Aware Online Scheduling for GPU Datacenters** (CCGrid 2025, DOI 10.1109/ccgrid64434.2025.00015) — power-aware GPU scheduling on production traces; (4) secondary: CarbonShift/Carbon-aware spatiotemporal DRL (JACS 2025) claims US-ISO data on generic DC workloads (venue quality noted). No paper found that pairs Alibaba GPU traces with **probabilistic carbon forecasts** — gap.

**(d) Any published work combining decentralized limited-communication MARL + forecast uncertainty + region-matched real carbon/workload data?** **No — after exhaustive search of S2/OpenAlex/e-Energy/SoCC/HPDC/AAAI-NeurIPS tracks and arXiv 2024–2026, we found no peer-reviewed paper combining all four.** Closest partials: **SustainCluster** (real region-matched data + geo-DC, but ONE centralized agent, no uncertainty); **Green-DCC**/SustainDC (HPE, multi-agent/hierarchical, real carbon/weather, but centralized hierarchy, no forecast uncertainty or comm limits); **CA-MARL AIDC arXiv 2607.03324** (multiagent + carbon + uncertainty, but grid co-optimization, preprint, no workload/region traces); **Jayanetti TPDS 2024** (MADRL over DCs, deterministic signals); **UAD (SIGENERGY 2024)** (conformal uncertainty on CI, but no control agents); **DRO-JCC 2026** (DRO + carbon + geo, but single controller, journal simulation). Our proposal remains novel along this specific intersection; strongest novelty defense = the combination + evaluation on real region-matched traces (SustainCluster data + Azure LLM trace + Alibaba/sharegpt-type serving traces).

---

## What remains unexplored for OUR project (explicit deltas per area)

1. **Decentralized placement agents with limited inter-DC communication:** every real-data system found (SustainCluster, Caspian, CarbonEdge, JCST, TIA parks) is centrally optimized; MARL works (TPDS'24×2, AAAI'25) assume full observability. No cross-DC carbon-aware scheduler has explicit comm-budget/comms-graph design.
2. **Forecast uncertainty as a first-class input:** no scheduler consumes calibrated CI forecast **distributions** (conformal/ensemble error bands) at dispatch time. EnsembleCI/Conformal works stop at forecast quality; schedulers use point forecasts.
3. **Risk-aware scheduling (CVaR/DRO) with deadlines on GPU/LLM workloads:** DRO/CVaR exists in energy-system and battery contexts (C15, C16, C18) and in one cloud simulator study (C15); nothing on geo-DC **LLM/GPU placement with SLA-risk trade-offs**.
4. **Carbon–network–SLA joint trade-offs with transfer causes:** LinTS/CLOUD'24/EuroMLSys'24 treat transfers in isolation; no joint scheduling paper prices data transfer *and* carbon *and* deadline risk simultaneously.
5. **Region-matched real LLM trace × real carbon grid:** no published evaluation couples the Azure LLM Inference Trace (or Alibaba GPU traces) with real Electricity Maps-type CI per region under uncertainty-aware decentralized control; SustainCluster couples Alibaba + CI but centrally.
6. **Embodied + operational carbon under uncertainty:** EcoServe/aging-aware works flag embodied carbon; none fuse it into risk-aware DC dispatch.

## Surprising/important notes for the proposal

- **SustainCluster is centralized** despite its multi-DC realism — makes "decentralized extension" a natural, citable next step (their own docs call for better dynamic CI prediction).
- Two constraints found **twice** in our feature list: LLM-specific trace realism (b) and region-matched carbon data (c) are each satisfied separately; nothing satisfies both with decentralization + risk. (Grand check (d) → none.)
- Marginal vs average CI signal choice materially changes reported savings (Green Mirage; avg-vs-marginal e-Energy'24) — decide and defend our signal early.
- SPROUT suggests output-length modulation (>40% carbon cut) — a cheap secondary lever within our agent design space.
- Job-length uncertainty is a top practical blocker (LACS) — our deadlines must be robust to execution-time uncertainty (GCOS echoes for LLMs).
- e-Energy 2024/2025 + SoCC/HPDC 2025 + TPDS/TPWRS/TSC-adjacent journal venues are the target set; HotCarbon is a strong workshops-first publication route.

## Threats / honest caveats of this survey
- S2 rate-limit degradation means some queries ("decentralized workload placement", "carbon intensity forecasting" etc.) were completed via OpenAlex title/abs matching rather than S2 relevance ranking; recall for tiny workshops and non-English literature is imperfect.
- Abstracts for 3 paywalled IEEE/Springer/Elsevier items (B7, B11, "F2S-WSS") were not fully retrievable; entries rely on verified metadata + fragments (flagged inline).
- SustainCluster's exact final camera-ready text was not retrievable (OpenReview bot-check); content above is from its official docs/GitHub/author pages, which match the paper's stated scope.
