# exp020 — one shipped scheduler, operating point chosen on training months

## The problem this closes

exp017, exp018 and exp019 each produced a **frontier**: six or nine arms, three
prices, two fleets, a different winner in every corner. That is the honest shape of
the evidence, but it is not a scheduler. A deployment knows its price — what a
missed GPU-hour costs it — and needs one arm, and the only defensible way to
choose that arm is on weeks the reported numbers do not come from.

So this experiment does one thing: it builds the selection rule from training data
and then applies it, once, to data it never saw.

1. Run six candidate arms over **Jan–Sep 2024** (39 weeks).
2. For each (fleet, price) cell, take the arm with the best mean objective there.
3. Report that arm on the **12 held-out Oct–Dec weeks**.
4. Also report the best arm per cell *on* the held-out weeks, so the cost of honest
   selection is printed rather than assumed.

## Results

Canonical record `runs/20261123T074944Z-a6bf9949-e15c` (`git f4ec8454`, clean tree).
Objective is `carbon_kg + price × missed_gpu_hours`, exactly as every rung scores.

### Candidate arms — capacity-bound fleet (25 GPUs/site)

| arm | kg | missed | train @0.1 | @0.3 | @1.0 | held-out @0.1 | @0.3 | @1.0 |
|---|---|---|---|---|---|---|---|---|
| `run_now` | 991.5 | 0.1073 | 896 | 1150 | **2038** | 1118 | 1372 | **2261** |
| `last_slot` | 817.0 | 0.1930 | 875 | 1332 | 2930 | 1045 | 1502 | 3100 |
| `plan_none` | 811.3 | 0.1355 | 800 | **1120** | 2241 | 972 | **1292** | 2414 |
| `plan_q95` | 783.9 | 0.1431 | 790 | 1129 | 2313 | 953 | 1292 | 2476 |
| `plan_ghost_q95` | **782.8** | 0.1431 | **789** | 1127 | 2310 | **952** | 1291 | 2475 |
| `plan_hold_seasonal` | 899.3 | 0.1350 | 856 | 1175 | 2289 | 1059 | 1378 | 2497 |

### Candidate arms — slack fleet (40 GPUs/site)

| arm | kg | missed | train @0.1 | @0.3 | @1.0 | held-out @0.1 | @0.3 | @1.0 |
|---|---|---|---|---|---|---|---|---|
| `run_now` | 1109.0 | 0.0000 | 872 | 872 | **872** | 1109 | 1109 | 1109 |
| `last_slot` | 870.6 | 0.0500 | 745 | 863 | 1277 | 930 | 1048 | 1462 |
| `plan_none` | 854.6 | 0.0342 | 704 | 785 | 1068 | 895 | 976 | 1259 |
| `plan_q95` | **810.1** | 0.0365 | **676** | 762 | 1064 | **853** | 940 | 1242 |
| `plan_ghost_q95` | 826.0 | 0.0302 | 682 | 751 | 994 | 862 | **933** | 1183 |
| `plan_hold_seasonal` | 916.1 | **0.0095** | 719 | **740** | **813** | 927 | 950 | **1029** |

### The shipped map, and what it cost to choose honestly

| fleet | price | chosen on train | held-out objective | best on held-out | cost of honesty |
|---|---|---|---|---|---|
| capacity-bound | 0.1 | `plan_ghost_q95` | 952.1 | `plan_ghost_q95` 952.1 | +0.00% |
| capacity-bound | 0.3 | `plan_none` | 1292.1 | `plan_ghost_q95` 1290.6 | +0.12% |
| capacity-bound | 1.0 | `run_now` | 2260.6 | `run_now` 2260.6 | +0.00% |
| slack | 0.1 | `plan_q95` | 853.3 | `plan_q95` 853.3 | +0.00% |
| slack | 0.3 | `plan_hold_seasonal` | 950.0 | `plan_ghost_q95` 933.2 | +1.79% |
| slack | 1.0 | `plan_hold_seasonal` | 1028.9 | `plan_hold_seasonal` 1028.9 | +0.00% |

Against never deferring, the shipped scheduler scores:

| fleet | @0.1 | @0.3 | @1.0 |
|---|---|---|---|
| capacity-bound | 952.1 (−14.8%) | 1292.1 (−5.8%) | 2260.6 (±0.0%) |
| slack | 853.3 (−23.1%) | 950.0 (−14.3%) | 1028.9 (−7.2%) |

At the parity price it also emits 21% less carbon on the capacity-bound fleet
(782.8 vs 991.5 kg) and 27% less on the slack fleet (810.1 vs 1109.0 kg), at the
cost of missing 14.3% and 3.7% of work where never deferring misses none — which
is the trade the price is there to arbitrate.

## What the run says

**1. Honest selection is nearly free.** Four of six cells pick the arm that was
also best on the held-out weeks, and the worst penalty for choosing on training
data is **1.79%**. That is the number that makes the frontier usable: the ordering
of arms by objective is a property of the fleet and the price, not of the quarter,
so a map built on Jan–Sep is still the right map in Oct–Dec.

**2. The two near-misses are near-ties, not sign errors.** Capacity-bound at 0.3:
`plan_none` 1120 against `plan_ghost_q95` 1127 on train — a 0.6% gap that inverts to
a 0.1% gap on test. Slack at 0.3: `hold_seasonal` 740 against `ghost_q95` 751 on
train, but 950 against 933 on test. Both cells are places where two arms genuinely
sit on top of each other, so the selection flips on noise; the penalty stays small
because the arms are close. The cells with a real gap (0.1 and 1.0) are all chosen
correctly.

**3. The shipped map is monotone in the price, and that is the story.** As a missed
GPU-hour gets more expensive the scheduler moves from carbon-first to
deadline-first, and the two fleets find different extremes:

| | cheap miss (0.1) | crossover (0.3) | expensive miss (1.0) |
|---|---|---|---|
| slack fleet | calibrated reserve, carbon-first | seasonal arrival hold | seasonal arrival hold |
| capacity-bound fleet | reserve **+ ghosts** | plain planner | never defer |

On a fleet with spare capacity the reliability extreme is still *deferring well*
(`hold_seasonal` beats `run_now` at 1.0 — exp019's result), because the carbon it
saves covers the few deadlines it misses. On a capacity-tight fleet the same arm
loses badly (2497 against 2261) and the selection correctly falls back to never
deferring: there is no slack to trade, so any miss is pure loss. That contrast is
the scheduler's behaviour, stated in one table and derived from the price rather
than from a hand-set mode.

**4. What is *not* re-tuned here.** The calibrated reserve came from exp018's level
0.95 and the arrival model from exp019; neither was re-swept for these cells. The
only thing chosen on training months is *which arm to run*, which is the smallest
possible selection problem and the one a deployment cannot avoid.

## Where this leaves the project

The scheduler the user asked for now exists as one artefact with a measured
operating rule:

* **rules + planners**: a capacity-aware cheapest-feasible-block planner with
  deadline windows as hard constraints (exp017);
* **one calibrated uncertainty input that changes decisions**: the arrival
  quantile, because the carbon band structurally cannot (exp018, exp011/016/017);
* **anticipation**: a causal arrival model, which buys service and — on the slack
  fleet — the only planner win over never deferring at the obligation price (exp019);
* **one selection rule**, built on training months, costing at most 1.79% against
  tuning on the test weeks (this experiment).

The honest limits are unchanged and should lead any write-up: the band does not
choose sites; the demand stream is one real Azure week reused as a profile; the
region-to-datacentre mapping is a declared assumption; and the residual 9–20% gap
to the exact schedule at matched volume is arrivals the plan has not seen, which is
where learned arrival pressure — not more tuning — is the next lever.
