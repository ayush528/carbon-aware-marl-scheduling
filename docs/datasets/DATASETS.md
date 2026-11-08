# Dataset catalog

Every dataset used in experiments is listed here with its source URL, license
and audit status. Audit evidence lives in `data-audit/` (verification tables,
small raw samples, fetch scripts). Status labels come from the audit:
**[VERIFIED]** downloaded & inspected by us, **[VERIFIED-S]** official
page/repo fetched by survey, **[DOCUMENTED]** official docs only.

## In active use

| Dataset | Source URL | License | Status | Local copy |
|---|---|---|---|---|
| NESO Carbon Intensity (national + 14 DNO regions, half-hourly forecast & actual) | API: `https://api.carbonintensity.org.uk` · docs: `http://docs.carbonintensity.org.uk` | open API | [VERIFIED] | `data-audit/downloads/uk_*.json` |
| EIA-930 (hourly demand/generation by Balancing Authority, US) | `https://www.eia.gov/electricity/gridmonitor/` · API: `https://api.eia.gov/v2/` | open (US gov) | [VERIFIED] | `data-audit/downloads/eia930_balance_2024_janjun_sample.csv` (42 MB, gitignored — refetch) |
| Azure LLM Inference Trace 2024 (code subset, 1 week) | `https://github.com/Azure/AzurePublicDataset` · direct: `https://github.com/Azure/AzurePublicDataset/releases/download/dataset-llm-2024/AzureLLMInferenceTrace_code_1week.csv` | CC-BY-4.0 (data), MIT (code) | [VERIFIED] | `data-audit/downloads/AzureLLMInferenceTrace_code_1week.csv` (692 MB, gitignored — refetch) |

## Surveyed / candidate

| Dataset | Source URL | License | Status | Region signal |
|---|---|---|---|---|
| Azure VM traces V1 (2017) / V2 (2019) | `https://github.com/Azure/AzurePublicDataset` (releases `dataset-v1`, `dataset-v2`) | CC-BY-4.0 / MIT | [VERIFIED-S] | "one geographical region" — unnamed by design |
| Alibaba GPU cluster traces 2020 | `https://aliopentrace.oss-cn-beijing.aliyuncs.com/v2020GPUTraces/` | see repo | [VERIFIED-S] | UTC+8 timezone hint only, no country named |
| Bitbrains GWA traces (SPEC RG) | `https://atlarge-research.com/gwa-traces/` | see site | [VERIFIED-S] | Netherlands provenance (paper-level) |
| Energy-Charts (Fraunhofer, EU power) | `https://api.energy-charts.info` | open API | [VERIFIED-S] | per-country, EU focus |
| WattTime marginal grid signal | `https://api.watttime.org/v3` | commercial API | [DOCUMENTED] | real grid regions, access-limited |

## Central audit finding

**No public workload trace ships an official per-DC/region → real-location
map** (verified across 29 trace families; the trend over time is *less*
geography, not more). The project therefore uses UK regional carbon intensity
as ground truth and maps workloads to sites as a disclosed assumption.
Details: `../research/findings-and-plan.md` §1.1.
