#!/usr/bin/env python3
"""Generate audit figures from the verified downloads (UK carbon + Azure LLM trace)."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, "..", "downloads")
FIG = os.path.join(HERE, "..", "..", "report", "figures")
os.makedirs(FIG, exist_ok=True)

# ---- Figure 1: UK national carbon intensity, Jan 2025, forecast vs actual ----
nat = json.load(open(os.path.join(DL, "uk_national_2025-01_full_month.json")))["data"]
rows = []
for r in nat:
    it = r["intensity"]
    if it.get("actual") is not None and it.get("forecast") is not None:
        rows.append({"from": pd.to_datetime(r["from"].replace("Z", "")),
                     "forecast": it["forecast"], "actual": it["actual"]})
df = pd.DataFrame(rows).drop_duplicates("from").set_index("from")
print(f"fig1: {len(df)} unique half-hour slots with both forecast and actual")

fig, ax = plt.subplots(figsize=(12, 4.2))
df["actual"].plot(ax=ax, lw=0.9, label="Actual (measured)", color="#1f77b4")
df["forecast"].plot(ax=ax, lw=0.8, ls="--", label="Forecast (NESO, as issued)", color="#d62728", alpha=0.85)
ax.set_ylabel("Carbon intensity (gCO$_2$/kWh)")
ax.set_xlabel("January 2025 (UTC)")
ax.set_title("Great Britain national grid carbon intensity — January 2025\n(NESO Carbon Intensity API: real forecast-vs-actual pairs, 30-min resolution)")
ax.legend(loc="upper right")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "uk_carbon_forecast_vs_actual_jan2025.png"), dpi=150)
plt.close(fig)

# ---- Figure 2: regional spread across 14 DNO regions (15 Jan 2025 12:00Z slot) ----
regdata = json.load(open(os.path.join(DL, "uk_regional_all_2025-01-15_1200Z.json")))["data"][0]["regions"]
names = [r["shortname"] for r in regdata if r["shortname"] not in ("England", "Scotland", "Wales", "GB")]
vals = [r["intensity"]["forecast"] for r in regdata if r["shortname"] not in ("England", "Scotland", "Wales", "GB")]
order = sorted(zip(names, vals), key=lambda x: x[1])
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh([n for n, _ in order], [v for _, v in order], color="#2ca02c")
ax.set_xlabel("Carbon intensity forecast (gCO$_2$/kWh)")
ax.set_title("GB regional carbon intensity — same half-hour slot\n(2025-01-15 12:00–12:30 UTC, 14 DNO distribution regions)")
for i, (n, v) in enumerate(order):
    ax.text(v + 1, i, str(v), va="center", fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "uk_regional_spread_sample_slot.png"), dpi=150)
plt.close(fig)

# ---- Figure 3: Azure LLM trace arrival intensity ----
src = os.path.join(DL, "AzureLLMInferenceTrace_code_1week.csv")
per_hour = pd.read_csv(src, usecols=["TIMESTAMP"], parse_dates=["TIMESTAMP"])
hourly = per_hour.set_index("TIMESTAMP").resample("1h").size()
fig, ax = plt.subplots(figsize=(12, 3.6))
hourly.plot(ax=ax, lw=1.0, color="#9467bd")
ax.set_ylabel("LLM inference requests / hour")
ax.set_xlabel("Time (UTC), 10–16 May 2024")
ax.set_title("Azure LLM Inference Trace (code subset) — arrival intensity\n16.8M production requests, 7 days; burstiness spans 74–5,884 requests/min")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "azure_llm_trace_arrivals.png"), dpi=150)
plt.close(fig)
print("figures written to", FIG)
