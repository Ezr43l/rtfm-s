#!/usr/bin/env bash
set -euo pipefail

readonly TARGET_UID=10001
readonly TARGET_GID=10001

die() {
  printf 'rtfm-uid-migration: ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "falta el comando requerido: $1"
}

require_root() {
  test "$(id -u)" -eq 0 || die 'esta operacion debe ejecutarse como root'
}

require_safe_text() {
  local name="$1" value="$2"
  test -n "$value" || die "$name no puede estar vacio"
  case "$value" in
    *$'\n'*|*$'\r'*|*$'\t'*) die "$name contiene caracteres de control" ;;
  esac
}

strict_child_of() {
  local child="$1" parent="$2"
  test "$child" != "$parent" || return 1
  case "$child/" in
    "$parent"/*/) return 0 ;;
    *) return 1 ;;
  esac
}

discover_data_mount() { # <container>; writes globals
  local container="$1"
  local -a sources=() types=()
  mapfile -t sources < <(
    docker inspect "$container" \
      --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{println .Source}}{{end}}{{end}}'
  )
  mapfile -t types < <(
    docker inspect "$container" \
      --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{println .Type}}{{end}}{{end}}'
  )
  test "${#sources[@]}" -eq 1 || die 'el contenedor debe tener exactamente un mount en /data'
  test "${#types[@]}" -eq 1 || die 'no se pudo determinar el tipo unico del mount /data'
  test "${types[0]}" = bind || die 'la migracion automatica sólo admite un bind mount'
  require_safe_text 'origen de /data' "${sources[0]}"
  DATA_SOURCE="${sources[0]}"
  test ! -L "$DATA_SOURCE" || die 'el origen de /data es un enlace simbolico'
  DATA_PATH="$(readlink -f -- "$DATA_SOURCE")"
  test -d "$DATA_PATH" || die 'la ruta real de /data no es un directorio'
  test "$DATA_SOURCE" = "$DATA_PATH" || die 'la ruta de /data atraviesa un enlace simbolico'
  CONTAINER_ID="$(docker inspect "$container" --format '{{.Id}}')"
  IMAGE_ID="$(docker inspect "$container" --format '{{.Image}}')"
  require_safe_text 'ID del contenedor' "$CONTAINER_ID"
  require_safe_text 'ID de imagen' "$IMAGE_ID"
}

assert_path_policy() { # <data-path> <allowed-root>
  local data_path="$1" allowed_root="$2" current
  current="$(readlink -f -- "$data_path")"
  test "$current" = "$data_path" || die 'la ruta de datos cambio o atraviesa un enlace'
  test -d "$data_path" || die 'la ruta de datos dejo de ser un directorio'
  test "$(readlink -f -- "$allowed_root")" = "$allowed_root" \
    || die 'la raiz permitida cambio o atraviesa un enlace'
  strict_child_of "$data_path" "$allowed_root" \
    || die 'la ruta de datos queda fuera de la raiz permitida o coincide con ella'
}

assert_no_nested_mounts() { # <data-path>
  local data_path="$1" mount_target resolved
  while IFS= read -r mount_target; do
    test -n "$mount_target" || continue
    resolved="$(readlink -f -- "$mount_target" 2>/dev/null || true)"
    test -n "$resolved" || continue
    if strict_child_of "$resolved" "$data_path"; then
      die "hay un mount anidado dentro de /data: $resolved"
    fi
  done < <(findmnt -rn -o TARGET)
}

assert_safe_tree() { # <data-path>
  local data_path="$1" unsafe
  unsafe="$(find "$data_path" -xdev ! -type d ! -type f -print -quit)"
  test -z "$unsafe" || die "tipo de fichero no permitido dentro de /data: $unsafe"
  unsafe="$(find "$data_path" -xdev -type f -links +1 -print -quit)"
  test -z "$unsafe" || die "hardlink no permitido dentro de /data: $unsafe"
  assert_no_nested_mounts "$data_path"
}

assert_no_local_writers() { # <data-path>
  local data_path="$1" container mount_source mount_destination running_source
  while IFS= read -r container; do
    test -n "$container" || continue
    while IFS=$'\t' read -r mount_source mount_destination; do
      test "$mount_destination" = /data || continue
      running_source="$(readlink -f -- "$mount_source" 2>/dev/null || true)"
      if test "$running_source" = "$data_path"; then
        die "el contenedor local $container sigue escribiendo sobre el mismo /data"
      fi
    done < <(
      docker inspect "$container" \
        --format '{{range .Mounts}}{{printf "%s\t%s\n" .Source .Destination}}{{end}}'
    )
  done < <(docker ps --quiet --no-trunc)
}

write_state() { # <state-dir> <name> <value>
  local state_dir="$1" name="$2" value="$3" temporary
  require_safe_text "$name" "$value"
  temporary="$state_dir/.${name}.$$"
  (umask 077; printf '%s\n' "$value" > "$temporary")
  chmod 0600 "$temporary"
  mv -f -- "$temporary" "$state_dir/$name"
}

read_state() { # <state-dir> <name>
  local state_dir="$1" name="$2" value
  test -f "$state_dir/$name" && test ! -L "$state_dir/$name" \
    || die "falta el campo de estado seguro: $name"
  {
    IFS= read -r value || true
    if IFS= read -r _; then
      die "el campo de estado $name contiene mas de una linea"
    fi
  } < "$state_dir/$name"
  require_safe_text "$name" "$value"
  printf '%s' "$value"
}

acquire_state_lock() { # <state-dir>
  local state_dir="$1"
  mkdir "$state_dir/operation.lock" 2>/dev/null \
    || die 'ya hay otra operacion usando este estado'
  trap 'rmdir -- "$STATE_DIR/operation.lock" 2>/dev/null || true' EXIT
}

assert_stopped_cluster() {
  test "${RTFM_ALL_NODES_STOPPED:-}" = yes \
    || die 'confirma la parada de todos los nodos con RTFM_ALL_NODES_STOPPED=yes'
}

prepare_state_directory() { # <new-state-dir> <data-path>
  local requested="$1" data_path="$2" parent resolved_parent expected
  case "$requested" in /*) ;; *) die '--state-dir debe ser una ruta absoluta' ;; esac
  parent="$(dirname -- "$requested")"
  resolved_parent="$(readlink -f -- "$parent")"
  test -d "$resolved_parent" || die 'el padre de --state-dir no existe'
  expected="$resolved_parent/$(basename -- "$requested")"
  test "$requested" = "$expected" || die '--state-dir atraviesa un enlace o no esta normalizado'
  test ! -e "$requested" && test ! -L "$requested" || die '--state-dir ya existe'
  strict_child_of "$requested" "$data_path" \
    && die '--state-dir no puede quedar dentro de /data'
  install -d -o 0 -g 0 -m 0700 -- "$requested"
  STATE_DIR="$requested"
  acquire_state_lock "$STATE_DIR"
}

revalidate_before_mutation() { # <container> <expected-id> <data> <allowed-root>
  local container="$1" expected_id="$2" data_path="$3" allowed_root="$4" running
  test "$(docker inspect "$container" --format '{{.Id}}')" = "$expected_id" \
    || die 'el contenedor fue sustituido desde que se creo el estado'
  running="$(docker inspect "$container" --format '{{.State.Running}}')"
  test "$running" = false || die 'el contenedor objetivo debe permanecer detenido'
  assert_path_policy "$data_path" "$allowed_root"
  assert_safe_tree "$data_path"
  assert_no_local_writers "$data_path"
}

migrate() { # <container> <allowed-root> <new-state-dir>
  local container="$1" allowed_root="$2" state_dir="$3" backup phase
  require_root
  assert_stopped_cluster
  allowed_root="$(readlink -f -- "$allowed_root")"
  test -d "$allowed_root" || die 'la raiz permitida no existe'
  discover_data_mount "$container"
  assert_path_policy "$DATA_PATH" "$allowed_root"
  prepare_state_directory "$state_dir" "$DATA_PATH"
  write_state "$STATE_DIR" container "$container"
  write_state "$STATE_DIR" container-id "$CONTAINER_ID"
  write_state "$STATE_DIR" image-id "$IMAGE_ID"
  write_state "$STATE_DIR" data-source "$DATA_SOURCE"
  write_state "$STATE_DIR" data-path "$DATA_PATH"
  write_state "$STATE_DIR" allowed-root "$allowed_root"
  write_state "$STATE_DIR" phase initialized

  test "$(docker inspect "$container" --format '{{.State.Running}}')" = false \
    || die 'deten todos los nodos, incluido el contenedor objetivo, antes de migrar'
  revalidate_before_mutation "$container" "$CONTAINER_ID" "$DATA_PATH" "$allowed_root"

  backup="$STATE_DIR/data-before-uid-${TARGET_UID}.tar"
  test ! -e "$backup" || die 'el backup de destino ya existe'
  tar --version | head -n 1 | grep -Fq 'GNU tar' || die 'se requiere GNU tar'
  # This check is intentionally adjacent to the recursive read.
  revalidate_before_mutation "$container" "$CONTAINER_ID" "$DATA_PATH" "$allowed_root"
  tar --acls --xattrs --numeric-owner --one-file-system \
    -C "$DATA_PATH" -cpf "$backup" .
  chmod 0600 "$backup"
  sha256sum "$backup" > "$backup.sha256"
  chmod 0600 "$backup.sha256"
  sha256sum --check "$backup.sha256" >/dev/null
  tar -tf "$backup" >/dev/null
  write_state "$STATE_DIR" backup "$backup"
  write_state "$STATE_DIR" phase backup-ready

  # Revalidate again immediately before the only recursive mutation.
  revalidate_before_mutation "$container" "$CONTAINER_ID" "$DATA_PATH" "$allowed_root"
  find "$DATA_PATH" -xdev -exec chown -h "$TARGET_UID:$TARGET_GID" {} +
  test -z "$(find "$DATA_PATH" -xdev \
    \( ! -user "$TARGET_UID" -o ! -group "$TARGET_GID" \) -print -quit)" \
    || die 'quedan entradas con un UID/GID distinto'

  docker run --rm --network none --read-only --user "$TARGET_UID:$TARGET_GID" \
    --cap-drop ALL --security-opt no-new-privileges \
    --mount "type=bind,src=$DATA_PATH,dst=/data" \
    --entrypoint sh "$IMAGE_ID" -c '
      set -eu
      test -r /data && test -w /data
      marker="/data/.rtfm-permission-check-$$"
      (umask 077; : > "$marker")
      rm -f -- "$marker"
    '
  phase=migrated
  write_state "$STATE_DIR" phase "$phase"
  printf 'rtfm-uid-migration: OK; datos migrados. Estado: %s\n' "$STATE_DIR"
  printf 'El contenedor permanece detenido; valida y arrancalo manualmente.\n'
}

rollback() { # <state-dir>
  local state_dir="$1" container container_id data_source data_path allowed_root backup phase
  local rollback_id restore_path failed_path
  require_root
  assert_stopped_cluster
  STATE_DIR="$(readlink -f -- "$state_dir")"
  test "$STATE_DIR" = "$state_dir" && test -d "$STATE_DIR" && test ! -L "$state_dir" \
    || die 'el directorio de estado no es una ruta real y segura'
  acquire_state_lock "$STATE_DIR"
  container="$(read_state "$STATE_DIR" container)"
  container_id="$(read_state "$STATE_DIR" container-id)"
  data_source="$(read_state "$STATE_DIR" data-source)"
  data_path="$(read_state "$STATE_DIR" data-path)"
  allowed_root="$(read_state "$STATE_DIR" allowed-root)"
  backup="$(read_state "$STATE_DIR" backup)"
  phase="$(read_state "$STATE_DIR" phase)"
  case "$phase" in backup-ready|migrated) ;; *) die "fase no recuperable automaticamente: $phase" ;; esac

  test "$data_source" = "$data_path" || die 'el estado contiene una ruta fuente inesperada'
  revalidate_before_mutation "$container" "$container_id" "$data_path" "$allowed_root"
  test "$backup" = "$STATE_DIR/data-before-uid-${TARGET_UID}.tar" \
    || die 'la ruta del backup no coincide con el estado'
  sha256sum --check "$backup.sha256" >/dev/null

  rollback_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  restore_path="${data_path}.restore-${rollback_id}"
  failed_path="${data_path}.failed-${rollback_id}"
  test ! -e "$restore_path" && test ! -L "$restore_path" || die 'ya existe la ruta restore'
  test ! -e "$failed_path" && test ! -L "$failed_path" || die 'ya existe la ruta failed'
  install -d -o 0 -g 0 -m 0700 -- "$restore_path"
  tar --acls --xattrs --numeric-owner --same-owner --same-permissions \
    -C "$restore_path" -xpf "$backup"
  assert_safe_tree "$restore_path"

  # Final adjacency check before the two same-parent atomic renames.
  revalidate_before_mutation "$container" "$container_id" "$data_path" "$allowed_root"
  mv -- "$data_path" "$failed_path"
  if ! mv -- "$restore_path" "$data_path"; then
    mv -- "$failed_path" "$data_path"
    die 'fallo al activar la restauracion; se repuso el arbol anterior'
  fi
  write_state "$STATE_DIR" failed-tree "$failed_path"
  write_state "$STATE_DIR" phase rolled-back
  printf 'rtfm-uid-migration: ROLLBACK OK; backup y arbol fallido conservados en:\n'
  printf '  %s\n  %s\n' "$backup" "$failed_path"
  printf 'El contenedor permanece detenido; valida y arrancalo manualmente.\n'
}

usage() {
  cat >&2 <<'USAGE'
Uso:
  RTFM_ALL_NODES_STOPPED=yes migrate-data-uid.sh migrate \
    --container NOMBRE --allowed-root RUTA --state-dir RUTA_NUEVA
  RTFM_ALL_NODES_STOPPED=yes migrate-data-uid.sh rollback --state-dir RUTA_ESTADO
USAGE
  exit 2
}

main() {
  local operation="${1:-}" container='' allowed_root='' state_dir=''
  test -n "$operation" || usage
  shift
  while test "$#" -gt 0; do
    case "$1" in
      --container) test "$#" -ge 2 || usage; container="$2"; shift 2 ;;
      --allowed-root) test "$#" -ge 2 || usage; allowed_root="$2"; shift 2 ;;
      --state-dir) test "$#" -ge 2 || usage; state_dir="$2"; shift 2 ;;
      *) usage ;;
    esac
  done
  for command in docker readlink find findmnt tar sha256sum stat install mv; do
    require_command "$command"
  done
  case "$operation" in
    migrate)
      test -n "$container" && test -n "$allowed_root" && test -n "$state_dir" || usage
      migrate "$container" "$allowed_root" "$state_dir"
      ;;
    rollback)
      test -z "$container" && test -z "$allowed_root" && test -n "$state_dir" || usage
      rollback "$state_dir"
      ;;
    *) usage ;;
  esac
}

if test "${RTFM_MIGRATION_LIBRARY_ONLY:-false}" != true; then
  main "$@"
fi
