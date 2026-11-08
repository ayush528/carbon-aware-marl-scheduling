# TODO

## This week (Phase 0 → Phase 1 start)

- [x] Repo restructure: docs/, experiments/, src/, tests/, scripts/
- [x] Versioned experiment framework (config → hash → run record → tag)
- [x] CI/CD: ruff + pytest (3.11/3.12) + Docker gate, PR-only merges
- [x] Dockerfile + compose; everything behind `make` targets
- [x] living context + protocol doc (local)
- [x] exp001: NESO Jan-2025 national baseline, reproducible end-to-end
- [x] TDD adopted for all code changes (ADR-0004)
- [x] README: architecture + data model + experiment lifecycle diagrams
- [ ] Get guide sign-off on `docs/research/report/executive-summary.md` (Step 0 gate)
- [x] Enable branch protection on `main` (require CI checks, no force push)
- [x] NESO regional puller, weekly-chunked (`src/carbon_scheduling/data/neso.py`) — exp002 verifies live pull == audit sample
- [x] 14-region x full-month matrix pull (`make data-pull-matrix`) — validated by exp003
- [x] exp003: matrix validation + actuals-gap pinned
- [x] exp004: split-conformal bands — held-out Feb 2025 coverage 92.1% (target 90%); Phase 1 exit test passed
- [x] exp005: regional bands via national scaling — 12/14 regions ≥ 90% on held-out Feb (mean 91.9%); Phase 1 complete
- [x] exp006: Azure LLM trace loader — 16.8M requests streamed, per-half-hour demand on the NESO grid
- [x] exp007: cluster energy model — NLR idle→peak × PUE, real-trace envelope (0.45 Wh/req, sanity range OK)
- [ ] Phase 2 next: run SustainCluster as-is → swap NESO regional carbon → 3–5 UK sites → baseline reproduced

## Backlog / later phases

- Phase 2: SustainCluster baseline reproduction; swap in NESO regional carbon
- Phase 2: 3–5 UK site topology; bands in observations
- Phase 3: RR / EDF / carbon-greedy baselines; then PPO → IPPO → MAPPO → +CVaR
- Phase 4: ablation + robustness harness; thesis skeleton from report chapters
