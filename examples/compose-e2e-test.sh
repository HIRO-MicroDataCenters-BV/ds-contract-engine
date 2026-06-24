#!/usr/bin/env bash
# End-to-end smoke test against the docker-compose stack.
#
# Prerequisites:
#   docker compose up -d  (from repo root)
#
# Tests:
#   1) Mint a contract for a local item — expect 200
#   2) Validate the freshly minted token — expect allow=true
#   3) Mint a contract for a cross-node item — expect 400
#   4) Revoke the contract via stub CH PATCH; re-validate — expect allow=false
#   5) Validate a malformed token — expect allow=false (not 500)

set -uo pipefail

GEN=${GEN:-http://localhost:8082}
VAL=${VAL:-http://localhost:8083}
CH=${CH:-http://localhost:8084}
NODE_ID=${NODE_ID:-ds-contract-generator}

pass() { printf '✓ %s\n' "$1"; }
fail() { printf '✗ %s\n   %s\n' "$1" "${2:-}" ; exit 1; }

echo "===== 1) Mint contract for a local item ====="
RESP=$(curl -sS -X POST "$GEN/v1/contracts" \
  -H "Content-Type: application/json" \
  -d "{
    \"consumer_id\": \"researcher-test\",
    \"order_id\": \"e2e-order-001\",
    \"ttl_seconds\": 600,
    \"items\": [{
      \"id\": \"https://${NODE_ID}/dataset-e2e-1\",
      \"identifier\": \"dataset_e2e_1\",
      \"title\": \"E2E test dataset\",
      \"hash\": \"sha256:$(printf 'a%.0s' {1..64})\"
    }]
  }")
TOKEN=$(echo "$RESP" | python -c 'import json,sys; print(json.load(sys.stdin).get("token",""))')
JTI=$(echo "$RESP" | python -c 'import json,sys; print(json.load(sys.stdin).get("jti",""))')
if [ -z "$TOKEN" ] || [ -z "$JTI" ]; then
    fail "mint did not return a token" "$RESP"
fi
pass "minted jti=$JTI"

echo "===== 2) Validate the freshly minted token ====="
VRESP=$(curl -sS -X POST "$VAL/v1/validate" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN\"}")
ALLOW=$(echo "$VRESP" | python -c 'import json,sys; print(json.load(sys.stdin).get("allow",""))')
REASON=$(echo "$VRESP" | python -c 'import json,sys; print(json.load(sys.stdin).get("reason",""))')
if [ "$ALLOW" != "True" ]; then
    fail "validation did not allow" "$VRESP"
fi
pass "validation allowed"

echo "===== 3) Mint contract for a cross-node item — expect refusal ====="
CODE=$(curl -sS -o /tmp/cross.json -w "%{http_code}" -X POST "$GEN/v1/contracts" \
  -H "Content-Type: application/json" \
  -d "{
    \"consumer_id\": \"researcher-test\",
    \"order_id\": \"e2e-order-002\",
    \"items\": [{
      \"id\": \"https://some-other-node.example.org/dataset-x\",
      \"identifier\": \"dataset_x\",
      \"title\": \"Cross-node dataset\",
      \"hash\": \"sha256:$(printf 'b%.0s' {1..64})\"
    }]
  }")
if [ "$CODE" != "400" ]; then
    fail "expected 400 for cross-node mint, got $CODE" "$(cat /tmp/cross.json)"
fi
pass "cross-node mint refused (400)"

echo "===== 4) Revoke contract via stub CH, then re-validate — expect deny ====="
PATCH_CODE=$(curl -sS -o /tmp/patch.json -w "%{http_code}" -X PATCH \
  "$CH/v1/contracts/${JTI}/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "revoked"}')
if [ "$PATCH_CODE" != "200" ]; then
    fail "expected 200 on status patch, got $PATCH_CODE" "$(cat /tmp/patch.json)"
fi
VRESP2=$(curl -sS -X POST "$VAL/v1/validate" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN\"}")
ALLOW2=$(echo "$VRESP2" | python -c 'import json,sys; print(json.load(sys.stdin).get("allow",""))')
REASON2=$(echo "$VRESP2" | python -c 'import json,sys; print(json.load(sys.stdin).get("reason",""))')
if [ "$ALLOW2" != "False" ]; then
    fail "revoked token still validated as allow=$ALLOW2" "$VRESP2"
fi
pass "revoked token denied: $REASON2"

echo "===== 5) Validate a malformed token — expect graceful deny ====="
VRESP3=$(curl -sS -X POST "$VAL/v1/validate" \
  -H "Content-Type: application/json" \
  -d '{"token": "not.a.real.jwt"}')
ALLOW3=$(echo "$VRESP3" | python -c 'import json,sys; print(json.load(sys.stdin).get("allow",""))')
if [ "$ALLOW3" != "False" ]; then
    fail "malformed token did not gracefully deny" "$VRESP3"
fi
pass "malformed token denied"

echo
echo "All checks passed."
