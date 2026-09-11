from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Response

from ..auth import COOKIE_NAME, Identity
from ..permissions import normalize_access_role
from ..services import Services


def session_payload(identity: Identity, user: dict | None = None) -> dict:
    totp = (user or {}).get("totp") or {}
    return {
        "actor": identity.actor,
        "display_name": (user or {}).get("display_name") or identity.display_name or identity.actor,
        "user_id": identity.user_id,
        "role": normalize_access_role((user or {}).get("role") or identity.role),
        "identity_type": identity.identity_type,
        "two_factor_enabled": bool(totp.get("enabled")),
        "password_change_required": bool((user or {}).get("password_change_required", False)),
        "csrf_token": identity.csrf_token,
        "expires_at": datetime.fromtimestamp(identity.expires_at, timezone.utc).isoformat().replace("+00:00", "Z")
        if identity.expires_at
        else None,
        "method": identity.method,
    }


def issue_session(response: Response, container: Services, user: dict) -> dict:
    token, identity = container.sessions.create(
        str(user["username"]),
        str(user["id"]),
        int(user.get("session_version", 1)),
        str(user.get("display_name", "")),
        normalize_access_role(user.get("role")),
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=container.settings.session_hours * 3600,
        httponly=True,
        secure=container.settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    return session_payload(identity, user)
