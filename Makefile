PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
EXP    ?=
ID     ?=

.DEFAULT_GOAL := help
.PHONY: help setup lint format test check exp-new exp-run exp-show rollback \
        data-fetch docker-build docker-test clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Create .venv and install pinned dependencies
	bash scripts/setup.sh

lint: ## Static checks (ruff check + format check)
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m ruff format --check src tests

format: ## Auto-format and auto-fix
	$(PYTHON) -m ruff format src tests
	$(PYTHON) -m ruff check --fix src tests scripts

test: ## Run the unit-test suite
	$(PYTHON) -m pytest -q

check: lint test ## Everything CI runs locally

exp-new: ## Scaffold an experiment: make exp-new ID=exp002-slug
	bash scripts/exp_new.sh $(ID)

exp-run: ## Run an experiment: make exp-run EXP=exp001-uk-carbon-baseline
	$(PYTHON) scripts/run_experiment.py $(EXP)

exp-show: ## Show an experiment's config, tag and run history
	bash scripts/exp_show.sh $(EXP)

rollback: ## Roll back to a tagged experiment: make rollback EXP=exp001-...
	bash scripts/rollback.sh $(EXP)

data-fetch: ## Re-fetch audit datasets: make data-fetch TARGET=uk-month
	bash scripts/fetch_data.sh $(TARGET)

data-pull-matrix: ## Pull 14-region carbon matrix (Jan 2025) -> data/uk_regional_2025-01_tidy.csv
	$(PYTHON) scripts/pull_regional_matrix.py

data-pull-national: ## Pull national carbon intensity: make data-pull-national START=... END=... OUT=data/uk_national_2025-02.json
	$(PYTHON) scripts/pull_national.py $(if $(START),--start $(START),) $(if $(END),--end $(END),) $(if $(OUT),--out $(OUT),)


docker-build: ## Build the reproducible image
	docker build -f docker/Dockerfile -t carbon-scheduling:dev .

docker-test: ## Run the test suite inside the image
	docker run --rm carbon-scheduling:dev

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .coverage src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
