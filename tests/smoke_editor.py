"""End-to-end smoke test for private images and rich Markdown documents."""

import base64
import http.cookiejar
import json
import os
import urllib.error
import urllib.request


BASE = os.getenv("BASE_URL", "http://127.0.0.1:7400")
PASSWORD = os.environ["APP_TOKEN"]
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
csrf = ""


def call(method: str, path: str, payload: dict | None = None, expected: int = 200) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if csrf and method not in {"GET", "HEAD", "OPTIONS"}:
        headers["X-CSRF-Token"] = csrf
    request = urllib.request.Request(BASE + "/api/v1" + path, data=data, method=method, headers=headers)
    try:
        response = opener.open(request, timeout=10)
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


session = call("POST", "/auth/session", {"actor": "editor-test", "credential": PASSWORD})
csrf = session["csrf_token"]
library = call("POST", "/libraries", {"name": "Pruebas de editor", "description": "Temporal"}, expected=201)
document = call(
    "POST",
    "/documents",
    {
        "library_id": library["id"],
        "title": "Documento enriquecido",
        "content": "# Editor\n\nTexto inicial.",
        "tags": ["editor", "smoke"],
    },
    expected=201,
)
document_id = document["meta"]["id"]
image = call(
    "POST",
    f"/documents/{document_id}/images",
    {
        "filename": "captura.png",
        "media_type": "image/png",
        "data": base64.b64encode(TINY_PNG).decode("ascii"),
    },
    expected=201,
)

image_request = urllib.request.Request(BASE + image["url"])
with opener.open(image_request, timeout=10) as response:
    assert response.headers.get_content_type() == "image/png"
    assert response.read() == TINY_PNG

markdown = f"""# Editor completo

**Negrita**, *cursiva*, [enlace interno](/documents/{document_id}) y una imagen:

![Captura]({image['url']})

```mermaid
flowchart LR
    A[Inicio] --> B{{Decisión}}
    B --> C[Fin]
```
"""
updated = call("PATCH", f"/documents/{document_id}", {"content": markdown})
assert updated["content"] == markdown
assert updated["images"][0]["id"] == image["id"]

invalid = call(
    "POST",
    f"/documents/{document_id}/images",
    {
        "filename": "peligro.svg",
        "media_type": "image/svg+xml",
        "data": base64.b64encode(b"<svg><script>alert(1)</script></svg>").decode("ascii"),
    },
    expected=422,
)
assert "Formato no permitido" in invalid["error"]["message"]

print(json.dumps({"status": "ok", "document_id": document_id, "image_id": image["id"], "mermaid": True}))
