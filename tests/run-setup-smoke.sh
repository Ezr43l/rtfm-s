#!/usr/bin/env bash
set -euo pipefail

export MSYS_NO_PATHCONV=1
IMAGE="${1:-rtfm:0.4.10}"
RUN_ID="$(date +%s)-$$-$RANDOM"
LABEL="io.ezr43l.rtfm-setup=$RUN_ID"
CONTAINER="rtfm-setup-$RUN_ID"
VOLUME="$CONTAINER-data"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker volume create --label "$LABEL" "$VOLUME" >/dev/null
docker run -d --name "$CONTAINER" --label "$LABEL" \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --pids-limit 256 --init --tmpfs /tmp:rw,nosuid,noexec,size=128m,mode=1777 \
  -v "$VOLUME:/data" "$IMAGE" >/dev/null

for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" python -c \
    "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:7400/api/v1/setup',timeout=2))['required']" \
    >/dev/null 2>&1; then break; fi
  sleep 1
done

docker exec -i "$CONTAINER" python - <<'PY'
import json
import urllib.request

payload = {
    "node": "standalone", "role_mode": "active",
    "public": {"scheme": "http", "forwarded_allow_ips": "127.0.0.1",
               "floating_ip": "", "floating_url": "", "session_cookie_secure": False},
    "keepalived": {"url": "", "api_key": "", "service": "rtfm",
                    "description": "RTFM", "claim_id": "", "health_path": "/api/health",
                    "service_ports": [], "timeout_seconds": 5,
                    "allow_insecure_http": False, "ca_pem": ""},
    "replication": {"peers": [], "allow_insecure_http": False, "ca_pem": "", "max_mb": 512},
    "policy": {"retention_days": 90, "sync_interval_seconds": 300,
               "max_image_size_mb": 10, "session_hours": 12,
               "login_max_attempts": 5, "login_window_seconds": 300,
               "password_min_length": 12, "totp_issuer": "RTFM"},
    "git": {"enabled": True, "author_name": "RTFM", "author_email": "rtfm@localhost"},
    "owner": {"username": "owner", "display_name": "Owner",
              "password": "Runtime-owner-password-2026"},
    "enrollment_code": "",
}
body = json.dumps(payload).encode()
request = urllib.request.Request("http://127.0.0.1:7400/api/v1/setup", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(request, timeout=20) as response:
    result = json.load(response)
assert result["ok"] and result["restarting"] and result["enrollment_code"]
PY

sleep 2
ready=0
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" python -c \
    "import json,urllib.request; s=json.load(urllib.request.urlopen('http://127.0.0.1:7400/api/v1/setup',timeout=2)); h=json.load(urllib.request.urlopen('http://127.0.0.1:7400/api/health',timeout=2)); assert not s['required'] and h['status']=='ok' and h['role']=='active'" \
    >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1

docker exec -i "$CONTAINER" python - <<'PY'
import http.cookiejar
import json
import urllib.request

base = "http://127.0.0.1:7400/api/v1"
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
body = json.dumps({"actor": "owner", "credential": "Runtime-owner-password-2026"}).encode()
request = urllib.request.Request(base + "/auth/session", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
with client.open(request, timeout=20) as response:
    session = json.load(response)
assert session["role"] == "full_control" and not session["password_change_required"]

with client.open(base + "/configuration", timeout=20) as response:
    configuration = json.load(response)
assert configuration["values"]["policy"]["retention_days"] == 90
assert configuration["values"]["keepalived"]["api_key"] == ""
assert "session_secret" not in json.dumps(configuration).lower()
configuration["values"]["policy"]["retention_days"] = 91
body = json.dumps(configuration["values"]).encode()
request = urllib.request.Request(
    base + "/configuration", data=body,
    headers={"Content-Type": "application/json", "X-CSRF-Token": session["csrf_token"]},
    method="PUT",
)
with client.open(request, timeout=20) as response:
    result = json.load(response)
assert result == {"ok": True, "restarting": True}
PY

sleep 2
ready=0
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" python -c \
    "import json,urllib.request; h=json.load(urllib.request.urlopen('http://127.0.0.1:7400/api/health',timeout=2)); assert h['status']=='ok' and h['role']=='active'" \
    >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1

docker exec -i "$CONTAINER" python - <<'PY'
import http.cookiejar
import json
import urllib.request

base = "http://127.0.0.1:7400/api/v1"
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
body = json.dumps({"actor": "owner", "credential": "Runtime-owner-password-2026"}).encode()
request = urllib.request.Request(base + "/auth/session", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
with client.open(request, timeout=20) as response:
    session = json.load(response)
assert session["role"] == "full_control"
with client.open(base + "/configuration", timeout=20) as response:
    configuration = json.load(response)
assert configuration["values"]["policy"]["retention_days"] == 91
assert configuration["values"]["keepalived"]["api_key"] == ""
PY

docker exec "$CONTAINER" sh -ec '
  test "$(stat -c "%u:%g:%a" /data/.rtfm)" = "10001:10001:700"
  test "$(stat -c "%u:%g:%a" /data/.rtfm/config.json)" = "10001:10001:600"
  test "$(stat -c "%u:%g:%a" /data/.rtfm/secrets/session-secret)" = "10001:10001:600"
  test "$(stat -c "%u:%g:%a" /data/.rtfm/secrets/replication-token)" = "10001:10001:600"
  ! grep -q "Runtime-owner-password\|session-secret\|replication-token" /data/.rtfm/config.json
'

test "$(docker ps -q --filter "label=$LABEL" | wc -l | tr -d ' ')" = 1
test "$(docker inspect "$CONTAINER" --format '{{.HostConfig.ReadonlyRootfs}}')" = true
test -z "$(docker inspect "$CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/run/secrets"}}{{.Destination}}{{end}}{{end}}')"
if docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(APP_TOKEN|SESSION_SECRET|REPLICATION_TOKEN|KEEPALIVED_API_KEY)='; then
  echo "Un secreto aparece en docker inspect" >&2
  exit 1
fi

echo "Asistente RTFM correcto: un contenedor, un volumen y configuración interna."
