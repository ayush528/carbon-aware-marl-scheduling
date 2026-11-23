# exp015 run lineage

| run | git | what it is |
|---|---|---|
| `20261122T142147Z` | `9d3853a` (dirty) | **Superseded.** Charged the idle floor on the padding slots the planner uses to schedule a late cohort, so the bound was taxed for slots no baseline pays for (slack 4 h read −25.9% instead of −29.4%). |
| `20261122T142348Z` | `9d3853a` (dirty) | **Superseded.** Fixed the padding charge, but flagged a horizon as "service unmatched" by comparing against `unserved_fraction` as the summary rounds it (four decimals), so a flow that landed on the baseline's exact served volume was marked unmatched. |
| `20261122T142748Z` | `9d3853a` (dirty) | **Superseded** only because it predates the commit that landed the code: same numbers as the canonical run to the printed digit, but its record cannot be reproduced from a SHA that matches what it ran. |
| `20261122T172248Z` | `06657a8` (clean) | **Canonical.** Padding charged for load energy only; matched service decided on unrounded volumes; run from a committed tree, so `git_dirty: false` and the SHA is the code that produced it. |

The first three are kept because the defects they captured are easy to
reintroduce: the environment rounds its summary and bills idle energy for the
slots it runs, and a bound has to be scored with the same conventions on both
sides or the comparison silently drifts by a few percent.

No run record is edited. Only the canonical record is cited.

## What the run says

At the 4-hour deadline (`deadline_slots: 8`) that every policy since exp012
faces, serving exactly the volume `run_now` serves:

| fleet | carbon-greedy | optimum | saved | worst week | best week |
|---|---|---|---|---|---|
| capacity-bound (25 GPUs/site) | 958.8 kg | 825.4 kg | **−14.5%** | −8.6% | −22.0% |
| slack (40 GPUs/site) | 1109.0 kg | 793.3 kg | **−29.4%** | −19.8% | −40.6% |

Better in 12/12 held-out weeks in both fleets, at identical served volume
(0.8718 / 0.8718 and 1.0000 / 1.0000).

Horizons shorter than 4 hours are reported but **not** service-matched in
either fleet: with less slack the flow cannot place the volume the baseline
places, and its carbon number is quoted next to the volume it actually served
so it cannot be read as a saving.

The gap is structural, not a training failure: under the service obligation an
agent expresses deferral only by `wait`, which withdraws its capacity and lets
the coordinator spill the work elsewhere, so deferral needs every agent to wait
in the same slot. That is the motivation for rung 7.
