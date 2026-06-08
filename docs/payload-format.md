# Contract Engine — Payload Format

**Status:** Locked for v1 implementation
**Scope:** The JWT token shape used by the Contract Generator and Validator
**Date:** 2026-04-23

---

## In short

A Contract Engine token is a signed JWT — three base64url parts joined by dots. The payload uses a **VC-JWT shape** (the W3C Verifiable Credential pattern) but **without** the JSON-LD `@context` strictness, so plain JOSE libraries are sufficient.

Two versions are described:

- **v1** — the locked POC format. No `policy` block. Validation gates on signature, audience, expiry, registration in the Clearing House, and catalog hash.
- **v2** — adds an optional structured `policy` block (`action`, `purpose`, `allowedRegions`, `isShared`). Backward-compatible — v1 tokens stay valid forever.

This document is the field-level reference. For the design rationale see the research doc; for runtime behaviour, environment variables, and upstream service contracts see the payload spec doc.

---

## Table of contents

1. [Token structure](#1-token-structure)
2. [Header](#2-header)
3. [Payload — v1 (locked)](#3-payload--v1-locked)
4. [Payload — v2 (forward-compatible)](#4-payload--v2-forward-compatible)
5. [Field origins](#5-field-origins)
6. [Worked example — HUS dataset](#6-worked-example--hus-dataset)
7. [v1 vs v2 — what changes](#7-v1-vs-v2--what-changes)
8. [Glossary](#glossary)

---

## 1. Token structure

On the wire, a token is one compact string:

```
<base64url(header)>.<base64url(payload)>.<base64url(signature)>
```

Three base64url-encoded parts joined by dots. Standard JWT — any JOSE library can parse it without special handling.

- **Signing algorithm:** **EdDSA** (Ed25519). Matches the platform's identity layer.
- **Public key discovery:** each provider node hosts `/.well-known/jwks.json`. The Validator reads the token's `kid` header to know which key to fetch and from where.

---

## 2. Header

```json
{
  "alg": "EdDSA",
  "typ": "JWT",
  "kid": "hus.nextgen.hiro-develop.nl#key-1"
}
```

| Field | Required | Description |
|---|---|---|
| `alg` | yes | Always `EdDSA`. |
| `typ` | yes | Always `JWT`. |
| `kid` | yes | Key identifier — `<provider_node_id>#<key_version>`. The Validator uses this to fetch the matching public key from the issuing node's JWKS endpoint. |

---

## 3. Payload — v1 (locked)

The complete payload a token will carry in v1:

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

### Outer JWT envelope

| Field | Required | Type | Description |
|---|---|---|---|
| `jti` | yes | UUIDv4 | Unique contract identifier. Generated fresh per token. Used by the Clearing House for registration / revocation lookup. |
| `iss` | yes | string | Issuer — the provider node's identity. Always equal to `NODE_ID`. |
| `aud` | yes | string | Audience — also equal to `NODE_ID`. **Validator rejects if `aud` does not match its own node identity.** Misrouted tokens fail with no coordination needed. |
| `sub` | yes | string | Subject — the consumer (researcher) identifier. |
| `iat` | yes | integer | Issued-at Unix timestamp. |
| `exp` | yes | integer | Expiry Unix timestamp. Equals `iat + ttl_seconds`, where TTL matches the Checkout order's lifetime. |
| `order_id` | yes | UUIDv4 | The opaque order identifier from Checkout. Same value across all sibling sub-contracts in the bundle. The audit-correlation key. |
| `vc` | yes | object | Wrapper for the VC-shaped fields. See below. |

### `vc` claim

| Field | Required | Description |
|---|---|---|
| `vc.type` | yes | Always `["NextGenContract"]` in v1. Static constant. |
| `vc.credentialSubject` | yes | The body of the contract — see below. |

### `credentialSubject` fields

`credentialSubject` carries only what is contract-specific. The consumer identity comes from the outer `sub` claim; the provider node identity comes from the outer `iss` / `aud` claims. No duplicated identifiers inside `credentialSubject`.

| Field | Required | Description |
|---|---|---|
| `catalogItem` | yes | Array of catalog items granted by this contract. **Per-node aggregation** — all selected items on this node fit in one token. |

### `catalogItem` element

| Field | Required | Description |
|---|---|---|
| `id` | yes | Catalog item URI — comes from the DCAT-AP record's `@id`. |
| `identifier` | yes | Short identifier — DCAT `dcterms:identifier`. |
| `title` | yes | Human-readable title — DCAT `dcterms:title`. |
| `hash` | yes | `sha256:<hex>` of the primary distribution. Used to detect tampering between mint time and access time. |

---

## 4. Payload — v2 (forward-compatible)

v2 adds a single optional field — `vc.credentialSubject.policy` — that captures a structured snapshot of the contract's terms at mint time.

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

### `policy` field reference (v2 only)

| Field | Required | Type | Origin (natural source) |
|---|---|---|---|
| `policy.action` | yes | string | **Consumer request** — declared intent (`train`, `infer`). |
| `policy.purpose` | yes | string | **Consumer request** — declared intent (`federated-learning`). |
| `policy.allowedRegions` | yes | string array | **Catalog item metadata** — the regions where the data may be used. |
| `policy.isShared` | yes | boolean | **Catalog item metadata** — whether the items are part of a shared / public-research pool. |

### Why `policy` is a merged view (and not a Policy Engine snapshot)

The Policy Engine endpoint (`POST /api/v1/policies/evaluate`) returns `{permissions: [...]}` — a flat list of permission strings keyed off `role + institute`. This is the right shape for the *gate decision* ("is this researcher allowed?"), but **not** the right shape for the contract's structured policy fields, because:

- `action` and `purpose` are **consumer-declared intents** — the consumer knows what they want to do; the Policy Engine confirms they are allowed.
- `allowedRegions` is **intrinsic to the catalog item** — a property of where the data is owned and may be used.
- `isShared` is also **intrinsic to the catalog item** — a property of the data, not of any policy decision about it.

So in v2, the Policy Engine's role is a **gate**: the Generator calls `/evaluate`, checks for the required permission string in the response (e.g. `data_train`), and if present, mints a token with the structured `policy` block populated from the merged sources above. If the required permission is absent, the mint is refused.

This keeps the integration thin — no Policy Engine API change required — and keeps each field at its natural source.

---

## 5. Field origins

Where every value comes from at runtime.

### Computed fresh per contract (Generator runtime)

| Field | How |
|---|---|
| `jti` | `uuid.uuid4()` at mint time. |
| `iat` | `int(time.time())` at mint time. |
| `exp` | `iat + ttl_seconds`. TTL from the Checkout request, or node default. |

### From node configuration

| Field | Source |
|---|---|
| `iss`, `aud` | Both equal to `NODE_ID` env var. |

### From the Checkout request

| Field | Notes |
|---|---|
| `sub` | Consumer identifier — flows from Marketplace auth context through Checkout. |
| `order_id` | Opaque UUID Checkout generates before fanning out to per-node Generators. Same across siblings. |

### From DCAT-AP catalog metadata (passed via Checkout)

| Field | DCAT source |
|---|---|
| `catalogItem[].id` | `@id` |
| `catalogItem[].identifier` | `dcterms:identifier` |
| `catalogItem[].title` | `dcterms:title` |
| `catalogItem[].hash` | `spdx:checksum` (or computed at enrichment time) |

### From the consumer request — v2 only

| Field | Notes |
|---|---|
| `policy.action` | What the consumer is asking to do. |
| `policy.purpose` | Why the consumer is asking. |

### From catalog metadata — v2 only

| Field | Notes |
|---|---|
| `policy.allowedRegions` | Region constraint declared on the catalog item. |
| `policy.isShared` | Boolean flag from the catalog item. |

### From the Policy Engine — v2 only (gate, not stored)

The Policy Engine response (`{permissions: [...]}`) is **checked but not stored**. It acts purely as an allow/deny gate at mint time. If the required permission string is present, the mint proceeds; otherwise it is refused.

### Static constants in Generator code

| Field | Value |
|---|---|
| `alg` (header) | `EdDSA` |
| `typ` (header) | `JWT` |
| `vc.type` | `["NextGenContract"]` |

---

## 6. Worked example — HUS dataset

Following one v1 contract for the HUS GWAS dataset.

### Inputs

- Researcher: `researcher-sai-kireeti`
- Selected dataset: `synthetic_dataset_test_2907` (HUS node)
- `order_id` from Checkout: `9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4`
- TTL: 3600 seconds (1 hour)
- Mint moment: `2026-04-23T12:00:00Z` → Unix `1745409600`

### Decoded payload

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

### On the wire (compact form)

```
eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCIsImtpZCI6Imh1cy5uZXh0Z2VuLmhpcm8tZGV2ZWxvcC5ubCNrZXktMSJ9
.
eyJqdGkiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAi...
.
3Rp4k9F8nQ2mVxT7bYcLzA8fW2eK5mN1pR7sX9jQ0vZ8a
```

A single base64url-encoded string with three dot-separated chunks. This is what Checkout returns to the consumer as one element of the `tokens` array, alongside the matching `order_id`.

---

## 7. v1 vs v2 — what changes

| Concern | v1 | v2 |
|---|---|---|
| All outer JWT claims (`jti`, `iss`, `aud`, `sub`, `iat`, `exp`, `order_id`) | Same | Same |
| `vc.type` | `["NextGenContract"]` | `["NextGenContract"]` |
| `credentialSubject.catalogItem[]` | Same | Same |
| `vc.credentialSubject.policy` | **Absent** | **Present** — `{action, purpose, allowedRegions, isShared}` |
| Generator → Policy Engine | Not called | Called once as a **gate** (allow/deny). Response checked but not stored. |
| Generator → Catalog Service | Not called (Checkout pre-enriches) | Not called (Checkout pre-enriches) |
| Validator → Policy Engine | Not called | Not called — mid-session policy changes propagate via Clearing House revocation |
| Backward compatibility | — | A v2 Validator accepts a v1 token by treating absent `policy` as "no constraint declared". v1 tokens issued before v2 launches stay valid forever. |

The change is purely **additive**. Existing v1 tokens never need to be reissued.

---

## Glossary

| Term | Plain meaning |
|---|---|
| **JWT** (JSON Web Token) | A compact, signed token format. Three base64url-encoded parts joined by dots: header, payload, signature. |
| **JWS** (JSON Web Signature) | The signing standard JWTs use. |
| **JWKS** (JSON Web Key Set) | The JSON document at `/.well-known/jwks.json` listing a node's public keys for signature verification. |
| **VC-JWT shape** | A JWT whose payload includes a `vc` claim wrapping a `credentialSubject` object and a `type` field. Resembles a W3C Verifiable Credential without claiming strict W3C compliance. |
| **`kid`** | Key identifier — the header field naming which key in the JWKS to use. |
| **`jti`** | JWT ID — the unique identifier of a single contract. |
| **`order_id`** | Opaque UUID assigned by Checkout that ties sibling sub-contracts together across nodes. |
| **EdDSA** | Edwards-curve Digital Signature Algorithm. Specifically Ed25519 for this design. |
| **DCAT-AP** | Data Catalog Vocabulary — Application Profile. The JSON-LD format used to describe catalog items in the platform. |
| **Per-node aggregation** | One token per provider node, bundling all of that node's items. Not one token per item. |
| **Policy Engine as gate** | In v2, the Policy Engine is called once at mint time to allow or deny. Its response is a flat permissions list and is **not stored** in the token. |

---

*End of document.*
