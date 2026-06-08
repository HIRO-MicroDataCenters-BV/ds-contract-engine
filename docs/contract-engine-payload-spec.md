# Contract Engine — Token Payload Specification (v1)

**Status:** Implementation reference for POC development
**Scope:** Token shape, field origins, runtime generation, node configuration, environment variables, upstream service contracts
**Companion to:** [contract-engine-research.md](contract-engine-research.md) — covers design rationale, trade-offs, and architectural choices. This document covers only "what to build."
**Date:** 2026-04-23

---

## In short

This document is the implementation reference for the Contract Engine v1 token. It tells a developer:

- The exact JWT token shape (header + payload)
- Where each field's value comes from at runtime
- How the Generator assembles a token step-by-step
- What must be pre-configured on each node before the service can run
- Which values belong in environment variables and how to name them
- What APIs the Generator and Validator depend on upstream

**v1 deliberately omits the Policy Engine integration.** The policy block is reserved as an optional future field; the Generator does not call any policy service in v1. Authorisation in v1 is "the issuing provider node took responsibility; whatever it signed is allowed for the named consumer until expiry or revocation."

---

## Table of contents

1. [Token structure](#1-token-structure)
2. [Header fields](#2-header-fields)
3. [Payload fields](#3-payload-fields)
4. [Field origin reference](#4-field-origin-reference)
5. [Runtime generation flow](#5-runtime-generation-flow)
6. [Node pre-configuration](#6-node-pre-configuration)
7. [Environment variables — Generator](#7-environment-variables--generator)
8. [Environment variables — Validator](#8-environment-variables--validator)
9. [Upstream service contracts](#9-upstream-service-contracts)
10. [Pydantic models](#10-pydantic-models)
11. [End-to-end worked example](#11-end-to-end-worked-example)
12. [Forward compatibility — v2 changes](#12-forward-compatibility--v2-changes)
13. [Glossary](#glossary)

---

## 1. Token structure

A Contract Engine token is a **JWS-signed JWT** with the standard three-part wire form:

```
<base64url(header)>.<base64url(payload)>.<base64url(signature)>
```

The payload uses the **VC-JWT shape** — a `vc` claim wraps a `credentialSubject` object — but does **not** include a JSON-LD `@context` and does **not** declare the `VerifiableCredential` type marker. The token is not a strict W3C Verifiable Credential. Plain JWT/JOSE libraries are sufficient to issue and verify; no JSON-LD processor is required.

---

## 2. Header fields

```json
{
  "alg": "EdDSA",
  "typ": "JWT",
  "kid": "hus.nextgen.hiro-develop.nl#key-1"
}
```

| Field | Required | Type | Source | Notes |
|---|---|---|---|---|
| `alg` | yes | string | Generator constant | Always `EdDSA`. Matches the platform's KERI/Ed25519 identity layer. |
| `typ` | yes | string | Generator constant | Always `JWT`. |
| `kid` | yes | string | Signing-key service | Returned by the signing-key service when the Generator requests an active key. Format: `<NODE_ID>#<key_version>`. The Validator uses this to fetch the matching public key from the issuing node's JWKS endpoint. |

---

## 3. Payload fields

### 3.1 Outer JWT envelope

```json
{
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "iss": "hus.nextgen.hiro-develop.nl",
  "aud": "hus.nextgen.hiro-develop.nl",
  "sub": "researcher-sai-kireeti",
  "iat": 1745409600,
  "exp": 1745413200,
  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
  "vc": { ... }
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `jti` | yes | UUIDv4 string | Unique contract identifier. Generated fresh per token. Used by the Clearing House for registration / revocation lookup. |
| `iss` | yes | string | Issuer — the provider node's identity. Always equal to `NODE_ID`. |
| `aud` | yes | string | Audience — also equal to `NODE_ID`. The token is scoped to exactly this node. **Validator rejects if `aud` does not match its own node identity.** This is the security boundary that prevents misrouted tokens from being accepted. |
| `sub` | yes | string | Subject — the consumer (researcher) identifier. Comes from the auth context the Marketplace UI established. |
| `iat` | yes | integer (Unix timestamp) | Issued-at time. |
| `exp` | yes | integer (Unix timestamp) | Expiry time. Equals `iat + ttl_seconds`. The `ttl_seconds` value comes from Checkout (matches the order's TTL) or falls back to a node default. |
| `order_id` | yes | UUIDv4 string | The opaque order identifier from Checkout. Same value across all sibling sub-contracts in the bundle. The audit-correlation key. |
| `vc` | yes | object | Wrapper for the W3C-VC-shaped fields. See §3.2. |

### 3.2 The `vc` claim

```json
"vc": {
  "type": ["NextGenContract"],

  "credentialSubject": {
    "catalogItem": [
      {
        "id": "https://hus.nextgen.hiro-develop.nl/dataset-test-2907",
        "identifier": "synthetic_dataset_test_2907",
        "title": "GWAS on Cats 2907",
        "hash": "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
      }
    ]
  }
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `vc.type` | yes | string array | Always `["NextGenContract"]` in v1. Static constant. |
| `vc.credentialSubject` | yes | object | The body of the contract. |

#### `credentialSubject` fields

`credentialSubject` carries only contract-specific data. The consumer identity comes from the outer `sub` claim; the provider node identity comes from the outer `iss` / `aud` claims. No duplicated identifiers inside `credentialSubject`.

| Field | Required | Type | Description |
|---|---|---|---|
| `catalogItem` | yes | array | One or more catalog items on this provider node that this contract grants access to. **Per-node aggregation** — all selected items on this node fit in one token. See §3.3. |

#### `catalogItem` element

| Field | Required | Type | Description |
|---|---|---|---|
| `id` | yes | URI string | The full catalog item URI. Comes from the DCAT-AP record's `@id`. |
| `identifier` | yes | string | The DCAT `dcterms:identifier` short form. |
| `title` | yes | string | The DCAT `dcterms:title` human-readable name. |
| `hash` | yes | string | `sha256:<hex>` of the item's primary distribution. Used by the Connector to detect tampering between mint time and access time. |

### 3.3 Full v1 payload — final, locked

The complete v1 payload assembled together:

```json
{
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "iss": "hus.nextgen.hiro-develop.nl",
  "aud": "hus.nextgen.hiro-develop.nl",
  "sub": "researcher-sai-kireeti",
  "iat": 1745409600,
  "exp": 1745413200,

  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",

  "vc": {
    "type": ["NextGenContract"],

    "credentialSubject": {
      "catalogItem": [
        {
          "id": "https://hus.nextgen.hiro-develop.nl/dataset-test-2907",
          "identifier": "synthetic_dataset_test_2907",
          "title": "GWAS on Cats 2907",
          "hash": "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
        }
      ]
    }
  }
}
```

### 3.4 Full v2 payload — forward-compatible, with `policy` block

v2 adds a single optional field — `vc.credentialSubject.policy` — that captures a structured **merged snapshot** of the contract's terms at mint time. The block is populated from three natural sources, **not** from the Policy Engine response alone. The Policy Engine acts as a **gate** (allow / deny the mint), not as the source of these field values.

```json
{
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "iss": "hus.nextgen.hiro-develop.nl",
  "aud": "hus.nextgen.hiro-develop.nl",
  "sub": "researcher-sai-kireeti",
  "iat": 1745409600,
  "exp": 1745413200,

  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",

  "vc": {
    "type": ["NextGenContract"],

    "credentialSubject": {
      "catalogItem": [
        {
          "id": "https://hus.nextgen.hiro-develop.nl/dataset-test-2907",
          "identifier": "synthetic_dataset_test_2907",
          "title": "GWAS on Cats 2907",
          "hash": "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
        }
      ],

      "policy": {
        "action": "train",
        "purpose": "federated-learning",
        "allowedRegions": ["hus"],
        "isShared": true
      }
    }
  }
}
```

#### v1 vs v2 — what changes, what doesn't

| Concern | v1 | v2 |
|---|---|---|
| All outer JWT claims (`jti`, `iss`, `aud`, `sub`, `iat`, `exp`, `order_id`) | Same | Same |
| `vc.type` | `["NextGenContract"]` | `["NextGenContract"]` |
| `credentialSubject.catalogItem[]` | Same | Same |
| `vc.credentialSubject.policy` | **Absent** | **Present** — `{action, purpose, allowedRegions, isShared}` |
| Generator runtime | No upstream policy call | One additional `POST /api/v1/policies/evaluate` call as a **gate** before signing |
| Validator runtime | Skips policy check entirely | Re-evaluates by calling `POST /api/v1/policies/evaluate` and verifying the granted permissions still include the action being attempted |
| Tokens are forward/backward compatible | Yes — v2 Validator accepts a v1 token by treating absent `policy` as "no constraint declared" | Yes |

#### `policy` field reference (v2)

| Field | Required | Type | Origin (natural source) | Description |
|---|---|---|---|---|
| `policy.action` | yes | string | **Consumer request** (declared intent) | What the contract grants — e.g. `train`, `infer`. Confirmed allowed by the Policy Engine gate. |
| `policy.purpose` | yes | string | **Consumer request** (declared intent) | Why — e.g. `federated-learning`. The reason for this access. |
| `policy.allowedRegions` | yes | string array | **Catalog item metadata** (the regions in which the data may be used; defaults to the owning node's region) | Region constraint. Used by downstream services to enforce locality. |
| `policy.isShared` | yes | boolean | **Catalog item metadata** | Whether the items are part of a shared / public-research pool. |

#### Why the `policy` block does NOT mirror the Policy Engine response

The Policy Engine endpoint (`POST /api/v1/policies/evaluate`) returns `{permissions: [...]}` — a flat list of permission strings keyed off the consumer's `role + institute`. This is the right shape for the *gate decision* ("is this researcher allowed?"), but it is **not** the right shape for the contract's structured policy fields, because:

- `action` and `purpose` are *consumer-declared intents* — the consumer knows what they want to do; the Policy Engine confirms they are allowed. These flow naturally from the consumer's request, not from a policy lookup.
- `allowedRegions` is **intrinsic to the catalog item** — a property of where the data is owned and may be used. Catalog metadata is the source of truth.
- `isShared` is **also intrinsic to the catalog item** — a property of the data, not a property of any policy decision about it.

The Policy Engine's role in v2 is therefore a gate: the Generator calls `/evaluate`, checks for the required permission string in the response (e.g. `data_train`), and if present, mints a token with the structured `policy` block populated from the merged sources above. If the required permission is not present, the mint is refused.

This keeps the integration **thin** (no Policy Engine API change), keeps each field at its natural source, and avoids coupling the Contract Engine's token shape to the Policy Engine's response schema.

### 3.5 What is NOT in the v1 payload

| Field | Why omitted | When it returns |
|---|---|---|
| `@context` | No JSON-LD strictness — the Generator and Validator do not require a JSON-LD processor. | Only if external W3C VC interop becomes a goal. |
| `VerifiableCredential` (in `type`) | Without `@context`, claiming W3C VC compliance would be misleading. | Returns alongside `@context`. |
| `vc.credentialSubject.policy` | v1 does not integrate with the Policy Engine. | v2 — see §12. |
| `vc.credentialStatus` | The Validator queries its own per-node Clearing House directly using `jti` — no in-token status pointer needed. Provider node = audience = CH owner. | When cross-node revocation lookups are needed (e.g. StatusList2021 hosted at Clearing House). |
| ODRL `permission` / `prohibition` / `constraint` | Heavier; flat policy fields (when added in v2) cover POC needs. | Optional future enrichment if portable rule expression becomes valuable. |

---

## 4. Field origin reference

Every field in the payload, every place it can come from, and exactly when it gets populated.

### 4.1 By field

| Field | Where the value originates | Populated by | At what moment |
|---|---|---|---|
| `jti` | Generator runtime — `uuid.uuid4()` | Generator | First step of mint |
| `iss` | Node configuration — `NODE_ID` env var | Generator | At mint time, read from settings |
| `aud` | Same as `iss` (`NODE_ID`) | Generator | At mint time |
| `sub` | Auth context of the researcher in Marketplace; passed in the Checkout request as `consumer_id` | Generator copies from request | At mint time |
| `iat` | Generator runtime — `int(time.time())` | Generator | At mint time |
| `exp` | Computed: `iat + ttl_seconds`. `ttl_seconds` from Checkout request, or node default `DEFAULT_TTL_SECONDS` | Generator | At mint time |
| `order_id` | Checkout — generated as `uuid.uuid4()` before fan-out | Generator copies from request | At mint time |
| `vc.type` | Static constant `["NextGenContract"]` in Generator code | Generator | Always |
| `catalogItem[].id` | DCAT-AP `@id` of the selected dataset | Checkout enriches via Catalog Service, passes in request | At mint time |
| `catalogItem[].identifier` | DCAT-AP `dcterms:identifier` | Same | At mint time |
| `catalogItem[].title` | DCAT-AP `dcterms:title` | Same | At mint time |
| `catalogItem[].hash` | SHA-256 of the primary distribution. Pre-computed by Catalog Service (`spdx:checksum`) or computed at request-enrichment time | Checkout enriches, passes in request | At mint time |

### 4.2 By source

| Source | Fields populated from this source |
|---|---|
| **Generator runtime (computed fresh)** | `jti`, `iat`, `exp` (partially) |
| **Generator code (static constants)** | `alg`, `typ` (header), `vc.type` |
| **Node environment / config (`NODE_ID`)** | `iss`, `aud` |
| **Checkout request — auth context** | `sub` |
| **Checkout request — Checkout-generated** | `order_id`, `ttl_seconds` (drives `exp`) |
| **Checkout request — enriched from Catalog Service** | All `catalogItem[]` fields including the SHA-256 hash |
| **Signing-key service** | `kid` (header), the signature (after token assembly) |

The Generator does **not** call the Catalog Service or the Policy Engine at runtime in v1. It is a pure transformation of the Checkout request plus its node identity, sealed by a signing-key service call.

---

## 5. Runtime generation flow

What happens, in order, when the Generator receives `POST /v1/contracts` from Checkout:

```
1.  Authenticate the caller (Gateway / mTLS / API key — platform standard)
2.  Validate request body (Pydantic schema)
3.  Generate jti        := uuid.uuid4()
4.  Compute iat         := int(time.time())
5.  Compute exp         := iat + (request.ttl_seconds or DEFAULT_TTL_SECONDS)
6.  Read NODE_ID from settings
7.  Assemble payload (see §3)
8.  Call signing-key service: get active signing key + kid
9.  Build header with alg, typ, kid
10. Sign — produces JWS
11. Self-verify the signed token (primary verification — see research doc §2.8)
12. Register jti in own Clearing House: POST /contracts {jti, status="active", order_id}
13. Emit log event: contract.generated {jti, order_id, sub, items}
14. Return signed JWT in the HTTP response body
```

Step 11 is non-negotiable in v1 — it catches signing-key misconfiguration, schema mishandling, and base64 errors before a token reaches the consumer.

---

## 6. Node pre-configuration

Things that must exist **before** the Generator service can be started on a node. None of these are runtime concerns.

### 6.1 Identity

- The node has a stable, globally-unique identifier. Convention: the node's external hostname (e.g. `hus.nextgen.hiro-develop.nl`). Provided as `NODE_ID`.

### 6.2 Cryptographic key registration

- The signing-key service holds an Ed25519 keypair for this node.
- The active key has a `kid` of the form `<NODE_ID>#<version>` (e.g. `hus.nextgen.hiro-develop.nl#key-1`).
- The public key is published at the node's JWKS endpoint: `https://<NODE_ID>/.well-known/jwks.json`.
- Key rotation is a signing-key-service operation; the Generator does not need to know about it.

### 6.3 JWKS endpoint hosted

- A public HTTP(S) endpoint at `/.well-known/jwks.json` exposing the node's current public keys in JWKS format.
- Reachable by every other node's Validators.
- Cacheable — Cache-Control headers are recommended (e.g. `max-age=3600`).

### 6.4 Clearing House available

- A per-node Clearing House service is running and reachable from the Generator pod.
- Exposes at minimum: `POST /contracts` (register a `jti`), `GET /contracts/{jti}` (read status). See §9.4.

### 6.5 Network connectivity

- Generator pod can reach: signing-key service, Clearing House.
- Validator pod can reach: every participating node's JWKS endpoint, every participating node's Clearing House (read-only), the local Policy Engine when v2 lands.

### 6.6 TLS

- All inter-service traffic is TLS-encrypted. mTLS at the cluster ingress is preferred.
- TLS certificates are provisioned out-of-band and mounted as Kubernetes Secrets — not stored in env vars.

### 6.7 Observability

- Log destination is the cluster's pod-log stack (stdout collected by Loki / Elasticsearch / equivalent).
- Tracing endpoint is reachable if OpenTelemetry is in use.

---

## 7. Environment variables — Generator

### 7.1 Naming convention

Follow the **12-factor app** convention for configuration:

- All non-secret config in environment variables.
- Names in `UPPER_SNAKE_CASE`.
- Service-prefixed to avoid collisions with sibling services.
- Secrets (private keys, API tokens) managed by the platform's secret store (Kubernetes Secrets, Vault), **not** placed directly in env vars.

The recommended prefix matches the service repository name: `DS_CONTRACT_GENERATOR_*`.

### 7.2 Required

| Env var | Example value | Description |
|---|---|---|
| `DS_CONTRACT_GENERATOR_NODE_ID` | `hus.nextgen.hiro-develop.nl` | This node's identity. Used as `iss`, `aud`, `provider_id`, `node`. |
| `DS_CONTRACT_GENERATOR_SIGNING_KEY_SERVICE_URL` | `https://auth.hus.nextgen.hiro-develop.nl` | Base URL of the signing-key service. The Generator calls this to fetch the active signing key and the corresponding `kid`. |
| `DS_CONTRACT_GENERATOR_CLEARING_HOUSE_URL` | `http://clearing-house:8080` | Base URL of the local Clearing House. Used to register newly-minted `jti`s. |
| `DS_CONTRACT_GENERATOR_DEFAULT_TTL_SECONDS` | `3600` | Default contract TTL when Checkout does not provide one. Should match the Checkout order's default TTL. |
| `DS_CONTRACT_GENERATOR_PORT` | `8080` | TCP port the service listens on. |

### 7.3 Recommended

| Env var | Default | Description |
|---|---|---|
| `DS_CONTRACT_GENERATOR_HOST` | `0.0.0.0` | Bind address. |
| `DS_CONTRACT_GENERATOR_LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARN`, `ERROR`. |
| `DS_CONTRACT_GENERATOR_HTTP_TIMEOUT_SECONDS` | `5` | Timeout for upstream calls (signing-key, Clearing House). |
| `DS_CONTRACT_GENERATOR_HTTP_RETRIES` | `2` | Retry budget for transient upstream failures. |
| `DS_CONTRACT_GENERATOR_MAX_ITEMS_PER_CONTRACT` | `50` | Reject requests bundling more catalog items than this. |
| `DS_CONTRACT_GENERATOR_ENVIRONMENT` | `production` | One of `development`, `staging`, `production`. Affects log format and a few defaults. |

### 7.4 Observability (optional)

| Env var | Example value | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | OpenTelemetry collector endpoint. Standard OTel env name — not service-prefixed. |
| `OTEL_SERVICE_NAME` | `ds-contract-generator` | Service name reported to the tracing backend. |
| `OTEL_RESOURCE_ATTRIBUTES` | `node=hus.nextgen.hiro-develop.nl` | Free-form resource attributes. |

### 7.5 Forbidden in env vars

| What | Why | Where it goes instead |
|---|---|---|
| Private signing keys | Secret material; keys never leave the signing-key service. | Held by the signing-key service; Generator only requests *signatures*, never keys. |
| TLS private keys | Secret material. | Mounted from a Kubernetes Secret as a file. |
| API tokens for upstream services | Rotatable secrets. | Mounted from a Kubernetes Secret as files referenced by an `*_FILE` variant of the env var (e.g. `DS_CONTRACT_GENERATOR_SIGNING_KEY_SERVICE_TOKEN_FILE=/run/secrets/sk-token`). |

### 7.6 Pydantic Settings example

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class GeneratorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DS_CONTRACT_GENERATOR_",
        env_file=".env",
        case_sensitive=False,
    )

    # Required
    node_id: str
    signing_key_service_url: str
    clearing_house_url: str

    # Required with defaults
    default_ttl_seconds: int = 3600
    port: int = 8080

    # Recommended with sensible defaults
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    http_timeout_seconds: int = 5
    http_retries: int = 2
    max_items_per_contract: int = 50
    environment: str = "production"
```

---

## 8. Environment variables — Validator

The Validator has a different set of upstream dependencies. JWKS discovery and Clearing House reads dominate.

### 8.1 Required

| Env var | Example value | Description |
|---|---|---|
| `DS_CONTRACT_VALIDATOR_NODE_ID` | `hus.nextgen.hiro-develop.nl` | This node's identity. Validator rejects any token whose `aud` is not this value. |
| `DS_CONTRACT_VALIDATOR_CLEARING_HOUSE_URL` | `http://clearing-house:8080` | Local Clearing House to query for `jti` registration / status. |
| `DS_CONTRACT_VALIDATOR_PORT` | `8080` | TCP port. |

### 8.2 Recommended

| Env var | Default | Description |
|---|---|---|
| `DS_CONTRACT_VALIDATOR_HOST` | `0.0.0.0` | Bind address. |
| `DS_CONTRACT_VALIDATOR_LOG_LEVEL` | `INFO` | |
| `DS_CONTRACT_VALIDATOR_JWKS_CACHE_TTL_SECONDS` | `3600` | How long to cache JWKS responses from other nodes. Public keys change rarely — caching is safe and saves latency. |
| `DS_CONTRACT_VALIDATOR_HTTP_TIMEOUT_SECONDS` | `5` | Timeout for upstream calls (JWKS fetch, Clearing House query). |
| `DS_CONTRACT_VALIDATOR_HTTP_RETRIES` | `2` | |
| `DS_CONTRACT_VALIDATOR_LEEWAY_SECONDS` | `5` | Clock skew tolerance when validating `iat` / `exp`. |
| `DS_CONTRACT_VALIDATOR_ENVIRONMENT` | `production` | |

### 8.3 v2 — when Policy Engine integration lands

| Env var | Description |
|---|---|
| `DS_CONTRACT_VALIDATOR_POLICY_ENGINE_URL` | Local Policy Engine endpoint. Required only when the `policy` field is being enforced (v2). |
| `DS_CONTRACT_VALIDATOR_POLICY_ENGINE_TIMEOUT_SECONDS` | Timeout for Policy Engine calls. |

---

## 9. Upstream service contracts

What the Generator and Validator depend on, exactly. These are the API shapes that need to exist before either service can start working end-to-end.

### 9.1 Checkout → Generator

The request Checkout sends to the Generator after grouping items by node.

```http
POST /v1/contracts HTTP/1.1
Host: <generator-internal-host>
Content-Type: application/json

{
  "consumer_id": "researcher-sai-kireeti",
  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
  "ttl_seconds": 3600,
  "items": [
    {
      "id": "https://hus.nextgen.hiro-develop.nl/dataset-test-2907",
      "identifier": "synthetic_dataset_test_2907",
      "title": "GWAS on Cats 2907",
      "hash": "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `consumer_id` | yes | Comes from the Marketplace auth context. |
| `order_id` | yes | Generated by Checkout before fan-out. Same UUID across all sibling sub-contracts. |
| `ttl_seconds` | no | Falls back to `DEFAULT_TTL_SECONDS` if omitted. |
| `items[]` | yes | One or more catalog items, all owned by this node. Pre-enriched by Checkout from the Catalog Service. |

Response (success):

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "token": "eyJhbGciOiJFZERTQSIs...",
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "exp": 1745413200
}
```

### 9.2 Generator → Signing-key service

Two operations the Generator depends on.

#### Get the active signing key reference

```http
GET /v1/keys/active?node_id=hus.nextgen.hiro-develop.nl HTTP/1.1
Authorization: Bearer <service-account-token>
```

```http
HTTP/1.1 200 OK
{
  "kid": "hus.nextgen.hiro-develop.nl#key-1",
  "alg": "EdDSA"
}
```

#### Sign a payload

The signing-key service signs on behalf of the Generator. Private keys never leave it.

```http
POST /v1/sign HTTP/1.1
Authorization: Bearer <service-account-token>
Content-Type: application/json

{
  "kid": "hus.nextgen.hiro-develop.nl#key-1",
  "data": "<base64url(header).base64url(payload)>"
}
```

```http
HTTP/1.1 200 OK
{
  "signature": "<base64url(signature)>"
}
```

The Generator then concatenates: `<data>.<signature>` to form the final token.

### 9.3 JWKS endpoint (every node hosts one)

Public, unauthenticated endpoint. Used by Validators on other nodes to verify signatures.

```http
GET /.well-known/jwks.json HTTP/1.1
Host: hus.nextgen.hiro-develop.nl
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: max-age=3600

{
  "keys": [
    {
      "kid": "hus.nextgen.hiro-develop.nl#key-1",
      "kty": "OKP",
      "crv": "Ed25519",
      "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"
    }
  ]
}
```

### 9.4 Generator → Clearing House (register)

```http
POST /v1/contracts HTTP/1.1
Content-Type: application/json

{
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
  "status": "active",
  "consumer_id": "researcher-sai-kireeti",
  "iat": 1745409600,
  "exp": 1745413200
}
```

```http
HTTP/1.1 201 Created
{ "jti": "550e8400-e29b-41d4-a716-446655440000", "status": "active" }
```

### 9.5 Validator → Clearing House (read)

```http
GET /v1/contracts/550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
```

```http
HTTP/1.1 200 OK
{
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4"
}
```

`status` is one of `active`, `completed`, `cancelled`, `revoked`. The Validator allows only `active`.

---

## 10. Pydantic models

Drop-in models for FastAPI / Pydantic v2. The same `Policy` model is defined in both versions but is `Optional[Policy] = None` in `CredentialSubject`, so v1 code simply leaves it out and v2 code populates it. **No schema fork needed** — v1 and v2 share one set of models.

### 10.1 Shared models — used by both v1 and v2

```python
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class CatalogItem(BaseModel):
    id: str
    identifier: str
    title: str
    hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

class Policy(BaseModel):
    """Structured snapshot of the contract's terms at mint time.

    Populated from three sources, NOT from the Policy Engine response alone:
      - action, purpose      → consumer request (declared intent)
      - allowedRegions       → catalog item metadata
      - isShared             → catalog item metadata

    The Policy Engine's /evaluate endpoint is called separately as a GATE —
    its response is checked for the required permission string but is not
    persisted into this object.
    """
    action: Literal["train", "infer"]
    purpose: Literal["federated-learning"]
    allowedRegions: List[str]
    isShared: bool

class CredentialSubject(BaseModel):
    catalogItem: List[CatalogItem]
    policy: Optional[Policy] = None     # absent in v1, populated in v2

class VerifiableCredential(BaseModel):
    type: List[str] = ["NextGenContract"]
    credentialSubject: CredentialSubject

class ContractPayload(BaseModel):
    jti: str
    iss: str
    aud: str
    sub: str
    iat: int
    exp: int
    order_id: str
    vc: VerifiableCredential
```

When serialising for the wire, use `model_dump(exclude_none=True)` so the absent `policy` field is dropped from v1 tokens entirely (rather than appearing as `"policy": null`).

### 10.2 Generator request — v1

```python
class GenerateRequestV1(BaseModel):
    consumer_id: str
    order_id: str
    ttl_seconds: Optional[int] = None
    items: List[CatalogItem]

class GenerateResponse(BaseModel):
    token: str
    jti: str
    exp: int
```

### 10.3 Generator request — v2

Adds the four consumer-attribute fields needed by the Policy Engine call. Backward-compatible — v1 callers simply do not send them, and the Generator falls back to v1 behaviour (skip the Policy Engine call, emit a token with no `policy` block).

```python
class GenerateRequestV2(BaseModel):
    consumer_id: str
    consumer_name: Optional[str] = None         # required only if v2 path is used
    consumer_email: Optional[str] = None        # required only if v2 path is used
    consumer_role: Optional[str] = None         # required only if v2 path is used
    consumer_institute: Optional[str] = None    # required only if v2 path is used
    order_id: str
    ttl_seconds: Optional[int] = None
    items: List[CatalogItem]
```

The Generator decides which path to take by checking whether the four optional `consumer_*` fields are populated. If they are, it calls the Policy Engine and embeds a `policy` block; if not, it produces a v1-shaped token.

### 10.4 Validator request / response

Same in both versions:

```python
class ValidateRequest(BaseModel):
    token: str

class ValidateResponse(BaseModel):
    allow: bool
    reason: Optional[str] = None
    jti: Optional[str] = None
    order_id: Optional[str] = None
```

### 10.5 Policy Engine integration models (v2)

These mirror the existing Policy Engine endpoint exactly — they live alongside the Contract Engine code so the HTTP integration is type-safe.

```python
class PolicyEvaluationRequest(BaseModel):
    """Mirror of the Policy Engine's existing input schema."""
    name: str
    email: str
    role: str
    institute: str

class PolicyEvaluationResult(BaseModel):
    """Mirror of the Policy Engine's existing output schema."""
    permissions: List[str]
```

---

## 11. End-to-end worked example

Following one contract from Marketplace selection to the bytes on the wire.

### Inputs

- Researcher logged in as `researcher-sai-kireeti`.
- Researcher selects `synthetic_dataset_test_2907` (a single HUS dataset).
- Checkout determines the dataset belongs to node `hus.nextgen.hiro-develop.nl` (from the dataset URI).
- Checkout generates `order_id = 9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4`.
- Checkout fetches the dataset's checksum from Catalog Service: `sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6`.

### Checkout → Generator request

```http
POST /v1/contracts HTTP/1.1
Host: ds-contract-generator.hus.nextgen.hiro-develop.nl
Content-Type: application/json

{
  "consumer_id": "researcher-sai-kireeti",
  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
  "ttl_seconds": 3600,
  "items": [
    {
      "id": "https://hus.nextgen.hiro-develop.nl/dataset-test-2907",
      "identifier": "synthetic_dataset_test_2907",
      "title": "GWAS on Cats 2907",
      "hash": "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
    }
  ]
}
```

### Inside the Generator

```python
# Generator runtime values
NODE_ID = "hus.nextgen.hiro-develop.nl"   # from env
DEFAULT_TTL_SECONDS = 3600                 # from env
now = 1745409600                           # int(time.time())

# Step 3-5: generate jti, compute timestamps
jti = "550e8400-e29b-41d4-a716-446655440000"   # uuid.uuid4()
iat = 1745409600
exp = 1745409600 + 3600   # = 1745413200

# Step 7: assemble payload
payload = {
    "jti": jti,
    "iss": NODE_ID,
    "aud": NODE_ID,
    "sub": "researcher-sai-kireeti",
    "iat": iat,
    "exp": exp,
    "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
    "vc": {
        "type": ["NextGenContract"],
        "credentialSubject": {
            "catalogItem": [
                {
                    "id": "https://hus.nextgen.hiro-develop.nl/dataset-test-2907",
                    "identifier": "synthetic_dataset_test_2907",
                    "title": "GWAS on Cats 2907",
                    "hash": "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
                }
            ]
        }
    }
}

# Step 8: fetch active key from signing-key service
# Returns: kid="hus.nextgen.hiro-develop.nl#key-1"

# Step 9: build header
header = {"alg": "EdDSA", "typ": "JWT", "kid": "hus.nextgen.hiro-develop.nl#key-1"}

# Step 10: sign
token = jwt.encode(payload, signing_key_handle, algorithm="EdDSA", headers=header)

# Step 11: self-verify (would raise if anything is wrong)
jwt.decode(token, public_key, algorithms=["EdDSA"], audience=NODE_ID)

# Step 12: register in own Clearing House
clearing_house.post("/v1/contracts", json={
    "jti": jti, "order_id": payload["order_id"], "status": "active",
    "consumer_id": payload["sub"], "iat": iat, "exp": exp
})

# Step 13: log
log.info("contract.generated", extra={"jti": jti, "order_id": payload["order_id"]})

# Step 14: return token
```

### On the wire

```
eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCIsImtpZCI6Imh1cy5uZXh0Z2VuLmhpcm8tZGV2ZWxvcC5ubCNrZXktMSJ9
.
eyJqdGkiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAiLCJpc3MiOiJodXMubmV4dGdlbi5oaXJvLWRldmVsb3AubmwiLCJhdWQiOiJodXMubmV4dGdlbi5oaXJvLWRldmVsb3AubmwiLCJzdWIiOiJyZXNlYXJjaGVyLXNhaS1raXJlZXRpIiwiaWF0IjoxNzQ1NDA5NjAwLCJleHAiOjE3NDU0MTMyMDAsIm9yZGVyX2lkIjoiOWQ4ZTdjNmItNWE0Zi0zZTJkLTFjMGItYTlmOGU3ZDZjNWI0IiwidmMiOnsidHlwZSI6WyJOZXh0R2VuQ29udHJhY3QiXSwiY3JlZGVudGlhbFN1YmplY3QiOnsuLi59fX0
.
3Rp4k9F8nQ2mVxT7bYcLzA8fW2eK5mN1pR7sX9jQ0vZ8a
```

### HTTP response back to Checkout

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "token": "eyJhbGciOiJFZERTQSIs...3Rp4k9F8nQ2mVxT7bYcLzA8fW2eK5mN1pR7sX9jQ0vZ8a",
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "exp": 1745413200
}
```

Checkout collects this token, plus the corresponding tokens from any other nodes in the same order, into `[token_HUS, token_NodeB, ...]` and hands the bundle (along with `order_id`) back to the researcher.

---

## 12. Forward compatibility — v2 changes

These changes are planned for v2 and described here so v1 code can be written without painting itself into a corner. All v2 additions are **purely additive** — v1 tokens remain valid forever, and v2 Validators must accept v1-shaped tokens by treating absent fields as "no constraint".

### 12.1 Policy Engine integration

The platform already runs a Policy Engine with a deployed Rego ruleset and the endpoint:

```
POST /api/v1/policies/evaluate
```

v2 reuses this **existing** endpoint — no new Policy Engine API is invented for the Contract Engine.

#### Request shape (existing)

```json
{
  "name": "Sai Kireeti",
  "email": "sai@example.nl",
  "role": "catalog_consumer",
  "institute": "hus"
}
```

#### Response shape (existing)

```json
{
  "permissions": ["catalog_read", "data_train"]
}
```

#### Generator integration in v2 — Policy Engine as a gate

```python
# v2 only — between payload assembly and signing
# 1. GATE: ask the Policy Engine whether this role+institute is allowed
policy_eval = await http.post(
    f"{POLICY_ENGINE_URL}/api/v1/policies/evaluate",
    json={
        "name": request.consumer_name,
        "email": request.consumer_email,
        "role": request.consumer_role,
        "institute": request.consumer_institute,
    },
)
permissions = policy_eval.json()["permissions"]

REQUIRED_PERMISSION = "data_train"  # configurable via env var
if REQUIRED_PERMISSION not in permissions:
    raise PermissionDenied(f"role lacks {REQUIRED_PERMISSION}")

# 2. BUILD policy block from natural sources (NOT from the Policy Engine response)
credential_subject.policy = {
    "action":         request.action,                                  # from consumer request
    "purpose":        request.purpose,                                 # from consumer request
    "allowedRegions": list({item.region for item in request.items}),   # from catalog metadata
    "isShared":       all(item.is_shared for item in request.items),   # from catalog metadata
}
```

The Policy Engine response is consumed **only as a yes/no gate** — its `permissions[]` list is checked for the required permission string, then discarded. The token's `policy` block is populated independently from consumer-declared intent and catalog metadata. This keeps each field at its natural source and avoids coupling the Contract Engine's token shape to the Policy Engine's response schema.

The `name` and `email` fields are sent to the Policy Engine because the existing endpoint requires them, but they are **deliberately not stored in the token** — keeping personally-identifying data out of the signed artefact.

#### Validator integration in v2

```python
# v2 only — additional check inside the parallel fan-out
if "policy" in cs:
    # Confirm the action and purpose declared in the token match what's being attempted
    requested_action  = validate_request.action   # supplied by Connector during the call
    requested_purpose = validate_request.purpose
    policy_ok = (
        cs["policy"]["action"]  == requested_action and
        cs["policy"]["purpose"] == requested_purpose
    )
else:
    # v1 token — no policy block, accept on the other checks
    policy_ok = True
```

The Validator in v2 does **not** re-call the Policy Engine. The reasoning:

- The Generator already gated at mint time using the Policy Engine.
- Mid-session policy changes propagate through revocation — when a policy tightens, affected `jti`s are marked `revoked` in the Clearing House, and the registration check in §9.5 catches it.
- The `policy` block in the token serves as the *contract terms* — what the consumer is permitted to do — and the Validator confirms the access being attempted matches those terms.

This keeps validation cheap and avoids tying Validator latency to Policy Engine availability.

### 12.2 Other planned v2 enhancements

| v1 → v2 change | What changes in the payload | What changes in code |
|---|---|---|
| **Cross-node revocation lookup via StatusList2021** | Add optional `vc.credentialStatus` block pointing at the issuing node's StatusList2021 endpoint | Validator adds a status-list-pull path; useful when revocation propagation across nodes becomes a requirement |
| **ODRL enrichment** | Replace the flat `policy` with ODRL `permission[]` / `prohibition[]` / `constraint[]` | Validator adds local ODRL evaluation step; tokens become self-describing for external W3C VC verifiers |
| **External W3C VC interop** | Add `vc.@context` and `VerifiableCredential` to `vc.type` | No code change inside Contract Engine; external verifiers can now consume tokens without custom integration |

### 12.3 What Checkout sends to Generator in v2

The Generator request gains three new fields for Policy Engine input:

```json
{
  "consumer_id": "researcher-sai-kireeti",
  "consumer_name": "Sai Kireeti",
  "consumer_email": "sai@example.nl",
  "consumer_role": "catalog_consumer",
  "consumer_institute": "hus",
  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
  "ttl_seconds": 3600,
  "items": [ ... ]
}
```

The three additions (`consumer_name`, `consumer_email`, `consumer_role`, `consumer_institute`) come from the Marketplace auth context that Checkout already has access to. The fields beyond `consumer_id` are required only when the Policy Engine call needs to be made — i.e. only in v2.

### 12.4 New env vars in v2

| Env var | Description |
|---|---|
| `DS_CONTRACT_GENERATOR_POLICY_ENGINE_URL` | Local Policy Engine base URL. The Generator appends `/api/v1/policies/evaluate`. |
| `DS_CONTRACT_GENERATOR_POLICY_ENGINE_TIMEOUT_SECONDS` | Timeout for the policy evaluation call. Default: `2`. |
| `DS_CONTRACT_VALIDATOR_POLICY_ENGINE_URL` | Same for the Validator. |
| `DS_CONTRACT_VALIDATOR_POLICY_ENGINE_TIMEOUT_SECONDS` | Timeout for the Validator's re-evaluation call. Default: `2`. |
| `DS_CONTRACT_VALIDATOR_REQUIRED_PERMISSION` | The permission string the Validator must find in the Policy Engine's response. Default: `data_train`. |

None of these are required for v1 to compile or run.

---

## Glossary

| Term | Meaning |
|---|---|
| **JWS** | JSON Web Signature — the underlying signing standard JWTs use. |
| **JWT** | JSON Web Token — a compact, signed token format. |
| **VC-JWT shape** | A JWT whose payload carries a `vc` claim wrapping `credentialSubject` and a `type` field. Resembles a W3C Verifiable Credential without claiming strict W3C compliance. |
| **JWKS** | JSON Web Key Set — a JSON document at `/.well-known/jwks.json` listing a service's public keys for signature verification. |
| **`kid`** | Key identifier — the header field naming which key in the JWKS to use. |
| **`jti`** | JWT ID — unique identifier of a single contract. |
| **`order_id`** | Opaque UUID assigned by Checkout that ties sibling sub-contracts together across nodes. |
| **EdDSA** | Edwards-curve Digital Signature Algorithm. Specifically Ed25519 for this design. |
| **DCAT-AP** | Data Catalog Vocabulary — Application Profile. The JSON-LD format describing catalog items in the platform. |
| **12-factor app** | A widely adopted set of best practices for building cloud-native services. The relevant principle here: configuration in environment variables, secrets in secret managers. |
| **Pydantic Settings** | The Python library convention for binding a Settings class to environment variables with validation. |
| **OpenTelemetry / OTel** | The observability standard for traces, metrics, and logs. The `OTEL_*` env vars are vendor-neutral and not service-prefixed. |

---

*End of document.*
