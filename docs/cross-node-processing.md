# Cross-node request processing

**Status:** Implementation reference
**Date:** 2026-06-24

This note explains how the Contract Engine handles requests and tokens that cross node boundaries inside a federated NextGen deployment. It maps each scenario to the exact code path that enforces it.

---

## In short

A node's Generator only signs for **its own data**. A node's Validator only honours tokens **issued for its own node**. Tokens are scoped to one node by `aud`; they don't travel between nodes for validation. Caller-level authentication (who is allowed to call the API at all) is a platform-level concern not yet wired into the services.

---

## Three scenarios, three behaviours

### Scenario A — Generator receives a mint request whose items belong to another node

**Example:** Checkout (or some other caller) sends `POST /v1/contracts` to Node A's Generator with `items: [{ "id": "http://node-b/dataset", ... }]`.

**Code path:** `app/core/usecases.py::_verify_node_ownership`.

The Generator parses every item's `id` as a URI, takes the `host`, and compares to its own `NODE_ID`. Mismatch raises `WrongNodeError`, which the REST layer turns into **HTTP 400** with a descriptive `detail`. A `WARNING` log line records the rejected attempt:

```
contract.refused.cross_node consumer=<id> order_id=<id>
  item_id=<id> item_host=<host> this_node=<NODE_ID>
```

**Outcome:** the Generator never signs for other nodes' data. Each node remains the sole authority for the items it owns.

### Scenario B — Validator receives a token signed by another node's Generator

**Example:** A researcher (or a misrouted Connector call) presents a token to Node A's Validator where the token was minted by Node B's Generator. The token has `iss=node-b`, `aud=node-b`.

**Code path:** `app/core/usecases.py::ValidateContractUsecase.execute`.

The Validator:

1. Decodes the (unverified) header to extract `kid` and the (unverified) payload's `iss`.
2. Fetches JWKS from the issuing node (`https://node-b/.well-known/jwks.json`) to retrieve the public key for `kid`.
3. Runs full `jwt.decode(...)` with `audience=self._node_id`.

Step 3 raises `InvalidAudienceError` because `aud=node-b` ≠ Validator A's `NODE_ID=node-a`. The Validator returns `allow=false` and logs:

```
contract.refused.cross_node iss=<node-b> kid=<...> this_node=<NODE_ID>
  reason=audience_mismatch
```

**Outcome:** a token issued by one node is never validated by another node, even though signature verification would succeed (the JWKS lookup works and the key is genuine). The `aud` claim is the strict scoping primitive.

### Scenario C — The HTTP call itself comes from an unauthenticated caller

**Example:** Someone reaches the Generator's `/v1/contracts` endpoint over the network and sends a well-formed body with `host=NODE_ID`.

**Code path:** none currently. There is **no caller-level authentication** on either service's REST API in v1.

The trust the system holds is anchored at:

- **Data identity** — item URLs are checked against `NODE_ID` (Scenario A).
- **Token scoping** — `aud` claim enforced (Scenario B).
- **Token integrity** — signed with Ed25519, verified via JWKS published by the claimed issuer.

The trust the system **does not yet hold** is anchored at the caller. A misbehaving or rogue Checkout could submit requests with valid item URLs, and the Generator would mint. Defences against that belong at the platform edge (mTLS between services, a gateway with token-based caller auth, or both). See [`contract-engine-payload-spec.md`](contract-engine-payload-spec.md) §12 for the open question.

---

## What this design buys us

| Property | Mechanism |
|---|---|
| **Federation autonomy** — each node controls its own data | `_verify_node_ownership` + `aud` |
| **No federation-level root of trust** | Each node has its own signing key; JWKS published per node |
| **No cross-node token replay** | `aud` scoping + per-node Clearing House registration |
| **Tamper-evidence** | Ed25519 signature over the full payload |
| **Revocation without token recall** | Clearing House status check on every validate |

## What this design does not buy us, and where the gap is closed

| Open concern | Where it is closed |
|---|---|
| Caller-identity authentication on the API | Platform edge — mTLS / gateway auth (out of this repo) |
| Catalog item integrity | Hash check on `catalogItem[].hash` at validation time |
| Live policy changes mid-session | Revocation via Clearing House `PATCH /v1/contracts/{jti}/status` |
| Compromised signing key | Key rotation via the signing-key service; old `kid` retires from JWKS |

---

## Where to look in the code

| Concern | File |
|---|---|
| Item-host check (Generator) | `server/contract-generator/app/core/usecases.py::_verify_node_ownership` |
| Audience check (Validator) | `server/contract-validator/app/core/usecases.py` |
| JWKS fetch (Validator) | `server/contract-validator/app/adapters/jwks_resolver.py` |
| Token shape | `server/contract-{generator,validator}/app/core/entities.py::ContractPayload` |
| Per-node Clearing House URL | `deploy/values/*-{generator,validator}.yaml` |
