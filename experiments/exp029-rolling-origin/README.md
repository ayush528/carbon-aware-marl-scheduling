# exp029 — full-year rolling-origin evaluation

**The shipped scheduler's choice is stable: the same arm is selected in 36 of
36 rolling weeks in five of six cells, and causal selection costs at most 1.33%
against a per-week oracle.** The train/test boundary of exp020 did not create
the result.

## Design

All 44 fully covered weeks of 2024 are used. After an eight-week warm-up, the
choice at week *t* is rebuilt from weeks 0…t−1 **only** (expanding window),
then applied to week *t*: 36 genuine rolling-origin evaluations per fleet and
price. Carbon bands are calibrated on the 28 days before each week; the arrival
reserve is the same causal quantile as exp018–021. The six candidates are
exp020's, unchanged. Every arm sees the same demand and carbon series.

## Results

### Capacity-bound fleet (25 GPUs/site)

| price of a missed GPU-hour | selected arm (weeks) | objective vs `run_now` | carbon vs `run_now` | missed (vs 10.73%) | cost of causal selection |
|---|---|---|---|---|---|
| 0.1 | `plan_ghost_q95` (36/36) | −12.75% | −19.75% | 14.29% | +0.01% |
| 0.3 | `plan_none` (36/36) | −3.48% | −17.06% | 13.54% | +0.43% |
| 1.0 | `run_now` (36/36) | 0.00% | 0.00% | 10.73% | 0.00% |

### Slack fleet (40 GPUs/site)

| price | selected arm (weeks) | objective vs `run_now` | carbon vs `run_now` | missed (vs 0.00%) | cost of causal selection |
|---|---|---|---|---|---|
| 0.1 | `plan_q95` (36/36) | −22.22% | −26.82% | 3.65% | +0.14% |
| 0.3 | `plan_hold_seasonal` (34/36), `plan_ghost_q95` (2/36) | −14.49% | −18.30% | 1.01% | +1.33% |
| 1.0 | `plan_hold_seasonal` (36/36) | −6.76% | −18.10% | 0.90% | +0.06% |

At the service-obligation price the capacity-bound fleet correctly selects
`run_now` in every week — the same conclusion exp017 reached on 12 weeks. On
the slack fleet, `hold_seasonal` beats `run_now` even at that price, which is
exp019's result reproduced across the year.

## The risk-qualified headline

A one-sided split-conformal bound on the **per-week** paired carbon saving,
using the 36 rolling weeks: at α = 0.1 the lower bounds are **+16.43%**
(capacity, price 0.1), **+13.87%** (capacity, 0.3), **+20.46%** (slack, 0.1),
**+13.49%** (slack, 0.3 and 1.0). These are lower bounds on *next week's* saving
under the selected arm — **not** on a matched-service comparison: at prices
0.1/0.3 the selected arms miss more work than `run_now`, and that difference is
in the tables above and must never be dropped. The bound is distribution-free
given exchangeable weeks; carbon seasonality makes that approximate, so it is
reported beside the mean, not as a guarantee.

## What this does and does not establish

* **Does:** the selection is stable through the year, and a causal selector
  loses ≤1.33% of objective to a selector that knows each week's outcome.
* **Does:** the 6–12% headline survives the extension from 12 held-out weeks to
  36 rolling weeks as a *Pareto-region* statement. The raw carbon percentages
  above are larger because those operating points trade service for carbon;
  they are not the headline.
* **Does not:** turn the demand source into more than one real week (exp031
  tests shape sensitivity), and does not replace the matched-service analysis
  in exp021.

## Reproduce

```
make exp-run EXP=exp029-rolling-origin
```
