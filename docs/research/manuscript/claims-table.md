# Claims table — every statement in the paper, with its evidence and its fence

This is the contract for the manuscript. A claim may appear in the paper only if
it has a row here, an experiment that produced it, and the stated fence beside
it. All rows below have canonical runs except where explicitly noted; no number
may enter the paper without one.

## Primary claims

| ID | Claim (exactly as it may be written) | Evidence | Fence that must travel with it |
|---|---|---|---|
| C1 | Where a deadline permits deferral, a forecast-and-reserve planner removes **6–12% of total carbon with no worse SLA** against serve-now placement, at the same money or less, with completion later but inside the deadline; on the capacity-bound fleet **8.7% at literally identical served volume**. | exp021 canonical run: capacity-bound `look8_ghost` −11.8% total / −8.7% matched, −2.34 pp misses, 12/12 weeks; slack fleet best within a 0.5 pp miss budget 6.6% (`look4_ghost`). exp020 selection on 39 weeks, 12 held-out. | The 27% figures from exp017–020 are **retracted as headlines**: those arms missed 3–4% where `run_now` misses none. Quote the 6–12% Pareto region with "no worse SLA"; the literally matched-service point is 8.7%. Never quote 21–27% without its miss cost. |
| C2 | The saving is not an artefact of the one real demand week's shape, volume or day order. | exp031: matched-service saving positive in **12/12** variant × fleet cells (2.69–18.69% capacity-bound, 3.73–18.24% slack); `real` row reproduces exp021 on the capacity-bound fleet (−11.76% total / −8.70% matched). | All variants are *transformations of one real trace*, not a second workload. Magnitude is demand-dependent; report the frontier, not one number. |
| C3 | Where the published benchmark forbids deferral, our causal planner **near-matches** the best published controller: 106,457.4 vs 106,449.2 kg (**+0.01%**), same 21,943 tasks and 0.05% SLA. | exp022 canonical run `20261123T133108Z-3650b862-11bb`, zero forecast fallbacks. | `lowest_carbon` reads the **realized** series and is an oracle; ours reads the NESO forecast. Do not call this a tie against a peer. The earlier "exact tie to the decimal" is **retracted** (tz-lookup artefact, `08039be`). |
| C4 | When the timing lever is given to every controller equally, our planner wins by **37.9 kg (0.036%)** at the published SLA at identical service, and its reserve cuts SLA violations **11×** at 8× slack (1.44% → 0.13%) while finishing 847 more tasks for +0.55% carbon. | exp030 canonical run. A tested runtime wrapper on the cluster manager; upstream source untouched; no task lost/duplicated, no deferral past the last legal start. | The carbon win is *small* — say so. Widening `sla_multiplier` is a disclosed benchmark modification applied identically to all arms. `lowest_carbon` remains an oracle. |
| C5 | The lever's value is a curve over slack: 0.03% → 1.07% → 2.04% of total carbon at 1.5×/4×/8× SLA. | exp030, same run. | One week, one estate. Normalise by the contestable range before comparing with other benchmarks. |
| C6 | A scaled regional carbon series has a **shared per-slot error factor**, so realized and forecast induce the same regional ranking; forecast-greedy is the slot optimum and any reordering band can only misprice. | exp026: 42 weeks / 18,757 slots, 0 reorders, 100% common-multiplicative, relative-error spread 1.78e-15; absolute band better in **0 of 42** weeks. | This is a theorem about the *construction*, not about grids. Data without regional actuals forces the construction; disclose it. |
| C7 | On a grid with real per-region actuals the structure is different: 25.03% of 4,339 hours reorder, volatility spans 106×, and the band helps in a minority of weeks by <0.5%. | exp027: EIA-930 generation by fuel per balancing authority, completeness-gated. | The mean effect is within 0.03% of zero at low λ and a cost by λ=2; gains run through spill order, not the winner. A relative band misprices the hydro region (worst week +41.6%). |
| C8 | In the published benchmark **88.7%** of carbon is idle draw the controller cannot touch; contestable carbon is 11.3%, of which `lowest_carbon` takes 60.95%. | exp023 canonical run `20261123T133136Z-514501a6-0b9c`: floor 101,414.2 of 114,306.2 kg. | Operating-point specific (~7% utilisation, four sites). **exp028 measured the curve: 96.88% → 65.72% floor share as utilisation rises 1.9% → 29.5%**; never quote the point alone. The marginal-intensity split is derived and stays out of headlines. |
| C9 | Calibrated conformal bands hit their target on held-out months: 92.1% vs 90% target (national, Feb), 12/14 regions ≥90% (regional). | exp004, exp005. | Bands on *level*, not on regional ranking (C6). |
| C10 | The arrival reserve calibrated on real arrivals nearly matches one tuned on the test set (810.1 vs 812.6 kg, 3.65% vs 3.75% misses on slack). | exp018. | Coverage is 0.778 at nominal 0.90 across the two halves of one diurnal week (1.0 reverse): one week is not exchangeable with itself. Best level is fleet-dependent → frontier. |

## Negative results (must be reported, not hidden)

| ID | Finding | Evidence | Why it matters |
|---|---|---|---|
| N1 | IPPO/MAPPO learners implement the deadline price they are given, but **never beat the planner** on the service frontier. | exp013/014: learner matches carbon-greedy when service is free; at parity it cuts carbon 26.6% while missing 25.8% — a different point, not a better Pareto point. exp016: no learner beats the best timing rule at any price. | The shipped system is the planner, **not** MARL. The title and abstract must not claim MARL as the contribution. |
| N2 | CVaR tail term is inert at α 0.8/0.9/0.95; communication and a centralised critic do not consistently help. | exp013 (terminal charge lands in 1 of 336 advantages), exp014 (mean within 2 points of risk-neutral against a 15-point seed spread). | Report as measured negatives with the mechanism, not as an ablation that "did not converge". |
| N3 | Band-in-the-observation is worth ≈0.01% (exp012); band in the decision changes 0.0000% at every λ on the UK series (exp017, exp026). | exp012, exp017, exp026. | Uncertainty earns its place on *level and timing*, never on site ranking. |
| N4 | Under deliberately favourable synthetic heterogeneity the band's exchange rate is ~170:1 against (0.003% tail for 0.54% mean). | exp026 boundary, labelled Modelled. | Prevents the reviewer extracting a spatial-uncertainty contribution that the data cannot support. |
| N5 | The published benchmark's non-carbon controllers barely benefit from the timing lever (−2.09% `round_robin`, −1.95% `least_pending` vs `lowest_carbon`'s −8.77% at 8×). | exp030. | Placement and timing are complementary levers; neither substitutes for the other. |

## Open items → paper sections

| Item | Status | Where it lands |
|---|---|---|
| exp028 idle-floor curve | **done, canonical `20261123T202530Z-aa4ce0b3-8ca8`** | §Benchmark denominator; replaces the standalone 88.7% point |
| exp029 rolling-origin over 44 weeks | **done, canonical `20261123T195131Z-eb623421-89a1`** | §Evaluation; replaces "12 held-out weeks" as the main stability evidence |
| Risk-qualified headline | **done in exp029**: one-sided conformal per-week saving lower bounds +13.5% to +20.5% at α 0.1, with the unmatched-service caveat | §Results |
| Manuscript draft | **draft complete** (`docs/research/manuscript/paper.md`); journal formatting remains | entire paper |
| One demand source / one main grid | disclosed, bounded by exp027 + exp031 | §Limitations |

## Reviewer-gap register

| Reviewer objection | Answer | Status |
|---|---|---|
| "The title says MARL; the learner loses to the planner." | The paper frames the contribution as uncertainty-aware planning; MARL is an explicit negative-results section (§7, N1, N2). | **closed in paper §1/§7** |
| "CVaR inert / communication useless." | Explicit negative-results subsection with mechanism (paper §7, N2). | **closed in paper §7** |
| "One Azure week reused." | exp031 transformations; limitation retained (C2). | **closed by exp031** |
| "Main result is one grid." | exp027 real-actual boundary + exp031 demand; claim stays conditional on the UK construction (C6/C7). | partly closed; disclosure required |
| "No manuscript." | `docs/research/manuscript/paper.md` draft + this table. | **draft closed; formatting remains** |
| "Beats existing systems?" | exp022: no (near-oracle, placement only); exp030: small carbon win at matched SLA + large SLA-robustness win. Honest answer stated in abstract. | **closed by exp022/exp030** |
| "Same price, latency, SLA, matched service?" | exp021/exp030 report all four; no shedding counted as saving. | **closed** |
| "Does the denominator matter?" | exp023 point + exp028 curve (96.9%→65.7% floor share). | **closed by exp028** |
| "Tuning on evaluation weeks?" | exp020 selection on 39 weeks; exp029 rolling origin, 36 weeks, ≤1.33% cost of causality. | **closed by exp029** |
