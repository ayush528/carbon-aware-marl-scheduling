# exp016 — rung 7: agents own queues

Rung 6 gave each agent a **site**. The only way such an agent could defer work
was to `wait`, which withdraws its capacity and lets the coordinator spill the
work somewhere else: one agent deferring accomplishes nothing, so deferral was
a *joint* action that independent learners never take. exp015 measured what that
gap costs — 29.4% of carbon on the slack fleet and 14.5% on the capacity-bound
fleet at identical served volume, at the 4-hour deadline every policy since
exp012 uses.

Rung 7 inverts the ownership. An agent now owns a **work stream and a
deadline-constrained backlog**, and its only decision is what fraction of its own
slack to coast before offering its queue. Nobody else's queue moves, so deferral
is unilateral and a policy can express it. A coordinator still places whatever
is offered, cheapest forecast site first, so rung 6's placement result — the
regional carbon ordering is exactly known under the national-scaling estimator —
is preserved and timing is the only lever under test.

## The pieces

| piece | file | what it does |
|---|---|---|
| environment | `src/carbon_scheduling/rl/queue_env.py` | four work classes with 1/2/4/8-hour deadlines, one per agent (the 4-hour class is the reference deadline of exp012–exp015); action = coast fraction of the agent's own slack; EDF coordinator over the offered work |
| rules | `src/carbon_scheduling/rl/queue_rules.py` | immediate, deadline-only holding, forecast-aware, band-aware |
| bound | `src/carbon_scheduling/rl/oracle.py` | `plan_multi`: the cheapest legal per-class schedule, a proven optimum (min-cost flow), verified against exhaustive search |
| learner | `src/carbon_scheduling/rl/marl_ppo.py` | IPPO / MAPPO; CVaR charged per step (`CVaRTracker`) or at the end |

## Design decisions a reader should question

**The arrivals are split equally between the four classes.** The Azure LLM trace
carries no latency labels, so there is no measured way to say which requests were
interactive and which were batch. The split is a disclosed modelling choice; it
is identical for every arm in the experiment, so every comparison stays matched,
and the classes are what make the agents genuinely different — a 30-minute class
cannot defer at all.

**The action is a fraction of the agent's own slack, not a number of slots.** An
absolute wait grid gave a deadline-2 class four actions out of six that behaved
identically, wasting most of its action space. As a fraction, "hold to the last
legal slot" means the same thing to every class while the number of slots
differs, so the same action index is comparable across agents.

**`gamma = 1` is the objective, not a tuning knob.** The thing being minimised is
the episode total (carbon plus priced misses). A discounted return systematically
under-prices a miss that lands ten or fifteen slots after the decision that
caused it, which is exactly the bias that makes deferral look free — and it was
measured here: at `gamma = 0.99` the learner held work it should have served.
`lam` and the episode count *are* chosen, on a hold-out slice of the **training**
months (July–September), never on the evaluation weeks.

**The bound is costed twice.** Once at the volume the immediate rule serves —
the headline ceiling — and once at each arm's *own* served volume. Unserved work
emits nothing, so a carbon-only reading rewards shedding, and the bound at a
lower volume is lower too; without the second number a policy can look close to
optimal by doing less. Service is reported beside every saving.

**exp016's bound is not exp015's bound.** exp015 put all work on one 4-hour
deadline; here a quarter of the work has a 30-minute deadline, which removes
placement freedom, so the same fleet's bound is a little *higher* than exp015's.
The two are not comparable and neither is quoted against the other.

**The idle floor is the operator's standing cost.** Every site draws its idle
power in every slot it runs, so it is billed in `summary()` and in
`idle_carbon_kg` but enters no agent's reward: no action an agent can take
changes it. Per-agent carbon is therefore the *marginal* energy of the work it
served, and the agent rewards sum to the fleet's variable cost exactly (tested).

## The rule frontier, and why timing and placement cannot be separated

The hand-written rules are not decoration: they are the bar. Measured on the 12
held-out weeks, with the objective `carbon + price × missed GPU-hours` at each
price in the sweep:

| slack fleet (40 GPUs/site) | kg | missed | p=0.1 | p=0.3 | p=1.0 |
|---|---|---|---|---|---|
| `run_now` | 1109.0 | 0.000 | 1109 | 1109 | 1109 |
| `last_slot` | 870.6 | 0.050 | 930 | 1048 | 1462 |
| `forecast_timing` | 1057.4 | 0.017 | 1077 | 1118 | 1258 |
| `band_timing` | 1086.4 | 0.006 | 1094 | 1108 | 1158 |
| bound at `run_now`'s volume | 811.5 | 0.000 | — | — | — |

| capacity-bound fleet (25 GPUs/site) | kg | missed | p=0.1 | p=0.3 | p=1.0 |
|---|---|---|---|---|---|
| `run_now` | 991.5 | 0.107 | 1118 | 1372 | 2261 |
| `last_slot` | 817.0 | 0.193 | 1045 | 1502 | 3100 |
| `forecast_timing` | 932.2 | 0.144 | 1102 | 1442 | 2633 |
| `band_timing` | 961.9 | 0.125 | 1110 | 1406 | 2442 |
| bound at `run_now`'s volume | 909.2 | 0.107 | — | — | — |

Two things worth reading off it. First, the **best rule changes hands at a
crossover price**: below it, holding to the last legal slot wins on the objective
despite serving 5 pp less; above it, `run_now` wins outright because a miss is
dearer than any carbon it saves. A learner that only ever rediscovers one of
these will be beaten in the other regime, which is why every arm is trained and
scored at three prices and never at one.

Second, **the rules are not ordered by how much they know.** `forecast_timing`
sees the whole forecast and is *worse* per served GPU-hour than `last_slot`,
which sees nothing but the deadline (65.4 vs 51.1 kg/MWh on the slack fleet).
Three candidate explanations were tested; the first two are refuted:

| candidate | test | outcome |
|---|---|---|
| it sheds the expensive work | cost the lost work at the cheapest site of the slot where it expired | refuted: the lost work would have cost 1.9 kg/week against a 238 kg/week advantage |
| the four deadlines de-align the class peaks | give all four classes the *same* deadline | refuted: the advantage survives (56.9 vs 68.7 kg/MWh at an 8-slot deadline) |
| its peaks land on expensive sites | share of served work placed on the dirtiest site (South Wales, 321 g/kWh, against 8 in South Scotland) | **supported**: 15.0% for `forecast_timing`, 8.0% for `last_slot` |

A direct intervention on the third candidate — making each agent hold for the
*(i+1)*-th cheapest slot of its own window, so the classes cannot converge — did
**not** recover the gap (64.8 vs 65.4 kg/MWh). So "the classes pile into one slot"
is too simple: the cost is the *placement* that the peaks force, and a per-agent
timing rule cannot see placement at all. The measurement is reproducible:
`scripts/exp016_bunching.py` prints the excess offered per slot for each rule.

That is the constructive outcome, and it is why `rl/hybrid.py` exists: *when* to
run has to be decided against the price of the capacity the work would actually
occupy. On the same 12 weeks a capacity-aware planner on the forecast
(`BlockPlanner`) reaches **812.6 kg at 3.75% missed** on the slack fleet — better
carbon *and* better service than `last_slot`'s 870.6 kg at 5.0%, and 49.5 kg/MWh
against `run_now`'s 68.7. Against the exact schedule at its own volume it leaves
20.9% on the table, where `run_now` leaves 36.7%.

## What the run says

Canonical record: `runs/20261122T192505Z-d550fa91-10b8` (git `0d0441c`, clean
tree, 600 episodes, 3 seeds, 32 training weeks, 12 held-out weeks).

**The rules first, on the objective the learner is also scored on.** Slack fleet
(40 GPUs/site), means over the 12 held-out weeks:

| arm | kg | missed | obj @ 0.1 | @ 0.3 | @ 1.0 |
|---|---|---|---|---|---|
| `run_now` | 1109.0 | 0.000 | 1109 | 1109 | 1109 |
| `last_slot` | 870.6 | 0.050 | **930** | 1048 | 1462 |
| `forecast_timing` | 1057.4 | 0.017 | 1077 | 1117 | 1258 |
| `band_timing` | 1086.4 | 0.006 | 1094 | 1108 | 1158 |
| `mappo` (best learner @0.1) | 911.1 | 0.032 | 949 | — | — |
| `ippo_comm_off` (best learner @0.3) | 966.3 | 0.023 | — | 1046 | — |
| `ippo_cvar_step` (best learner @1.0) | 1053.4 | 0.008 | — | — | 1152 |

**The learner does not beat the best rule at any price.** It gets close at the
parity price (949 against `last_slot`'s 930 on the slack fleet, a 2.1% gap) and at
0.3 it is within noise of it (1046 against 1048), but at 1.0 — where a miss costs
ten times a GPU-hour of serving — it still over-defers by 3.9% and pays more in
misses than it saves in carbon. The capacity-bound fleet tells the same story
(best learner 1070 at 0.1 against `last_slot`'s 1045; 1414 at 0.3 against
`run_now`'s 1372), so this is not a single-fleet artefact.

Two mechanisms explain the shortfall, and both are visible in the action traces
the run records (`mean_coast_by_agent`, `hold_fraction_by_agent`):

* **The action space is too coarse to express the schedule.** A coast fraction
  can only withhold work older or younger than an age threshold; it cannot say
  *how much* to serve. Every learned arm holds roughly all of its slack on the
  first agent and none on another (`hold` traces of 1.0 and 0.0), which is a
  timing pattern, not a capacity plan.
* **Deferral without placement knowledge loses.** The plan the agents need is the
  one measured above: keep each slot inside the capacity of the site it will
  actually run on. No per-agent timing rule can see that, which is why
  `forecast_timing` loses to `last_slot` and why every learned arm here lands
  between them.

`share_of_bound_pct` is reported but should not be read as progress: an arm that
serves 3 pp less has a lower bound too, and the matched-service column
(`gap_to_own_bound_pct`) is the honest one. On that column every learned arm is
27–40% above the exact schedule at its own volume — `run_now` is 37% above it, so
the learner improves carbon by serving less rather than by scheduling better.

**The constructive result is in `rl/hybrid.py`.** A capacity-aware planner on the
forecast, which decides how much of each queue runs in the current slot against
the price of the capacity it would occupy, reaches 812.6 kg at 3.75% misses on
the slack fleet and 770.9 kg at 15.6% on the capacity-bound one — beating every
rule above on the objective at 0.1 and 0.3 while serving no less than they do.
Rung 7's conclusion is therefore not "learning does not work" but "learning in a
timing-only action space cannot express the schedule the problem needs"; the next
experiment puts the planner in the loop and leaves the learner the decision it
can actually make (how much risk to price in).
