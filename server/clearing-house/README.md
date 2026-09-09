# ds-clearing-house

**The per-node contract registry, and the history of what happened to each contract.**

Replaces [`clearing-house-stub`](../clearing-house-stub), which holds state in
memory and loses it on pod restart. That matters more than it sounds: contract
validation is fail-closed, so losing the registry does not merely lose audit
history — it **denies every outstanding token at that node**.

The stub stays in the repository for local compose runs and for the Generator's
development-mode fallback.

## What it does

| | |
|---|---|
| **Registry** | one row per issued contract, and whether it is still `active` |
| **History** | an append-only log of what happened, and when |

## What it deliberately does not do

There is **no hash chain and no signature**. This service records history; it
does not prove the record was never edited. Someone with database access can
change it silently — the same guarantee as the pod logs it replaces, in a
better-shaped place.

Closing that gap needs signed checkpoints witnessed by peer nodes, which is a
larger piece of work and is not in scope here.

Settlement, escrow and the ethics body described in the NextGen proposal are
also out of scope.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST /v1/contracts` | Register a freshly minted contract as `active` |
| `GET /v1/contracts/{jti}` | Read current status — **the hot path** |
| `PATCH /v1/contracts/{jti}/status` | Change status, e.g. revoke |
| `GET /health-check/` | Health probe |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` | OpenAPI UI |

`GET /v1/contracts/{jti}` is read by the Contract Validator on **every data
access**, and it blocks on the answer. An unknown `jti` must return **404** —
the Validator maps that to `not_registered` and denies gracefully.

## Storage

SQLite today, on a ReadWriteOnce volume. PostgreSQL later, by changing one URL.

That portability is deliberate and enforced: every storage test runs against
**both** engines, so a query that works on one and not the other fails the
build. See `app/core/models/base.py` for the four rules that keep the schema
engine-neutral.

Because SQLite is single-writer, the Deployment runs `replicaCount: 1` with
`strategy: Recreate`. This is a requirement, not a default.

## Running locally

```bash
poetry install --no-root --with dev,test
poetry run uvicorn app.main:app --port 8085
```

```bash
curl http://localhost:8085/health-check/     # {"status":"OK"}
```

## Tests

```bash
poetry run pytest
```

## Collaboration guidelines

HIRO uses and requires from its partners
[GitFlow with Forks](https://hirodevops.notion.site/GitFlow-with-Forks-3b737784e4fc40eaa007f04aed49bb2e?pvs=4)
