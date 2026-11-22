# exp014 run lineage

| run | config hash | what it is |
|---|---|---|
| `20261122T104833Z-10e8ccc4` | `10e8ccc4` | **Superseded.** Run at learning rate 3e-3, deadline price 1.0 and holding price 0.05 — the settings exp013 showed to be a diverging learner at a price eleven times the cost of serving. Its seed spread (CVaR 0/5 seeds with the same sign) is the measurement that made "one seed is not a result" concrete. |
| `20261122T122704Z-3a65eb4e` | `3a65eb4e` | **Canonical.** Learning rate 3e-4, parity price 0.1, holding price 0, learning gate per seed. |

Read the seed spread before the mean. The capacity-bound arms are bimodal across
seeds (about -30% or about -59% carbon), so the mean is a summary of two
behaviours, not of a continuum.
