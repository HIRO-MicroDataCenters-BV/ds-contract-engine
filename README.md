# ds-contract-engine

**NextGen Data Space — Contract Engine.** Hosts two sub-services that issue and verify VC-JWT contracts inside the federated Data Space.

| Sub-service | Ticket | Path | Default port |
|---|---|---|---|
| **Contract Generator** | DS-306 | [`server/contract-generator/`](server/contract-generator/) | 8082 |
| **Contract Validator** | DS-307 | [`server/contract-validator/`](server/contract-validator/) | 8083 |

Each sub-service is independently deployable, has its own Dockerfile, its own Helm chart, and is scoped to a single concern.

## Repository layout

Strictly mirrors the [`ds-catalog`](https://github.com/HIRO-MicroDataCenters-BV/ds-catalog) repo conventions:

```
ds-contract-engine/
├── api/                      # OpenAPI specs (one per sub-service)
│   ├── contract-generator/
│   └── contract-validator/
├── client/                   # OpenAPI-generated client SDKs (regenerated via tools/)
│   ├── contract-generator/
│   └── contract-validator/
├── docs/                     # Design docs and payload specifications
│   ├── contract-engine-research.md
│   ├── contract-engine-payload-spec.md
│   └── payload-format.md
├── examples/                 # Worked examples (cURL, Python, end-to-end)
├── server/                   # FastAPI services
│   ├── contract-generator/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   ├── core/         # entities, use-cases, ports
│   │   │   ├── adapters/     # signing key, clearing house clients
│   │   │   └── rest_api/     # routes, depends, response, serializers
│   │   └── charts/server/    # Helm chart for this sub-service
│   └── contract-validator/
│       └── (same shape as generator)
├── tools/                    # Helper scripts
├── LICENSE
├── README.md
├── VERSION
├── pyproject.toml            # Repo-level metadata
└── poetry.lock
```

## Documentation

- **[`docs/contract-engine-research.md`](docs/contract-engine-research.md)** — design rationale, trade-offs, sequence diagrams, known risks.
- **[`docs/payload-format.md`](docs/payload-format.md)** — locked v1 token format (Notion-import friendly).
- **[`docs/contract-engine-payload-spec.md`](docs/contract-engine-payload-spec.md)** — full implementation reference: env vars, runtime flow, upstream service contracts.

## Quick start

Both sub-services are FastAPI applications managed with Poetry.

### Run the Generator locally

```bash
cd server/contract-generator
poetry install
DS__NODE_ID="hus.nextgen.hiro-develop.nl" \
DS__SIGNING_KEY_PATH="./local-ed25519.pem" \
DS__SIGNING_KEY_ID="hus.nextgen.hiro-develop.nl#key-1" \
DS__CLEARING_HOUSE_URL="http://localhost:9001" \
DS__ENVIRONMENT="development" \
poetry run uvicorn app.main:app --reload --port 8082
```

The Generator will create a fresh Ed25519 key on first run if `DS__SIGNING_KEY_PATH` does not exist (development convenience only — production deployments mount a Kubernetes Secret).

### Run the Validator locally

```bash
cd server/contract-validator
poetry install
DS__NODE_ID="hus.nextgen.hiro-develop.nl" \
DS__CLEARING_HOUSE_URL="http://localhost:9001" \
DS__JWKS_BASE_URL_TEMPLATE="http://localhost:8082" \
DS__ENVIRONMENT="development" \
poetry run uvicorn app.main:app --reload --port 8083
```

The `DS__JWKS_BASE_URL_TEMPLATE` override points the Validator at the local Generator's JWKS endpoint instead of trying to derive `https://<iss>/.well-known/jwks.json` from the token's `iss` claim.

### End-to-end: mint then validate

With both services running:

```bash
# 1. Mint a contract via the Generator
TOKEN=$(curl -s -X POST http://localhost:8082/v1/contracts \
  -H "Content-Type: application/json" \
  -d '{
    "consumer_id": "researcher-sai-kireeti",
    "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
    "ttl_seconds": 3600,
    "items": [{
      "id": "https://hus.nextgen.hiro-develop.nl/dataset-test-2907",
      "identifier": "synthetic_dataset_test_2907",
      "title": "GWAS on Cats 2907",
      "hash": "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
    }]
  }' | jq -r '.token')

# 2. Validate the freshly minted token
curl -s -X POST http://localhost:8083/v1/validate \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN\"}"
```

Expected response: `{"allow": true, "reason": null, "jti": "...", "order_id": "..."}`.

## Helm

Each sub-service has its own chart:

```bash
helm install ds-contract-generator ./server/contract-generator/charts/server
helm install ds-contract-validator ./server/contract-validator/charts/server
```

See each sub-service's `charts/server/values.yaml` for configuration options.

## Status

v1 implementation. Policy Engine integration is documented as a v2 enhancement — see [`docs/contract-engine-payload-spec.md`](docs/contract-engine-payload-spec.md) §12.

