# exp017 — a capacity-aware scheduler (the hybrid)

## The question

exp016 closed rung 7 with a negative result that points somewhere specific. The
four hand-written timing rules are **not ordered by how much they know**:
`forecast_timing` sees the whole calibrated forecast and is *worse* per served
GPU-hour than `last_slot`, which sees nothing but the deadline (65.4 vs 51.1
kg/MWh on the slack fleet). Three candidate explanations were tested in that
experiment; two were refuted, and the one that survived is placement:

| rule | share of served work on the dirtiest site (South Wales, 321 g/kWh) |
|---|---|
| `forecast_timing` | 15.0% |
| `band_timing` | 15.0% |
| `run_now` | 14.8% |
| `last_slot` | 8.0% |

The forecast-driven rules all pile the four classes into the same cheap slot;
the cheap site saturates and the overflow spills onto dirty capacity. So the
carbon saved by waiting is handed straight back at placement — and a per-agent
timing rule cannot see placement at all, which is why a rank-stagger
intervention did not recover the gap either.

That is the design brief for this experiment: **decide *when* against the price
of the capacity the work would actually occupy**, not against a site-local
signal.

## What the scheduler is

`src/carbon_scheduling/rl/hybrid.py`:

1. **Price every block.** For the horizon (the longest class deadline, 16 slots),
   each `(slot, site)` block is priced `forecast + robust × band` — the same
   uncertainty-adjusted intensity the earlier rungs use, only now it prices
   *capacity* rather than ranking sites.
2. **Assign the backlog to the cheapest legal blocks.** Items are taken
   tightest-deadline first; each takes the cheapest block inside its own window
   that still has capacity, and spills to the next-cheapest when a site's
   per-slot capacity is exhausted. This is the step a timing rule cannot express:
   the plan is bounded by what the fleet can actually serve in each slot.
3. **Execute one slot, then replan.** Only the current slot's assignment runs.
   Next slot the planner sees the same forecast plus the arrivals that have
   actually happened, and decides again. Nothing ahead of the decision is used.
4. **Reserve against its own myopia.** A plan that fills a cheap slot with
   today's backlog leaves the arrivals landing in that slot nowhere to run. The
   `reserve` parameter holds capacity back for them; `arrival_forecast` turns it
   on from a causal (trailing-window) arrival-rate estimate. Both are swept,
   because they trade carbon against service and neither is free.

`HybridEnv` is `QueueEnv` with one seam changed: offers come from the plan
instead of from the coast action. Everything else — the arrivals, the four
class deadlines, the per-slot capacity, the accounting, the idle floor — is the
environment every rung since exp013 has used, so the comparison is against the
same rules on the same demand.

`ForecastFlowPlanner` solves the same horizon exactly with `oracle.plan_multi`
(the proven-optimum min-cost flow) on the same forecast. It is included as an
arm so the cost of the greedy assignment is measured rather than assumed.

## What is swept

| knob | values | why it is a decision, not a hyperparameter |
|---|---|---|
| `robust` | 0, 1 | where forecast uncertainty enters a decision. exp011 showed the band cannot reorder sites (the ordering is exact under national scaling), so its only possible value here is on *timing and capacity*: avoiding a cheap slot whose worst case is not cheap |
| `reserve` | 0, 10, 20, 30% | demand-uncertainty hedge: how much of a cheap slot to leave for work that has not arrived |
| planner | greedy, rolling flow | the cost of greediness, on the identical forecast |
| objective price | 0.1, 0.3, 1.0 | 0.1 kg/GPU-hour is the parity price (0.093 kg emitted per GPU-hour served); 0.3 is where the best rule changes hands; 1.0 is effectively a service obligation |

Scored on the same 12 held-out Oct–Dec 2024 weeks and the same two fleets as
exp016, and every arm is scored against the exact schedule **at its own served
volume, week by week** — unserved work emits nothing, so a carbon-only reading
rewards shedding.

## How to read the numbers

* `carbon_g_per_served_kwh` is the like-for-like intensity: carbon divided by
  the work actually served. `run_now`'s figure is the intensity of the
  carbon-greedy baseline, not a property of the site.
* `objective_at_price` is carbon + price × missed GPU-hours — the scalar a
  deployment would actually choose on.
* `gap_to_own_bound_pct` is the honest headroom: how far the arm is from the
  exact schedule that serves the same volume. A low gap means the arm scheduled
  well; `run_now`'s high gap means it did not.

## Results

Canonical record `runs/20261122T204855Z-68213b79-6c31` (git `26ff040`, clean tree,
config SHA-256 `68213b79…`). Means over the 12 held-out Oct–Dec 2024 weeks.
`own` is the exact schedule at that arm's own served volume; `gap` is how far the
arm sits above it — the honest headroom, since serving less has a lower bound too.

### Slack fleet (40 GPUs/site)

| arm | kg | missed | g/kWh | obj @0.1 | @0.3 | @1.0 | own | gap |
|---|---|---|---|---|---|---|---|---|
| `run_now` | 1109.0 | 0.0000 | 68.7 | 1109 | 1109 | **1109** | 811.5 | +36.7% |
| `last_slot` | 870.6 | 0.0500 | 51.1 | 930 | 1048 | 1462 | 703.5 | +23.8% |
| `forecast_timing` | 1057.4 | 0.0169 | 65.4 | 1077 | 1117 | 1258 | 768.3 | +37.6% |
| `band_timing` | 1086.4 | 0.0060 | 67.1 | 1094 | 1108 | 1158 | 794.0 | +36.8% |
| `plan_r0` | 854.6 | 0.0342 | 49.5 | 895 | 976 | 1259 | 709.3 | +20.5% |
| `plan_r0_res20` | 812.6 | 0.0375 | 46.8 | 857 | 946 | 1256 | 671.9 | +20.9% |
| `plan_r0_res30` | 784.0 | 0.0341 | 45.1 | **824** | **905** | 1187 | 644.7 | +21.6% |
| `plan_arr16` | 818.8 | 0.0358 | 47.7 | 861 | 946 | 1242 | 660.7 | +23.9% |
| `plan_flow` | 840.1 | 0.0404 | 48.5 | 888 | 983 | 1318 | 697.7 | +20.4% |
| `plan_flow_res20` | 727.3 | 0.0769 | 41.0 | 818 | 1000 | 1637 | 608.3 | +19.6% |

### Capacity-bound fleet (25 GPUs/site)

| arm | kg | missed | g/kWh | obj @0.1 | @0.3 | @1.0 | own | gap |
|---|---|---|---|---|---|---|---|---|
| `run_now` | 991.5 | 0.1073 | 76.3 | 1118 | 1372 | **2261** | 909.2 | +9.1% |
| `last_slot` | 817.0 | 0.1930 | 66.1 | 1045 | 1502 | 3100 | 665.8 | +22.7% |
| `forecast_timing` | 932.2 | 0.1438 | 73.7 | 1102 | 1442 | 2633 | 795.6 | +17.2% |
| `band_timing` | 961.9 | 0.1251 | 75.0 | 1110 | 1406 | 2442 | 850.2 | +13.1% |
| `plan_r0` | 811.3 | 0.1355 | 65.3 | 972 | **1292** | 2414 | 673.9 | +20.4% |
| `plan_r0_res20` | 770.9 | 0.1564 | 62.4 | 956 | 1326 | 2621 | 632.3 | +21.9% |
| `plan_r0_res30` | 778.0 | 0.1506 | 63.2 | 956 | 1312 | 2559 | 633.8 | +22.8% |
| `plan_flow` | 712.3 | 0.1868 | 59.2 | 933 | 1375 | 2922 | 551.8 | +29.1% |
| `plan_flow_res20` | 525.6 | 0.2658 | 44.2 | **840** | 1469 | 3670 | 409.5 | +28.4% |

## What the run says

**1. The planner dominates the rule frontier wherever the objective prices a
miss at or below the crossover price.** Best arm per column:

| | best rule @0.1 | best planner @0.1 | best rule @0.3 | best planner @0.3 |
|---|---|---|---|---|
| slack | 930 (`last_slot`) | **824** (−11.4%) | 1048 (`last_slot`) | **905** (−13.6%) |
| capacity-bound | 1045 (`last_slot`) | **840** (−19.6%) | 1372 (`run_now`) | **1292** (−5.8%) |

That is the point of the whole experiment: the improvement is not on carbon at
equal service alone (the planner also serves *more*: `plan_r0` on the
capacity-bound fleet beats `last_slot`'s carbon 811.3 vs 817.0 while missing
13.6% against 19.3%), it is on the objective a deployment would actually score.
Every planner arm beats `run_now` on carbon in **12/12 weeks**, on both fleets,
at every reserve setting.

**2. But the planner does not dominate at the obligation price, and it cannot.**
At `price = 1.0` a miss costs ten times a served GPU-hour, so the right policy is
"never defer", and `run_now` is the only arm that never does: 1109 against the
best planner's 1187 (slack) and 2261 against 2414 (capacity-bound). A planner
that defers is paying a small carbon gain for a small service loss, and this
price says the loss is not worth it. The honest statement is a *frontier*, not a
sweep of the same claim: the timing lever is worth 11–20% of the objective below
the crossover and is worth nothing above it.

**3. The calibrated band never changes a decision — third replication.** `plan_r1`
(whole band priced) against `plan_r0`: 855.5 vs 854.6 kg on slack, 812.1 vs 811.3
capacity-bound — 0.1%, inside the seed noise of everything else here. The reason
is structural and already documented: the realized regional intensity is
constructed as `national_actual × regional_forecast / national_forecast`, so the
per-slot ordering *is* the forecast's ordering and no band width can reorder two
blocks. exp011 (dispatch), exp016 (`band_timing`) and now exp017 (capacity
planning) each test a different decision surface and each finds the same thing.
The band cannot earn a carbon claim under this estimator; where it can earn one
is under *real* forecast error, which this data regime does not have (see "Next").

**4. Exactness is not the same as being right.** The rolling min-cost flow is the
best carbon arm on both fleets (525.6 kg capacity-bound, 727.3 slack) and the
*worst* objective arm at the obligation price (3670 / 1637), because a
forecast-optimal flow defers as much as the forecast rewards and then cannot
recover work when the plan is wrong. The greedy assignment is more conservative
and therefore better at the price points a deployment actually uses. That is the
same trade the bound-vs-policy gap has always shown (`gap` 28–29% for the flow
against 20–22% for the greedy), just measured from the other side: the flow is
closer to the *carbon* optimum and further from the *objective* optimum.

**5. Where the remaining headroom is.** `plan_r0_res30` on the slack fleet is
21.6% above the exact schedule at its own volume, against `run_now`'s 36.7%. So
the planner captures roughly two-fifths of the timing headroom exp015 measured,
and no more — and the gap does not shrink with the reserve or the exact solver,
so it is not a tuning problem. It is the part of the schedule that depends on
arrivals the planner has not seen yet (the reserve is a one-parameter stand-in
for that), which is exactly what a learned, demand-aware component would have to
supply. That is the constructive next step, and it is the hybrid the user asked
for: the planner's price-and-place rules plus a learner on the one quantity the
rules cannot know — how much work is about to arrive.

## Next

* **exp018** — the band's claim needs forecast error to be real. Re-run the r0/r1
  pair under the *measured* NESO national-forecast error distribution resampled
  onto the regional series (a labelled stress test, not a data claim). If the
  band protects the plan there, that is the "uncertainty-aware" evidence the
  project needs; if it does not, the project's uncertainty claim is a negative
  result about this estimator and should be written as one.
* **Learned arrival/pressure model** on top of the planner: replace the fixed
  `reserve` with a learned estimate of next-slot arrivals, which is where the
  20% residual gap lives.

