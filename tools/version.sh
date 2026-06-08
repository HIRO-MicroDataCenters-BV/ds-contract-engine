#!/usr/bin/env bash
# Versioning + chart patching for a single sub-service of ds-contract-engine.
#
# Usage:
#   ./tools/version.sh <docker-image-name> <service-name>
#
# Example:
#   ./tools/version.sh ghcr.io/hiro-microdatacenters-bv/ds-contract-generator contract-generator
#
# Adapted from ds-catalog/tools/version.sh. The only structural change is that
# the chart path is parameterised by service name because this repo hosts
# three sub-services under ./server/<service>/.

set -o errexit
set -o nounset

ROOT="${GITHUB_WORKSPACE}"
CHART_NAME="server"

VERSION_APP_PATH="./VERSION_APP"
VERSION_CHART_PATH="./VERSION_CHART"
VERSION_DOCKER_PATH="./VERSION_DOCKER"
DOCKER_IMAGES_PATH="./DOCKER_IMAGES"

make_version() {
  GIT_SHA=$(git log -1 --pretty=%H)
  SHORT_SHA=$(echo "$GIT_SHA" | cut -c1-8)

  VERSION_BASE_HASH=$(git log --follow -1 --pretty=%H VERSION)
  VERSION_BASE=$(cat VERSION)
  GIT_COUNT=$(git rev-list --count "$VERSION_BASE_HASH"..HEAD)

  BRANCH=${GITHUB_HEAD_REF:-${GITHUB_REF##*/}}
  TAG=$( [[ $GITHUB_REF == refs/tags/* ]] && echo "${GITHUB_REF##refs/tags/}" || echo "" )

  echo "GIT_SHA: $GIT_SHA"
  echo "SHORT_SHA: $SHORT_SHA"
  echo "BRANCH: $BRANCH"
  echo "TAG: $TAG"
  echo "VERSION_BASE_HASH: $VERSION_BASE_HASH"
  echo "VERSION_BASE: $VERSION_BASE"
  echo "GIT_COUNT: $GIT_COUNT"

  if [[ "$TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    VERSION_APP="$TAG"
    VERSION_CHART="$TAG"
    VERSION_DOCKER="$TAG,${TAG}-${SHORT_SHA}"
  else
    BRANCH_TOKEN=$(echo "${BRANCH//[^a-zA-Z0-9-_.]/-}" | cut -c1-16 | sed -e 's/-$//')
    VERSION_APP="$VERSION_BASE+dev${GIT_COUNT}-${BRANCH_TOKEN}-${SHORT_SHA}"
    VERSION_CHART="$VERSION_BASE-dev.${GIT_COUNT}.${BRANCH_TOKEN}.${SHORT_SHA}"
    VERSION_DOCKER="$VERSION_CHART"
  fi

  echo "APP VERSION: ${VERSION_APP}"
  echo "CHART VERSION: ${VERSION_CHART}"
  echo "DOCKER VERSIONS: ${VERSION_DOCKER}"

  echo -n "${VERSION_APP}"    > "${VERSION_APP_PATH}"
  echo -n "${VERSION_DOCKER}" > "${VERSION_DOCKER_PATH}"
  echo -n "${VERSION_CHART}"  > "${VERSION_CHART_PATH}"
}

make_docker_images_with_tags() {
  DOCKER_IMAGE_NAME="$1"
  DOCKER_IMAGE_TAGS=$(cat "${VERSION_DOCKER_PATH}")

  IFS=',' read -ra TAGS_ARRAY <<< "$DOCKER_IMAGE_TAGS"

  RESULT=""
  for TAG in "${TAGS_ARRAY[@]}"; do
    RESULT+="${DOCKER_IMAGE_NAME}:${TAG},"
  done
  RESULT=${RESULT%,}

  echo "DOCKER IMAGES WITH TAGS: ${RESULT}"
  echo -n "${RESULT}" > "${DOCKER_IMAGES_PATH}"
}

patch_helm_chart() {
  DOCKER_IMAGE_NAME="$1"
  SERVICE_NAME="$2"

  CHART_PATH="./server/${SERVICE_NAME}/charts/${CHART_NAME}"

  DOCKER_IMAGE_TAG=$(rev "${VERSION_DOCKER_PATH}" | cut -d ',' -f 1 | rev)
  VERSION_CHART=$(cat "${VERSION_CHART_PATH}")

  sed -i "s#repository: \"\"#repository: \"$DOCKER_IMAGE_NAME\"#" "${CHART_PATH}/values.yaml"
  sed -i "s#tag: \"\"#tag: \"$DOCKER_IMAGE_TAG\"#" "${CHART_PATH}/values.yaml"
  sed -i "s#version: \"0.1.0\"#version: \"$VERSION_CHART\"#" "${CHART_PATH}/Chart.yaml"
  sed -i "s#appVersion: \"0.1.0\"#appVersion: \"$VERSION_CHART\"#" "${CHART_PATH}/Chart.yaml"
}

main() {
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <docker-image-name> <service-name>" >&2
    exit 1
  fi

  DOCKER_IMAGE_NAME="$1"
  SERVICE_NAME="$2"

  cd "$ROOT"

  make_version
  make_docker_images_with_tags "$DOCKER_IMAGE_NAME"
  patch_helm_chart "$DOCKER_IMAGE_NAME" "$SERVICE_NAME"
}

main "$@"
