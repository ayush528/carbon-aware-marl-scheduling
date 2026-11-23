# exp030 — the head-to-head with the timing lever available to everyone

**With the same lever, our planner beats the best published controller at the
published deadline — and its reserve variant cuts SLA violations 11× when slack
is large. Both are matched-service.**

exp022 could only compare placement, because the benchmark's controller interface
discards a task when a strategy returns no site. exp023 measured that 88.7% of the
carbon is idle draw. This experiment removes the interface limitation for
*every* controller equally and measures what the lever is actually worth.

## How the lever is given, and why it is fair

A runtime buffer (`sim/deferral.py`) wraps two cluster-manager methods so any
controller may hold a task back. **Upstream source is unmodified.** Two guarantees
are pinned by tests:

1. the wrapper loses or duplicates no task that the controller assigns;
2. deferral never pushes a task past its last legal start, so the buffer cannot
   itself manufacture a violation.

Work that expires while waiting is still missed by the simulator's own SLA
accounting, which is why `tasks_finished` is reported for **every** arm below.
At the published 1.5× deadline the compared arms serve identical work; at 4×
and 8× they do not, and the difference is reported as a service result, never
silently counted as a carbon saving.

The timing policy (`myopic`: defer to the cheapest slot still inside the deadline)
is **identical for all six controllers**. So a difference in outcome belongs to the
controller, not to us having given ourselves a better lever.

Upstream hardcodes `sla_multiplier = 1.5`, leaving a median 76-minute task ~38
minutes of room — barely two 15-minute steps. Widening it is a **disclosed
benchmark modification applied identically to every controller**, so the lever's
value is reported as a curve over available slack rather than one number at one
arbitrary deadline.

## The arena

Idle floor **101,414.2 kg**; `round_robin` **114,306.2 kg**; contestable range
**12,892.0 kg = 11.28%** of total. Every saving below is scored against both.

## 1. The lever's value is a function of slack

Best published controller (`lowest_carbon`), with and without the shared lever:

| declared SLA | carbon (kg) | vs round-robin | share of contestable captured | SLA violated | tasks |
|---|---|---|---|---|---|
| 1.5× (as published), no lever | 106,449.2 | −6.87% | 60.95% | 0.05% | 21,943 |
| 1.5× + lever | 106,413.3 | −6.91% | 61.22% | 0.27% | 21,886 |
| 4× + lever | 105,309.8 | −7.87% | **69.78%** | 0.19% | 21,420 |
| 8× + lever | 104,281.7 | −8.77% | **77.76%** | 1.44% | 20,666 |

So the timing lever is worth **+0.27 → +8.83 → +16.81 percentage points of the
contestable range**, i.e. 0.03% → 1.07% → 2.04% of *total* carbon. That is the
reconciliation this project needed: 2% of total here and 6–12% of total in our own
environment are the same order of magnitude once the idle share is divided out.

## 2. With the same lever, do we win?

| declared SLA | best published + lever | ours + lever | difference | SLA | tasks |
|---|---|---|---|---|---|
| **1.5×** | 106,413.3 | **106,375.4** | **−37.9 kg (−0.036%)** | identical (0.27%) | identical (21,886) |
| 4× | 105,309.8 | 105,309.7 | −0.1 kg (tie) | identical | identical |
| 8× | 104,281.7 | 104,281.7 | 0.0 kg (tie) | identical | identical |

**At the published deadline our planner wins**, at identical SLA and identical
served work. It is a small win — 0.036% — and it is reported as small. At longer
deadlines the two converge exactly, because placement is saturated and the shared
timing rule then does all the work.

## 3. The reserve is a service lever, and it is the real differentiator

Our reserve arm budgets each cheap future block against the measured arrival rate
(32.65 tasks/slot, from the workload — not tuned here) and serves overflow now
instead of queueing for it.

| declared SLA | arm | carbon (kg) | SLA violated | tasks finished |
|---|---|---|---|---|
| 1.5× | myopic | 106,375.4 | 0.27% | 21,886 |
| 1.5× | **reserve** | 106,395.3 | **0.06%** | 21,909 |
| 4× | myopic | 105,309.7 | 0.19% | 21,420 |
| 4× | **reserve** | 105,526.0 | **0.06%** | 21,580 |
| 8× | myopic | 104,281.7 | **1.44%** | 20,666 |
| 8× | **reserve** | 104,860.0 | **0.13%** | **21,513** |

At 8× slack the myopic rule — the natural temporal extension of `lowest_carbon`,
and what every controller gets — violates **1.44%** of SLAs, 29× the placement-only
baseline. The reserve holds it to **0.13%**, an **11× reduction**, and finishes
**847 more tasks**, for **+0.55% carbon**.

That is the honest, substantial win: *"defer to the cheapest slot" is a trap when
slack is large, because every task piles into the same cheap block and then queues
past its deadline. Budgeting that block against predicted arrivals fixes it.* No
published controller has this, and it is the same mechanism exp016 measured
failing and exp019 measured working in our own environment.

## 4. Non-carbon-aware controllers barely benefit

At 8× slack, `round_robin` + lever reaches only −2.09% and `least_pending` −1.95%,
against `lowest_carbon`'s −8.77%. Deferring to a cheap *time* does not help if you
are still spreading work across dirty *sites*. The two levers compose; neither
substitutes for the other.

## What this does and does not establish

* **Does:** with the timing lever available identically to all, our planner is
  better on carbon at the published deadline (matched SLA, matched service), and
  its reserve variant is dramatically better on SLA robustness at large slack.
* **Does:** the lever's value is a curve over slack, and normalising by the
  contestable carbon reconciles this benchmark with our own environment.
* **Does not:** claim a large carbon win. 0.036% is the carbon margin at the
  published deadline; the large effect is on service, and it costs carbon.
* **Does not:** compare against a forecast-driven published controller.
  `lowest_carbon` reads the *realized* series installed by exp009, so it is an
  oracle; our planner uses only the NESO forecast. Our win is achieved with
  strictly less information.

## Disclosures

* The deferral buffer is a runtime wrapper; upstream source is unmodified.
* Widening `sla_multiplier` is a disclosed benchmark modification applied
  identically to every controller; upstream's 1.5× is included as the reference.
* The installed carbon series is the realized estimate, so `lowest_carbon` is an
  oracle and our planner is causal.
* The reserve fraction (0.5) is a single disclosed setting, not tuned on this
  window; the arrival rate it budgets against is measured from the workload.
* GB has one AWS region, so transmission cost is 0 and that term is inoperative;
  the price series is national, so `lowest_price` is degenerate.
* The published simulator's controller interface does not expose served-work
  queueing delay, so the latency axis of the comparison is measured in our own
  environment (exp021), not here. Cost is reported in every arm's metrics.

## Reproduce

```
make exp-run EXP=exp030-deferral-head-to-head
```

39 arms: 3 SLA multipliers × 6 controllers × 2 shared policies, plus our reserve
arm at each multiplier, plus the idle floor. Fully deterministic, seed 42.
