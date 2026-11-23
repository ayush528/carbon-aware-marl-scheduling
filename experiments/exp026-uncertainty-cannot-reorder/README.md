# exp026 — can calibrated uncertainty change a carbon decision?

**Answer: not on data built the way almost all of it is built. That is a theorem,
and the theorem is the contribution.**

exp011 ran this question on one week and reported an awkward result — a pooled
relative band changed nothing, a per-region absolute band reordered 1.8–3 % of
slots but only ever cost carbon. It was reported as a finding. It is not a
finding; it is a property of the data construction, and stating it that way is
what makes it useful to anyone else doing spatial carbon-aware scheduling.

## The theorem

Regional carbon *actuals* mostly do not exist. NESO's regional API ships
forecasts only (verified live in exp003: zero actuals across the full Jan-2025
matrix and recent windows), so the standard repair is to scale a national
series:

```
realized_r(t) = national_actual(t) · forecast_r(t) / national_forecast(t)        (Verified: exp003)
```

Substitute that into the definition of the forecast error:

```
realized_r − forecast_r = forecast_r · [ national_actual/national_forecast − 1 ]
                                        └──────────── one number per slot ────────┘
```

The bracket is a single value per slot, identical for every region. Therefore:

1. **Ranking is inherited.** `realized` and `forecast` order the regions
   identically, no matter how wrong the national forecast was.
2. **Forecast-greedy is already optimal.** Filling sites in ascending forecast
   order is the optimum of the slot's linear capacity problem
   (`min Σ e_s·c_s` subject to `Σ e_s = D`, `0 ≤ e_s ≤ cap_s`), because forecast
   order *is* realized order. No permutation emits less.
3. **A reordering band can only misprice.** By (2) any band that changes the
   order is weakly worse, and by (1) the change carries no information.

Nothing here depends on the band being calibrated badly. It is a statement about
the estimator, and it generalises: any regional series that is a common monotone
transform of its own forecast has the same property. `uncertainty.classify` is
the diagnostic — `common-multiplicative` (scaled), `common-additive`
(level-shifted), or `regional`. Only `regional` leaves a band anything to act
on.

## What was measured

42 fully covered weeks of 2024 (a week is used only if the week **and** its
whole 28-day calibration window are present), 18,757 slots, calibrated on the
28 days before each week, two fleets from exp021/exp023.

| check | result |
|---|---|
| slots where the realized ordering differs from the forecast ordering | **0 of 18,757** |
| error structure | **100 % common-multiplicative** |
| max spread of `realized/forecast` across regions | **1.78 × 10⁻¹⁵** (float noise) |
| pooled relative band, λ ∈ {0.5, 1, 2, 4} | **0.0000 %** carbon change, **0** reordered slots |
| per-region relative band | reorders 0.22–2.96 %, costs +0.0004…+0.052 %, **0 of 42 weeks better** |
| per-region absolute band | reorders **4.6–10.0 %** of slots, **0 of 42 weeks better** |

> **Correction on the record.** The first run of this experiment applied
> relative bands by *adding* the fraction to the intensity instead of scaling
> the forecast. That turned every relative band into a common additive constant,
> which cannot reorder for a trivial reason — so the proportional-band theorem
> looked verified while never being exercised. exp011 had the application right;
> this experiment did not. It is fixed, pinned by a regression test
> (`test_relative_bands_multiply_the_forecast_not_add_a_constant`), and the
> corrected result is **stronger**: the pooled band is still exactly invariant,
> and the per-region relative band — now properly applied — reorders up to 2.96 %
> of slots and is still better in 0 of 42 weeks. The earlier run record is kept
> unaltered as evidence; the canonical run is the corrected one below.

The per-region absolute band is the interesting one, because it *does* reorder —
a conformal quantile of that region's residual trajectory is not a fixed multiple
of its level, so widths differ across regions. And it is worse, in every fleet
and every λ:

| fleet | λ | mean carbon | best week | worst week | weeks better | weeks worse |
|---|---|---|---|---|---|---|
| capacity_bound | 0.5 | +0.017 % | 0.000 % | +0.086 % | **0** | 36 |
| capacity_bound | 1.0 | +0.049 % | 0.000 % | +0.270 % | **0** | 37 |
| capacity_bound | 2.0 | +0.128 % | 0.000 % | +1.137 % | **0** | 39 |
| capacity_bound | 4.0 | +0.185 % | 0.000 % | +1.141 % | **0** | 40 |
| slack | 2.0 | +0.166 % | 0.000 % | +2.607 % | **0** | 40 |
| slack | 4.0 | +0.247 % | 0.000 % | +3.043 % | **0** | 41 |

`best week = 0.000 %` in every row is the theorem showing up as an exact tie:
the band either leaves the dispatch alone or makes it worse, never better.

## The boundary: when *could* a band act?

Two counterfactuals, **Modelled** (synthetic noise on top of the measured
series), because the real series has one shared factor and therefore no
heterogeneity to test. They separate *uncertainty* from *uncertainty that
differs across regions*.

| equal noise σ (control) | mean carbon | tail (CVaR-95) | weeks better |
|---|---|---|---|
| 0.00 (anchor = measured) | +0.166 % | +0.001 % | 0 |
| 0.05 | +0.181 % | +0.001 % | 0 |
| 0.10 | +0.214 % | +0.001 % | 2 |
| 0.20 | +0.294 % | +0.006 % | 1 |
| 0.40 | +0.379 % | +0.025 % | 5 |

Equal noise keeps the widths roughly proportional to the level, so the band
stays inert and merely adds cost. The tail gets *worse* too, not better.

| region-specific noise × profile | mean carbon | tail (CVaR-95) | weeks better |
|---|---|---|---|
| 0.0 (anchor) | +0.166 % | +0.001 % | 0 |
| 1.0 | +0.251 % | +0.006 % | 1 |
| 2.0 | +0.344 % | +0.018 % | 3 |
| 4.0 | +0.543 % | **−0.003 %** | 4 |

At four times a realistic volatility profile — wind-heavy South Scotland
steadiest, gas-heavy South Wales most volatile — the band finally buys tail
carbon: **0.003 % of tail for 0.54 % of mean, an exchange rate of about 170 : 1
against.** That is the band's only defensible role on a placement decision, and
it does not come close to paying for itself.

## What this does and does not establish

* **Does:** on any regional series built by scaling a national one, a calibrated
  band cannot improve a placement decision, and this is a proof plus 18,757
  measured slots, not an observation. The diagnostic is shipped
  (`uncertainty.classify`) so the claim can be checked on other datasets.
* **Does not:** say forecast uncertainty is useless for carbon scheduling. It
  says an *unconditional* band on a *scaled* series cannot choose a site. A
  conditional error model, or genuine regional actuals, would be a different
  object — which is why the boundary experiment is here rather than a footnote.
* **Does not:** measure any real grid's regional error structure. The
  counterfactuals are labelled Modelled. The honest next step is a grid that
  publishes per-region actuals (EIA-930 per balancing authority) and to re-run
  `classify` there.
* **Corollary for the literature:** a spatial-uncertainty result computed on a
  scaled regional series is vacuous at best and harmful at worst. That is a
  statement about a *method*, not about any paper's arithmetic.

## Why this matters for the rest of the project

It is the fourth independent confirmation that the band cannot reorder sites
(exp011 dispatch, exp016 timing, exp017 capacity, exp023 simulator), and the
first one that explains *why* in a way that transfers. It is also why the
project's scheduler claim is a **timing** claim: exp021's 6–12 % at matched
service comes from deferral, not from band-driven placement, and the band enters
as a level/tail hedge, never as a site selector.

## Disclosures

* Realized intensity is the national-scaling estimate, not a measurement. That
  is exactly what makes the theorem apply, and it is disclosed in every
  experiment that uses it.
* Demand is the single real Azure LLM week, laid positionally over each carbon
  week. Carbon is the only thing that differs between weeks.
* The boundary counterfactuals are synthetic (labelled **Modelled**); their σ
  axis is a sensitivity, not a measurement of any grid.
* The 2024 NESO pull has a real outage (15 hourly slots, 11–12 Jun 2024). The
  week rule drops any week whose calibration window touches a hole rather than
  interpolating.

## Reproduce

```
make exp-run EXP=exp026-uncertainty-cannot-reorder
```

Canonical run `20261123T125030Z-375cf197-ebc1`, git `96f61381`, `git_dirty:
false` (the corrected relative-band application). Deterministic: the
counterfactual uses the config seed.

**The boundary is now also measured on real data:** exp027 repeats this
diagnostic on EIA-930, where regional actuals come from each authority's own
measured fuel mix. There the structure is 100 % `regional`, 25 % of hours reorder,
and the band does occasionally help — by a fraction of a percent, in a minority
of weeks. So the theorem above is a statement about the scaling construction,
not about grids, and exp027 is what keeps it honest.
