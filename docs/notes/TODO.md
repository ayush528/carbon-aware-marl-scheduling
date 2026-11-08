# TODO

## This week (Phase 0 → Phase 1 start)

- [x] Repo restructure: docs/, experiments/, src/, tests/, scripts/
- [x] Versioned experiment framework (config → hash → run record → tag)
- [x] CI/CD: ruff + pytest (3.11/3.12) + Docker gate, PR-only merges
- [x] Dockerfile + compose; everything behind `make` targets
- [x] PROJECT.md with full context + protocol
- [x] exp001: NESO Jan-2025 national baseline, reproducible end-to-end
- [x] TDD adopted for all code changes (ADR-0004)
- [x] README: architecture + data model + experiment lifecycle diagrams
- [ ] Get guide sign-off on `docs/research/report/executive-summary.md` (Step 0 gate)
- [x] Enable branch protection on `main` (require CI checks, no force push)
- [x] NESO regional puller, weekly-chunked (`src/carbon_scheduling/data/neso.py`) — exp002 verifies live pull == audit sample
- [ ] 14-region × full-month matrix pull (all 14 DNO regions, Jan 2025) on top of the puller
- [ ] exp003: forecast-error histogram → first conformal band prototype
- [ ] Azure LLM trace sampled stream loader (unit-tested)

## Backlog / later phases

- Phase 2: SustainCluster baseline reproduction; swap in NESO regional carbon
- Phase 2: 3–5 UK site topology; bands in observations
- Phase 3: RR / EDF / carbon-greedy baselines; then PPO → IPPO → MAPPO → +CVaR
- Phase 4: ablation + robustness harness; thesis skeleton from report chapters
