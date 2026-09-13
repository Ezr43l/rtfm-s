"""Prove that 0.4.0 libraries stay accessible after an in-place upgrade to 0.4.10."""

import http.cookiejar
import json
import os
import urllib.request


BASE = os.getenv("BASE_URL", "http://127.0.0.1:7400") + "/api/v1"
PASSWORD = os.environ["APP_TOKEN"]
PHASE = os.getenv("PHASE", "check")
LIBRARY_NAME = "Compatibility 0.4.0 library"


cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
csrf = ""


def call(method: str, path: str, payload: dict | None = None, expected: int = 200) -> dict:
    global csrf
    headers = {"Content-Type": "application/json"}
    if csrf and method not in {"GET", "HEAD", "OPTIONS"}:
        headers["X-CSRF-Token"] = csrf
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
        headers=headers,
    )
    with opener.open(request, timeout=8) as response:
        assert response.status == expected
        body = json.loads(response.read().decode("utf-8"))
    if path == "/auth/session" and method == "POST":
        csrf = body["csrf_token"]
    return body


session = call("POST", "/auth/session", {"actor": "upgrade-admin", "credential": PASSWORD})
assert session["role"] == "full_control"

if PHASE == "seed":
    library = call("POST", "/libraries", {"name": LIBRARY_NAME}, expected=201)
    document = call("POST", "/documents", {
        "library_id": library["id"],
        "title": "Document created by 0.4.0",
        "content": "This content must survive the patch upgrade.",
    }, expected=201)
    print(json.dumps({"status": "seeded", "library_id": library["id"], "document_id": document["meta"]["id"]}))
else:
    libraries = call("GET", "/libraries")["items"]
    library = next(item for item in libraries if item["name"] == LIBRARY_NAME)
    assert library["access_mode"] == "open"
    assert library["effective_role"] == "full_control"
    assert "access" not in library and "grants" not in library
    documents = call("GET", f"/documents?library_id={library['id']}")["items"]
    document = next(item for item in documents if item["title"] == "Document created by 0.4.0")
    record = call("GET", f"/documents/{document['id']}")
    assert record["content"] == "This content must survive the patch upgrade."
    assert record["meta"]["effective_role"] == "full_control"
    print(json.dumps({"status": "compatible", "library_id": library["id"], "document_id": document["id"]}))
