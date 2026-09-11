#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VERSION="$(tr -d ' \r\n' < VERSION)"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-rtfm}"
IMAGE="${IMAGE_REPOSITORY}:${VERSION}"
SOURCE_URL="${SOURCE_URL:-https://github.com/Ezr43l/rtfm-s}"
LICENSE_SPDX="${LICENSE_SPDX:-Apache-2.0}"
PUBLISH="${PUBLISH:-false}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
VCS_REF="$(git rev-parse --short=12 HEAD 2>/dev/null || printf unknown)"

common=(
  --pull
  --file Dockerfile
  --build-arg "VERSION=$VERSION"
  --build-arg "SOURCE_URL=$SOURCE_URL"
  --build-arg "LICENSE=$LICENSE_SPDX"
  --build-arg "BUILD_DATE=$BUILD_DATE"
  --build-arg "VCS_REF=$VCS_REF"
  --tag "$IMAGE"
)

if [[ "$PUBLISH" == "true" ]]; then
  if [[ "$IMAGE_REPOSITORY" != */* ]]; then
    echo "Para publicar, IMAGE_REPOSITORY debe incluir un registro o namespace." >&2
    exit 2
  fi
  docker buildx build "${common[@]}" --platform "$PLATFORMS" --push .
  echo "Imagen multi-arquitectura publicada: $IMAGE ($PLATFORMS)"
else
  docker buildx build "${common[@]}" --load .
  echo "Imagen local construida y probada: $IMAGE"
fi
