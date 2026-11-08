# Reproducible environment for tests and experiments.
# Build:  docker build -f docker/Dockerfile -t carbon-scheduling:dev .
# Run:    docker run --rm carbon-scheduling:dev            (test suite)
#         docker compose run --rm exp                      (exp001)
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# make (Makefile targets) and git (runner records the commit SHA)
RUN apt-get update \
    && apt-get install -y --no-install-recommends make git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY pyproject.toml Makefile ./
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
COPY experiments ./experiments
COPY docs/datasets/data-audit/downloads ./docs/datasets/data-audit/downloads

RUN pip install -e . --no-deps

CMD ["make", "test"]
