#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-rtfm:0.4.11}"
RUN_ID="$(date +%s)-$$-$RANDOM"
RESOURCE_LABEL_NAME="io.ezr43l.rtfm-ha-conflict-smoke"
LABEL="$RESOURCE_LABEL_NAME=$RUN_ID"
NETWORK="rtfm-ha-$RUN_ID"
CONTROL_VOLUME="rtfm-ha-$RUN_ID-control"
APP_TOKEN="Rtfm-ha-${RUN_ID}-Aa9-secure-password"
SESSION_SECRET="rtfm-ha-session-${RUN_ID}-0123456789abcdef"
REPLICATION_TOKEN="rtfm-ha-replication-${RUN_ID}-0123456789abcdef"
TESTS_DIR="$PWD/tests"
if command -v cygpath >/dev/null 2>&1; then
  TESTS_DIR="$(cygpath -w "$TESTS_DIR")"
fi

declare -A VOLUMES=(
  [node-a]="rtfm-ha-$RUN_ID-a-data"
  [node-b]="rtfm-ha-$RUN_ID-b-data"
  [node-c]="rtfm-ha-$RUN_ID-c-data"
)

cleanup() {
  mapfile -t containers < <(docker ps -aq --filter "label=$LABEL")
  if ((${#containers[@]})); then
    docker rm -f "${containers[@]}" >/dev/null 2>&1 || true
  fi
  docker volume rm "${VOLUMES[node-a]}" "${VOLUMES[node-b]}" \
    "${VOLUMES[node-c]}" "$CONTROL_VOLUME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

start_node() {
  local node="$1" role="$2" peers="$3" volume="${VOLUMES[$1]}"
  MSYS_NO_PATHCONV=1 docker run -d --name "rtfm-ha-$RUN_ID-$node" --label "$LABEL" \
    --network "$NETWORK" --network-alias "$node" \
    --read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 256 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m \
    -v "$volume:/data" \
    -e "NODE_NAME=$node" -e "ROLE_MODE=$role" -e GIT_ENABLED=false \
    -e SYNC_INTERVAL_SECONDS=86400 \
    -e REPLICATION_ALLOW_INSECURE_HTTP=true -e "PEERS=$peers" \
    -e "APP_TOKEN=$APP_TOKEN" -e "SESSION_SECRET=$SESSION_SECRET" \
    -e "REPLICATION_TOKEN=$REPLICATION_TOKEN" \
    "$IMAGE" >/dev/null
}

wait_node() {
  local node="$1" role="$2" container="rtfm-ha-$RUN_ID-$1"
  for _ in $(seq 1 90); do
    if MSYS_NO_PATHCONV=1 docker exec "$container" python -c \
      "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:7400/api/health', timeout=2)); assert d['status']=='ok' and d['role']=='$role' and d['version']=='0.4.11'" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  docker logs "$container" >&2 || true
  return 1
}

run_client() {
  local phase="$1"
  MSYS_NO_PATHCONV=1 docker run --rm --label "$LABEL" \
    --network "$NETWORK" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --pids-limit 128 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
    -v "$CONTROL_VOLUME:/control" \
    --mount "type=bind,source=$TESTS_DIR,target=/tests,readonly" \
    -e "APP_TOKEN=$APP_TOKEN" --entrypoint python "$IMAGE" \
    /tests/ha_conflict_rejoin_smoke.py "$phase"
}

docker network create --label "$LABEL" "$NETWORK" >/dev/null
for volume in "${VOLUMES[@]}"; do
  docker volume create --label "$LABEL" "$volume" >/dev/null
done
docker volume create --label "$LABEL" "$CONTROL_VOLUME" >/dev/null
MSYS_NO_PATHCONV=1 docker run --rm --user 0:0 \
  -v "$CONTROL_VOLUME:/control" --entrypoint sh "$IMAGE" \
  -c 'chown 10001:10001 /control && chmod 0700 /control'

start_node node-a active 'node-b=http://node-b:7400,node-c=http://node-c:7400'
start_node node-b passive 'node-a=http://node-a:7400'
start_node node-c passive 'node-a=http://node-a:7400'
wait_node node-a active
wait_node node-b passive
wait_node node-c passive
run_client seed

docker rm -f "rtfm-ha-$RUN_ID-node-b" "rtfm-ha-$RUN_ID-node-c" >/dev/null
start_node node-b active ''
wait_node node-b active
run_client conflict

docker rm -f "rtfm-ha-$RUN_ID-node-b" >/dev/null
start_node node-b passive 'node-a=http://node-a:7400'
start_node node-c passive 'node-a=http://node-a:7400'
wait_node node-b passive
wait_node node-c passive
run_client reconcile
