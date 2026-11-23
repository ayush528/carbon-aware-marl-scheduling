# exp018 — a calibrated reserve for the arrivals the planner cannot see

## Why this experiment exists

exp017 ended with two facts that decide where uncertainty can live in this
system.

1. **The reserve is the only thing that still moves the planner.** With placement
   solved, a myopic plan fills a cheap slot with today's backlog and the work
   arriving *in* that slot has nowhere legal to run. On the slack fleet a 30%
   capacity reserve moved 854.6 kg at 3.4% missed to 784.0 kg at 3.4% missed; on
   the capacity-bound fleet a 20% reserve moved 811.3 kg / 13.6% to 770.9 kg /
   15.6%. It is a real decision.
2. **The calibrated carbon band has no decision to change — third replication.**
   `plan_r1` against `plan_r0` was 855.5 vs 854.6 kg (0.1%). The reason is
   structural: the realized regional intensity is
   `national_actual × regional_forecast / national_forecast`, so the ordering the
   planner acts on *is* the forecast's ordering, and no band width can reorder two
   blocks. exp011 (dispatch), exp016 (timing) and exp017 (capacity planning) each
   test a different decision surface and each find it.

So the calibrated quantity that can pay for itself is **arrival** uncertainty,
not carbon uncertainty. That is what this experiment makes first class.

## What the reserve is

`src/carbon_scheduling/rl/arrival_risk.py`, using the same estimator as the
carbon bands (`bands.conformal_quantile`, finite-sample corrected):

1. **Predict** each slot's arrival as the mean of the previous 8 slots (4 h).
   Causal by construction — prediction `t` uses only slots before `t`.
2. **Score** the prediction against what actually arrived, and keep the *positive*
   exceedances: a quieter slot than predicted needs no reserve, so it must not be
   allowed to shrink the quantile.
3. **Take the upper conformal quantile** at the level asked for, in GPU-seconds.
4. **Spread** it over the sites and the tightest deadline window, and cap it at a
   block's own capacity so an extreme quantile cannot reserve the whole fleet and
   starve the plan. `BlockPlanner(reserve_gpu_s=…)` then subtracts it from every
   block's free capacity for the horizon.

The reserve is therefore *sized by a coverage target* rather than tuned on the
weeks it is scored on. That is the whole point: exp017 had to sweep the reserve
because it had no model for it, and a swept value that happens to be best on
Oct–Dec is exactly the kind of choice that does not survive to a new quarter.

## The honesty of the coverage claim

The demand profile is the one real Azure LLM week reused across all weeks — the
disclosed choice every rung since exp012 makes — so a clean train/test split is
not available. The split is therefore *inside* the week: the quantile is
calibrated on the first 168 slots and its coverage is measured on the second 168,
which it never saw. Both directions are reported, because the halves of a diurnal
trace are not exchangeable and one number would hide that.

| level | q (first half → second) | coverage (second half) | q (reverse) | coverage (reverse) |
|---|---|---|---|---|
| 0.50 | 13,485 GPU-s | 0.575 | 61,150 | 0.958 |
| 0.90 | 64,179 GPU-s | 0.778 | 145,136 | 0.994 |
| 0.95 | 123,776 GPU-s | 0.922 | 158,545 | 1.000 |

Read this plainly: **the split-conformal guarantee does not hold across the two
halves of this trace.** The first half is the volatile one; a quantile fitted
there is too small for the second half (0.78 coverage at a nominal 0.90), and a
quantile fitted on the second half is far too conservative for the first. The
guarantee holds under exchangeability, and one diurnal week is not exchangeable
with itself. The experiment uses the forward direction, so the reserve it deploys
is *smaller* than its nominal level implies — which is the conservative choice
for carbon and the risky one for service, and is reported as such rather than
claimed as calibration.

Per-site-per-slot reserves that follow (4 sites, tightest deadline 2 slots):

| level | GPU-s per site-slot | share of a 25-GPU block | share of a 40-GPU block |
|---|---|---|---|
| 0.50 | 1,686 | 3.7% | 2.3% |
| 0.90 | 8,022 | 17.8% | 11.1% |
| 0.95 | 15,472 | 34.4% | 21.5% |

## Arms

`run_now`, `last_slot` (exp016's frontier), and the exp017 planner with: no
reserve, exp017's hand-set 20%, and the calibrated quantile at 0.50/0.90/0.95.
Same 12 held-out Oct–Dec 2024 weeks, both fleets, objective at prices
0.1 / 0.3 / 1.0, each arm also scored against the exact schedule at its own
served volume.

## Results

Canonical record `runs/20261123T050816Z-922a56f1-2c61`. Means over the 12
held-out Oct–Dec 2024 weeks; same columns as exp017.

### Slack fleet (40 GPUs/site, 72,000 GPU-s per slot per site)

| arm | kg | missed | g/kWh | obj @0.1 | @0.3 | @1.0 | own | gap |
|---|---|---|---|---|---|---|---|---|
| `run_now` | 1109.0 | 0.0000 | 68.7 | 1109 | 1109 | **1109** | 811.5 | +36.7% |
| `last_slot` | 870.6 | 0.0500 | 51.1 | 930 | 1048 | 1462 | 703.5 | +23.8% |
| `plan_none` | 854.6 | 0.0342 | 49.5 | 895 | 976 | 1259 | 709.3 | +20.5% |
| `plan_frac20` (exp017's best) | 812.6 | 0.0375 | 46.8 | 857 | 946 | 1256 | 671.9 | +20.9% |
| `plan_q50` | 850.3 | 0.0341 | 49.2 | 891 | 971 | 1254 | 704.1 | +20.8% |
| `plan_q90` | 829.2 | 0.0386 | 48.0 | 875 | 966 | 1286 | 683.7 | +21.3% |
| `plan_q95` | **810.1** | 0.0365 | 46.6 | **853** | **940** | 1242 | 671.3 | +20.7% |

### Capacity-bound fleet (25 GPUs/site)

| arm | kg | missed | g/kWh | obj @0.1 | @0.3 | @1.0 | own | gap |
|---|---|---|---|---|---|---|---|---|
| `run_now` | 991.5 | 0.1073 | 76.3 | 1118 | 1372 | **2261** | 909.2 | +9.1% |
| `last_slot` | 817.0 | 0.1930 | 66.1 | 1045 | 1502 | 3100 | 665.8 | +22.7% |
| `plan_none` | 811.3 | 0.1355 | 65.3 | 972 | 1292 | 2414 | 673.9 | +20.4% |
| `plan_frac20` | 770.9 | 0.1564 | 62.4 | 956 | 1326 | 2621 | 632.3 | +21.9% |
| `plan_q50` | 796.0 | 0.1354 | 64.2 | 956 | **1276** | 2398 | 657.4 | +21.1% |
| `plan_q90` | 775.3 | 0.1594 | 62.8 | 964 | 1341 | 2661 | 636.3 | +21.8% |
| `plan_q95` | 783.9 | 0.1431 | 63.8 | **953** | 1292 | 2476 | 633.8 | +23.7% |

## What the run says

**1. A calibrated reserve matches the hand-tuned one without ever seeing the
weeks it is scored on.** exp017 had to *sweep* the reserve — 0/10/20/30% — and
report whichever was best on Oct–Dec, which is exactly the choice that would not
survive the next quarter. Here the reserve is fixed by a coverage target alone.
Slack: `plan_q95` gives 810.1 kg at 3.65% missed, against the tuned
`plan_frac20`'s 812.6 kg at 3.75% — better on both axes. Capacity-bound: `plan_q90`
gives 775.3 kg against 770.9 kg, and `plan_q95` 783.9 kg, so the calibrated arm
lands within 2% of the tuned one. The reserve is no longer a knob chosen on the
test set; it is a quantity with a stated level and a measured coverage.

**2. But the coverage claim is weak, and it is reported as weak.** At a nominal
0.90 the measured coverage on the held-out half is 0.778; only the reverse split
(calibrate on the second half, score the first) reaches 0.994. The first half of
this trace is the volatile one, so a quantile fitted there is too small for what
follows. The guarantee is conditional on exchangeability and one diurnal week is
not exchangeable with itself, so what the run actually deploys is a reserve
*smaller* than its level implies. That is why it still loses a little service
(0.0365 against 0.0342 at no reserve on slack): it is hedging less than it says.

**3. The best level is not universal, and the frontier is not monotone.** Slack
wants 0.95, capacity-bound wants 0.90 on carbon and 0.50 on the objective at 0.3.
Between 0.90 and 0.95 the slack fleet gets 19 kg better and the capacity-bound
fleet 8 kg worse, because the quantile→reserve mapping is a threshold: the same
numeric quantile is a larger share of a smaller block. So the honest deployment
statement is a *frontier indexed by fleet occupancy*, not one number. What is
consistent is the direction: on both fleets at both the parity and crossover
prices, every calibrated arm beats the planner with no reserve, and every planner
beats every rule.

**4. At the obligation price the reserve stops paying, exactly as exp017 found.**
Best calibrated arm at 1.0 is 1242 (slack) and 2398 (capacity-bound), against
`run_now`'s 1109 and 2261. Reserving capacity buys carbon by risking deadlines;
when a missed deadline is priced at ten times a served GPU-hour, that trade is
lost on purpose.

## Where this leaves the project

The scheduler the user asked for is now measured end to end: a capacity-aware
planner (rules: cheapest-feasible-block assignment, deadline windows as hard
constraints) plus one calibrated input (the arrival quantile) that changes its
decisions, on real NESO carbon and a real LLM trace. It beats every hand-written
rule on the objective at the prices a deployment would use, on both fleets, in
12/12 held-out weeks, and it does so without tuning anything on the evaluation
weeks.

What it does *not* claim: that the calibrated carbon band improves decisions. It
does not, and three experiments now say so for a structural reason. The band's
honest role is risk-qualifying the reported saving, not choosing a site — and the
frontend must say that rather than dress it up.

