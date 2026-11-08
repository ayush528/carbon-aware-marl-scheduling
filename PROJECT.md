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

- **The problem:** public workload traces never name the grid region their
  data center sits in, so carbon-aware scheduling rests on an unverifiable
  assumption.
- **Our angle:** UK carbon data (NESO) as region-matched ground truth, with
  **calibrated forecast-uncertainty bands** (conformal prediction) as a
  first-class input to the scheduler, plus a CVaR risk term on SLA
  violations.
- **The moat:** measured uncertainty — every design decision protects it.
  Claims are relative only (identical demand); absolutes are labelled
  illustrative. The region-mapping assumption is disclosed early.
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
loaders in `src/carbon_scheduling/carbon.py` → Phase 1: conformal bands +
demand models (`src/data/`, planned) → Phase 2: simulator env → Phase 3:
agents (heuristics → PPO → IPPO/MAPPO + CVaR) → Phase 4: evaluation.

**Experiment framework (working today):**

| Component | File | Role |
|---|---|---|
| Runner | `src/carbon_scheduling/runner.py` | loads config, hashes config+data, seeds RNG, writes run records (manifest + metrics) |
| Experiment functions | `src/carbon_scheduling/experiments/` | pure `config → metrics` callables, registered in `__init__.py` |
| Configs | `experiments/<id>/config.yaml` | committed before running; the versioned experiment definition |
| Run records | `experiments/<id>/runs/` | append-only evidence: git SHA, config SHA-256, data SHA-256s, seed, metrics |
| Registry | `experiments/registry.yaml` | status + rollback tag per experiment |
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
| `make docker-build` / `docker-test` | build image / run tests in it |
| `docker compose run --rm exp` with `EXP=...` | run experiment in container, records land on host |

## Data rules

- Catalog with URLs, licenses and audit status: `docs/datasets/DATASETS.md`.
- Raw downloads land in `docs/datasets/data-audit/downloads/`; only small
  evidence JSONs are committed (CSVs gitignored, re-fetchable).
- Any dataset used by an experiment must be listed in its config `data:` —
  the runner hashes every listed file into the manifest.

## Status / milestone log

| Date | Milestone | Reference |
|---|---|---|
| 2026-11-04 | Feasibility study complete (report, 30-paper survey, data audit) | initial commit |
| 2026-11-08 | Phase 0 infra: docs restructure, experiment framework, CI/CD, Docker, Makefile | PR #1 |
| 2026-11-08 | Agent skills vendored in-repo + load-before-work protocol (ADR-0004) | PR #2 |

## Roadmap (from `docs/research/findings-and-plan.md` Part 5)

| Phase | Weeks | Work | Exit test |
|---|---|---|---|
| 0. Infra | done | repo, CI/CD, Docker, experiment framework | CI green; exp001 reproducible in Docker |
| 1. Data freeze | 1–4 | NESO 14-region chunked puller; conformal bands; Azure demand model | bands hit target coverage on held-out month |
| 2. Simulator | 5–10 | SustainCluster → NESO regional carbon → 3–5 UK sites | baseline reproduced; carbon matches GB actuals |
| 3. Agents | 11–18 | RR/EDF/carbon-greedy → centralized PPO → IPPO → MAPPO → +CVaR | each level beats/matches previous |
| 4. Evaluate & write | 19–24 | ablations, robustness, thesis | claims inside EuroSys-2024 envelope |

## Next up (Phase 1 — data freeze)

- [ ] Guide sign-off on `docs/research/report/executive-summary.md` (Step 0 gate)
- [ ] NESO 14-region long-window puller, chunked weekly (`src/data/`)
- [ ] Forecast-error conformal bands; coverage eval on held-out month (exp002+)
- [ ] Azure LLM trace sampled stream loader + demand-model sketch
- [ ] Branch protection on `main` requiring CI checks
