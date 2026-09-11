"""End-to-end smoke test for category ordering and personal favorites."""

import http.cookiejar
import json
import os
import urllib.error
import urllib.request


BASE = os.getenv("BASE_URL", "http://127.0.0.1:7400") + "/api/v1"
PASSWORD = os.environ["APP_TOKEN"]
cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
csrf = ""


def call(method: str, path: str, payload: dict | None = None, expected: int = 200) -> dict:
    global csrf
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if csrf and method not in {"GET", "HEAD", "OPTIONS"}:
        headers["X-CSRF-Token"] = csrf
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        response = opener.open(request, timeout=10)
    except urllib.error.HTTPError as error:
        body = json.loads(error.read().decode("utf-8"))
        raise AssertionError(f"{method} {path}: HTTP {error.code}, esperado {expected}: {body}") from error
    with response:
        assert response.status == expected, f"{method} {path}: HTTP {response.status}, esperado {expected}"
        raw = response.read()
        result = json.loads(raw.decode("utf-8")) if raw else {}
        if method == "POST" and path == "/auth/session":
            csrf = result["csrf_token"]
        return result


call("POST", "/auth/session", {"actor": "catalog-test", "credential": PASSWORD})
library = call("POST", "/libraries", {"name": "Orden y favoritos"}, expected=201)
categories = [
    call("POST", f"/libraries/{library['id']}/categories", {"name": name}, expected=201)
    for name in ("Zulu", "Árbol", "Docker")
]

call("PATCH", f"/libraries/{library['id']}", {"category_sort": "alphabetical"})
alphabetical = call("GET", f"/libraries/{library['id']}/tree")
assert [item["name"] for item in alphabetical["categories"]] == ["Árbol", "Docker", "Zulu"]

call("PATCH", f"/libraries/{library['id']}", {"category_sort": "manual"})
manual_ids = [categories[2]["id"], categories[0]["id"], categories[1]["id"]]
call("PUT", f"/libraries/{library['id']}/categories/order", {"parent_id": None, "category_ids": manual_ids})
manual = call("GET", f"/libraries/{library['id']}/tree")
assert [item["id"] for item in manual["categories"]] == manual_ids

document = call("POST", "/documents", {
    "library_id": library["id"], "title": "Documento importante", "content": "Contenido",
}, expected=201)
document_id = document["meta"]["id"]
assert call("PUT", f"/favorites/{document_id}")["favorite"] is True
assert call("GET", "/favorites")["items"][0]["id"] == document_id
assert call("DELETE", f"/favorites/{document_id}")["favorite"] is False
assert call("GET", "/favorites")["items"] == []

print(json.dumps({"status": "ok", "alphabetical": True, "manual": True, "favorites": True}))
