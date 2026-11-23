# exp027 — does the band reorder on a grid whose regional actuals are measured?

**Yes. The theorem's premise fails on a real grid — and the band's decision value
is still small, fragile, and mostly an artefact of forecaster quality.**

exp026 proves that a regional series built by scaling a national one leaves a
calibrated band nothing to decide. The obvious objection is that this is a
statement about *our estimator*, not about grids. This experiment removes the
objection with real data.

## The data, and what was refused

EIA-930 publishes hourly net generation **by fuel** for every US balancing
authority (public domain, no key). So each region's realized intensity is
computed from its own measured mix, not borrowed from a national series.

The reader gates on completeness rather than imputing. An hour is priced only
when its fuel breakdown accounts for the reported net generation within 0.5% —
integer-rounding noise, since the audited median mismatch is 0.004%. That rule,
applied uniformly, excludes:

* **PJM and NYIS** structurally (median mismatch 1.5% and worse),
* a **−1,174,570 MW** outlier in SRP,
* every hour with non-positive generation or any unknown fuel.

Five authorities were chosen for a wide spread in *both* intensity and
volatility, and all five pass the gate at ≥99.98%:

| site | mean realized gCO₂/kWh | relative forecast-error std | "Other" fuel share |
|---|---|---|---|
| BPAT (Bonneville, hydro 71%) | 24.2 | **4.114** | 1.70% |
| CISO (California, gas + solar) | 176.0 | 0.197 | −0.48% |
| ERCO (ERCOT, gas + wind) | 298.2 | 0.320 | 0.42% |
| MISO (Midcontinent, coal + gas + wind) | 427.9 | 0.143 | 0.43% |
| LGEE (Louisville, coal 84%) | 949.0 | **0.039** | 0.00% |

Sanity check against an independent source: our computed CISO 176 g/kWh sits
beside eGRID's CAMX subregion rate (428.5 lb/MWh ≈ 194 g/kWh), and ISNE 225
beside NEWE (539.3 lb/MWh ≈ 245 g/kWh). Same ballpark, as expected given that
eGRID includes interchange and CH₄/N₂O and we do not.

## 1. The structure is regional, not common

| | UK (exp026, scaled estimator) | US (exp027, measured mix) |
|---|---|---|
| hours classified | 18,757 | 4,339 |
| `common-multiplicative` | **18,757 (100%)** | **0** |
| `regional` | 0 | **4,339 (100%)** |
| hours where realized ordering ≠ forecast ordering | **0 (0.00%)** | **1,086 (25.03%)** |
| max spread of `realized/forecast` across regions | 1.78 × 10⁻¹⁵ | **48.24** |

So the theorem is exactly as narrow as it claims to be: it is a property of the
scaling construction, and on a grid with genuine regional actuals the premise
fails on a quarter of all hours.

## 2. Volatility differs by two orders of magnitude

BPAT's relative error std is 4.11 against LGEE's 0.039 — a **106× spread**. This
is the heteroskedasticity exp026 could only simulate, and it is real: a
hydro-dominated authority's intensity sits near zero, so its *relative* error
explodes, while a coal-dominated one barely moves.

## 3. Does the band help? Barely, and not reliably

18 rolling-origin weeks of Jan–Jun 2024, each calibrated on the 28 days before
it, same demand and fleets as exp026.

| fleet | band | λ | mean carbon | best week | worst week | weeks better | weeks worse |
|---|---|---|---|---|---|---|---|
| capacity_bound | absolute | 0.5 | **−0.024%** | **−0.412%** | +0.164% | **4** | 9 |
| capacity_bound | absolute | 1.0 | +0.043% | −0.221% | +0.198% | 2 | 13 |
| capacity_bound | absolute | 2.0 | +0.236% | 0.000% | +0.568% | 0 | 16 |
| capacity_bound | absolute | 4.0 | +0.644% | 0.000% | +1.746% | 0 | 16 |
| slack | absolute | 0.5 | +0.004% | −0.313% | +0.655% | **5** | 5 |
| slack | absolute | 4.0 | +1.079% | −0.001% | +2.404% | 1 | 16 |

**This is the first time in the project that a band has ever improved a
placement decision** — 4 and 5 weeks out of 18, best week −0.41%. But the mean
effect at low risk aversion is within ±0.03% of zero, and by λ = 2 the band is
strictly a cost. So the honest statement is: *the band can help on a real grid,
by a fraction of a percent, in a minority of weeks, and only if you are barely
risk-averse at all.*

## 4. The mechanism: spill order, not the winner

The top pick **never changes** (0.00% at every λ) because BPAT at 24 g/kWh beats
the next site by 150 g/kWh — no plausible band width closes that. The entire
effect runs through the *order of the remaining sites* when capacity binds:

| λ | top pick changed | full ranking changed |
|---|---|---|
| 0.5 | 0.00% | 9.39% |
| 2.0 | 0.00% | 34.66% |
| 4.0 | 0.00% | 68.19% |

That is worth stating plainly, because "the band reorders sites" and "the band
changes the assignment" are different claims, and only the second one is true
here.

## 5. A relative band actively misprices a near-zero-intensity region

| fleet | band | λ | mean carbon | worst week |
|---|---|---|---|---|
| capacity_bound | per-region relative | 2.0 | **+1.698%** | +23.91% |
| slack | per-region relative | 4.0 | **+3.261%** | **+41.59%** |

Here the top pick *does* change (9.09% of hours), and it changes for the worse:
BPAT's relative width is enormous (std 4.11), so a relative band penalises the
**cleanest site on the grid** hardest and pushes work onto dirtier ones. A
relative band is therefore not a safe default when any region's intensity
approaches zero — a concrete, measured failure mode, not a caution.

## 6. Most of the apparent value is the forecaster, not the grid

EIA publishes no carbon forecast, so the forecast is ours. Running a better one
— the mean of the same hour over the previous week, instead of day-ahead
persistence — shrinks everything:

| forecaster | hours reordered | absolute λ=0.5 mean | weeks better |
|---|---|---|---|
| persistence 24 h | 25.03% | −0.024% | 4 / 18 |
| same-hour 7-day mean | 20.63% | **+0.002%** | 2 / 18 |

So the band's small benefit is largely compensation for a naive forecast. A
better forecast removes most of the room it had.

## 7. Sensitivity: the unclassified fuel does not drive the answer

Re-pricing "Other Fuel Sources" at the natural-gas factor instead of zero leaves
the structure **100% regional** and the reorder rate at 23.62% (from 25.03%).
The conclusion does not depend on that assumption.

## What this does and does not establish

* **Does:** the exp026 theorem is about a construction, not about grids. On
  measured regional actuals the premise fails on 25% of hours, volatility is
  genuinely heteroskedastic, and a band can improve a decision.
* **Does:** the improvement is a fraction of a percent, in a minority of weeks,
  vanishes as risk aversion rises, and mostly disappears with a better
  forecaster. It is not a scheduling contribution.
* **Does not:** claim these five authorities are representative of all grids, or
  that our forecast is a published one. Both are disclosed.
* **Does not:** attribute interchange, so an importing authority looks dirtier
  than its consumption would.

## Disclosures

* Emission factors are published EIA national averages (coal 2.31, gas 0.96,
  petroleum 2.46 lb CO₂/kWh) applied to each authority's **measured** mix. The
  mix is data; the factor is a modelling assumption, with a sensitivity above.
* Operational CO₂ only — no upstream fuel-cycle or embodied emissions.
* The forecast is ours (two causal models), because EIA ships none.
* Demand is the single real Azure week laid positionally over each carbon week,
  as in every other dispatch experiment. Hourly slots double both demand and
  capacity, so utilisation matches exp026.
* CISO's "Other" share is negative (−0.48%): storage charging appears as negative
  generation in that column. It is priced at zero and left in the denominator.

## Reproduce

```
make exp-run EXP=exp027-regional-actuals-boundary
```

Canonical run `20261123T125113Z-8b3b07d7-2729`, git `96f61381`, `git_dirty:
false`. Fully deterministic — no randomness is used.
