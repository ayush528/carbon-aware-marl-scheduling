# Carbon-Aware Scheduling Under Forecast Uncertainty: A Matched-Service Evaluation of Placement and Timing in Geo-Distributed Data Centres

**Draft v0.1 — every number in this document must appear in `claims-table.md` before submission.**
Pending numbers are marked `⟨exp028⟩` / `⟨exp029⟩` and are the only placeholders allowed.

## Abstract

Carbon-aware schedulers are usually evaluated as a percentage reduction against
another controller, under identical demand but with little attention to two
questions: how much of the reported denominator was ever controllable, and
whether the saving survives a correction for work that missed its deadline. We
answer both. On real UK grid data and a real LLM inference trace, a forecast-
and-reserve planner removes **6–12% of total carbon with no worse SLA** where deadlines
permit deferral, at the same or lower electricity cost; on the capacity-bound
fleet this is **8.7% at literally identical served volume**, with completion
later but inside the deadline. The saving survives volume
changes, diurnal rotation, day permutation and block bootstrap of the demand
trace (12/12 cells). In the published SustainCluster benchmark, by contrast,
the controller interface exposes placement only and 88.7% of emissions are idle
draw; there our causal planner comes within **0.01%** of the best published
controller even though that controller reads realized carbon and ours reads a
forecast. Giving all controllers the same tested deferral buffer yields a small
carbon win (0.036%) at matched SLA and service, and an 11× reduction in SLA
violations from our calibrated reserve at large slack. Our uncertainty result
is negative in a specific, useful sense: when regional actuals are estimated by
scaling a national forecast, all regions share one per-slot error factor, so
calibrated bands cannot reorder sites and forecast-greedy is already the slot
optimum (0 of 42 weeks improved); on real per-region grid data 25% of hours do
reorder, but the band's mean benefit stays within 0.03% of zero. The
contribution is therefore an evaluation methodology — matched service, an
explicit controllable denominator, rolling-origin selection and a characterised
boundary for uncertainty — rather than a new learning algorithm.

## 1. Introduction

Public workload traces do not identify the grid region of the data centre that
served them. Carbon-aware scheduling built on such traces therefore rests on an
unverifiable mapping. We use UK national and regional carbon data (NESO) as
region-matched ground truth, conformal prediction bands on the forecast, and a
real Azure LLM inference trace, and we disclose the mapping assumption in the
abstract rather than a footnote.

The paper asks three questions a reviewer should ask of any result in this area:

1. **Is it better than existing systems?** Against the published controllers in
   SustainCluster, without deferral: essentially no (§5). With the same deferral
   lever for everyone: a small carbon win and a large service-robustness win
   (§5).
2. **Is the comparison like-for-like?** Every number is at matched served
   volume, with price, latency (completion time) and SLA reported beside carbon
   (§4). Savings from shedding work are not counted as savings.
3. **Does uncertainty actually help?** We characterise exactly when it cannot,
   prove the structural reason, and measure the boundary on a grid with real
   regional actuals (§6).

We do not claim a novel MARL algorithm. Independent PPO agents, a centralised
critic, communication and a CVaR tail term were evaluated and are reported as
negative results (§7). The shipped scheduler is a capacity-aware planner.

## 2. Related work and the denominator problem

Carbon-aware scheduling papers report percentages against a baseline controller.
That practice hides two quantities: the idle carbon that no controller can
remove, and the service difference between the arms. In our UK instantiation,
the identical simulator with the task stream switched off emits 101,414.2 kg of
`round_robin`'s 114,306.2 kg over one week — **88.7%** is idle draw, leaving an
11.3% contestable range of which the best published rule already captures
60.95% (exp023). ⟨exp028: the full curve over utilisation, showing that this
share is an operating point and not a constant.⟩ We therefore state the claim
with its arena: *where a deadline permits deferral*, our planner removes 6–12%
at matched service; *where the benchmark forbids deferral*, the two are nearly
identical. The claim is never "the denominator is wrong in prior work" — it is
that the denominator is rarely reported.

## 3. Data and the uncertainty model

- **Carbon.** NESO national forecasts and actuals; 14 DNO regional forecasts.
  Regional actuals do not exist in the API (verified live), so realized regional
  intensity is estimated as `national_actual × regional_forecast /
  national_forecast`. This assumption is disclosed wherever a regional result
  appears.
- **Demand.** The Azure LLM inference trace (16.8M requests) is mapped to
  half-hourly arrivals and token counts on the NESO grid; one real week is
  reused across carbon weeks (§8).
- **Bands.** Split conformal on national forecast residuals, calibrated on the
  28 days before each evaluated week. Held-out coverage 92.1% against a 90%
  target nationally; 12/14 regions ≥90% regionally.
- **Price / time.** Real GB day-ahead (Elexon MID, GBP→USD at the ECB 2024 mean).
  Served-work queueing delay is reported for *served work only*, since shed work
  has no response time and excluding it would flatter arms that miss deadlines.

### 3.1 A theorem about scaled regional series

Let `f_r(t)` be the regional forecast and `a(t)` the national actual. The
estimated regional actual is

    x_r(t) = a(t) · f_r(t) / f_n(t) = f_r(t) · [ a(t) / f_n(t) ] .

The bracket does not depend on `r`. Hence for every slot, `x_r(t)/f_r(t)` is a
shared factor and the realized regional ranking equals the forecast ranking.
For the linear per-slot capacity problem, forecast-greedy is therefore the
optimum and any band that reorders sites is reordering on zero information.
Measured on 42 weeks / 18,757 slots: 0 reordered slots, 100% common-
multiplicative structure, relative-error spread 1.78e-15; a pooled relative
band changes 0.0000% of carbon at every λ; a per-region absolute band reorders
4.6–10.0% of slots and improves **0 of 42** weeks. The theorem is about the
*construction*, not about grids: with EIA-930 per-balancing-authority fuel mix,
4,339 hours are 100% regional, 25.03% reorder, volatility spans 106×, and the
band helps in 4–5 of 18 weeks by at most 0.41% — a mean within 0.03% of zero.

## 4. Scheduler and evaluation protocol

`BlockPlanner` prices each (slot, site) block by `forecast + λ·band`, assigns the
tightest-deadline backlog to the cheapest legal capacity, executes one slot and
replans. It accepts three levers used in the results: a calibrated arrival
reserve (§3), an anticipation model that books predicted arrivals into future
blocks, and a maximum lookahead that turns deferral into one bounded parameter
(`0` = serve now, `None` = full horizon). All levers are disclosed; the
operating point for a given fleet and price is selected on training weeks only
(§5).

Two fleets (25 and 40 GPUs per site), four deadline classes (1/2/4/8 h, equally
split because the trace has no latency labels), three price weights for a missed
GPU-hour, and 12 held-out Oct–Dec 2024 weeks form the main arena. Every arm sees
the same demand and the same carbon series; selection never sees an evaluation
week. `⟨exp029: rolling-origin choice on all 44 weeks of 2024, with the
oracle-per-week reference.⟩`

## 5. Results

### 5.1 Matched service, cost and latency

At matched served volume the capacity-bound fleet's `look8_ghost` removes
11.8% of carbon (8.7% after extrapolation to the reference's volume) and
2.34 percentage points of misses, 12/12 weeks; the slack fleet's best point
within a 0.5 pp miss budget removes 6.6%. Every arm is cheaper at the real GB
day-ahead price (−1.5…−9.4%), and served work completes 16→181 minutes later
(slack) / 85→170 (capacity-bound), monotonically with lookahead, always within
the deadline. Earlier 21–27% figures are retracted as headlines because those
arms missed 3–4% where serve-now misses none.

### 5.2 Demand robustness

⟨exp031 numbers: 12/12 cells positive; table in the experiment README.⟩

### 5.3 Published benchmark: placement only

Our causal planner emits 106,457.4 kg against `lowest_carbon`'s 106,449.2 kg
(+0.01%), same 21,943 tasks and 0.05% SLA. `lowest_carbon` reads realized
carbon, ours reads the forecast; this is near-matching an oracle with less
information, not a tie with a peer. The earlier "exact tie" was a timezone
lookup artefact and is retracted.

### 5.4 Published benchmark: equal timing lever

A tested runtime deferral buffer given identically to all six controllers
yields, at the published 1.5× SLA, 106,375.4 kg for our planner against
106,413.3 kg for `lowest_carbon` (−0.036%) at identical 0.27% SLA and 21,886
tasks. At 4× and 8× slack the two converge. The lever is worth 0.03%, 1.07%
and 2.02% of total carbon at 1.5×/4×/8×. At 8× the natural myopic timing rule
violates 1.44% of SLAs (29× the placement baseline); our calibrated reserve
holds it to 0.13% while finishing 847 more tasks for +0.55% carbon.

### 5.5 The denominator

⟨exp028 table: floor share, contestable share and savings at five arrival rates.⟩

## 6. What uncertainty buys

Bands are valuable on *level and timing* (arrival reserve, deadline risk) and
not on *regional ranking*. We prove the construction-specific impossibility,
measure its boundary on real per-region grid data, and show that a relative
band actively misprices a near-zero-carbon hydro region (+41.6% worst week).
Under deliberately favourable synthetic heterogeneity the exchange rate is
~170:1 against. The risk-qualified headline for the 6–12% result is
`⟨pending: band-derived lower bound on level⟩`.

## 7. Negative results

Independent PPO agents converge to immediate carbon-greedy when service is free
and implement whatever deadline price they are given; they never dominate the
planner on the service frontier. At the parity price the learner cuts carbon
26.6% while missing 25.8% of work — a different point, not a better one. CVaR
at α 0.8/0.9/0.95 has no measurable effect: the terminal charge lands in one of
336 advantages, and the per-step version stays within 2 points of risk-neutral
against a 15-point seed spread. Communication and a centralised critic do not
consistently help. Multi-seed replication shows the direction is robust but the
magnitude bimodal. These results are why the shipped system is a planner, and
why the paper does not claim MARL as a contribution.

## 8. Limitations

1. One real LLM demand week; exp031 shows shape-independence but not a second
   source.
2. One main grid (UK); the US data in exp027 is a boundary test, not a second
   evaluation arena.
3. Deadline classes are assumed equal because the trace has no latency labels.
4. GB has one AWS region, so transmission cost is zero and that term is
   inoperative; the GB price is national, so `lowest_price` is degenerate.
5. The contestable-share number is operating-point dependent (§2, exp028).
6. All savings are relative to an identical-demand baseline; absolute numbers
   are illustrative.

## 9. Conclusion

The defensible contribution is a measurement discipline: match service, expose
the controllable denominator, select on the past, and characterise the boundary
of the uncertainty claim. Under that discipline the planner delivers 6–12% at
matched service where deferral is expressible, and a near-oracle result where it
is not. We did not find a setting in which a multi-agent learner or a calibrated
band outperforms this planner on the same objective; we report that instead of
framing it as an ablation.

## Reproducibility

One experiment = a committed `config.yaml` + a registered function; `make
exp-run EXP=<id>` appends an immutable record with git SHA, config/data hashes,
seed and metrics. Rollback via `make rollback EXP=<id>` checks out the tagged
state; re-running must reproduce the recorded hashes and metrics. CI runs lint
and tests on Python 3.11/3.12 plus a Docker build and in-image test run.
