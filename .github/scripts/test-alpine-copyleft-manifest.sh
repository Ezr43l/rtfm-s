#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
validator="$root/.github/scripts/validate-alpine-copyleft-manifest.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/rtfm-manifest-test.XXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT

valid="$work/valid.tsv"
for origin in ca-certificates git iproute2; do
  printf 'linux/amd64,linux/arm64\t%s\t%s\t%s\t%s\t%s\n' \
    "$origin" 0123456789abcdef0123456789abcdef01234567 "$origin" 1.0 GPL-2.0-only
done > "$valid"
bash "$validator" "$valid" >/dev/null

head -n 2 "$valid" > "$work/missing.tsv"
if bash "$validator" "$work/missing.tsv" >/dev/null 2>&1; then
  echo 'validator accepted a manifest without iproute2' >&2
  exit 1
fi

sed 's#linux/amd64,linux/arm64#linux/amd64#' "$valid" > "$work/platform.tsv"
if bash "$validator" "$work/platform.tsv" >/dev/null 2>&1; then
  echo 'validator accepted the wrong platform set' >&2
  exit 1
fi

printf '%s\n' 'Alpine copyleft manifest validator tests: OK'
