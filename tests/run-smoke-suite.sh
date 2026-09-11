#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-rtfm:0.4.9}"
RUN_ID="$(date +%s)-$$-$RANDOM"
RESOURCE_LABEL_NAME="io.ezr43l.rtfm-smoke"
LABEL="$RESOURCE_LABEL_NAME=$RUN_ID"
APP_TOKEN="Rtfm-smoke-${RUN_ID}-Aa9-secure-password"
SESSION_SECRET="rtfm-smoke-session-${RUN_ID}-0123456789abcdef"
TESTS_DIR="$PWD/tests"
if command -v cygpath >/dev/null 2>&1; then
  TESTS_DIR="$(cygpath -w "$TESTS_DIR")"
fi

cleanup() {
  mapfile -t containers < <(docker ps -aq --filter "label=$LABEL")
  if ((${#containers[@]})); then
    docker rm -f "${containers[@]}" >/dev/null 2>&1 || true
  fi
  mapfile -t volumes < <(docker volume ls -q --filter "label=$LABEL")
  if ((${#volumes[@]})); then
    docker volume rm "${volumes[@]}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "· exportación PDF compilada"
docker run --rm --label "$LABEL" --entrypoint sh "$IMAGE" -c '
  set -eu
  grep -R -F "Exportar PDF" /app/app/static/assets/*.js >/dev/null
  grep -R -F "Preparando PDF" /app/app/static/assets/*.js >/dev/null
  grep -R -F "@media print" /app/app/static/assets/*.css >/dev/null
  grep -R -F "exporting-document-pdf" /app/app/static/assets/*.css >/dev/null
'

wait_ready() {
  local container="$1"
  for _ in $(seq 1 90); do
    if docker exec "$container" python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7400/api/health', timeout=2).read()" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  docker logs "$container" >&2 || true
  echo "RTFM no quedó disponible para el smoke $container" >&2
  return 1
}

start_container() {
  local name="$1" volume="$2"
  MSYS_NO_PATHCONV=1 docker run -d --name "$name" --label "$LABEL" \
    --read-only --cap-drop ALL --security-opt no-new-privileges:true \
    --pids-limit 256 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m \
    -v "$volume:/data" \
    --mount "type=bind,source=$TESTS_DIR,target=/smoke,readonly" \
    -e ROLE_MODE=active -e GIT_ENABLED=true \
    -e "APP_TOKEN=$APP_TOKEN" -e "SESSION_SECRET=$SESSION_SECRET" \
    "$IMAGE" >/dev/null
  wait_ready "$name"
}

run_smoke() {
  local script="$1" slug="${1#smoke_}"
  slug="${slug%.py}"
  local name="rtfm-smoke-${RUN_ID}-${slug}"
  local volume="rtfm-smoke-${RUN_ID}-${slug}-data"
  docker volume create --label "$LABEL" "$volume" >/dev/null
  start_container "$name" "$volume"
  MSYS_NO_PATHCONV=1 docker exec -e "APP_TOKEN=$APP_TOKEN" -e PYTHONPATH=/app \
    "$name" python "/smoke/$script"
  docker rm -f "$name" >/dev/null
  docker volume rm "$volume" >/dev/null
}

for script in \
  smoke_runtime.py \
  smoke_editor.py \
  smoke_profile.py \
  smoke_permissions.py \
  smoke_order_favorites.py; do
  echo "· $script"
  run_smoke "$script"
done

# Reproduce la forma persistida por 0.4.0 (biblioteca sin miembro `access`) y
# comprueba que 0.4.9 la abre sin reescribirla destructivamente. La validación
# local de release conserva, además, la prueba binaria real 0.4.0 -> versión actual.
echo "· smoke_upgrade_040_to_041.py"
upgrade_name="rtfm-smoke-${RUN_ID}-upgrade"
upgrade_volume="rtfm-smoke-${RUN_ID}-upgrade-data"
docker volume create --label "$LABEL" "$upgrade_volume" >/dev/null
start_container "$upgrade_name" "$upgrade_volume"
MSYS_NO_PATHCONV=1 docker exec -e "APP_TOKEN=$APP_TOKEN" -e PHASE=seed -e PYTHONPATH=/app \
  "$upgrade_name" python /smoke/smoke_upgrade_040_to_041.py
docker rm -f "$upgrade_name" >/dev/null

docker run --rm --label "$LABEL" -v "$upgrade_volume:/data" \
  --entrypoint python "$IMAGE" -c \
  "import json,pathlib; files=list(pathlib.Path('/data/catalog/libraries').glob('*.json')); assert len(files)==1, files; data=json.loads(files[0].read_text()); assert data.pop('access', None) is not None; files[0].write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding='utf-8')"

start_container "$upgrade_name" "$upgrade_volume"
MSYS_NO_PATHCONV=1 docker exec -e "APP_TOKEN=$APP_TOKEN" -e PHASE=check -e PYTHONPATH=/app \
  "$upgrade_name" python /smoke/smoke_upgrade_040_to_041.py
docker rm -f "$upgrade_name" >/dev/null
docker volume rm "$upgrade_volume" >/dev/null

echo "Suite smoke RTFM completada para $IMAGE"
