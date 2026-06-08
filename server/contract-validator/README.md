# ds-contract-validator

**Sub-service of the NextGen Data Space Contract Engine — DS-307.**

Validates incoming VC-JWT contracts before the central Connector Service fetches node-local data.

## What it does

When called with a token, it runs (in parallel where possible):

1. **Signature check** — fetch the issuing node's public key from its JWKS endpoint, verify EdDSA signature.
2. **Audience check** — reject if `aud` does not match this node's identity.
3. **Expiry check** — reject if `exp` has passed (with configurable leeway).
4. **Registration check** — query this node's local Clearing House for the `jti`'s status; reject if not `active`.
5. **Catalog hash check** — recompute the SHA-256 of each catalog item's primary distribution and compare to the `hash` in the token.

Returns `{allow: bool, reason: str | null, jti: str, order_id: str}`.

## What it does NOT do (in v1)

- Does not call the Policy Engine. Mid-session policy changes propagate via Clearing House revocation in v1.
- Does not evaluate ODRL rules.

## Quick start (local development)

```bash
poetry install
DS__NODE_ID="hus.nextgen.hiro-develop.nl" \
DS__CLEARING_HOUSE_URL="http://localhost:9001" \
DS__JWKS_BASE_URL_TEMPLATE="http://localhost:8082" \
poetry run uvicorn app.main:app --reload --port 8083
```

The service exposes:

| Path | Purpose |
|---|---|
| `POST /v1/validate` | Validate a token |
| `GET /health-check/` | Health probe |
| `GET /docs` | Auto-generated OpenAPI docs |
| `GET /metrics` | Prometheus metrics |

## Configuration

All configuration is via environment variables with the prefix `DS__`. See [`app/settings.py`](app/settings.py).

## Helm chart

See [`charts/server/`](charts/server/).
