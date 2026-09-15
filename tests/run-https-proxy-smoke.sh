#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-rtfm:0.4.11}"
RUN_ID="$(date +%s)-$$-$RANDOM"
RESOURCE_LABEL_NAME="io.ezr43l.rtfm-https-smoke"
LABEL="$RESOURCE_LABEL_NAME=$RUN_ID"
NETWORK="rtfm-https-$RUN_ID"
DATA_VOLUME="rtfm-https-$RUN_ID-data"
TLS_VOLUME="rtfm-https-$RUN_ID-tls"
APP_CONTAINER="rtfm-https-$RUN_ID-app"
PROXY_CONTAINER="rtfm-https-$RUN_ID-proxy"
APP_TOKEN="Rtfm-https-${RUN_ID}-Aa9-secure-password"
SESSION_SECRET="rtfm-https-session-${RUN_ID}-0123456789abcdef"
TESTS_DIR="$PWD/tests"
STAGE="inicialización"
if command -v cygpath >/dev/null 2>&1; then
  TESTS_DIR="$(cygpath -w "$TESTS_DIR")"
fi

cleanup() {
  mapfile -t containers < <(docker ps -aq --filter "label=$LABEL")
  if ((${#containers[@]})); then
    docker rm -f "${containers[@]}" >/dev/null 2>&1 || true
  fi
  docker volume rm "$DATA_VOLUME" "$TLS_VOLUME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
finish() {
  local status=$?
  trap - EXIT
  if test "$status" -ne 0; then
    printf 'HTTPS proxy gate: fallo durante %s\n' "$STAGE" >&2
  fi
  cleanup
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

STAGE="creación de recursos aislados"
docker network create --label "$LABEL" "$NETWORK" >/dev/null
docker volume create --label "$LABEL" "$DATA_VOLUME" >/dev/null
docker volume create --label "$LABEL" "$TLS_VOLUME" >/dev/null

MSYS_NO_PATHCONV=1 docker run --rm --user 0:0 \
  -v "$TLS_VOLUME:/tls" --entrypoint sh "$IMAGE" \
  -c 'chown 10001:10001 /tls && chmod 0700 /tls'

STAGE="arranque del terminador TLS"
MSYS_NO_PATHCONV=1 docker run -d --name "$PROXY_CONTAINER" --label "$LABEL" \
  --network "$NETWORK" --network-alias proxy \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 128 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
  -v "$TLS_VOLUME:/tls" \
  --mount "type=bind,source=$TESTS_DIR,target=/tests,readonly" \
  -e BACKEND_HOST=rtfm -e BACKEND_PORT=7400 \
  --entrypoint python "$IMAGE" /tests/https_proxy_smoke.py proxy >/dev/null

STAGE="generación de la PKI efímera"
for _ in $(seq 1 60); do
  if MSYS_NO_PATHCONV=1 docker exec "$PROXY_CONTAINER" test -s /tls/ca.pem >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! MSYS_NO_PATHCONV=1 docker exec "$PROXY_CONTAINER" test -s /tls/ca.pem; then
  docker logs "$PROXY_CONTAINER" >&2 || true
  exit 1
fi
proxy_ip="$(docker inspect "$PROXY_CONTAINER" \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
[[ "$proxy_ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || {
  echo "No se pudo resolver la IP aislada del proxy" >&2
  exit 1
}

STAGE="arranque de RTFM detrás del proxy"
MSYS_NO_PATHCONV=1 docker run -d --name "$APP_CONTAINER" --label "$LABEL" \
  --network "$NETWORK" --network-alias rtfm \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 256 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m \
  -v "$DATA_VOLUME:/data" \
  -e ROLE_MODE=active -e GIT_ENABLED=false \
  -e PUBLIC_SCHEME=https -e SESSION_COOKIE_SECURE=true \
  -e "FORWARDED_ALLOW_IPS=$proxy_ip" \
  -e LOGIN_MAX_ATTEMPTS=3 -e LOGIN_WINDOW_SECONDS=300 \
  -e "APP_TOKEN=$APP_TOKEN" -e "SESSION_SECRET=$SESSION_SECRET" \
  "$IMAGE" >/dev/null

STAGE="espera de salud de RTFM"
for _ in $(seq 1 90); do
  if docker exec "$APP_CONTAINER" python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7400/api/health', timeout=2).read()" \
    >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! docker exec "$APP_CONTAINER" python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7400/api/health', timeout=2).read()" \
    >/dev/null 2>&1; then
  docker logs "$APP_CONTAINER" >&2 || true
  exit 1
fi

STAGE="validación TLS y de proxy confiable"
MSYS_NO_PATHCONV=1 docker run --rm --label "$LABEL" \
  --network "$NETWORK" \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 128 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
  -v "$TLS_VOLUME:/tls:ro" \
  --mount "type=bind,source=$TESTS_DIR,target=/tests,readonly" \
  -e "APP_TOKEN=$APP_TOKEN" \
  --entrypoint python "$IMAGE" /tests/https_proxy_smoke.py client
