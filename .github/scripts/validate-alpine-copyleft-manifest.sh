#!/usr/bin/env bash
set -euo pipefail

manifest="${1:-}"
expected_platforms="${2:-linux/amd64,linux/arm64}"
test -n "$manifest" || { echo 'usage: validate-alpine-copyleft-manifest.sh MANIFEST [PLATFORMS]' >&2; exit 2; }
test -f "$manifest" && test ! -L "$manifest" && test -s "$manifest"
[[ "$expected_platforms" =~ ^linux/(amd64|arm64)(,linux/(amd64|arm64))?$ ]]

awk -F '\t' -v expected="$expected_platforms" '
  NF != 6 || $1 != expected ||
  $2 !~ /^[A-Za-z0-9+._-]+$/ ||
  length($3) != 40 || $3 !~ /^[0-9a-f]+$/ ||
  $4 == "" || $5 == "" || $6 == "" { exit 1 }
  END { if (NR == 0) exit 1 }
' "$manifest"

for origin in ca-certificates git iproute2; do
  awk -F '\t' -v expected="$expected_platforms" -v origin="$origin" '
    $1 == expected && $2 == origin { found = 1 }
    END { exit !found }
  ' "$manifest"
done

printf 'Alpine copyleft manifest: %s rows, required origins present\n' "$(wc -l < "$manifest" | tr -d ' ')"
