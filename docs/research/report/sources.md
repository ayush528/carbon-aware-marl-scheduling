# Source & Reference List

All URLs verified 4 November 2026 unless marked otherwise. [V] = downloaded/inspected by us; [S] = official page/repo fetched by survey pass; [D] = documented only.

## Datasets & APIs

**Carbon intensity / electricity**
1. NESO Carbon Intensity API (UK) — https://api.carbonintensity.org.uk — free, no key, CC BY 4.0. [V]
2. Carbon Intensity homepage & methodology — https://carbonintensity.org.uk — 14 DNO region IDs, forecast methodology, license. [V]
3. Elexon BMRS Insights API — https://data.elexon.co.uk/bmrs/api/v1/ (datasets FUELHH, FUELINST) — free, no key. [S]
4. EIA Hourly Grid Monitor (EIA-930) bulk CSVs — https://www.eia.gov/electricity/gridmonitor/ — free, no key; archive list `sixMonthFiles/EIA930_File_List_Meta.csv`. [V]
5. EIA API v2 (key required) — https://api.eia.gov/v2/ — registration: https://www.eia.gov/opendata/register.php. [S]
6. CAISO Today's Outlook — https://www.caiso.com/outlook/history/{YYYYMMDD}/co2.csv and `fuelsource.csv` — free, keyless, ≥2019. [S]
7. EPA eGRID2023 (rev2, 2025-06) — https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx — free. [S]
8. Fraunhofer ISE Energy-Charts API — https://api.energy-charts.info (OpenAPI: /openapi.json; /v2/public_power, /v2/public_power_forecast) — free, no key. [S]
9. Fingrid Open Data — https://data.fingrid.fi — free API key; datasets 265/266/396 (emission factors); limits 10k req/24h, 1 req/2s. [S]
10. ENTSO-E Transparency Platform — https://transparency.entsoe.eu — free token; 400 req/min (Zendesk: https://transparencyplatform.zendesk.com/hc/en-us/articles/12783148966036). [S]
11. OpenElectricity (OpenNEM) v4 API — https://api.opennem.org.au (spec: /openapi.json) — free, keyless. [S]
12. Waseda University, "Time-Varying Grid CO2 Emission Factors Derived from TSO-Level Generation Mix in Japan" — https://zenodo.org/records/18396311 — CC BY 4.0, FY2024, 9 TSO areas. [S]
13. Electricity Maps pricing — https://www.electricitymaps.com/pricing — paid (€6,000/yr per country; 14-day trial); API docs https://portal.electricitymaps.com/docs. [S]
14. WattTime data plans — https://www.watttime.org/docs-dev/data-plans/ — free Basic tier = CAISO_NORTH; research access by application. [S]
15. Grid Controller of India — https://grid-india.in — free daily/VRE reports. [S]
16. CEA CO₂ Baseline Database v20/v21 — https://cea.nic.in/cdm-co2-baseline-database/ — annual factors. [S]
17. Google region-carbon-info — https://github.com/GoogleCloudPlatform/region-carbon-info — per-region CFE % + grid CI, 2019–2025. [S]
18. Google data-center efficiency (PUE) — https://www.google.com/about/datacenters/efficiency/ — fleet TTM 1.09 (2025); per-campus tables since 2008. [S]
19. Ireland CSO StatBank MEC02 — https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/MEC02/CSV/1.0/en — quarterly data-centre GWh since 2015Q1. [S]
20. EU Energy Efficiency Directive datacentre reporting platform — https://policy-reporting-platform.ec.europa.eu/Reporting/web/screen/home:registration — aggregate dashboard. [S]

**Workload traces**
21. Azure LLM Inference Trace 2024 — https://github.com/Azure/AzurePublicDataset/blob/master/AzureLLMInferenceDataset2024.md — CC BY 4.0; download: https://github.com/Azure/AzurePublicDataset/releases/download/dataset-llm-2024/AzureLLMInferenceTrace_code_1week.csv. [V]
22. AzurePublicDataset repo (V1 2017, V2 2019 VM traces, Functions, Packing) — https://github.com/Azure/AzurePublicDataset — CC BY 4.0. [S]
23. Alibaba clusterdata (GPU v2020 et al.) — https://github.com/alibaba/clusterdata — research-use clause; cite NSDI'22 "MLaaS in the Wild". [S]
24. Google cluster-data v3 (Borg 2019) — https://github.com/google/cluster-data — CC BY 4.0; spec PDF contains cell→timezone table. [S]
25. Grid Workloads Archive / Bitbrains GWA-T-12 — mirror https://atlarge-research.com/gwa-traces/ (canonical gwa.ewi.tudelft.nl had DNS failure from our sandbox). [S]
26. Helios (SenseTime S-Lab) — https://github.com/S-Lab-System-Group/HeliosData — CC BY 4.0. [S]
27. Philly trace (MSR) — https://github.com/msr-fiddle/philly-traces — ATC'19. [S]
28. AcmeTrace (InternLM) — https://github.com/InternLM/AcmeTrace — CC BY 4.0 (KaLOs only; SeReN missing from tree). [S]
29. Mooncake traces (FAST'25) — https://github.com/kvcache-ai/Mooncake — code Apache-2.0. [S]
30. BurstGPT — https://github.com/HPMLL/BurstGPT — CC BY 4.0. [S]

**Power / PUE measurement**
31. NLR (ex-NREL) Generative AI Workload Power Profiles — https://data.nlr.gov/submissions/312 — DOI 10.7799/3025227; arXiv:2604.07345. [S, sample inspected]
32. Harvard Dataverse GPU Power & Performance Metrics — DOI 10.7910/DVN/RNGJFI — CC0. https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/RNGJFI. [S]
33. GPU-DVFS-Dataset — https://github.com/zyjopensource/GPU-DVFS-Dataset. [S]
34. amodo H200 NVL corpus — https://zenodo.org/records/23521636 — CC BY 4.0 (65 GB). [S]
35. Watt Counts (preprint, dataset pending) — arXiv:2604.09048. [S]

**Network**
36. Azure inter-region latency (Microsoft) — https://learn.microsoft.com/en-us/azure/networking/azure-network-latency; table: https://www.azurespeed.com/Azure/RegionToRegionLatency. [S]
37. cloudping.co (AWS inter-region RTT) — https://www.cloudping.co; repo https://github.com/mda590/cloudping.co (MIT). [S]
38. RIPE Atlas — https://atlas.ripe.net — free account, 50k starter credits; archived results free. [S]
39. Cloudflare Radar — https://radar.cloudflare.com — free API (token). [S]
40. Cloud egress pricing — AWS https://aws.amazon.com/ec2/pricing/on-demand/; Azure https://azure.microsoft.com/pricing/details/bandwidth/; GCP https://cloud.google.com/network/pricing. [S]

## Code / benchmarks
41. SustainCluster — https://github.com/HewlettPackard/sustain-cluster — MIT; paper: OpenReview https://openreview.net/forum?id=AgTASkryb6 (NeurIPS 2025 D&B). [V]
42. SustainDC — https://github.com/HewlettPackard/dc-rl; paper arXiv:2408.07841 (NeurIPS 2024 D&B). [S]

## Papers (2024–2026; all DOIs resolved against Crossref/OpenAlex/arXiv records)
43. Guillen-Perez et al., "SustainCluster: Benchmarking Dynamic Workload Distribution Techniques for Sustainable Data Center Cluster", NeurIPS 2025 D&B. OpenReview AgTASkryb6.
44. Naug et al., "SustainDC: Benchmarking for Sustainable Data Center Control", NeurIPS 2024 D&B. arXiv:2408.07841.
45. Sarkar et al., "Green-DCC: Hierarchical Multi-Agent Framework for Carbon-Efficient Liquid-Cooled Data Center Clusters", AAAI 2025. DOI 10.1609/aaai.v39i28.35370.
46. Bahreini & Tantawi et al., "Caspian: A Carbon-aware Workload Scheduler in Multi-Cluster Kubernetes Environments", IEEE/ACM MASCOTS 2024. DOI 10.1109/MASCOTS64422.2024.10786568.
47. Wu et al., "CarbonEdge: Leveraging Mesoscale Spatial Carbon-Intensity Variations for Low Carbon Edge Computing", ACM HPDC 2025. DOI 10.1145/3731545.3731576.
48. Sukprasert et al., "On the Limitations of Carbon-Aware Temporal and Spatial Workload Shifting in the Cloud", ACM EuroSys 2024. DOI 10.1145/3627703.3650079.
49. Li et al., "Uncertainty-Aware Decarbonization for Datacenters", ACM SIGENERGY Energy Informatics Review 2024. DOI 10.1145/3727200.3727221.
50. Yan et al., "EnsembleCI: Ensemble Learning for Carbon Intensity Forecasting", ACM e-Energy 2025. DOI 10.1145/3679240.3734630.
51. Bostandoost et al., "LACS: Learning-Augmented Algorithms for Carbon-Aware Resource Scaling with Uncertain Demand", ACM e-Energy 2024. DOI 10.1145/3632775.3661942.
52. Ruparel et al., "Carbon-aware scheduling and distributionally robust optimization for cloud systems", J. Cloud Computing 2026. DOI 10.1186/s13677-026-00904-7.
53. Hall et al., "Carbon-Aware Computing for Data Centers with Probabilistic Performance Guarantees", IEEE TPWRS 2025. DOI 10.1109/tpwrs.2025.3630499.
54. Wang et al., "Tail-risk-aware Bit-Watt co-optimization for data center integrated energy systems under joint forecast uncertainty", IJEPES 2026. DOI 10.1016/j.ijepes.2026.112227.
55. Jayanetti et al., "Multi-Agent Deep RL Framework for Renewable Energy-Aware Workflow Scheduling on Distributed Cloud Data Centers", IEEE TPDS 2024. DOI 10.1109/tpds.2024.3360448.
56. Chen & Li et al., "Two-Timescale Joint Optimization of Task Scheduling and Resource Scaling in Multi-Data Center System Based on MADRL", IEEE TPDS 2024. DOI 10.1109/TPDS.2024.3467212.
57. Bian et al., "CAFE: Carbon-Aware Federated Learning in Geographically Distributed Data Centers", ACM e-Energy 2024. DOI 10.1145/3632775.3661970.
58. Wiesner et al., "FedZero: Leveraging Renewable Excess Energy in Federated Learning", ACM e-Energy 2024. DOI 10.1145/3632775.3639589.
59. Patel et al., "Characterizing Power Management Opportunities for LLMs in the Cloud", ACM ASPLOS 2024. DOI 10.1145/3620666.3651329.
60. Stojkovic et al., "DynamoLLM: Designing LLM Inference Clusters for Performance and Energy Efficiency", IEEE HPCA 2025. DOI 10.1109/hpca61900.2025.00102; arXiv:2408.00741.
61. Stojkovic et al., "TAPAS: Thermal- and Power-Aware Scheduling for LLM Inference in Cloud Platforms", ACM ASPLOS 2025. DOI 10.1145/3676641.3716025.
62. Li et al., "EcoServe: Designing Carbon-Aware AI Inference Systems", arXiv:2502.05043 (2025, preprint).
63. "PecSched: Preemptive and Efficient Cluster Scheduling for LLM Inference", arXiv:2409.15104 (2024, preprint).
64. Li et al., "SPROUT: Green Generative AI with Carbon-Efficient LLM Inference", EMNLP 2024. DOI 10.18653/v1/2024.emnlp-main.1215.
65. Rodrigues et al., "LinTS: Carbon-Aware Temporal Data Transfer Scheduling Across Cloud Datacenters", IEEE CLOUD 2025. DOI 10.1109/cloud67622.2025.00034.
66. Strati et al., "ML Training with Cloud GPU Shortages: Is Cross-Region the Answer?", EuroMLSys 2024. DOI 10.1145/3642970.3655843.
67. Caprara et al., "Data center workload flexibility for power system demand response: Evidence from Alibaba traces", IJEPES 2026. DOI 10.1016/j.ijepes.2026.111940.
68. Gu et al., "GreenFlow: A Carbon-Efficient Scheduler for Deep Learning Workloads", IEEE TPDS 2024. DOI 10.1109/tpds.2024.3470074.
69. Zhai et al., "F2S-WSS: forecast-driven two-stage workload scheduling for carbon-aware geo-distributed DCs with wind power integration", Sustainable Computing: Informatics and Systems 2025. DOI 10.1016/j.suscom.2025.101216.
70. Topçu et al., "Dissecting the Carbon-SLO Tension in Geo-Distributed LLM Serving", arXiv:2610.14571 (2026, preprint).
71. Zhou et al., "HealthServe: A Public Health-Aware Inference Framework", ACM SIGMETRICS/POMACS 2026. DOI 10.1145/3805638.
72. Hanafy et al., "Going Green for Less Green: Optimizing the Cost of Reducing Cloud Carbon Emissions", ACM ASPLOS 2024. DOI 10.1145/3620666.3651374.
73. Sukprasert et al., "On the Implications of Choosing Average vs Marginal Carbon Intensity Signals", ACM e-Energy 2024 (notes). DOI 10.1145/3632775.3661953.
74. Maji et al., "The Green Mirage", ACM e-Energy 2024. DOI 10.1145/3632775.3639587.
75. Bashir et al., "The Sunk Carbon Fallacy", ACM SoCC 2024. DOI 10.1145/3698038.3698542.
76. Persico et al., "On the Interplay between Wide Area Networking and Data Transfer..." IEEE GLOBECOM 2016 (RTT/throughput empirical source used by SustainCluster). https://www.sciencedirect.com/science/article/abs/pii/S138912861630353X.
77. Aslan et al., "The carbon footprint of data transfer" (0.06 kWh/GB), J. Industrial Ecology 2017. DOI 10.1111/jiec.12630.
78. Wei et al., "MLaaS in the Wild: Workload Analysis and Scheduling of Large Scale Heterogeneous GPU Clusters" (Alibaba GPU trace 2020 characterization), NSDI 2022.
79. Stojkovic et al. — Azure trace documentation page (item 21) is the authoritative provenance for the Azure LLM Inference Trace.

## Survey-method notes
- Semantic Scholar Graph API (rate-limited during the session): https://api.semanticscholar.org/graph/v1/ ; fallbacks: OpenAlex https://api.openalex.org/works ; Crossref https://api.crossref.org/works/{DOI} ; arXiv Atom https://export.arxiv.org/api/query.
- Where an abstract could not be retrieved (3 paywalled items), entries rely on verified metadata and are flagged in research-notes/C-literature-2024-2026.md.
