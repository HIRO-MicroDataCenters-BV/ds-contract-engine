# ds-clearing-house-stub

**In-memory Clearing House stub for testing the Contract Engine end-to-end on cluster.**

This is **not** the real Clearing House. It provides just enough API surface to let the Contract Generator register newly minted `jti`s and the Contract Validator look up their status. State is held in memory and lost on pod restart.

Once the real Clearing House is built, this service is removed and replaced — no Contract Engine code changes.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST /v1/contracts` | Register a freshly minted contract as `active` |
| `GET /v1/contracts/{jti}` | Read current status |
| `PATCH /v1/contracts/{jti}/status` | Manually change status (for testing revocation) |
| `GET /v1/contracts` | List all registered contracts (debug) |
| `GET /health-check/` | Health probe |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` | OpenAPI UI |

## Configuration

| Env var | Default | Description |
|---|---|---|
| `DS__PORT` | `8084` | Listen port |
| `DS__LOG_LEVEL` | `INFO` | Logging verbosity |

## Quick start

```bash
poetry install
poetry run uvicorn app.main:app --reload --port 8084
```
