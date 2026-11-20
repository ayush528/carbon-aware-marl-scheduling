# Frontend (`viz/frontend/`)

Next.js app that presents the project's experiment evidence. It is a **view**:
it computes nothing. Every figure comes from the Python service in
`viz/backend`, which reads committed artifacts (`config.yaml`,
`run/manifest.json`, `run/metrics.json`, `registry.yaml`).

```
make api        # terminal 1: Python service on 127.0.0.1:8000
make web-dev    # terminal 2: Next.js on 127.0.0.1:3000
```

## Why two processes

The Python side already holds the artifacts and their parsing, and it is tested
against the run records (`tests/test_api_service.py`). Re-implementing that in
TypeScript would create a second source of truth for numbers that are supposed
to be auditable, so the Node layer only proxies and renders.

Calls happen in React Server Components, so:

* the browser never talks to the Python service,
* no CORS is needed in deployment,
* the Python service can bind to loopback.

Every page is `force-dynamic`: the build never needs the service, and a page
always shows the evidence that exists now rather than a snapshot baked at build
time.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `EXPERIMENT_API_URL` | `http://127.0.0.1:8000` | where the Python service listens |

If the service is unreachable the pages say so, with the command that starts it —
they never render placeholder numbers.

## Pages

| Route | What it argues |
|---|---|
| `/` | the claim, the phase status, and where each piece of evidence lives |
| `/data` | what the data is, what it is not, and the disclosed gaps |
| `/uncertainty` | conformal bands, the 2024 walk-forward grid, decision relevance |
| `/simulator` | the unmodified SustainCluster baseline and the UK substitution |
| `/policies` | the seven-rung ladder, observation/action/objective |
| `/experiments` | the registry, each run's manifest, and the raw metrics |
| `/roadmap` | phases, exit tests, the reproducibility contract, limits |

## Checks

```
npm run typecheck
npm run build
```
