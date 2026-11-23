# Carbon-aware scheduling, 2024–2026: what the published numbers actually compare

**Purpose.** Answer the question "is this scheduler better than the available
algorithms, at the same price, latency, time and SLA?" with published evidence,
and correct our own novelty claims where the literature has moved.

Every identifier below was resolved live through the arXiv API on 2026-11-23.
Labels: **Verified** = read from the paper's own metadata/abstract; **Inspected**
= read in the repo/simulator; **Modelled** = our own estimate; **Assumption** =
disclosed, not proved.

---

## 1. The papers, with their own numbers and their own baselines

| # | Paper | ID / date | Technique | Reported carbon | SLA / latency | Baseline it beats | Caveat |
|---|---|---|---|---|---|---|---|
| 1 | Dissecting the Carbon-SLO Tension in Geo-Distributed LLM Serving (Topcu et al.) | arXiv 2610.14571, 2026-10-10 | MILP over batched requests, load-coupled ILP, per-request heuristics | up to **60%** | **~3%** average SLO violation | round-robin | Simulated; savings shrink as system load rises; depends on how often load updates arrive |
| 2 | CATS: A Carbon-Aware Task Simulator | arXiv 2609.14775, 2026-09-13 | trace-driven simulator; spatial and temporal shifting | **38.4%** spatial; **16%** temporal | 3.27% SLA violations | speed-first | 600k tasks, fleet utilisation 0.37; simulator, not a deployment |
| 3 | EcoServe | arXiv 2502.05043, 2025-02-07 | cross-stack ILP, Reduce/Reuse/Rightsize/Recycle | up to **47%** | "maintaining performance targets and SLOs" (no single % given) | performance-, energy- and cost-optimised design points | Production traces from *two* services at one cloud; includes embodied carbon |
| 4 | SLA-Constrained Carbon-Aware Routing in Geo-Distributed Serverless Clouds | arXiv 2607.22806, 2026-07-24 | constrained optimisation, latency-feasible region | **46.8%** max; **27.4%** average | **zero** SLA violations | latency-driven routing | Routing only (no deferral); 5→12 AWS regions; real carbon intensity |
| 5 | Carbon and Reliability-Aware Computing for Heterogeneous Data Centers | arXiv 2504.00518, 2025-04-01 | MILP with embodied-carbon and server-lifetime model | up to **21%** total | SLA-compliant by construction | carbon-oblivious dispatch | Numerical case study, not a live trace comparison |
| 6 | Uncertainty-Aware Decarbonization for Datacenters | arXiv 2407.02390, 2024-07-02 (rev. 2026-11-23) | **conformal prediction** on carbon-intensity forecast; temporal + spatial shifting | avoiding a **5%** (temporal) / **14%** (spatial) *increase* | not the focus | uncertainty-blind shifting | Production power traces; 20 MW cluster; **this is the closest prior art to our uncertainty claim** |
| 7 | CarbonEdge | arXiv 2603.27420, 2026-03-28 | carbon-aware partitioning + green scheduling at the edge | not quantified in abstract | latency-weighted scoring | latency/throughput-only edge frameworks | Edge, not datacenter fleet |
| 8 | DCcluster-Opt / SustainCluster (HPE, MIT) | arXiv 2511.00117, 2025-10-31 | Gymnasium benchmark; RBCs + SAC | benchmark, no single % | SLA is a reward term | — | **This is our exp008/exp009 environment**; its own reward leaves `timeliness_penalty` commented out |
| 9 | CarbonX | arXiv 2510.01521, 2025-10-01 | time-series foundation models + uncertainty for carbon forecasts | forecasting tool | — | grid-specific forecasting models | A forecasting tool, not a scheduler |
| 10 | GreenPassport | arXiv 2609.06784, 2026-09-06 | request-level carbon accounting with uncertainty and provenance | accounting | — | regional averages | Accounting, not scheduling |

**Verified**: all ten identifiers, dates and headline numbers above are taken from
each paper's own abstract, fetched 2026-11-23.

---

## 2. Why the published percentages are not comparable to each other

The range 16–60% is not a disagreement about physics; it is four different
measurements:

- **Different baselines.** Round-robin (1, 2), latency-driven routing (4),
  performance/energy/cost-optimised design points (3), carbon-oblivious dispatch
  (5). Round-robin is a weak baseline; beating it by 60% says less than beating a
  cost-optimised scheduler by 21%.
- **Different levers.** Spatial only (4, most of 1), temporal only (6), both (2,
  3, 5). Spatial shifting requires real regional carbon spread; temporal shifting
  requires slack in the deadline.
- **Different work.** Batch/offline inference (3, 6) can defer freely; online
  serving (1, 4) cannot. Our workload is a mix with explicit deadline classes.
- **Different SLA accounting.** "3% violations" (1), "3.27%" (2), "zero" (4),
  "avoiding a 14% increase" (6), and "up to 47% while maintaining SLOs" with no
  number (3) are not the same quantity.

So a single cross-paper comparison table is a category error. What *is* legitimate
is to place our result inside the band the SLA-respecting papers occupy, and say
so.

---

## 3. Where our result sits, stated honestly

Our matched-service measurement (exp021, canonical run
`20261123T094258Z-487d8c96-fa5e`, 12 held-out Oct–Dec 2024 weeks):

| | carbon vs never-defer | SLA change | money | latency of served work |
|---|---|---|---|---|
| Capacity-bound, `look8_ghost` | **−11.8%** | **−2.34 pp misses** | −3.5% | 140 m vs 85 m |
| Capacity-bound, matched served volume | **−8.7%** | identical | — | — |
| Slack, inside a 0.5 pp miss budget (`look4_ghost`) | **−6.6%** | +0.48 pp | −1.6% | 53 m vs 16 m |
| Slack, full horizon (`plan_q95`) | −26.9% | **+3.65 pp** | −9.4% | 181 m vs 16 m |

Three honest statements follow:

1. **Our 11.8%-with-better-SLA result is inside the SLA-respecting band** of the
   literature (CATS temporal 16% at 3.27%; serverless routing 27.4% average at
   zero violations; uncertainty-aware 5–14%). It is not the largest number in the
   table, and claiming it were would be false.
2. **Our 26.9% number is the one a careless paper would headline**, and it is the
   one that costs 3.65 pp of SLA. The literature papers that report ~60% (1) also
   report ~3% violations — i.e. they, too, are paying a service price, and the
   comparison should be made at equal SLA, not at equal headline.
3. **The 6.6% slack result is the conservative end**, and it is the number we can
   defend without an asterisk, because `run_now` there misses nothing.

---

## 4. Price and latency: what the literature does and does not report

- **Price.** Most carbon papers (1, 2, 4, 6) report carbon only. EcoServe (3)
  reports cost as one of several design points. **We report both**, and find that
  in GB every arm is also *cheaper* (−1.5% to −9.4%) because low-carbon hours
  are low-price hours. That correlation is a GB fact, not a universal one; in a
  solar-heavy grid the price trough can sit at midday while the carbon trough is
  elsewhere. **Recommendation:** re-run the price column on a grid with a
  different carbon-price correlation before generalising the claim.
- **Latency.** Papers report SLO *violation rate* (1, 2) or routing overhead
  (4: <0.02% of request latency), not the latency distribution of served work.
  Ours is finer-grained and more conservative: we report GPU-second-weighted mean
  queueing delay of **served** work, which rises 16 → 181 min on slack and
  85 → 170 min on the capacity-bound fleet. That is a real product cost that the
  violation rate alone hides.

---

## 5. The novelty claim has to change

The project context currently says the contribution is the *first* combination of
decentralised limited-communication MARL + calibrated forecast uncertainty + real
region-matched carbon + risk-aware deadlines. **Paper 6 (arXiv 2407.02390) already
does conformal carbon-intensity uncertainty for datacenter load shifting**, and
CarbonX (9) ships uncertainty with its forecasts. "First to use conformal
prediction on carbon intensity" is therefore **not defensible** and must be
removed.

What remains defensible, and should be the revised claim:

1. **A measured negative result about where the band can act.** Under the
   national-scaling estimator (`realized = national_actual × regional_forecast /
   national_forecast`), per-slot regional ordering is exact, so the calibrated
   band cannot reorder sites — replicated on three decision surfaces (exp011
   dispatch, exp016 timing, exp017 capacity). Paper 6 uses the band to avoid
   *carbon increases* under forecast error; we show that on a real regional
   series the band's decision value is on level and timing risk, not on ranking.
   That is a different and, as far as the survey found, unclaimed result — but
   "unclaimed" is weaker than "first", and must be written as "we did not find".
2. **Decentralised multi-agent scheduling with a CVaR tail term on SLA
   violations**, evaluated with matched-service accounting. Papers 1–5 are
   centralised solvers or heuristics; none is a decentralised MARL scheduler with
   an explicit tail-risk term, and none reports matched-service extrapolation.
3. **The matched-service protocol itself** — reporting the carbon-vs-miss
   frontier rather than a single point — is a methodological contribution the
   field currently lacks, and it is what makes our 11.8% honest where a 60%
   headline is not.

**Assumption / limitation to state in the paper:** "we did not find" is not
"nobody has done it". The 30-paper survey predates papers 1–10 above; the survey
must be refreshed before the claim is written.

---

## 6. The one comparison still missing

Our "beats every rule" result compares our planner to **our own** rules. That is
not "beats existing algorithms". The only same-simulator, same-data literature
comparator available to us is **DCcluster-Opt / SustainCluster** (paper 8), which
we already run and whose UK inputs we already install (exp008, exp009). The
missing experiment is the head-to-head:

> our planner vs SustainCluster's `lowest_carbon` / `lowest_price` / round-robin
> RBCs, in the same simulator, on the same 7-day UK window, at matched SLA.

Until that table exists, the paper claim must be "beats hand-written scheduling
rules **in our environment**, and reproduces the SustainCluster baseline" — not
"beats existing schedulers".

---

## 7. Direct answers to the four questions

| question | answer | evidence |
|---|---|---|
| **Same carbon?** | Yes, a real saving at matched service: −11.8% (capacity, better SLA) / −6.6% (slack, +0.5 pp). Not 27%. | exp021 |
| **Same price?** | Yes or better: every arm −1.5% to −9.4% at the real GB day-ahead price. GB-specific correlation; not generalised. | exp021 |
| **Same latency?** | **No.** Served work waits 1–2 h longer, inside its deadline. This is the honest cost. | exp021 |
| **Similar SLA?** | Yes on the capacity fleet (**better**: −2.34 pp). Slack needs +0.5 pp for the 6.6% figure. | exp021 |
| **Better than existing algorithms?** | **Not yet demonstrated against a published scheduler.** Against our own rules, yes. Against SustainCluster, untested. Cross-paper numbers are not comparable. | §2, §6 |
