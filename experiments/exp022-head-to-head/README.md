# exp022 — our scheduler against the published controllers, in their simulator

**Run:** `20261123T112936Z-3650b862-a7e7` · git `62be82c7` · `git_dirty: false`
**Window:** 2024-01-09T18:00Z + 7 days (the window the simulator actually read, seed 42,
clock aligned) · 4 UK sites · 21,943 tasks served by every controller

## Why this experiment exists

Every "we beat the rules" result in this project compared our planner to **our own**
rules. That is not evidence against the published algorithms, and cross-paper numbers
cannot supply it: the reported 16–60 % savings are measured against different baselines,
on different work, with different SLA accounting (see
`docs/research/2024-2026-carbon-scheduling-comparison.md`).

SustainCluster is the one comparator that can be held fixed — same simulator, same
workload, same four UK sites, same derived carbon series, same accounting. So our rule
was injected **into its own controller map** rather than bolted on through the action
space, which means it takes the identical assignment path as the published rules: same
`can_schedule` check, same pending queue, same step boundary, no transit step.

## What the planner sees, and what it is scored on

* **Decisions** use the NESO *forecast* (regional half-hours averaged to the hour) plus a
  conformal band calibrated on national residuals strictly **before** the window
  (`calibration_end = 2024-01-09T00:00Z`). A planner that read the simulator's installed
  realized series would have perfect foresight and the comparison would be void.
* **Accounting** is the simulator's own, on its realized series.

## Correction on the record (read this first)

The first run of this experiment reported an **exact tie to the decimal**. That
was an artefact and it is retracted. `current_time_task` inside the simulator is
a timezone-aware UTC timestamp, while our loaded forecast series are keyed by
naive datetimes. Every lookup therefore missed, `_window_risk` returned `None`,
and `DurationAwareStrategy` fell back to `dc.get_current_carbon_intensity()` —
which *is* `lowest_carbon`'s signal. All three "planner" arms were literally
`lowest_carbon`, so the tie measured nothing.

Fixed by normalising to naive UTC in `_hour`, pinned by three regression tests,
and made impossible to repeat silently: the strategy now counts fallbacks, the
driver reports them, and this experiment **raises** if any arm fell back. The
canonical run below reports `forecast_fallbacks: 0` for all three arms.

## A second fact the correction exposed

The carbon series installed into the simulator is the **realized** estimate
(`national_actual × regional_forecast / national_forecast`, see exp009). So
`lowest_carbon`, which reads `dc.get_current_carbon_intensity()`, sees realized
intensity: **it is an oracle.** Our planner reads the NESO *forecast* and is
causal. The comparison is therefore not like-for-like in information, and the
honest framing is "how close does a causal forecast-driven rule get to an oracle
that sees the answer", not "do we beat a published scheduler".

## Results

| controller | carbon (kg) | vs RR | vs `lowest_carbon` | SLA violated | tasks | information |
|---|---|---|---|---|---|---|
| `lowest_carbon` (published) | **106,449.2** | −6.87 % | +0.00 % | 0.05 % | 21,943 | **realized (oracle)** |
| `planner_window` (ours, causal) | 106,457.4 | −6.86 % | **+0.01 %** | 0.05 % | 21,943 | forecast |
| `planner_window_band` (ours, causal) | 106,457.4 | −6.86 % | **+0.01 %** | 0.05 % | 21,943 | forecast + band |
| `planner_instant` (ours, causal) | 106,477.9 | −6.86 % | **+0.03 %** | 0.05 % | 21,943 | forecast |
| `least_pending` (published) | 114,240.9 | −0.06 % | +7.32 % | 0.00 % | 21,943 | load only |
| `round_robin` (published) | 114,306.2 | +0.00 % | +7.38 % | 0.00 % | 21,943 | none |
| `most_available` (published) | 114,579.5 | +0.24 % | +7.64 % | 0.00 % | 21,943 | load only |
| `lowest_price` (published) | 117,863.7 | +3.11 % | +10.72 % | 0.05 % | 21,943 | price only |

**Verdict, stated plainly: we do not beat the published best here — we come
within 0.01 % of it while using strictly less information.** 8.2 kg out of
106,449 kg. Every arm serves identical work (21,943 tasks) at identical SLA
(0.05 %). The calibrated band changes nothing at all (`planner_window` and
`planner_window_band` are identical), which is exp026's theorem showing up in the
simulator for the fourth independent time.

Two measured facts explain why there is so little room.

**1. The only decision the interface exposes is *which site*.** `ClusterManager.distribute_workload`
queues a task only if the strategy returns a datacenter id; returning `None` discards it,
and `get_tasks_for_timestep` builds each step's tasks fresh and never re-serves them.
Deferral exists only in the `manual_rl` action path, which none of the rule-based
controllers use. So every controller in this table — published and ours — is placement-only.
(A first attempt drove the action path instead: it inserted a transit step before every task
ran and manufactured a 22 % SLA violation. That is a harness artefact, not a result, which
is why the controller map is the right entry point.)

**2. On this grid, the placement optimum is a single site for almost every hour.**
Over the run window, South Scotland (region 2) is the lowest-forecast region in 336 of 348
hours; North West England is cheapest in the other 12. Any rule that computes the argmin of
regional intensity therefore computes the *same assignment*, which is why duration-weighting
changes nothing and the calibrated band — which scales all sites by a common factor within a
slot, so it cannot reorder them, as exp011/exp016/exp017 each measured independently —
changes nothing either.

So the correct reading is: **this benchmark is saturated for the decision it exposes, the
published `lowest_carbon` rule already attains the optimum, and it attains it with realized
information we deliberately do not use.** exp023 quantifies how much of
the arena was ever contestable at all by measuring the idle floor; that is where the
explanation belongs, not in an excuse here.

## What this does and does not establish

* **Does:** on identical terms, in the published simulator, on the published controllers'
  own playing field, our scheduler is **not worse** than the best published controller — and
  the published −6.87 % vs round-robin is reproduced exactly, so the harness is trustworthy.
* **Does not:** prove our scheduler beats the published algorithms. It cannot, here. A
  head-to-head win requires a lever the interface does not offer.
* **Where the win does live:** exp021 compares against `run_now`, and `run_now` *is* the
  published rule's decision — place immediately at the cheapest site, spilling by capacity
  (`baselines.run_now` → `action_for_lam(0.0)`). The difference is that exp021's environment
  makes the deadline a policy variable (4 h) instead of `1.5 × duration`, so timing becomes
  expressible. There, at matched served volume, the planner cuts **11.8 % carbon and 2.34 pp
  of misses** capacity-bound, and **6.6 % carbon inside a 0.5 pp miss budget** on the slack
  fleet, 12/12 weeks, at equal or lower GB day-ahead cost.
* The honest combined claim is therefore conditional and must always be written with its
  condition: *where a workload's deadline permits deferral, our planner removes 6–12 % of
  carbon at matched service against the same decision rule the published controllers use;
  where the benchmark forbids deferral, the two are provably identical.*

## Disclosures carried from exp009

* Carbon is the derived regional estimate (`national actual × regional forecast ÷ national
  forecast`) because NESO ships no regional actuals — verified across the full matrix.
* The GB price series is **national**, so `lowest_price` has nothing to differentiate and is
  degenerate (+3.11 % carbon). Not a finding about price-aware scheduling.
* GB has exactly one AWS region (`eu-west-2`), so the transmission-cost matrix is 0 on the
  diagonal and that term is inoperative for a UK-only run. Never read as a finding.
* GPU utilisation is 7.42 % under every controller, so capacity never binds — placement is
  not being limited by space, which is what makes the argmin argument bite.

## Reproduce

```
make exp-run EXP=exp022-head-to-head
```

Requires the external checkout (`make sc-setup`) with the UK inputs installed
(`make sc-uk-data && make sc-uk-install`); the run asserts all eight controllers read one
identical window and one identical clock, and fails rather than silently compare two weeks.

Canonical run recorded under `runs/`; see the manifest for git SHA, config hash and data hashes.
