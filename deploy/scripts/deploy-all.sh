#!/usr/bin/env bash
# Deploy the full Contract Engine stack (generator, validator, stub CH) into one
# namespace using helm.
#
# Usage:
#   ./deploy/scripts/deploy-all.sh <namespace> <node-short-name> <registry> <tag>
#
# Example:
#   ./deploy/scripts/deploy-all.sh nextgen hus registry.nextgen.hiro-develop.nl 0.1.0
#
# Requires:
#   - kubectl context set to the target cluster
#   - helm v3
#   - Images already pushed to <registry>
#   - Signing key Secret already created via generate-signing-key.sh

set -euo pipefail

NAMESPACE="${1:-}"
NODE_SHORT="${2:-}"
REGISTRY="${3:-}"
TAG="${4:-0.1.0}"

if [[ -z "$NAMESPACE" || -z "$NODE_SHORT" || -z "$REGISTRY" ]]; then
    echo "Usage: $0 <namespace> <node-short-name> <registry> <tag>" >&2
    echo "  e.g. $0 nextgen hus registry.nextgen.hiro-develop.nl 0.1.0" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VALUES_DIR="${ROOT}/deploy/values"

ch_values="${VALUES_DIR}/${NODE_SHORT}-clearing-house.yaml"
gen_values="${VALUES_DIR}/${NODE_SHORT}-generator.yaml"
val_values="${VALUES_DIR}/${NODE_SHORT}-validator.yaml"

for f in "$ch_values" "$gen_values" "$val_values"; do
    if [[ ! -f "$f" ]]; then
        echo "Missing values file: $f" >&2
        echo "Copy deploy/values/hus-*.yaml to ${NODE_SHORT}-*.yaml and adjust." >&2
        exit 1
    fi
done

echo "--- Deploying ds-clearing-house-stub ---"
helm upgrade --install ds-clearing-house-stub \
    "${ROOT}/server/clearing-house-stub/charts/server" \
    -n "$NAMESPACE" --create-namespace \
    -f "$ch_values" \
    --set image.repository="${REGISTRY}/ds-clearing-house-stub" \
    --set image.tag="$TAG" \
    --wait

echo "--- Deploying ds-contract-generator ---"
helm upgrade --install ds-contract-generator \
    "${ROOT}/server/contract-generator/charts/server" \
    -n "$NAMESPACE" \
    -f "$gen_values" \
    --set image.repository="${REGISTRY}/ds-contract-generator" \
    --set image.tag="$TAG" \
    --wait

echo "--- Deploying ds-contract-validator ---"
helm upgrade --install ds-contract-validator \
    "${ROOT}/server/contract-validator/charts/server" \
    -n "$NAMESPACE" \
    -f "$val_values" \
    --set image.repository="${REGISTRY}/ds-contract-validator" \
    --set image.tag="$TAG" \
    --wait

echo
echo "All three services deployed in namespace $NAMESPACE."
kubectl -n "$NAMESPACE" get pods -l 'app.kubernetes.io/name in (ds-contract-generator,ds-contract-validator,ds-clearing-house-stub)'
