#!/usr/bin/env python3
"""Inspect the downloaded Azure LLM Inference Trace (code subset, 1 week, May 2024)."""
import json
import os

import pandas as pd

SRC = os.path.join(os.path.dirname(__file__), "..", "downloads", "AzureLLMInferenceTrace_code_1week.csv")
AN = os.path.join(os.path.dirname(__file__), "..", "analysis")
os.makedirs(AN, exist_ok=True)

chunks = []
for chunk in pd.read_csv(SRC, chunksize=2_000_000, parse_dates=["TIMESTAMP"]):
    chunks.append(chunk)
df = pd.concat(chunks)
print(f"rows={len(df):,}")
print(f"columns={list(df.columns)}")
print(f"time range: {df.TIMESTAMP.min()} .. {df.TIMESTAMP.max()}")
print(f"nulls: {df.isna().sum().to_dict()}")
print(f"duplicate rows: {df.duplicated().sum():,}")
print(f"ContextTokens: min={df.ContextTokens.min()} p50={df.ContextTokens.median():.0f} mean={df.ContextTokens.mean():.0f} p95={df.ContextTokens.quantile(0.95):.0f} max={df.ContextTokens.max():,}")
print(f"GeneratedTokens: min={df.GeneratedTokens.min()} p50={df.GeneratedTokens.median():.0f} mean={df.GeneratedTokens.mean():.0f} p95={df.GeneratedTokens.quantile(0.95):.0f} max={df.GeneratedTokens.max():,}")

per_min = df.set_index("TIMESTAMP").resample("1min").size()
per_hour = df.set_index("TIMESTAMP").resample("1h").size()
print(f"requests/min: min={per_min.min()} p50={per_min.median():.0f} mean={per_min.mean():.0f} p95={per_min.quantile(0.95):.0f} max={per_min.max():,}")
print(f"requests/hour: min={per_hour.min()} mean={per_hour.mean():.0f} max={per_hour.max():,}")
print("per-day totals:")
print(df.set_index("TIMESTAMP").resample("1D").size().to_string())

summary = {
    "source": "Azure LLM Inference Trace 2024 (code subset, 1 week)",
    "url": "https://github.com/Azure/AzurePublicDataset/releases/download/dataset-llm-2024/AzureLLMInferenceTrace_code_1week.csv",
    "rows": int(len(df)),
    "columns": list(df.columns),
    "time_min": str(df.TIMESTAMP.min()),
    "time_max": str(df.TIMESTAMP.max()),
    "nulls": {k: int(v) for k, v in df.isna().sum().items()},
    "duplicate_rows": int(df.duplicated().sum()),
    "context_tokens_stats": {k: float(v) for k, v in
        {"min": df.ContextTokens.min(), "p50": df.ContextTokens.median(), "mean": df.ContextTokens.mean(),
         "p95": df.ContextTokens.quantile(0.95), "max": df.ContextTokens.max()}.items()},
    "generated_tokens_stats": {k: float(v) for k, v in
        {"min": df.GeneratedTokens.min(), "p50": df.GeneratedTokens.median(), "mean": df.GeneratedTokens.mean(),
         "p95": df.GeneratedTokens.quantile(0.95), "max": df.GeneratedTokens.max()}.items()},
    "req_per_min_max": int(per_min.max()),
    "req_per_hour_mean": float(per_hour.mean()),
    "region_field_present": False,
}
json.dump(summary, open(os.path.join(AN, "azure_llm_trace_summary.json"), "w"), indent=2)
print("summary saved")
