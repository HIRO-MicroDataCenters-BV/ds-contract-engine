#!/usr/bin/env bash
# Generate an Ed25519 signing key for a Contract Generator and create the
# Kubernetes Secret the chart expects to mount.
#
# Usage:
#   ./deploy/scripts/generate-signing-key.sh <namespace> <node-id>
#
# Example:
#   ./deploy/scripts/generate-signing-key.sh nextgen hus.nextgen.hiro-develop.nl
#
# The resulting Secret is named ds-contract-generator-signing-key and contains
# one key: ed25519.pem (PEM-encoded PKCS8 private key).

set -euo pipefail

NAMESPACE="${1:-}"
NODE_ID="${2:-}"

if [[ -z "$NAMESPACE" || -z "$NODE_ID" ]]; then
    echo "Usage: $0 <namespace> <node-id>" >&2
    exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required" >&2
    exit 1
fi

TMP_KEY="$(mktemp)"
trap 'rm -f "$TMP_KEY"' EXIT

echo "Generating Ed25519 keypair for node $NODE_ID"
openssl genpkey -algorithm Ed25519 -out "$TMP_KEY"

echo "Ensuring namespace $NAMESPACE exists"
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
    || kubectl create namespace "$NAMESPACE"

SECRET_NAME="ds-contract-generator-signing-key"

echo "Creating/updating Secret $SECRET_NAME in $NAMESPACE"
kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
    --from-file=ed25519.pem="$TMP_KEY" \
    --dry-run=client -o yaml \
    | kubectl apply -f -

echo
echo "Done. The signing key has been mounted as Secret '$SECRET_NAME'."
echo "Make sure the Generator chart's values use:"
echo "  contractGenerator.signingKeyId: \"$NODE_ID#key-1\""
echo "  contractGenerator.nodeId:       \"$NODE_ID\""
