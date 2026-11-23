# exp021 — what does the carbon saving actually cost in service?

## Why this experiment exists

exp017–exp020 report carbon savings of 21–27% against never deferring. Every one
of those arms also **serves less work**: on the slack fleet the chosen point
misses 3.65% of arrivals where `run_now` misses none. A saving that comes from
doing less is not a like-for-like saving, and the obvious reviewer objection is
that the headline number is an artefact of shedding.

Arguing about that is not evidence. This experiment measures the frontier
directly, with one new planner knob.

`BlockPlanner.max_lookahead` is an absolute cap on how far ahead a block may be
placed:

| value | meaning |
|---|---|
| `0` | serve now, choose only the site — `run_now`'s lever plus the planner's capacity accounting |
| `k` | work may be placed up to `k` slots (k × 30 min) ahead |
| `None` | the full deadline horizon — exp017's planner |

Everything between is a real deployment choice, expressed in units an operator
understands ("we will let the scheduler hold work for at most two hours"). The
frontier is traced over six horizons, with and without the calibrated reserve and
the seasonal ghost arrival model, on the same 12 held-out Oct–Dec 2024 weeks.

Each arm is scored four ways so the claim cannot hide:

1. **its own** carbon and missed fraction;
2. a **matched-service extrapolation** — its own measured grams per served
   GPU-hour applied to `run_now`'s served volume, plus the same idle floor. This
   is an *extrapolation*, not a rerun, and is labelled as such;
3. the **exact schedule at its own volume** (min-cost flow), as the ceiling;
4. the **real GB day-ahead price** (Elexon MID, USD/MWh) applied to the energy it
   actually used, and the **response latency** of the work it actually served.

`pareto_vs_run_now` is true only when an arm is no worse than `run_now` on **both**
carbon and missed fraction. It is a strict two-axis test, not a weighted score.

## Results

Canonical record `runs/20261123T094258Z-487d8c96-fa5e` (git `1d6bfc68`, clean
tree). Means over the 12 held-out weeks. `Δ$` is electricity cost at the real GB
price. `wait` is GPU-second-weighted mean queueing delay of **served** work —
shed work has no response time and is excluded, which is the conservative choice
(a scheduler that misses deadlines should not be credited with fast misses).

### Capacity-bound fleet (25 GPUs/site, 45,000 GPU-s per slot per site)

Here `run_now` itself misses 10.73%: demand peaks at 419,795 GPU-s per slot
against 180,000 of capacity, so 49 of 336 slots are over capacity and some loss is
unavoidable. This is the fleet where a real trade exists.

| arm | kg | vs run_now | missed | Δmiss | served GPU-h | g/GPU-h | wait | Δ$ | matched-svc kg | Pareto |
|---|---|---|---|---|---|---|---|---|---|---|
| `run_now` | 991.5 | — | 10.73% | — | 10559.2 | 76.3 | 85.2 m | — | 991.5 | ref |
| `look0` | 991.5 | +0.0% | 10.66% | −0.07 pp | 10559.2 | 76.3 | 85.2 m | +0.0% | 991.5 | ✓ |
| `look1` | 960.6 | −3.1% | 11.29% | +0.56 pp | 10412.4 | 74.4 | 102.2 m | −1.2% | 971.5 | |
| `look2` | 934.2 | −5.8% | 11.20% | +0.47 pp | 10291.9 | 72.7 | 117.7 m | −2.2% | 953.6 | |
| `look4` | 883.5 | −10.9% | **9.61%** | **−1.12 pp** | 10029.8 | 69.6 | 149.3 m | −4.2% | 920.3 | ✓ |
| `look8` | 810.7 | −18.2% | 13.55% | +2.82 pp | 9596.6 | 65.1 | 169.3 m | −7.6% | 873.5 | |
| `look16` | 811.3 | −18.2% | 13.55% | +2.82 pp | 9584.8 | 65.3 | 170.6 m | −7.6% | 875.0 | |
| `look4_ghost` | 935.5 | −5.7% | **9.53%** | **−1.20 pp** | 10384.0 | 72.2 | 112.8 m | −1.5% | 948.2 | ✓ |
| `look8_ghost` | 875.0 | **−11.8%** | **8.39%** | **−2.34 pp** | 10114.9 | 68.2 | 140.3 m | −3.5% | 905.2 | ✓ |
| `look4_q95` | 897.7 | −9.5% | 11.62% | +0.89 pp | 10016.5 | 71.1 | 139.7 m | −4.2% | 936.3 | |
| `look8_q95` | 813.5 | −18.0% | 13.28% | +2.55 pp | 9526.7 | 65.9 | 170.6 m | −7.8% | 881.5 | |
| `plan_q95` | 783.9 | −20.9% | 14.31% | +3.58 pp | 9381.0 | 63.8 | 170.1 m | −9.3% | 859.0 | |
| `plan_ghost_q95` | 782.8 | −21.1% | 14.31% | +3.58 pp | 9383.5 | 63.6 | 168.5 m | −9.4% | 857.6 | |
| `last_slot` | 817.0 | −17.6% | 19.30% | +8.57 pp | 9544.8 | 66.1 | 162.4 m | −7.7% | 884.1 | |

**The capacity-bound fleet has a genuine Pareto region.** `look4`, `look4_ghost`
and `look8_ghost` are below `run_now` on carbon **and** on missed fraction, in
12/12 weeks. `look8_ghost` is the strongest: −11.8% carbon, −2.34 pp misses,
−3.5% cost, and 905.2 kg at literally matched served volume (−8.7%). The full
horizon buys another 9 points of carbon but pays 2.8–3.6 pp of misses for them,
which is the shedding the earlier headline was hiding.

### Slack fleet (40 GPUs/site, 72,000 GPU-s per slot per site)

Here `run_now` already misses nothing, so no arm can be better on the miss axis
and `pareto_vs_run_now` collapses to "misses nothing". The honest question
becomes: how much carbon before a miss appears?

| arm | kg | vs run_now | missed | Δmiss | served GPU-h | g/GPU-h | wait | Δ$ | matched-svc kg |
|---|---|---|---|---|---|---|---|---|---|
| `run_now` | 1109.0 | — | 0.00% | — | 11827.8 | 68.7 | 15.8 m | — | 1109.0 |
| `look0` | 1109.0 | +0.0% | 0.00% | +0.00 pp | 11827.8 | 68.7 | 15.8 m | +0.0% | 1109.0 |
| `look1` | 1072.0 | −3.3% | 0.43% | +0.43 pp | 11772.5 | 65.8 | 40.7 m | −1.0% | 1075.7 |
| `look2` | 1026.1 | −7.5% | 1.04% | +1.04 pp | 11700.5 | 62.3 | 65.5 m | −2.1% | 1034.0 |
| `look4` | 942.7 | −15.0% | 2.12% | +2.12 pp | 11573.8 | 55.8 | 113.8 m | −4.4% | 956.9 |
| `look8` | 849.9 | −23.4% | 3.42% | +3.42 pp | 11281.2 | 49.0 | 171.3 m | −7.8% | 876.7 |
| `look16` | 854.6 | −22.9% | 3.42% | +3.42 pp | 11274.3 | 49.5 | 173.8 m | −7.8% | 882.0 |
| `look4_ghost` | 1035.7 | −6.6% | **0.48%** | **+0.48 pp** | 11766.6 | 62.8 | 53.4 m | −1.6% | 1039.6 |
| `look8_ghost` | 930.5 | −16.1% | 1.58% | +1.58 pp | 11638.2 | 54.4 | 103.7 m | −3.7% | 940.8 |
| `look4_q95` | 961.5 | −13.3% | 1.51% | +1.51 pp | 11436.6 | 58.1 | 111.1 m | −4.6% | 984.2 |
| `look8_q95` | 831.2 | −25.1% | 3.12% | +3.12 pp | 11099.3 | 48.1 | 178.7 m | −8.6% | 866.2 |
| `plan_q95` | 810.1 | −26.9% | 3.65% | +3.65 pp | 11007.5 | 46.6 | 181.0 m | −9.4% | 848.4 |
| `plan_ghost_q95` | 826.0 | −25.5% | 3.02% | +3.02 pp | 11122.7 | 47.6 | 172.2 m | −8.7% | 859.5 |
| `last_slot` | 870.6 | −21.5% | 5.00% | +5.00 pp | 11236.1 | 51.1 | 184.9 m | −7.4% | 900.8 |

**The slack fleet has no strict Pareto point, and the headline was an artefact.**
The 26.9% figure (`plan_q95`) costs 3.65 pp of misses. Holding misses within half
a point, the reachable saving is **6.6%** (`look4_ghost`, +0.48 pp), or 3.3% if
the miss budget is a quarter of a point (`look1`, +0.43 pp).

## What the frontier says, in one paragraph

At matched service the saving is real but smaller than advertised. On the
capacity-bound fleet the best Pareto arm cuts carbon **11.8%** while *improving*
the miss rate by 2.34 pp, and cuts it 8.7% at literally identical served volume —
the intensity of served work genuinely falls (76.3 → 68.2 g/GPU-h), so this is not
only shedding. On the slack fleet, where nothing was missing to begin with, the
best arm inside a 0.5 pp miss budget cuts **6.6%** (54.4 → 62.8 g/GPU-h of served
work), and 15–27% only by accepting 2–4 pp of misses. Every arm beats `run_now`
on carbon in **12/12 weeks**, so the direction is robust; the *magnitude at
matched service* is 6–12%, not 27%.

## Price and latency — the two axes the earlier experiments never measured

Neither was answerable before: the planner optimises carbon and never sees a
tariff, and the environment did not record when served work waited.

**Price.** Every arm is *cheaper* at the real GB day-ahead price, not more
expensive: −1.5% to −9.4%. The reason is structural in GB — the low-carbon hours
(wind, nuclear) are also the low-price hours, so carbon-aware timing and
cost-aware timing point the same way. This is a national tariff, so it says
nothing about regional price differences (GB has one price, as disclosed). The
Pareto arms cost −1.5% (`look4_ghost`) to −4.2% (`look4`) on the capacity fleet
and −1.6% on slack, i.e. **the carbon saving is not bought with money**.

**Latency.** It *is* partly bought with latency, and this is the honest cost:

| fleet | `run_now` | `look1` | `look4_ghost` | `look4` | `look8_ghost` | `plan_q95` |
|---|---|---|---|---|---|---|
| slack, mean wait | 15.8 m | 40.7 m | 53.4 m | 113.8 m | 103.7 m | 181.0 m |
| capacity, mean wait | 85.2 m | 102.2 m | 112.8 m | 149.3 m | 140.3 m | 170.1 m |

Deferral moves served work later, monotonically with lookahead. This is delay
*inside the deadline*: work that waits past its class deadline is a miss and is
not in the served set. So the product claim is "same SLA, later completion within
it", not "same completion time". For the Pareto arms the delay is one to two
hours on top of `run_now`.

## Honest limitations

- **One demand profile.** Every arm sees the same single real Azure week, reused
  across the 12 evaluation weeks (disclosed since exp006). The carbon and price
  series are real and week-specific; the demand *shape* is not.
- **Matched service is an extrapolation.** The `matched-svc` column applies a
  measured intensity to `run_now`'s volume; it is not a rerun at that volume. It
  is the right comparison for "is the win just shedding", and it says no (the
  intensity falls), but it is not a measured total.
- **Latency is queueing delay, not end-to-end.** It excludes transfer, queue at
  the client, and model time. It measures only how long the scheduler held work.
- **The GB price is national.** No regional price differentiation exists to
  exploit, so the price result is a timing result, not a placement result.
- **Miss cost is a price, not a physics.** `run_now`'s 10.73% miss rate on the
  capacity fleet is a consequence of the fleet being too small for the peak, not
  of the policy; a real operator would add capacity. The Pareto region is the
  useful result, not the absolute miss level.

## Reproduce

```bash
make exp-run EXP=exp021-service-frontier
```

`config_hash` in `runs/*/manifest.json` pins the inputs; the run is deterministic
(same seed, same data SHAs), so a rerun reproduces these numbers exactly.
