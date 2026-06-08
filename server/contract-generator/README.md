# ds-contract-generator

**Sub-service of the NextGen Data Space Contract Engine — DS-306.**

Mints signed VC-JWT contracts when a researcher selects catalog items in the Marketplace and Checkout fans out per node.

## What it does

1. Receives `POST /v1/contracts` from Checkout with a node-specific bundle of selected catalog items.
2. Fetches the active signing key from the platform's signing-key service.
3. Assembles a VC-JWT payload (see [`docs/payload-format.md`](../../docs/payload-format.md)).
4. Signs with EdDSA.
5. Self-verifies the freshly minted token (primary verification).
6. Registers the `jti` in this node's local Clearing House.
7. Returns the signed JWT to Checkout.

## What it does NOT do (in v1)

- Does not call the Policy Engine. v1 trusts Checkout's prior authorisation. Policy Engine integration is documented as a v2 enhancement in [`docs/contract-engine-payload-spec.md`](../../docs/contract-engine-payload-spec.md) §12.
- Does not enforce ODRL rules.
- Does not embed `credentialStatus` in the token. Validators query the Clearing House directly using `jti`.

## Quick start (local development)

```bash
poetry install
DS__NODE_ID="hus.nextgen.hiro-develop.nl" \
DS__SIGNING_KEY_PATH="./local-ed25519.pem" \
DS__SIGNING_KEY_ID="hus.nextgen.hiro-develop.nl#key-1" \
DS__CLEARING_HOUSE_URL="http://localhost:9001" \
poetry run uvicorn app.main:app --reload --port 8082
```

The service exposes:

| Path | Purpose |
|---|---|
| `POST /v1/contracts` | Mint a contract |
| `GET /.well-known/jwks.json` | Publish this node's public key for Validators |
| `GET /health-check/` | Health probe |
| `GET /docs` | Auto-generated OpenAPI docs |
| `GET /metrics` | Prometheus metrics |

## Configuration

All configuration is via environment variables with the prefix `DS__`. See [`app/settings.py`](app/settings.py).

## Running with Docker

```bash
docker build -t ds-contract-generator:dev .
docker run -p 8082:8082 \
  -e DS__NODE_ID="hus.nextgen.hiro-develop.nl" \
  -e DS__SIGNING_KEY_ID="hus.nextgen.hiro-develop.nl#key-1" \
  -e DS__CLEARING_HOUSE_URL="http://ds-clearing-house:8080" \
  -v $(pwd)/keys:/keys \
  -e DS__SIGNING_KEY_PATH="/keys/ed25519.pem" \
  ds-contract-generator:dev
```

## Helm chart

See [`charts/server/`](charts/server/).

```bash
helm install ds-contract-generator ./charts/server
```
