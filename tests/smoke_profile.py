"""End-to-end account migration, profile, password and TOTP smoke test.

Run against an isolated container; it creates the first owner account in its data volume.
"""

import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.accounts import AccountSecurity


BASE = os.getenv("BASE_URL", "http://127.0.0.1:7400")
BOOTSTRAP_PASSWORD = os.environ["APP_TOKEN"]
NEW_PASSWORD = os.getenv("TEST_NEW_PASSWORD", "frase de prueba segura 2026")
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
        response = opener.open(request, timeout=8)
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


session = call("POST", "/auth/session", {"actor": "operator", "credential": BOOTSTRAP_PASSWORD})
csrf = session["csrf_token"]
assert session["password_change_required"] is True

profile = call("PATCH", "/profile", {"display_name": "Administrador de ejemplo"})
assert profile["display_name"] == "Administrador de ejemplo"

password_result = call(
    "POST",
    "/profile/password",
    {"current_password": BOOTSTRAP_PASSWORD, "new_password": NEW_PASSWORD},
)
csrf = password_result["session"]["csrf_token"]
assert password_result["profile"]["password_change_required"] is False

setup = call("POST", "/profile/2fa/setup", {"current_password": NEW_PASSWORD})
assert setup["qr_data_url"].startswith("data:image/svg+xml;base64,")
totp_code = AccountSecurity._totp(setup["secret"], int(time.time()) // 30)
enabled = call("POST", "/profile/2fa/enable", {"code": totp_code})
csrf = enabled["session"]["csrf_token"]
assert enabled["profile"]["two_factor_enabled"] is True
assert len(enabled["recovery_codes"]) == 10

stored_text = "\n".join(
    path.read_text(encoding="utf-8", errors="ignore")
    for path in Path("/data").rglob("*")
    if path.is_file() and ".git" not in path.parts
)
assert BOOTSTRAP_PASSWORD not in stored_text
assert NEW_PASSWORD not in stored_text
assert setup["secret"] not in stored_text
assert enabled["recovery_codes"][0] not in stored_text

call("DELETE", "/auth/session", expected=204)
csrf = ""
challenge = call("POST", "/auth/session", {"actor": "operator", "credential": NEW_PASSWORD}, expected=401)
assert challenge["error"]["code"] == "TWO_FACTOR_REQUIRED"

totp_code = AccountSecurity._totp(setup["secret"], int(time.time()) // 30)
session = call("POST", "/auth/session", {"actor": "operator", "credential": NEW_PASSWORD, "otp": totp_code})
csrf = session["csrf_token"]
assert session["two_factor_enabled"] is True

totp_code = AccountSecurity._totp(setup["secret"], int(time.time()) // 30)
disabled = call(
    "POST",
    "/profile/2fa/disable",
    {"current_password": NEW_PASSWORD, "code": totp_code},
)
assert disabled["profile"]["two_factor_enabled"] is False

print(json.dumps({"status": "ok", "profile": profile["display_name"], "totp_round_trip": True}))
