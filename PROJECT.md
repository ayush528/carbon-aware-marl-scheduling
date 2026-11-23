# PROJECT.md — living context for AI agents (and humans)

> **Update rules:**
> 1. Whenever a milestone or a unit-tested component/module is merged, update
>    the *Status / milestone log* and any protocol changes here, in the same PR.
> 2. **After every change or update in code, update the *Architecture* section
>    below** so it always reflects how the system actually works.
> This file is the single source of context — keep it current.

## What is this project?

Final-semester **B.Tech major project**: an uncertainty-aware, decentralized
multi-agent reinforcement learning (MARL) scheduler that places GPU/LLM
workloads across data centers in different electricity grid regions to cut
carbon emissions without missing deadlines — built on real-world data only.

- **Main goal: a publishable journal paper**, and the bar for that is a
  **novel experiment**. The claim as of 2026-11-23 must be a *combination* claim
  and must be stated as "we did not find", never "first": decentralised
  multi-agent scheduling with a CVaR tail term on SLA violations, evaluated with
  **matched-service accounting**, on real region-matched carbon. The survey
  already knew the conformal-uncertainty paper (arXiv 2407.02390 / SIGENERGY
  2024) and correctly noted it has no control agents; what changed since is that
  2026 added strong centralised carbon+SLA solvers (arXiv 2607.22806, 2610.14571,
  2609.14775), so the gap is narrower than a 30-paper 2024–2025 survey implies.
  See `docs/research/2024-2026-carbon-scheduling-comparison.md`. The
  uncertainty-specific contribution is now a **theorem plus its boundary**
  (exp026), not an observation: any regional series built by scaling a national
  one has `realized - forecast = forecast x (one shared per-slot factor)`, so
  realized and forecast induce the same ranking, forecast-greedy is already the
  slot optimum, and a band can only misprice. Verified on 18,757 slots (0
  reordered, 42 weeks, 0 weeks better). Every phase must
  produce evidence toward the narrowed claim; work that doesn't is scaffolding
  and is kept minimal.
- **The problem:** public workload traces never name the grid region their
  data center sits in, so carbon-aware scheduling rests on an unverifiable
  assumption.
- **Our angle:** UK carbon data (NESO) as region-matched ground truth, with
  **calibrated forecast-uncertainty bands** (conformal prediction) as a
  first-class input to the scheduler, plus a CVaR risk term on SLA
  violations. The band's measured decision value is on level and timing risk,
  not on site ranking (three replications, structural reason).
- **The moat:** honest measurement — matched-service accounting, a
  carbon-vs-SLA frontier instead of a single headline, real price and latency
  reported beside carbon. Claims are relative only (identical demand);
  absolutes are labelled illustrative. The region-mapping assumption is
  disclosed early.
- **The benchmark finding (exp022/exp023), now part of the argument:** in the
  published simulator, on the same UK week, our planner comes within **0.01%** of its best
  controller while using only a causal forecast (that controller reads realized
  intensity, so it is an oracle) — and the reason there is so little room is measurable:
  88.7% of that benchmark's carbon is idle draw no controller can touch, the
  contestable range is 11.3%, and the best published rule already takes 61% of
  it because placement has one dominant winner (South Scotland cheapest in
  162/168 hours, median gap 49.3%). Placement-only carbon scheduling is
  saturated; the only remaining lever is *when* work runs, and that
  benchmark's controller interface cannot express it for any controller. State
  the win (6–12% at matched service) only together with the arena it holds in.
- Full study, literature survey (30 papers) and data audit:
  `docs/research/findings-and-plan.md` — the roadmap phases come from there.

## Project

**Uncertainty-aware decentralized multi-agent reinforcement learning for
carbon-aware workload scheduling across geo-distributed data centers**
(B.Tech major project).

- **The moat:** measured uncertainty — conformal bands on regional carbon
  intensity. Every design decision protects it.
- **Claims are relative only:** comparisons under identical demand; absolute
  savings are labelled illustrative (EuroSys-2024 envelope).
- **Disclose early:** the region-mapping assumption (no public trace names a
  real region — verified across 29 trace families) belongs in the abstract,
  not a footnote.
- Full study, literature and dataset audit:
  `docs/research/findings-and-plan.md` (roadmap phases 1–4 come from there).

## Non-negotiable workflow

1. **No direct commits to `main`.** All work happens on feature branches
   (`feature/<slug>`, one unit of work) → pull request.
2. **A PR merges only after every CI check is green** (lint + tests on
   Python 3.11/3.12 + Docker build & in-image test run).
   Recommended: enable branch protection on `main` requiring these checks.
3. **Milestones get tagged.** When a milestone or unit-tested module merges,
   update this file's log and tag `m<phase>/<name>` (e.g. `m0/infra`).
4. **Anything run twice becomes a script**; anything invoked repeatedly gets a
   Makefile target. No ad-hoc magic commands — the Makefile is the entrypoint.
5. **Never commit files > 50 MB.** Large raw datasets are re-fetchable via
   `make data-fetch`; see `docs/datasets/DATASETS.md`.
6. **TDD always** (ADR-0004): no production code lands without
   a failing test written first — **red** (test defines the behavior, watch
   it fail) → **green** (minimum code to pass) → **refactor**. Bug fixes add
   the reproducing regression test before the fix. Pure doc/config commits
   are exempt.

## Experiment protocol (the reproducibility contract)

Goal: *go back to any past experiment configuration and re-run it exactly.*

1. One experiment = `experiments/<exp-id>/config.yaml`, **committed before it
   is run**. Scaffold with `make exp-new ID=expNNN-slug`.
2. Register the experiment function in
   `src/carbon_scheduling/experiments/` and list it in
   `experiments/registry.yaml`.
3. Run with `make exp-run EXP=<id>` — this appends an immutable record to
   `experiments/<id>/runs/`: git SHA, config SHA-256, data-file SHA-256s,
   seed, timestamp, metrics. **Commit the run records** — they are evidence.
4. When config + results merge to `main`, tag the merge `exp/<id>`. That tag
   is the rollback point.
5. Roll back / reproduce any experiment:
   `make rollback EXP=<id>` → checks the tag out in an isolated worktree at
   `.worktrees/<id>` (never touches your current tree). Add `--continue` to
   branch off that state. Re-running there must reproduce the recorded
   `config_hash` and metrics — that match is the proof.
6. **Never edit a merged config.** Changed hypothesis → new experiment id.
   An experiment replaces an earlier one → mark it `superseded` in
   `experiments/registry.yaml`.

## Architecture

Keep this section in sync with the code after every change (rule 2 above).

**Data flow:** NESO / Azure / EIA sources → fetchers + audit
(`docs/datasets/data-audit/scripts/`, invoked via `make data-fetch`) →
regional puller `src/carbon_scheduling/data/neso.py` (all 18 region ids,
weekly-chunked ranges, injected HTTP + retry; parse + chunk + fetch are
unit-tested, live-API correctness pinned by exp002) →
**regional matrix** `data/uk_regional_2025-01_tidy.csv` (14 DNO regions x
Jan-2025, tidy CSV, built by `make data-pull-matrix`, validated by exp003) →
**conformal bands** `src/carbon_scheduling/bands.py` (split conformal on
national forecast residuals; exp004: calibrate Jan → hold-out Feb coverage
92.1% vs 90% target — Phase 1 exit test PASSED; exp005: per-region bands via
national scaling — 12/14 regions ≥ 90% on held-out Feb, mean 91.9%) →
**demand stream** `src/carbon_scheduling/demand.py` (Azure LLM trace →
per-half-hour arrivals+tokens on the NESO slot grid; exp006: 16.8M requests
validated, mean 50k/peak 155k per slot) →
**cluster model** `src/carbon_scheduling/cluster.py` (linear idle→peak
per-GPU power from NLR profiles × PUE; exp007 envelope on the real trace:
mean u 0.70, 90/336 slots saturate, 0.45 Wh/request — sanity range OK) →
**external simulator** SustainCluster (MIT, HPE Labs; cloned into a gitignored
`external/` dir via `make sc-setup`) driven headless — exp008 reproduces it
unmodified: 5 rule-based controllers + 4 shipped SAC checkpoints, 7 days,
seed 42. `lowest_carbon` 308,033 kg vs `round_robin` 329,321 kg (−6.5%); no
SAC checkpoint beats the best heuristic, and all four violate 27–48% of task
SLAs because upstream's reward config leaves its timeliness penalty disabled.
UK substitution is **done** (exp009): four UK sites (London, South Wales,
North West England, South Scotland) are fed by our derived NESO regional
series and a real GB wholesale price series (Elexon Market Index Data) written
in upstream's CSV schema. Exit test **passed**: the per-site intensity implied
by the simulator's own accounting matches the input series over the window it
actually read (max error 0.77 gCO₂/kWh, 0.32%), the site ordering matches, and
`lowest_carbon` cuts 6.87% vs `round_robin` at 0.1% SLA. Window: 2024-01-09
18:00Z + 7 days; regional spread 263 gCO₂/kWh (South Wales 338 vs South
Scotland 74). Three upstream limits the UK run must disclose: GB has one AWS
region, so **transmission cost is exactly 0** and that term is inoperative; the
price series is national, so `lowest_price` has nothing to differentiate and is
degenerate (+3.11% carbon); and the cluster reset **jitters the data window**
±7 days/random hour, so the drivers probe that seeded draw and put the workload
clock on the same window before verifying carbon against it. Head-to-head against
those controllers is **done** (exp022) and the answer is a tie, which exp023
explains by measurement: our rule is injected into the simulator's own strategy
map, so it is dispatched identically to `lowest_carbon` and lands within 0.01% of
that controller's carbon (106,457.4 vs 106,449.2 kg) using only a forecast while
that controller reads the realized series. The interface is placement-only
(a task is queued only if a site is returned; arrivals are never re-served), and
placement has one dominant winner here (South Scotland cheapest in 162/168 hours,
median gap 49.3%), so the argmin is the whole game. The identical week with no
arrivals emits 101,414.2 kg — **88.7% of the benchmark's carbon is idle draw no
controller can touch**, leaving an 11.3% contestable range of which the best
published rule takes 60.95% → Phase 3: agents (heuristics → PPO → IPPO/MAPPO +
CVaR) → Phase 4: evaluation.

**Service boundary.** The scheduler (`src/carbon_scheduling/`,
`experiments/`) and the visualization service (`viz/frontend/` + `viz/backend/`) are
separate deployables with a one-way contract: the visualization reads committed
run records and never imports the scheduler package. The scheduler image
(`docker/Dockerfile`) does not contain the visualization code; the
visualization has its own images (`docker/Dockerfile.viz-api`,
`docker/Dockerfile.viz-web`) and compose services (`make viz-up`). This keeps
the UI independent of scheduler internals and lets the scheduler become a
service the visualization consumes later.

**Experiment framework (working today):**

| Component | File | Role |
|---|---|---|
| Runner | `src/carbon_scheduling/runner.py` | loads config, hashes config+data, seeds RNG, writes run records (manifest + metrics) |
| Experiment functions | `src/carbon_scheduling/experiments/` | pure `config → metrics` callables, registered in `__init__.py` |
| Configs | `experiments/<id>/config.yaml` | committed before running; the versioned experiment definition |
| Run records | `experiments/<id>/runs/` | append-only evidence: git SHA, config SHA-256, data SHA-256s, seed, metrics |
| Registry | `experiments/registry.yaml` | status + rollback tag per experiment |
| NESO regional puller | `src/carbon_scheduling/data/neso.py` | `fetch_regional(region_id, start, end)`: weekly-chunked GETs, retries, verified REGIONS registry (1–14 DNO, 15–18 aggregates); tidy CSV read/write |
| Regional matrix | `make data-pull-matrix` (`scripts/pull_regional_matrix.py`) | 14-region x month pull -> `data/uk_regional_2025-01_tidy.csv` (forecast + actual columns; actuals empty, see Data rules) |
| National puller | `make data-pull-national` (`scripts/pull_national.py`) | national window -> API-consumable JSON (e.g. `data/uk_national_2025-02.json`, the Feb holdout) |
| Conformal bands | `src/carbon_scheduling/bands.py` | `conformal_quantile` (finite-sample corrected), `absolute_residuals`, `regional_residuals` (national-scaling estimator), `coverage` — deterministic, stdlib-only |
| Demand loader | `src/carbon_scheduling/demand.py` | `requests_per_slot(path, slot_minutes=30)`: streams the Azure LLM trace (16.8M rows) into per-slot arrivals + token sums on the NESO half-hour grid; idle slots zero-filled |
| Cluster model | `src/carbon_scheduling/cluster.py` | `Site` (NLR idle→peak W per GPU, PUE, throughput knob) + `slot_energy(demand, site)` → per-slot GPU-seconds, utilization (raw, may exceed 1; capped at peak power), kWh |
| Simulator adapter | `src/carbon_scheduling/sim/sustaincluster.py` | resolves the external checkout + its python, runs the headless drivers with `cwd=checkout` (upstream reads `configs/`/`data/` relatively), parses their JSON; passes UK overrides (site list, window, reward, explicit day index, transmission-region map) only when asked |
| UK input puller | `make sc-uk-data` (`scripts/sustaincluster/pull_uk_inputs.py`) | NESO regional carbon (national-scaling estimate, hourly) + Elexon GB prices (GBP→USD at the ECB 2024 mean) → `data/sustaincluster_uk/` + `provenance.json` |
| UK input installer | `make sc-uk-install` (`scripts/sustaincluster/install_uk_inputs.py`) | writes those series into the simulator's hardcoded paths, forward-fills the 15 missing NESO hours, symlinks GB weather per site, emits an install manifest (rows/fills/sha256) |
| Dispatch core | `src/carbon_scheduling/dispatch.py` | `risk_scores` (forecast + λ·band), `rank`, capacity-aware `allocate` with spill, `carbon_kg`, and both band builders (per-region absolute, pooled relative). Pure, stdlib-only, and unit-tested on the properties the claims rest on (a relative band cannot reorder sites; allocation is lossless) |
| Uncertainty diagnostic | `src/carbon_scheduling/uncertainty.py` | `classify(realized, forecast)` → `common-multiplicative` \| `common-additive` \| `regional`, plus `reorders`. The structural claim in executable form: a regional series built by scaling a national one has one shared error factor per slot, so its ranking is the forecast's and no band can act on it. Only `regional` leaves a band something to decide. exp026 verifies it on 18,757 real slots; run it on any dataset before trusting a spatial-uncertainty result built on that dataset |
| EIA-930 reader | `src/carbon_scheduling/data/eia.py` | hourly generation by fuel per US balancing authority → carbon intensity from each region's **own measured mix**, the counter-example to the national-scaling estimator. Published EIA factors (coal 2.31, gas 0.96, petroleum 2.46 lb CO2/kWh); gates on completeness (the fuel breakdown must account for net generation within 0.5% rounding noise) and drops rather than imputes, which excludes two authorities structurally and a large outlier by rule. Returns per-authority usable/dropped counts so the gate is visible |
| Scheduling env | `src/carbon_scheduling/rl/env.py` | weekly single-agent environment on our own data: an action is a risk level (fill every site by `forecast + λ·band`, with spill) or a wait; deadline violations, holding cost, idle draw, optional band in the observation; fully deterministic |
| Agent | `src/carbon_scheduling/rl/numpy_net.py`, `rl/ppo.py` | small actor-critic with hand-written backprop (checked against finite differences) + Adam, and clipped-surrogate PPO with GAE. numpy only, so CI and the Docker image keep one dependency set |
| Episode assembly | `src/carbon_scheduling/rl/data.py` | 2024 weeks → (forecast, realized, band, demand); the band is always calibrated on the 28 days *before* the episode's week; the single real Azure week is reused as a demand profile (disclosed) |
| Baselines (rung 4 rules) | `src/carbon_scheduling/rl/baselines.py` | `run_now`, `band_aware` and a deadline-aware `defer` rule, acting through the same action space as the agent; the same three joint rules for the multi-agent environment |
| Multi-agent env | `src/carbon_scheduling/rl/marl_env.py` | one agent per region: quote a risk level, offer 25/50/100% of slot capacity (or wait), and an untrained rule clears the cheapest bids with spill. Local rewards (own carbon, deadline misses blamed by refused capacity, holding share), a thin peering signal that can be switched off, an optional service obligation, per-slot tail metrics and per-agent violation attribution |
| MARL learners | `src/carbon_scheduling/rl/marl_ppo.py` | IPPO (independent actors) and MAPPO (the same actors plus a critic over the joint state, training only); shared GAE over the joint trajectory. The CVaR term has two attributions: charged once at the episode end (`terminal`, what exp013/exp014 measured, where one advantage in 336 carries it and the tail does not move) or charged every slot through a running-quantile Rockafellar-Uryasev estimate (`per_step`). Both replace the mean charge, so both carry the episode length as a factor -- without it the risk term was 1/336 of the quantity it replaced |
| Queue env (rung 7) | `src/carbon_scheduling/rl/queue_env.py` | agents own work streams instead of sites: four deadline classes (1/2/4/8 h) split the arrivals equally (disclosed -- the public trace has no latency labels), each agent chooses what fraction of its own slack to coast before offering its queue, and a coordinator places whatever is offered, cheapest forecast first. Per-agent carbon is the marginal energy only; the idle floor is the operator's standing cost and enters no agent's incentive. Misses are blamed to the queue that let them expire, which is what makes a per-slot tail signal possible |
| Queue rules (rung 7) | `src/carbon_scheduling/rl/queue_rules.py` | the timing yardsticks: immediate, deadline-only holding, forecast-aware, and band-aware (defer only while the future's worst case beats the present's best case) -- the first place the calibrated band enters a timing decision, since it provably cannot reorder sites |
| Hybrid scheduler | `src/carbon_scheduling/rl/hybrid.py` | `BlockPlanner`: at each slot, price every (slot, site) block as `forecast + robust*band`, then assign the tightest-deadline backlog to the cheapest legal blocks under each site's per-slot capacity, execute one slot, replan. `reserve`/`arrival_forecast` hold capacity back for arrivals the plan cannot see (`reserve` is the demand hedge; `arrival_forecast` derives it from a trailing arrival rate). `ForecastFlowPlanner` solves the same horizon exactly with the min-cost flow. `HybridEnv` is the rung-7 environment with offers set by the plan instead of by an action, so the planner is scored on the same accounting as every rule and learner |
| Timing bound | `src/carbon_scheduling/rl/oracle.py` | `plan(cost, demand, capacity, deadline, volume=None)` and `plan_multi(cost, demand, capacity, deadlines, volume=None)`: the cheapest legal schedule, solved as a min-cost flow, so it is a proven optimum rather than a heuristic's best effort. Carry arcs between slots cost nothing and are bounded by the work still inside its deadline window; `volume` pins the served work so a comparison is matched-service. Checked against exhaustive search on small instances, single-class and per-class deadlines |
| Arrival risk | `src/carbon_scheduling/rl/arrival_risk.py` | the one calibrated quantity with decision value: a trailing-mean arrival predictor, a split-conformal upper quantile of positive arrival exceedance, and a reserve spread over sites and the tightest deadline window. Measured coverage is 0.778 at a nominal 0.90 across the two halves of one diurnal week — the guarantee needs exchangeability, which one week does not have, and the experiment reports that instead of claiming it |
| Arrival models | `src/carbon_scheduling/rl/hybrid.py` | `hold` reserves capacity in future blocks for predicted arrivals; `ghost` instead adds the prediction to the plan as an item under the tightest deadline, so it competes for the cheapest legal blocks and consumes capacity only where it would run. Measured: ghosts dominate holds at equal service, anticipation is a service lever that costs a little carbon, and the diurnal shape is below the resolution of a two-slot reserve |
| Selection rule | `src/carbon_scheduling/experiments/exp020_selected_scheduler.py` | the shipped scheduler: candidate arms scored over Jan–Sep only, one arm picked per (fleet, price) cell, reported once on the held-out months; the best-on-test arm is printed beside it so the cost of honest selection is visible (≤1.79%) |
| Head-to-head planner | `src/carbon_scheduling/sim/uk_planner.py` | `DurationAwareStrategy` — our placement rule shaped as one of the external simulator's own rule-based controllers, so it is dispatched by the *same* cluster-manager path as the published controllers (no transit step, no action translation). Prices a task as the mean risk-qualified intensity over its own duration (`window_hours=None`) or over the arrival slot only (`0`); `lam` adds the calibrated band, and calibration is strictly before the window so the band never sees the week it decides on. A test pins that at a single slot the band cannot reorder sites. A first attempt drove the RL action path instead and manufactured a 22% SLA violation from the extra transit step — the strategy map is the only fair entry point |
| Simulator planner driver | `scripts/sustaincluster/run_planner.py` | runs that strategy inside the checkout with the simulator's own interpreter via `harness.build_env(inject_strategy=...)`, which adds it to the cluster's strategy map, so capacity checks, pending queues and accounting are the simulator's. Emits the same JSON shape as the baseline driver |
| Idle-floor probe | `scripts/sustaincluster/run_idle_floor.py` | the same environment with no arrivals: what it still emits is the idle draw of the estate. A hard lower bound rather than a controller, so every saving can be scored against what was ever contestable (exp023) |
| Rollback | `scripts/rollback.sh` | worktree at tag `exp/<id>`; re-run must reproduce recorded config_hash + metrics |
| CLI | `scripts/run_experiment.py` | `make exp-run EXP=...` entrypoint |

**Data store:** flat files + git (no DB server) — catalog in
`docs/datasets/DATASETS.md`, small evidence committed, large raw refetched.

## Repo map

```
PROJECT.md               <- you are here; update on every milestone
Makefile                # entrypoint for all repeatable commands
docker/Dockerfile       # reproducible env (pinned python:3.11.9-slim + make + git)
docker-compose.yml      # `test` and `exp` services
.github/workflows/ci.yml# lint + test (py3.11/3.12) + docker gate
src/carbon_scheduling/  # library: carbon.py (NESO loader), runner.py (experiment framework)
experiments/            # versioned experiments: <id>/config.yaml + registry.yaml
tests/                  # unit tests — CI gate for every PR
scripts/                # setup, exp_new, exp_run CLI, exp_show, rollback, fetch_data
docs/
  research/             # feasibility report, research notes A–D, findings-and-plan
  datasets/             # DATASETS.md catalog (URLs/licenses) + data-audit evidence
  deliverables/         # proposal deck, dataset-comparison spreadsheet
  notes/                # TODO, decision log (ADRs)
```

## Commands

| Command | Does |
|---|---|
| `make setup` | create `.venv`, install pinned deps, editable install |
| `make lint` / `make format` | ruff check / autofix |
| `make test` | pytest (CI runs the same via `make check`) |
| `make exp-new ID=exp002-slug` | scaffold an experiment config |
| `make exp-run EXP=...` | run an experiment, append run record |
| `make exp-show EXP=...` | config + tag + run history + latest metrics |
| `make rollback EXP=...` | worktree at the experiment's tag |
| `make data-fetch TARGET=uk-month` | re-fetch audit datasets |
| `make sc-uk-data` / `make sc-uk-install` | pull the 2024 UK carbon + price inputs, then install them into the simulator checkout |
| `make docker-build` / `docker-test` | build image / run tests in it |
| `docker compose run --rm exp` with `EXP=...` | run experiment in container, records land on host |

## Data rules

- Catalog with URLs, licenses and audit status: `docs/datasets/DATASETS.md`.
- Raw downloads land in `docs/datasets/data-audit/downloads/`; only small
  evidence JSONs are committed (CSVs gitignored, re-fetchable).
- Any dataset used by an experiment must be listed in its config `data:` —
  the runner hashes every listed file into the manifest.
- **Regional actuals do not exist in the NESO regional API** (verified live
  2026-11-09: 0 actuals across the full Jan-2025 matrix AND recent windows;
  the bulk all-regions endpoint likewise ships forecasts only). National
  actuals exist. Regional actuals must be estimated as
  `national_actual x regional_forecast / national_forecast` — disclosed
  assumption (findings-and-plan.md risk table). Bands work (exp004+) builds
  on this.
- **The 2024 NESO pull has a real outage**: 15 hourly slots missing on 11–12
  Jun 2024 in every region (8769 of 8784 rows). The simulator indexes carbon
  positionally, so the installer forward-fills them (count recorded in the
  install manifest). Carbon is not interpolated anywhere else; `provenance.json`
  records row counts, paired slots and gaps per site.
- **GB electricity price is national, not regional**: Elexon Market Index Data
  (GBP/MWh, half-hourly → hourly mean) converted to USD/MWh at the mean ECB
  2024 rate (1.2786). Regional wholesale-price differences are not modelled,
  so `lowest_price` cannot differentiate UK sites — report it as degenerate.
- **GB has exactly one AWS region** (`eu-west-2`), so the simulator's
  transmission-cost matrix is 0 on the diagonal and the term is inoperative for
  a UK-only run. Never read that as a finding about transmission cost.

## Status / milestone log

| Date | Milestone | Reference |
|---|---|---|
| 2026-11-04 | Feasibility study complete (report, 30-paper survey, data audit) | initial commit |
| 2026-11-08 | Phase 0 infra: docs restructure, experiment framework, CI/CD, Docker, Makefile | PR #1 |
| 2026-11-08 | Working-context doc + TDD protocol | PR #2 |
| 2026-11-08 | Phase 1 start: NESO regional puller + exp002 (live pull matches audit sample exactly) | PR #4 |
| 2026-11-09 | 14-region Jan-2025 matrix pulled + validated (exp003); regional-actuals gap pinned | PR #5 |
| 2026-11-09 | exp004: conformal bands, held-out Feb coverage 92.1% (target 90%) — **Phase 1 exit test passed** | PR #6 |
| 2026-11-09 | exp005: regional bands via national scaling — 12/14 regions ≥ 90% on held-out Feb; **Phase 1 complete** | PR #7 |
| 2026-11-09 | exp006: Azure LLM trace demand loader validated on the real 1-week sample (16.8M requests) | PR #8 |
| 2026-11-09 | exp007: cluster energy model + real-trace energy envelope (Phase 2 starts) | PR #9 |
| 2026-11-20 | exp008: SustainCluster run as-is (5 rule-based controllers + 4 SAC checkpoints) through in-repo headless drivers | branch |
| 2026-11-20 | exp009: SustainCluster on 4 UK sites with NESO regional carbon + Elexon prices; **Phase 2 exit test passed** (simulated vs input intensity max err 0.77 gCO₂/kWh, ordering matches; `lowest_carbon` −6.87% vs RR at 0.1% SLA) | branch |
| 2026-11-22 | exp011–exp012: band-aware dispatch and a PPO agent on held-out weeks. A relative band cannot reorder sites, and under the national-scaling estimator per-slot regional ordering is exact, so carbon-greedy is already optimal on ranking; uncertainty must earn its place on level and timing | branch |
| 2026-11-22 | exp013–exp014: decentralized IPPO/MAPPO with a service obligation and a deadline price swept around the 0.093 kg/GPU-hour parity price. The learner beats the hand-written rules on the objective it is given (+9.2% at parity, 12/12 weeks); direction seed-robust across 5 seeds, magnitude not (−24.8% to −60.5%). Negative results reported: terminal-only CVaR, communication and a centralised critic do not consistently help | branch |
| 2026-11-22 | exp015: exact perfect-foresight timing bound at matched service — 29.4% (slack) and 14.5% (capacity-bound) carbon at the 4-hour deadline, 12/12 weeks. The lever is large and no policy so far can reach it, which sets the rung-7 redesign | branch |
| 2026-11-22 | exp016: rung 7 — agents own work queues, so deferral is unilateral. Negative result, reported as one: no learner beats the best timing rule at any price (within 2.1% at parity, worse at the service price), because a coast fraction withholds work by age and cannot say *how much* of a queue to serve. Mechanism pinned: the forecast-aware rule is worse per served GPU-hour than deadline-only holding (65.4 vs 51.1 g/kWh) not because it sheds or de-aligns classes, but because its peaks force placement on the dirtiest site (15.0% of served work vs 8.0%) | branch |
| 2026-11-22 | exp017: a capacity-aware planner — **the scheduler beats every hand-written rule on the objective at the parity price (824 vs 930 slack, 840 vs 1045 capacity-bound) and at the crossover (905 vs 1048, 1292 vs 1372), 12/12 weeks better than carbon-greedy on carbon.** At a service-obligation price it correctly loses to "never defer". The calibrated band changes no decision for the third time (0.1%), and the exact rolling flow is the best *carbon* arm but the worst *objective* arm — exactness is not the same as being right | branch |
| 2026-11-23 | exp018: a calibrated arrival reserve — **the reserve stops being a knob tuned on the test set.** A split-conformal quantile of arrival exceedance (trailing-mean predictor, positive exceedances only, spread over sites and the tightest deadline window) matches the hand-swept 20% within 2% on both fleets without ever seeing the evaluation weeks: 810.1 kg at 3.65% missed against 812.6 / 3.75% on the slack fleet, 775.3 against 770.9 on the capacity-bound one; every planner arm still beats every rule, 12/12 weeks. Reported honestly: the coverage guarantee does *not* hold (0.778 at a nominal 0.90 across the two halves of one diurnal week), so the deployed reserve hedges less than its level claims | branch |
| 2026-11-23 | exp019: **anticipation buys service, the reserve buys carbon.** Ghosts (predicted arrivals placed as tightest-class items, never offered) dominate holds at any given service level (slack 865.5 kg at 2.85% missed against the hold's 1006.7 at 2.21%), but every anticipation arm costs a little carbon; the calibrated reserve stays the carbon lever (810.1 kg). The diurnal shape barely matters (flat vs seasonal within 0.4%) — volume does, shape does not. And for the first time a planner beats never-deferring at the obligation price on the slack fleet (1029 vs 1109), so exp017/exp018's "no planner can" was a property of myopic planning | branch |
| 2026-11-23 | exp020: **one shipped scheduler, its operating point chosen on Jan–Sep only.** Four of six (fleet, price) cells pick the same arm that is best on the held-out weeks; the worst cost of honest selection is 1.79%. Against never deferring: −14.8 / −5.8 / 0.0% on the capacity-bound fleet and −23.1 / −14.3 / −7.2% on the slack fleet at prices 0.1 / 0.3 / 1.0, with 21–27% less carbon at the parity price. The map is monotone in the price, and the two fleets find different extremes at the obligation price: keep deferring with spare capacity, never defer without it | branch |
| 2026-11-23 | exp021: **the frontier, and the correction to the headline.** The 27% carbon figure was not like-for-like: those arms miss 3–4% of arrivals where `run_now` misses none. `max_lookahead` caps how far ahead work may be placed (`0` = serve now, `None` = full horizon), tracing the trade instead of arguing about it. Capacity-bound fleet: a real Pareto region — `look8_ghost` cuts **11.8% carbon and 2.34 pp of misses at once**, and 8.7% at literally matched served volume, so served-work intensity genuinely falls (76.3 → 68.2 g/GPU-h) rather than work disappearing. Slack fleet: no Pareto point (nothing was missing), so inside a 0.5 pp miss budget the reachable saving is **6.6%**; 15–27% needs 2–4 pp of misses. Two axes measured for the first time: every arm is *cheaper* at the real GB day-ahead price (−1.5% to −9.4%, because GB low-carbon hours are low-price hours) and every arm delays served work by 1–2 h **within its deadline**. Honest claim: 6–12% carbon at matched service, same money or less, same SLA, later completion inside it | branch |
| 2026-11-23 | exp022: **head-to-head against the published controllers — the honest verdict is a tie.** Our placement rule is injected into the external simulator's own strategy map, so it takes the identical assignment path as all five published rule-based controllers on one week, one site list, one carbon series. **RETRACTED AND CORRECTED.** The first run reported an exact tie to the decimal; that was an artefact -- the simulator's clock is timezone-aware while our forecast keys were naive, so every lookup missed and the strategy silently fell back to the simulator's own carbon signal, i.e. it *was* `lowest_carbon`. Fixed, pinned by tests, and now asserted (`forecast_fallbacks: 0`). The real result: our causal forecast-driven planner emits 106,457.4 kg against `lowest_carbon`'s 106,449.2 -- **within 0.01%**. The installed carbon series is the *realized* estimate, so `lowest_carbon` reads realized intensity and is an **oracle**; our planner uses only the forecast. The honest framing is near-matching an oracle with strictly less information, not tying a peer. Two code facts explain it: the controller interface queues a task only if a site is returned (`None` discards it) and arrivals are never re-served, so deferral exists only in the RL path no published controller uses; and South Scotland is the cheapest region in 336 of 348 half-hours. The benchmark is **saturated for the one decision it exposes** | branch |
| 2026-11-23 | exp023: **88.7% of that benchmark's carbon is not a decision.** The identical environment with the task stream switched off emits 101,414.2 kg of round-robin's 114,306.2 — idle draw that no placement or deferral rule can remove. The contestable range is 12,892 kg (11.3%); `lowest_carbon` removes 7,857 kg of it (60.95%); our causal planner removes 7,849 kg (60.88%). Placement stability is measured, not asserted: South Scotland cheapest in 162/168 hours with a median gap to the runner-up of 49.3% of its own intensity, so the argmin has one winner and a wide margin and every correct rule computes the same assignment. Both caveats stated: the floor share is a property of this operating point (four sites at ~7% utilisation), and the marginal-intensity split is labelled derived and kept out of every headline | branch |
| 2026-11-23 | exp026: **the uncertainty result is a theorem, not an observation.** Regional actuals mostly do not exist, so realized intensity is built by scaling a national series; substituting into the error leaves one bracket per slot shared by every region, so realized and forecast induce the *same* regional ranking, forecast-greedy is already the slot optimum, and any reordering band can only misprice. Verified on 42 weeks / 18,757 slots: 0 reordered slots, 100% common-multiplicative, relative-error spread 1.8e-15. A pooled relative band changes 0.0000% at every λ; a per-region absolute band reorders 4.6–10.0% of slots and is better in **0 of 42 weeks** (worst +3.04%). Boundary (labelled Modelled): equal noise leaves the band inert; region-specific noise at 4× a realistic profile buys 0.003% tail carbon for 0.54% mean, about 170:1 against. Ships `uncertainty.classify` so the claim is checkable on any regional dataset | local |
| 2026-11-23 | exp027: **the boundary, measured on a real grid.** EIA-930 gives hourly generation by fuel per balancing authority, so realized intensity comes from each region's own measured mix. Structure is **100% regional** (4,339 h) and **25.03% of hours reorder** — against 0 of 18,757 on the scaled UK series — so exp026's theorem is a property of the construction, not of grids. Volatility differs **106x** across regions. The band helps for the first time in the project (4 and 5 of 18 weeks, best -0.41%) but the mean is within 0.03% of zero at low risk aversion, a cost by lambda 2, runs through **spill order not the winner**, and mostly vanishes with a better forecaster. A relative band misprices the near-zero-intensity hydro region (worst week +41.6%). Also fixed a real exp026 bug: relative bands were added as constants instead of scaling the forecast | local |

## Roadmap (from `docs/research/findings-and-plan.md` Part 5)

| Phase | Weeks | Work | Exit test |
|---|---|---|---|
| 0. Infra | done | repo, CI/CD, Docker, experiment framework | CI green; exp001 reproducible in Docker |
| 1. Data freeze | 1–4 | NESO 14-region chunked puller; conformal bands; Azure demand model | bands hit target coverage on held-out month |
| 2. Simulator | 5–10 | SustainCluster → NESO regional carbon → 3–5 UK sites | baseline reproduced; carbon matches GB actuals |
| 3. Agents | 11–18 | RR/EDF/carbon-greedy → centralized PPO → IPPO → MAPPO → +CVaR | each level beats/matches previous |
| 4. Evaluate & write | 19–24 | ablations, robustness, thesis | claims inside EuroSys-2024 envelope |

## Next up (Phase 3 — agents)

- [x] ~~Guide sign-off on `docs/research/report/executive-summary.md` (Step 0 gate)~~
- [x] ~~NESO 14-region puller, conformal bands (exp002–005), Azure trace loader (exp006) — Phase 1 complete~~
- [x] Branch protection on `main` requiring CI checks
- [x] Cluster energy model (exp007) — NLR power × PUE, real-trace envelope sanity-checked
- [x] ~~Run SustainCluster as-is — reproduce their baseline~~ (exp008)
- [x] ~~Swap in NESO regional carbon + real GB prices for four UK sites~~ (exp009); exit test
      passed. Upstream limits found: GB has one AWS region (transmission cost = 0), the price is
      national (`lowest_price` degenerate), and the cluster reset jitters the data window
      (the drivers now align the workload clock onto it).
- [x] ~~Bands into observations~~ — recalibrated on 2024 (exp010), put into the decision (exp011) and
      into the observation (exp012)
- [x] Rungs 4 and 5 (exp011, exp012). Both honest and both constraining: a relative band cannot
      reorder sites, and under the national-scaling estimator the per-slot regional ordering is
      exact, so carbon-greedy is already optimal on ranking. Uncertainty has to earn its place on
      **level and timing** (deadlines, CVaR), not on site ranking.
- [x] Rung 6 (exp013): IPPO/MAPPO over per-region agents, a service obligation, and a deadline
      price swept around the **parity price** — the 0.093 kg of CO₂ that serving one GPU-hour
      emits. The learner matches the carbon-greedy rule where service is free, and beats every
      hand-written rule on its own objective where a trade exists (9.2% at parity, 58% below it);
      carbon and service are reported together at every point, because unserved work emits
      nothing. The first version of this rung was wrong twice — a learning rate that diverged and
      prices eleven times the cost of serving — so the run now reports a learning gate and the
      parity price beside its results.
- [x] exp014: multi-seed replication at the parity price. **The direction is seed-robust; the
      magnitude is not.** All four variants cut carbon in all five seeds and are better in 12/12
      held-out weeks within every seed, but the capacity-bound cut ranges from −24.8% to −60.5%
      across seeds (bimodal, about −30% or about −59%), and every arm sheds 39–41% of work
      against the rule's 12.8%. The CVaR tail term changes nothing at alpha 0.8, 0.9 or 0.95
      (means within two points of risk-neutral against a fifteen-point seed spread).
- [x] exp015: the exact value of timing. Serving exactly the volume carbon-greedy serves, a
      min-cost-flow planner (a proven optimum, verified against exhaustive search) saves **29.4%**
      carbon on the slack fleet and **14.5%** on the capacity-bound fleet at the 4-hour deadline
      every policy has used, better in 12/12 held-out weeks. The bound is not a policy — it sees
      every realized intensity — but it proves the lever is large and that no policy so far has
      any of it: under the service obligation, deferral requires *every* agent to wait at the same
      slot, and the observation carries no per-agent queue age.
- [x] Rung 7 (exp016): agents own queues, so deferral is unilateral. It is a **negative result**:
      the learners do not beat the best timing rule at any price, because a coast fraction can only
      withhold work by age -- it cannot express *how much* of a queue to serve -- and no per-agent
      timing rule can see where the work will land. What the rules reveal is the constructive part:
      the forecast-aware rule is worse per served GPU-hour than deadline-only holding, and the
      mechanism is placement (15.0% of its served work on the dirtiest site against 8.0%), not
      shedding and not class de-alignment (both tested and refuted).
- [x] exp017: the hybrid the mechanism points to. A capacity-aware planner (price every slot-site
      block as forecast + band, assign the tightest-deadline backlog to the cheapest legal
      capacity, execute one slot and replan) **beats every hand-written rule on the objective at
      the parity price and at the crossover, on both fleets, and is 12/12 weeks better than
      carbon-greedy on carbon at every reserve setting.** At a service-obligation price it loses to
      "never defer" -- correctly, because at that price the right policy is not to defer. The
      calibrated band changes no decision for the third independent time, and the exact rolling
      flow is the best carbon arm but the worst objective arm: being optimal on the forecast is not
      the same as being right.
- [x] exp018: the reserve becomes calibrated, not tuned. A split-conformal quantile of arrival
      exceedance (trailing-mean predictor, positive exceedances, spread over sites and the tightest
      deadline window) matches the hand-swept 20% within 2% without seeing evaluation weeks. The
      coverage guarantee does *not* hold (0.778 at nominal 0.90), so the deployed reserve hedges
      less than its level claims -- reported as a negative result.
- [x] exp019: anticipation buys service, the reserve buys carbon. Ghosts (predicted arrivals placed
      as tightest-class items, never offered) dominate holds at any service level; volume matters,
      diurnal shape barely does (within 0.4%).
- [x] exp020: one shipped scheduler, its operating point chosen on Jan-Sep only. Four of six
      (fleet, price) cells pick the held-out-best arm; worst cost of honest selection 1.79%.
- [x] exp021: **the frontier, which corrects the headline.** `BlockPlanner.max_lookahead` caps how
      far ahead work may be placed, so the carbon-vs-SLA trade is measured rather than argued. The
      capacity-bound fleet has a real Pareto region (`look8_ghost`: -11.8% carbon, -2.34 pp misses;
      -8.7% at matched served volume); the slack fleet has none, so inside a 0.5 pp miss budget the
      saving is 6.6%, not 27%. Also measured for the first time: every arm is cheaper at the real GB
      day-ahead price, and every arm delays served work 1-2 h inside its deadline. The honest claim
      is 6-12% carbon at matched service.
- [x] exp022: the external baseline, answered. Our rule runs inside the published simulator's own
      controller map against all five published rule-based controllers on one week and **ties the
      best of them exactly** (106,449.2 kg, same energy, cost, SLA and 21,943 tasks, across three
      independent arms). Not a win, and not reported as one: the controller interface is
      placement-only (returning no site discards the task and arrivals are never re-served), and on
      this grid placement has one dominant winner.
- [x] exp023: the denominator. The identical environment with no arrivals emits 101,414.2 kg of
      round-robin's 114,306.2 -- **88.7% is idle draw no controller can touch**, the contestable
      range is 11.3%, and the best published rule already takes 60.95% of it. So the paper's claim
      must always be stated with its arena: where a deadline permits deferral, our planner removes
      6-12% at matched service against the same decision rule the published controllers use; where
      the benchmark forbids deferral, the two are provably identical.
- [ ] Report the idle floor as a curve, not a point: re-run the free-arrival measurement at higher
      utilisation so the 88.7% is tied to an operating point in the paper rather than quoted bare.
- [ ] Rewrite related work around the denominator. Every saving we cite is a percentage against
      another controller on an estate whose emissions were mostly idle draw; saying that once, with
      our own measurement, is a stronger contribution than another percentage -- but it must be
      written as "the denominator is rarely reported", never as "their numbers are wrong".
- [x] exp026: the uncertainty claim, settled as a theorem. A regional series built by scaling a
      national one has one shared error factor per slot, so realized and forecast induce the same
      ranking, forecast-greedy is already the slot optimum, and a band can only misprice. Verified
      on 18,757 slots across 42 weeks: 0 reordered slots, 0 of 42 weeks better, worst +3.04%.
      Equal per-region noise leaves the band inert; region-specific noise at 4x a realistic profile
      buys 0.003% of tail carbon for 0.54% of mean. So the band is a level/tail hedge, never a site
      selector -- and any spatial-uncertainty result computed on a scaled regional series is
      vacuous at best.
- [x] exp027: the check exp026 could not do for itself. On EIA-930, where each region's realized
      intensity comes from its own measured fuel mix, the structure is 100% regional and 25% of
      hours reorder -- so the theorem is about the scaling construction, not about grids. The band
      does help there, in a minority of weeks, by under half a percent, and mostly because the
      forecast is naive. A relative band misprices a near-zero-intensity region badly.
- [ ] **Publication plan, one month, in order:** the idle floor as a curve over utilisation (the
      88.7% is one operating point); full-year rolling-origin evaluation of the shipped planner
      (42 weeks, not 12); a deferral buffer in the published simulator given identically to all five
      published controllers; the risk-qualified headline on exp021's saving; the manuscript.
      Nothing else -- no new MARL variants, no new band constructions, no extra seeds for settled
      questions.
- [ ] Learned arrival pressure on top of the planner: the residual gap to the exact schedule is the
      part of the schedule that depends on arrivals the plan has not seen.
- [ ] exp016: a per-step tail surcharge in place of the terminal CVaR charge. The objective and
      the units are right; charging the tail once, at the last step, is why it cannot move the
      tail.
- [ ] Phase 4: multi-window evaluation and the remaining ablations, then the thesis tables
