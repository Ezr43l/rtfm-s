#!/usr/bin/env bash
set -euo pipefail

PYTHON_IMAGE="python:3.12-alpine@sha256:d09d15e60962ca365d1cd544a48773bac9d33f2fb1b00f2aa0deec78ade7dc31"
PIP_TOOLS_VERSION="7.5.2"
MODE="${1:---check}"
case "$MODE" in
  --check|--write) ;;
  *) echo "Uso: $0 [--check|--write]" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/requirements.txt"
test -f "$ROOT/requirements.lock"
test ! -L "$ROOT/requirements.txt"
test ! -L "$ROOT/requirements.lock"
TEMP="$(mktemp -d "${TMPDIR:-/tmp}/rtfm-requirements.XXXXXXXX")"
cleanup() {
  case "$TEMP" in
    "${TMPDIR:-/tmp}"/rtfm-requirements.*) rm -rf -- "$TEMP" ;;
  esac
}
trap cleanup EXIT INT TERM

docker_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}

MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 \
  -e PIP_INDEX_URL=https://pypi.org/simple \
  -e PIP_EXTRA_INDEX_URL= \
  -v "$(docker_path "$ROOT"):/src:ro" \
  -v "$(docker_path "$TEMP"):/out" \
  "$PYTHON_IMAGE" sh -c '
    set -eu
    python -m pip install --disable-pip-version-check -q "pip-tools=='"$PIP_TOOLS_VERSION"'"
    pip-compile --quiet --resolver=backtracking --generate-hashes --strip-extras \
      --no-header --no-annotate --no-emit-index-url --no-emit-trusted-host \
      --output-file=/out/requirements.lock /src/requirements.txt
  '
test -s "$TEMP/requirements.lock"

if test "$MODE" = "--check"; then
  cmp "$TEMP/requirements.lock" "$ROOT/requirements.lock" || {
    echo "requirements.lock no es la salida reproducible esperada" >&2
    exit 1
  }
  echo "requirements.lock reproducible: OK"
else
  cp "$TEMP/requirements.lock" "$ROOT/requirements.lock"
  echo "requirements.lock actualizado"
fi
