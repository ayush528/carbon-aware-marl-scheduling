# carbon-aware-marl-scheduling

Uncertainty-aware decentralized multi-agent reinforcement learning for
carbon-aware workload scheduling across geo-distributed data centers
(B.Tech major project).

Every experiment in this repo is **versioned, reproducible and traceable**:
configs are committed before running, runs record git SHA + config hash +
data hashes + metrics, and merged experiments are git-tagged so any past
configuration can be rolled back with one command.

[![CI](https://github.com/ayush528/carbon-aware-marl-scheduling/actions/workflows/ci.yml/badge.svg)](https://github.com/ayush528/carbon-aware-marl-scheduling/actions/workflows/ci.yml)

## Quickstart

```bash
make setup            # .venv + pinned deps
make test             # unit tests (same suite CI runs)
make exp-run EXP=exp001-uk-carbon-baseline
```

Docker (no local Python needed):

```bash
make docker-test      # build image + run tests inside it
EXP=exp001-uk-carbon-baseline docker compose run --rm exp
```

## Experiment lifecycle

```
make exp-new ID=exp002-slug        # scaffold config
#   edit config, register function, COMMIT
make exp-run EXP=exp002-slug       # append run record (git SHA, hashes, metrics)
#   commit records, PR, CI green, merge -> tag exp/exp002-slug
make rollback EXP=exp002-slug      # reproduce/continue from that exact state
```

Full protocol: [PROJECT.md](PROJECT.md). Roadmap and feasibility evidence:
[docs/research/findings-and-plan.md](docs/research/findings-and-plan.md).
Dataset catalog with URLs and licenses:
[docs/datasets/DATASETS.md](docs/datasets/DATASETS.md).
