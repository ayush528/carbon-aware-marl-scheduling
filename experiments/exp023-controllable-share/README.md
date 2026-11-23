# exp023 — how much of the published benchmark's carbon is a decision at all?

**Run:** `20261123T114026Z-514501a6-b84e` · git `54890444` · `git_dirty: false`
**Window:** 2024-01-09T18:00Z + 168 h (identical to exp022) · seed 42 · clock aligned

## The question

exp022 tied SustainCluster's best published controller *exactly*. A tie can mean two very
different things: our rule is no better than theirs, or there is nothing left to win.
A percentage quoted against another controller cannot tell them apart — which is the form
every published number in this area takes.

So this experiment measures the denominator. The **identical environment** — same four UK
sites, same jittered week, same carbon and price series, same HVAC and server power model,
same alignment — is run with the task stream switched off (`cluster_manager.tasks = None`;
`get_tasks_for_timestep` then returns no arrivals, so it is the same environment with no
work, not a different one). What it still emits is the idle draw of the estate: servers,
cooling, pumps, fans. No placement rule and no deferral rule can remove it.

## Result

| | carbon (kg) | energy (kWh) |
|---|---|---|
| **idle floor** (no work at all) | **101,414.2** | 521,913 |
| `round_robin` | 114,306.2 | 588,234 |
| `lowest_carbon` (best published) | 106,449.2 | 591,224 |
| our planner (causal forecast) | 106,457.4 | 591,228 |

* **88.7 % of this benchmark's carbon is idle draw.** Energy and carbon agree to the decimal
  because the floor run spreads load evenly, so the two ratios coincide.
* **The contestable range is 12,892 kg** (`round_robin` − floor) = **11.3 % of the reported
  carbon**.
* `lowest_carbon` removes **7,857 kg = 60.95 %** of that range. Our causal planner removes
  **7,849 kg = 60.88 %** — a 0.07 percentage-point shortfall, 8.3 kg out of 12,892.

> **Correction on the record.** The first run of this experiment reported our planner
> removing *exactly* the same 7,857 kg. That was an artefact: a timezone mismatch made every
> forecast lookup miss, so our strategy silently fell back to the simulator's own carbon
> signal and *was* `lowest_carbon` (see exp022's correction). The numbers above are the
> corrected run, with `forecast_fallbacks: 0` asserted.
>
> **And `lowest_carbon` is an oracle.** The series installed into the simulator is the
> *realized* estimate, and that controller reads it directly. Our planner reads the NESO
> forecast. So the honest reading of the 0.07 pp gap is: a causal, forecast-driven rule
> captures 60.88 % of the contestable range against an oracle's 60.95 %.

## Why placement cannot do better

| statistic (measured over the 168 hours) | value |
|---|---|
| hours South Scotland is the cheapest region | 162 / 168 (**96.4 %**) |
| hours North West England is cheapest | 5 |
| hours London is cheapest | 1 |
| mean gap to the runner-up region | 54.2 gCO₂/kWh |
| median *relative* gap to the runner-up | **49.3 %** |

The cheapest region is not marginally cheapest — it is typically **half** the intensity of
the next one. So the placement decision is an argmin with a large margin and a single
winner, which is why every correct rule computes nearly the same assignment: `lowest_carbon`
lands on 106,449.2 kg and our three causal arms on 106,457.4–106,477.9 kg, a spread of 0.03 %. The fourth independent confirmation that a common scaling cannot reorder
sites (after exp011, exp016, exp017).

Under `lowest_carbon` the movable work is on South Scotland: implied intensity 72.4 gCO₂/kWh
at that site versus 237.8 (London), 338.0 (South Wales), 128.0 (North West England), and
South Scotland carries 33 % of the estate's energy against 25 % under round-robin while
every other site loses energy. *Derived estimate:* the ~5,035 kg still above the floor is
the carbon of running the work at the cleanest site in each hour, not a placement error.
It is a decomposition rather than a measurement (splitting energy into floor and variable
assumes the floor is placement-invariant, which is only approximately true), so treat it as
±5 %.

## What this means for the claim

1. **The published percentages are small because the denominator is mostly fixed.** A
   −6.87 % headline against round-robin is **61 % of everything the controller could
   actually decide** in this benchmark. Both statements are true; only one is informative.
2. **Our tie in exp022 is a saturation result, not a capability result.** We match the
   optimum of an arena with one dominant site, no capacity pressure (GPU utilisation 7.4 %
   under every controller) and no temporal lever.
3. **The honest limitation of this measurement:** the floor share is a property of *this
   operating point* — four sites at ~7 % utilisation. At high utilisation the moveable part
   grows and the floor share falls. It is reported because it is the operating point at
   which the published numbers in this area were produced, not as a universal law.
4. **The lever that is left is time, and this interface cannot reach it.**
   `distribute_workload` queues a task only if the strategy returns a datacenter id;
   returning `None` discards it and the stream is never re-served. Deferral exists only in
   the `manual_rl` action path, which no rule-based controller uses. That is why exp021 —
   where the deadline is a policy variable rather than `1.5 × duration` — is the only place
   a real win can be shown, and where it is: 11.8 % carbon *and* 2.34 pp fewer misses
   capacity-bound, 6.6 % inside a 0.5 pp miss budget on the slack fleet, 12/12 weeks.

## Not tuned, and no arithmetic asserted

The floor is a run. The controller range is runs. The stability statistic is a count over
the forecast series. The only derived quantity is the marginal-intensity split, labelled
above and excluded from every headline.

## Reproduce

```
make exp-run EXP=exp023-controllable-share
```

Canonical run recorded under `runs/`; see the manifest for git SHA, config hash and data hashes.
