#!/usr/bin/env bash
# End-to-end smoke test: mint a contract, then validate it.
#
# Prerequisites:
#   - Generator running on http://localhost:8082
#   - Validator running on http://localhost:8083 with DS__JWKS_BASE_URL_TEMPLATE
#     pointing at the local Generator
#   - jq installed
#
# Usage:
#   ./examples/end-to-end.sh

set -euo pipefail

GEN_URL="${GEN_URL:-http://localhost:8082}"
VAL_URL="${VAL_URL:-http://localhost:8083}"

echo "1) Mint contract via Generator"
RESPONSE=$(curl -s -X POST "${GEN_URL}/v1/contracts" \
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
    }')
TOKEN=$(echo "$RESPONSE" | jq -r '.token')
JTI=$(echo "$RESPONSE" | jq -r '.jti')
echo "   minted jti=${JTI}"

echo "2) Validate via Validator"
curl -s -X POST "${VAL_URL}/v1/validate" \
    -H "Content-Type: application/json" \
    -d "{\"token\": \"${TOKEN}\"}" | jq

echo "Done."
