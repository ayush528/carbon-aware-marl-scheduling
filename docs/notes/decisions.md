# Decision log (ADRs)

Append-only. One entry per decision that shapes the repo or the science.

## ADR-0001 — Git-native experiment versioning (no MLflow/DVC yet)

**Date:** 2026-11-08 · **Status:** accepted

Every experiment is `experiments/<id>/config.yaml` committed before running;
runs append manifests (git SHA, config SHA-256, data SHA-256s, seed, metrics)
under `experiments/<id>/runs/`; merged experiments are tagged `exp/<id>`.
Rollback = `make rollback EXP=<id>` (git worktree at the tag).

*Why:* the goal is "return to any past configuration from a command". Git
already gives content-addressing, history and rollback; a tracking server or
data tool adds setup cost with no benefit at current scale. DVC may be added
later only if model/data artifacts outgrow git.

## ADR-0002 — Stdlib-first runtime, tiny pinned deps

**Date:** 2026-11-08 · **Status:** accepted

Runtime deps: PyYAML + requests only. Statistics/hash/CSV via stdlib. Dev
deps: pytest, ruff. All pinned exact versions.

*Why:* reproducibility is the product; the fewer moving parts, the longer the
chain stays reproducible. Heavy deps (torch, gymnasium) arrive in Phase 2/3
with their own pinned lockfile.

## ADR-0003 — docs/ restructure

**Date:** 2026-11-08 · **Status:** accepted

`feasibility-study/` split into `docs/research/` (notes, report, plan),
`docs/datasets/` (data-audit + catalog), `docs/deliverables/`. Audit fetch
scripts stay inside `data-audit/scripts/` and are invoked via
`scripts/fetch_data.sh`.

*Why:* separates durable reference material (docs) from code (src/scripts)
and experiments (experiments/), so agents and humans can find each by role.

## ADR-0004 — TDD is mandatory for all code changes

**Date:** 2026-11-08 · **Status:** accepted

No production code merges without a test written first: red (the failing
test defines the behavior) → green (minimum code to pass) → refactor. Bug
fixes land their reproducing regression test before the fix. Pure
docs/config changes are exempt. CI (pytest on py3.11/3.12) is the
enforcement gate.

*Why:* the project's core claim is reproducibility — tests-first is the
same discipline applied to code: behavior is pinned before it exists, and
every PR's CI run re-proves the pinned behavior.

