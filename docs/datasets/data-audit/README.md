# Data Audit Folder — Guide

This folder contains the **evidence base** for the feasibility study. Everything here was
produced on 2026-11-04 during the audit; nothing is quoted from memory or from READMEs alone
unless explicitly marked.

```
data-audit/
├── downloads/   Raw samples actually fetched during the audit
├── scripts/     Fetch + inspection scripts (reproducible)
└── analysis/    Computed summaries + the verification table
```

## Contents

### downloads/
| File | Size | What it is |
|---|---|---|
| `uk_national_2025-01-01_to_2025-01-02.json` | 5.8 KB | NESO Carbon Intensity API, national, 1 day (49 slots, forecast+actual) |
| `uk_national_2025-01_full_month.json` | 183 KB | National, January 2025 (1,493 slots) |
| `uk_regional_all_2025-01-01_to_2025-01-02.json` | 384 KB | All 14 DNO regions + aggregates, 1 day, incl. generation mix |
| `uk_region13_london_2025-01-01_to_2025-01-08.json` | 139 KB | London (regionid 13), 1 week |
| `uk_region13_london_2025-01_full_month.json` | 612 KB | London, January 2025 |
| `uk_generation_2025-01-01_to_2025-01-02.json` | 17.8 KB | GB national generation mix, 1 day |
| `AzureLLMInferenceTrace_code_1week.csv` | 692 MB | Microsoft Azure LLM inference trace, code subset, 7 days (16.8M rows) |
| `eia930_balance_2024_janjun_sample.csv` | 41.7 MB | EIA-930 hourly demand/generation by Balancing Authority, Jan–Jun 2024 |

### scripts/
| Script | Purpose |
|---|---|
| `fetch_uk_carbon.py` | First-pass UK CI API probes (documents the wrong-path 400s too) |
| `fetch_uk_carbon_v2.py` | Corrected regional endpoints + generation mix |
| `fetch_uk_carbon_month.py` | Window-cap probe, chunked month download, statistics (MAE/RMSE of forecast vs actual, regional spread, gap check) |
| `inspect_azure_llm_trace.py` | Full-file pandas inspection of the 16.8M-row trace |
| `make_figures.py` | Generates the three report figures from the downloaded data |

### analysis/
| File | Purpose |
|---|---|
| `VERIFICATION_TABLE.md` | The required sample-verification tables (sections 5.A–5.D of the study) |
| `uk_carbon_summary.json` | Machine-readable UK carbon statistics |
| `azure_llm_trace_summary.json` | Machine-readable trace statistics |

## Reproduction

```bash
python3 data-audit/scripts/fetch_uk_carbon.py          # needs: requests
python3 data-audit/scripts/fetch_uk_carbon_v2.py
python3 data-audit/scripts/fetch_uk_carbon_month.py
python3 data-audit/scripts/inspect_azure_llm_trace.py  # needs: pandas (692 MB CSV)
python3 data-audit/scripts/make_figures.py             # needs: pandas, matplotlib
```

All scripts are idempotent and write only inside this study folder.
