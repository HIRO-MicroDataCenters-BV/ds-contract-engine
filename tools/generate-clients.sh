#!/usr/bin/env bash
# Regenerate Python client SDKs from the OpenAPI specs.
#
# Usage:
#   ./tools/generate-clients.sh                    # both services
#   ./tools/generate-clients.sh contract-generator # one service
#
# Requires: openapi-generator-cli (https://openapi-generator.tech)
#   brew install openapi-generator
#   or
#   docker run --rm openapitools/openapi-generator-cli ...

set -euo pipefail

SERVICES=("${@:-contract-generator contract-validator}")
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for service in $SERVICES; do
    spec="${ROOT}/api/${service}/openapi.yaml"
    out="${ROOT}/client/${service}"
    pkg="ds_${service//-/_}"

    if [[ ! -f "$spec" ]]; then
        echo "Spec not found: $spec" >&2
        exit 1
    fi

    echo "Generating ${pkg} from ${spec} into ${out}"
    openapi-generator-cli generate \
        -i "$spec" \
        -g python \
        -o "$out" \
        --package-name "$pkg" \
        --additional-properties=projectName=ds-${service},packageVersion=0.1.0
done

echo "Done."
