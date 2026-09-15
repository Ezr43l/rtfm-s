"""Current API smoke test for the basic document lifecycle and audit trail."""

import http.cookiejar
import json
import os
import urllib.error
import urllib.request


BASE = os.getenv("BASE_URL", "http://127.0.0.1:7400")
PASSWORD = os.environ["APP_TOKEN"]
cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
csrf = ""


def call(method: str, path: str, payload: dict | None = None, expected: int = 200) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if csrf and method not in {"GET", "HEAD", "OPTIONS"}:
        headers["X-CSRF-Token"] = csrf
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        response = opener.open(request, timeout=8)
    except urllib.error.HTTPError as error:
        body = json.loads(error.read().decode("utf-8"))
        raise AssertionError(
            f"{method} {path}: HTTP {error.code}, esperado {expected}: {body}"
        ) from error
    with response:
        if response.status != expected:
            raise AssertionError(f"{method} {path}: HTTP {response.status}, esperado {expected}")
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


health = call("GET", "/api/health")
assert health["status"] == "ok"
assert health["version"] == "0.4.11"

session = call(
    "POST",
    "/api/v1/auth/session",
    {"actor": "runtime-verification", "credential": PASSWORD},
)
csrf = session["csrf_token"]
assert session["role"] == "full_control"

library = call("POST", "/api/v1/libraries", {"name": "Runtime smoke library"}, expected=201)
created = call(
    "POST",
    "/api/v1/documents",
    {"library_id": library["id"], "title": "Prueba del nodo", "content": "# Smoke test"},
    expected=201,
)
document_id = created["meta"]["id"]
updated = call(
    "PATCH",
    f"/api/v1/documents/{document_id}",
    {"content": "# Smoke test\n\nActualizado."},
)
assert updated["meta"]["version"]["clock"] > created["meta"]["version"]["clock"]
deleted = call("DELETE", f"/api/v1/documents/{document_id}")
assert deleted["meta"]["status"] == "deleted"
restored = call("POST", f"/api/v1/documents/{document_id}/restore")
assert restored["content"].endswith("Actualizado.")
call("DELETE", f"/api/v1/documents/{document_id}")

audit = call("GET", "/api/v1/logs?limit=50")
assert any(event.get("document_id") == document_id for event in audit["items"])
print(json.dumps({"status": "ok", "document_id": document_id, "audit_events_checked": len(audit["items"])}))
