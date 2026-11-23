# exp028 — the idle-floor curve

**The 88.7% is one point on a curve, not a property of the benchmark.** As real
arrivals rise from 0.25× to 4× the real stream, the idle floor's share of total
carbon falls from **96.9% to 65.7%**, and the contestable range grows from
**3.1% to 34.3%**. A published-style percentage against `round_robin` therefore
means very different things at different utilisation: **+1.94%** at 1.9% GPU
utilisation and **+16.7%** at 29.5%.

## Design

The real Alibaba 2020 task stream is resampled per 15-minute slot (tested
transformation, `sim/workload_scaling.py`): without replacement below 1×, with
replacement above. **No job shape or arrival time is invented.** Every scaled
pickle is SHA-256 hashed into the metrics, so the exact bytes the simulator
consumed are recorded. Same sites, same week, same six controllers at every
point; the floor is measured once by switching the task stream off in the
identical environment. Seed 42, one week.

## The curve

| arrival scale | tasks | mean GPU util | `round_robin` kg | floor share | contestable share | `lowest_carbon` vs RR | our planner vs RR |
|---|---|---|---|---|---|---|---|
| 0.25× | 325,656 | 1.9% | 104,681.4 | **96.88%** | 3.12% | +1.94% | +1.94% |
| 0.5× | 650,384 | 3.7% | 107,740.8 | 94.13% | 5.87% | +3.55% | +3.55% |
| 1× (exp023) | 1,300,144 | 7.4% | 114,306.2 | 88.72% | 11.28% | +6.87% | +6.87% |
| 2× | 2,600,288 | 15.4% | 128,034.6 | 79.21% | 20.79% | +12.54% | +12.51% |
| 4× | 5,200,576 | 29.5% | 154,302.5 | **65.72%** | **34.28%** | +16.73% | +16.76% |

The exp023 point is reproduced exactly at 1×, which validates the harness. The
floor is the same 101,414.2 kg at every point, as it must be: it is set by the
estate, not by the workload.

## What this establishes

* **The denominator is measurable and small at low utilisation.** At the
  published operating point, 88.7% of the number a controller is scored on is
  not a decision. At a busier estate the same accounting leaves two-thirds of
  the total uncontestable — still a majority.
* **The two controllers converge at low load and diverge at high load.** At
  0.25× both save 1.94% (all contestable carbon is captured by either rule);
  at 4× the margin is ~16.7% because placement matters more when the estate is
  busy.
* **The floor share is operating-point dependent, so no single percentage may
  be quoted without it.** This is the precise form of the related-work caveat:
  published percentages are not wrong, but the denominator is rarely reported.

## Disclosures

* Arrivals are resampled real tasks; a new arrival rate is not a new workload.
* The installed carbon series is the realized estimate, so `lowest_carbon`
  reads realized carbon (an oracle) and our planner reads the NESO forecast.
* GB has one AWS region (transmission cost 0) and a national price series
  (`lowest_price` degenerate), as in exp009/exp022.

## Reproduce

```
make exp-run EXP=exp028-idle-floor-curve
```
