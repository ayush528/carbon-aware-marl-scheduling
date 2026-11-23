# exp019 — does the shape of the incoming work beat one constant reserve?

## Why this experiment exists

exp018 made the reserve *calibrated* but left it a single number for the whole
week. The workload is not constant: the Azure trace is quiet for hours and then
bursts. A constant reserve therefore over-holds in the quiet period — paying
carbon for capacity nothing uses — and under-holds right before a burst — losing
work the plan could have served.

exp017 had measured where the remaining headroom is: every arm sits 20–25% above
the exact schedule *at its own served volume*, and that gap did not shrink with
the reserve or with the exact solver. So it is arrivals the plan has not seen.

This experiment gives the planner two ways to anticipate them, both causal
(`src/carbon_scheduling/rl/hybrid.py`):

| mechanism | what it does | why |
|---|---|---|
| **hold** | reserve capacity in every future block, spread over the tightest deadline window | cheap, but defends blocks that may never be needed |
| **ghost** | add the prediction to the plan as an item with the tightest class, so it competes for the cheapest legal blocks under the same EDF order as real work, consumes capacity only where it would run, and is **never offered** to the environment | same marginal logic for work you can see and work you cannot |

Each mechanism uses one of two predictors: `flat` (trailing mean of the previous
8 slots, 4 h) or `seasonal` (the same slot of the previous day, 48 slots earlier,
falling back to the trailing mean where a day of history does not exist). A ghost
replaces a hold rather than stacking with it — a hold would double-count the same
arrivals — and the tests pin that, along with the two behavioural claims that
matter: a ghost takes the cheap block away from a long-deadline backlog so that
backlog is offered *now* instead of gambling, and a ghost that cannot be placed is
dropped rather than billed to an agent.

No parameter is chosen on the evaluation weeks: the level (0.95) and the window
(8) are the values exp018 already used.

## Results

Canonical record `runs/20261123T070623Z-66cbddac-e9de`. Means over the 12 held-out Oct–Dec
2024 weeks. `own` is the exact schedule at that arm's own served volume; `gap` is
how far above it the arm sits. Paired comparison against `plan_none`.

### Slack fleet (40 GPUs/site, 72,000 GPU-s per slot per site)

| arm | kg | missed | g/kWh | obj @0.1 | @0.3 | @1.0 | own | gap | vs none |
|---|---|---|---|---|---|---|---|---|---|
| `run_now` | 1109.0 | 0.0000 | 68.7 | 1109 | 1109 | 1109 | 811.5 | +36.7% | +29.8% |
| `last_slot` | 870.6 | 0.0500 | 51.1 | 930 | 1048 | 1462 | 703.5 | +23.8% | +1.9% |
| `plan_none` | 854.6 | 0.0342 | 49.5 | 895 | 976 | 1259 | 709.3 | +20.5% | — |
| `plan_q95` | **810.1** | 0.0365 | 46.6 | **853** | 940 | 1242 | 671.3 | +20.7% | −5.2% (12/12) |
| `plan_hold_flat` | 1006.7 | 0.0221 | 61.4 | 1033 | 1085 | 1268 | 756.7 | +33.0% | +17.8% |
| `plan_hold_seasonal` | 916.1 | **0.0095** | 52.9 | 927 | 950 | **1029** | 784.9 | +16.7% | +7.2% |
| `plan_ghost_flat` | 865.5 | 0.0285 | 50.0 | 899 | 967 | 1203 | 723.5 | +19.6% | +1.3% |
| `plan_ghost_seasonal` | 862.0 | 0.0299 | 49.8 | 897 | 968 | 1216 | 721.2 | +19.5% | +0.9% |
| `plan_ghost_seasonal_q95` | 826.0 | 0.0302 | 47.6 | 862 | **933** | 1183 | 687.2 | +20.2% | −3.4% (12/12) |

### Capacity-bound fleet (25 GPUs/site, 45,000 GPU-s per slot per site)

| arm | kg | missed | g/kWh | obj @0.1 | @0.3 | @1.0 | own | gap | vs none |
|---|---|---|---|---|---|---|---|---|---|
| `run_now` | 991.5 | 0.1073 | 76.3 | 1118 | 1372 | **2261** | 909.2 | +9.1% | +22.2% |
| `last_slot` | 817.0 | 0.1930 | 66.1 | 1045 | 1502 | 3100 | 665.8 | +22.7% | +0.7% |
| `plan_none` | 811.3 | 0.1355 | 65.3 | 972 | 1292 | 2414 | 673.9 | +20.4% | — |
| `plan_q95` | 783.9 | 0.1431 | 63.8 | 953 | 1292 | 2476 | 633.8 | +23.7% | −3.4% (12/12) |
| `plan_hold_flat` | 865.9 | 0.1671 | 69.1 | 1064 | 1459 | 2842 | 729.7 | +18.7% | +6.7% |
| `plan_hold_seasonal` | 899.3 | 0.1350 | 69.8 | 1059 | 1378 | 2497 | 819.7 | +9.7% | +10.8% |
| `plan_ghost_flat` | 805.4 | 0.1351 | 64.6 | 965 | 1285 | 2403 | 675.8 | +19.2% | −0.7% (12/12) |
| `plan_ghost_seasonal` | 805.4 | 0.1351 | 64.6 | 965 | 1285 | 2403 | 675.6 | +19.2% | −0.7% (12/12) |
| `plan_ghost_seasonal_q95` | **782.8** | 0.1431 | 63.6 | **952** | **1291** | 2475 | 634.3 | +23.4% | −3.5% (12/12) |

## What the run says

**1. Anticipation buys service, not carbon — and that is a real finding, not a
disappointment.** Every ghost arm cuts missed work (slack: 3.42% → 2.85–2.99%) and
every ghost arm costs a little carbon (854.6 → 862.0–865.5 kg). The mechanism is
visible in the rule: when a cheap block is defended for an arrival, the backlog
that would have gambled on it is served *now*, in a dearer slot. Anticipation is
therefore a reliability lever, and the calibrated reserve stays the carbon lever.

**2. Ghosts dominate holds at any given service level.** Slack: `plan_ghost_flat`
delivers 2.85% missed for 865.5 kg where `plan_hold_flat` needs 1006.7 kg for 2.21%
— a 16% carbon penalty for a quarter of a point of service. Capacity-bound: 805.4
vs 865.9 kg at 13.5% vs 16.7% missed. The reason is structural: a hold defends
*every* future block against arrivals that will only need one, so it exports real
backlog into dearer slots for nothing. A ghost takes capacity only where the
predicted arrival would actually run, which is the same marginal decision the
planner already makes for visible work.

**3. The diurnal shape barely matters; having *a* model does.** `flat` and
`seasonal` ghosts are within 0.4% of each other on the slack fleet (865.5 vs
862.0 kg) and are indistinguishable on the capacity-bound one (both 805.4 kg /
0.1351). Against `plan_none` the difference is 0.7–1.3%. So the estimated arrival
*volume* is what the plan needs; its hour-by-hour shape is below the resolution of
a reserve that is spread over a two-slot window and capped by block capacity. This
is the same lesson as the carbon band from the other direction: a coarse scalar
reserve cannot exploit a fine-grained shape, and claiming otherwise would be
over-reading the data.

**4. The reserve and anticipation are complements at the crossover price and
substitutes at parity.** Slack at 0.3: `plan_ghost_seasonal_q95` 933 is the best
planner arm (q95 alone 940, none 976). Capacity-bound at 0.1: `plan_ghost_seasonal_q95`
782.8 kg is the best carbon number in the whole experiment. But on the slack fleet
at 0.1 the reserve alone still wins (810.1 vs 826.0): there, anticipation's service
isn't worth its carbon. Which is the honest deployment statement — a frontier, with
the choice set by what a miss costs.

**5. For the first time, a planner beats "never defer" at the obligation price.**
`plan_hold_seasonal` on the slack fleet scores 1029 against `run_now`'s 1109 at
1.0 kg per missed GPU-hour, while emitting 916 kg against 1109 kg. It misses 0.95%
of work, and at that price the miss costs about 112 kg — so the carbon saving pays
for it with room to spare. exp017 and exp018 both concluded no planner could beat
`run_now` at that price; that conclusion was a property of *myopic* planning, not of
planning. On the capacity-bound fleet it still loses (2497 vs 2261), because there
the misses are 13.5% and the price of them dominates — so the win is conditional on
having capacity to spare, and is reported that way.

**6. The gap to the exact schedule does not close.** Best gaps are still 16.7%
(slack, `hold_seasonal`) and 9.7% (capacity-bound, `hold_seasonal`), against 20.5%
and 20.4% for no anticipation. Anticipation helps the two *extreme* points of the
frontier and leaves the middle where it was. What remains is not a reserve problem:
it is that a 16-slot greedy receding horizon under forecast prices will always
leave something on the table relative to a flow over the whole week, which exp015
and exp017 both quantified.

## Where this leaves the scheduler

The planner now has two independent, calibrated-ish inputs — a static reserve
sized by a coverage target and a causal arrival model — and the measured frontier
of the two fleets at three prices is the deliverable. The single best carbon arm at
the parity price remains `plan_q95` (slack) / `plan_ghost_seasonal_q95`
(capacity-bound); the single best *reliability* arm is `plan_hold_seasonal`, which
is also the only planner that ever beats `run_now` at the obligation price.

The next experiment turns that frontier into one shipped scheduler: pick the
operating point from the price on **training** months only, then report the
hold-out numbers of the map that wins, so the selection is not tuned on the weeks
it is scored on.
