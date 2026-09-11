"""End-to-end users, roles and independent API token smoke test.

Run only against an isolated active container with a fresh /data volume.
"""

import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


BASE = os.getenv("BASE_URL", "http://127.0.0.1:7400") + "/api/v1"
ADMIN_PASSWORD = os.environ["APP_TOKEN"]


class BrowserClient:
    def __init__(self) -> None:
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = ""

    def call(self, method: str, path: str, payload: dict | None = None, expected: int = 200) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.csrf and method not in {"GET", "HEAD", "OPTIONS"}:
            headers["X-CSRF-Token"] = self.csrf
        result = request(self.opener, method, path, payload, headers, expected)
        if path == "/auth/session" and method == "POST" and expected == 200:
            self.csrf = result["csrf_token"]
        return result


def request(opener, method: str, path: str, payload: dict | None, headers: dict, expected: int) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    operation = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        response = opener.open(operation, timeout=8)
    except urllib.error.HTTPError as error:
        body = json.loads(error.read().decode("utf-8"))
        if error.code != expected:
            raise AssertionError(f"{method} {path}: HTTP {error.code}, esperado {expected}: {body}") from error
        return body
    with response:
        if response.status != expected:
            raise AssertionError(f"{method} {path}: HTTP {response.status}, esperado {expected}")
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def api_call(token: str, method: str, path: str, payload: dict | None = None, expected: int = 200) -> dict:
    return request(
        urllib.request.build_opener(),
        method,
        path,
        payload,
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        expected,
    )


def legacy_api_call(method: str, path: str, payload: dict | None = None, expected: int = 200) -> dict:
    return request(
        urllib.request.build_opener(),
        method,
        path,
        payload,
        {
            "Authorization": f"Bearer {ADMIN_PASSWORD}",
            "X-Actor": "legacy-smoke",
            "Content-Type": "application/json",
        },
        expected,
    )


admin = BrowserClient()
session = admin.call("POST", "/auth/session", {"actor": "admin", "credential": ADMIN_PASSWORD})
assert session["role"] == "full_control"
assert session["identity_type"] == "person"

library = admin.call("POST", "/libraries", {"name": "Pruebas de permisos"}, expected=201)

reader_password = "reader secure password 2026"
operator_password = "operator secure password 2026"
reader = admin.call("POST", "/users", {
    "username": "reader", "display_name": "Reader", "password": reader_password,
    "role": "reader", "current_password": ADMIN_PASSWORD,
}, expected=201)
operator = admin.call("POST", "/users", {
    "username": "operator", "display_name": "Operator", "password": operator_password,
    "role": "operator", "current_password": ADMIN_PASSWORD,
}, expected=201)
assert reader["role"] == "reader" and operator["role"] == "operator"

reader_browser = BrowserClient()
reader_browser.call("POST", "/auth/session", {"actor": "reader", "credential": reader_password})
reader_browser.call("GET", "/libraries")
reader_browser.call("POST", "/libraries", {"name": "Forbidden"}, expected=403)

operator_browser = BrowserClient()
operator_browser.call("POST", "/auth/session", {"actor": "operator", "credential": operator_password})
document = operator_browser.call("POST", "/documents", {
    "library_id": library["id"], "title": "Documento de operador", "content": "Operador",
}, expected=201)
operator_browser.call("DELETE", f"/documents/{document['meta']['id']}", expected=403)
operator_browser.call("POST", f"/documents/{document['meta']['id']}/archive")

api_operator = admin.call("POST", "/users/api-clients", {
    "name": "Operator API", "role": "operator", "current_password": ADMIN_PASSWORD,
}, expected=201)
operator_token = api_operator["token"]
api_call(operator_token, "GET", "/libraries")
api_document = api_call(operator_token, "POST", "/documents", {
    "library_id": library["id"], "title": "Documento API", "content": "API",
}, expected=201)
api_call(operator_token, "DELETE", f"/documents/{api_document['meta']['id']}", expected=403)

api_full = admin.call("POST", "/users/api-clients", {
    "name": "Full API", "role": "full_control", "current_password": ADMIN_PASSWORD,
}, expected=201)
full_token = api_full["token"]
api_call(full_token, "DELETE", f"/documents/{api_document['meta']['id']}")
api_call(full_token, "GET", "/users", expected=403)

restricted = admin.call("POST", "/libraries", {"name": "Biblioteca restringida"}, expected=201)
hidden = admin.call("POST", "/libraries", {"name": "Biblioteca oculta"}, expected=201)
admin.call("PUT", f"/libraries/{restricted['id']}/permissions", {
    "mode": "restricted",
    "grants": [
        {"subject_type": "user", "subject_id": reader["id"], "role": "full_control"},
        {"subject_type": "user", "subject_id": operator["id"], "role": "operator"},
        {"subject_type": "api_client", "subject_id": api_operator["item"]["id"], "role": "operator"},
    ],
    "current_password": ADMIN_PASSWORD,
})
admin.call("PUT", f"/libraries/{hidden['id']}/permissions", {
    "mode": "restricted", "grants": [], "current_password": ADMIN_PASSWORD,
})

restricted_view = reader_browser.call("GET", f"/libraries/{restricted['id']}")
assert restricted_view["access_mode"] == "restricted"
assert restricted_view["effective_role"] == "reader"  # global reader is a hard ceiling
assert "access" not in restricted_view and "grants" not in restricted_view
reader_library_ids = {item["id"] for item in reader_browser.call("GET", "/libraries")["items"]}
assert restricted["id"] in reader_library_ids and hidden["id"] not in reader_library_ids
reader_browser.call("GET", f"/libraries/{hidden['id']}", expected=404)
reader_browser.call("POST", "/documents", {
    "library_id": restricted["id"], "title": "No permitido", "content": "Reader",
}, expected=403)

restricted_document = operator_browser.call("POST", "/documents", {
    "library_id": restricted["id"], "title": "Documento restringido", "content": "Operador",
}, expected=201)
assert restricted_document["meta"]["effective_role"] == "operator"
operator_browser.call("POST", f"/documents/{restricted_document['meta']['id']}/move", {
    "library_id": hidden["id"], "category_id": None,
}, expected=404)
api_call(operator_token, "POST", "/documents", {
    "library_id": restricted["id"], "title": "API restringida", "content": "API",
}, expected=201)
api_call(full_token, "GET", f"/libraries/{restricted['id']}", expected=404)
api_call(full_token, "GET", f"/libraries/{hidden['id']}", expected=404)
legacy_api_call("GET", f"/libraries/{restricted['id']}", expected=404)

hidden_document = admin.call("POST", "/documents", {
    "library_id": hidden["id"], "title": "Secreto", "content": "Oculto", "tags": ["topsecret"],
}, expected=201)
hidden_image = admin.call("POST", f"/documents/{hidden_document['meta']['id']}/images", {
    "filename": "pixel.png",
    "media_type": "image/png",
    "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
}, expected=201)
reader_browser.call("GET", f"/documents/{hidden_document['meta']['id']}", expected=404)
reader_browser.call("GET", f"/documents/{hidden_document['meta']['id']}/images/{hidden_image['id']}", expected=404)
reader_browser.call("PUT", f"/favorites/{hidden_document['meta']['id']}", expected=404)
reader_browser.call("POST", f"/libraries/{hidden['id']}/categories", {"name": "Oculta"}, expected=403)
operator_browser.call("POST", f"/libraries/{hidden['id']}/categories", {"name": "Oculta"}, expected=404)
assert not reader_browser.call("GET", "/documents?query=Secreto")["items"]
assert "topsecret" not in {item["name"] for item in reader_browser.call("GET", "/documents/meta/tags/all")["items"]}
reader_browser.call("GET", "/logs", expected=403)
dashboard = reader_browser.call("GET", "/dashboard")
assert dashboard["counts"]["libraries"] == 2
assert dashboard["recent_activity"] == []
reader_status = reader_browser.call("GET", "/status")
admin_status = admin.call("GET", "/status")
assert reader_status["sync"]["documents"] < admin_status["sync"]["documents"]

admin.call("PATCH", f"/users/{reader['id']}", {
    "status": "disabled", "current_password": ADMIN_PASSWORD,
})
disabled = BrowserClient()
disabled.call("POST", "/auth/session", {"actor": "reader", "credential": reader_password}, expected=401)

stored = "\n".join(
    path.read_text(encoding="utf-8", errors="ignore")
    for path in Path("/data").rglob("*")
    if path.is_file() and ".git" not in path.parts
)
assert operator_token not in stored and full_token not in stored

logs = admin.call("GET", "/logs?limit=200")
actors = {event.get("actor") for event in logs["items"]}
assert "operator" in actors and "api:Operator API" in actors and "api:Full API" in actors

print(json.dumps({
    "status": "ok", "users": 3, "api_clients": 2,
    "global_roles_enforced": True, "library_permissions_enforced": True,
}))
