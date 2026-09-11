#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
mock_bin="$test_root/bin"
mkdir -p "$mock_bin"
trap 'rm -rf -- "$test_root"' EXIT

cat > "$mock_bin/findmnt" <<'MOCK'
#!/usr/bin/env bash
printf '%s' "${MOCK_MOUNTS:-}"
MOCK
chmod 0755 "$mock_bin/findmnt"

export PATH="$mock_bin:$PATH"
export RTFM_MIGRATION_LIBRARY_ONLY=true
# shellcheck disable=SC1091
source "$repo_root/scripts/migrate-data-uid.sh"

expect_tree_rejection() {
  local name="$1" tree="$2"
  if (assert_safe_tree "$tree") >/dev/null 2>&1; then
    printf 'se esperaba rechazo del arbol: %s\n' "$name" >&2
    exit 1
  fi
}

valid="$test_root/valid"
mkdir "$valid"
printf 'safe\n' > "$valid/document.md"
MOCK_MOUNTS='' assert_safe_tree "$valid"

outside="$test_root/outside"
hardlinks="$test_root/hardlinks"
mkdir "$outside" "$hardlinks"
printf 'shared\n' > "$outside/shared"
ln "$outside/shared" "$hardlinks/linked-outside"
expect_tree_rejection hardlink "$hardlinks"
test "$(stat -c %u:%g "$outside/shared")" = "$(id -u):$(id -g)"

special="$test_root/special"
mkdir "$special"
mkfifo "$special/persistent.pipe"
expect_tree_rejection fifo "$special"

nested="$test_root/nested"
mkdir -p "$nested/mounted"
export MOCK_MOUNTS="$nested/mounted"$'\n'
expect_tree_rejection nested-mount "$nested"

unset MOCK_MOUNTS
strict_child_of "$valid" "$test_root"
if strict_child_of "$test_root" "$test_root"; then
  echo 'la raiz permitida no puede ser el propio destino' >&2
  exit 1
fi

grep -Fq 'RTFM_ALL_NODES_STOPPED' "$repo_root/scripts/migrate-data-uid.sh"
grep -Fq 'phase backup-ready' "$repo_root/scripts/migrate-data-uid.sh"
grep -Fq 'phase rolled-back' "$repo_root/scripts/migrate-data-uid.sh"

printf 'data uid migration safety tests: OK\n'
