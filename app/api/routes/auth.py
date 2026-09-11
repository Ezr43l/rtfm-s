from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...accounts import normalize_display_name, normalize_username
from ...auth import COOKIE_NAME, Identity
from ..dependencies import require_identity, services
from ..schemas import SessionCreate
from ..session import issue_session, session_payload


router = APIRouter(prefix="/auth", tags=["authentication"])


def problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def rejected(request: Request, actor: str, reason: str, throttle_key: str) -> None:
    container = services(request)
    container.login_throttle.record_failure(throttle_key)
    container.store.record_system_operation(
        "auth.login_rejected",
        f"anonymous:{actor[:80]}",
        {"reason": reason},
    )


@router.post("/session")
def create_session(payload: SessionCreate, request: Request, response: Response) -> dict:
    container = services(request)
    if not container.sessions.available or not container.account_security.available:
        raise problem(503, "AUTH_NOT_CONFIGURED", "El acceso todavía no está configurado")

    throttle_key = container.login_throttle.key(
        request.client.host if request.client else None,
        payload.actor,
    )
    retry_after = container.login_throttle.retry_after(throttle_key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "LOGIN_RATE_LIMITED",
                "message": "Demasiados intentos; espera antes de volver a identificarte",
            },
            headers={"Retry-After": str(retry_after)},
        )

    user = container.store.find_user_by_username(payload.actor)
    bootstrap = False
    if not container.store.has_users():
        if not container.settings.app_token:
            raise problem(503, "AUTH_NOT_CONFIGURED", "Falta la credencial inicial para crear la cuenta propietaria")
        if not container.sessions.credential_matches(payload.credential, container.settings.app_token):
            rejected(request, payload.actor, "invalid_bootstrap_credential", throttle_key)
            raise problem(401, "INVALID_CREDENTIALS", "Usuario o contraseña no válidos")
        try:
            username = normalize_username(payload.actor)
            display_name = normalize_display_name(payload.actor)
        except ValueError as error:
            raise problem(422, "INVALID_PROFILE", str(error)) from error
        user = container.store.create_owner(
            username,
            display_name,
            container.account_security.hash_password(payload.credential),
            username,
        )
        bootstrap = True

    if not user or user.get("status", "active") != "active" or not container.account_security.verify_password(payload.credential, str(user.get("password_hash", ""))):
        rejected(request, payload.actor, "invalid_credentials", throttle_key)
        raise problem(401, "INVALID_CREDENTIALS", "Usuario o contraseña no válidos")

    second_factor_method: str | None = None
    if (user.get("totp") or {}).get("enabled"):
        if not payload.otp:
            raise problem(401, "TWO_FACTOR_REQUIRED", "Introduce el código de tu aplicación 2FA o un código de recuperación")
        verification = container.account_security.verify_second_factor(user, payload.otp)
        if not verification:
            rejected(request, payload.actor, "invalid_second_factor", throttle_key)
            raise problem(401, "INVALID_SECOND_FACTOR", "El código de verificación no es válido")
        second_factor_method, recovery_index = verification
        if second_factor_method == "recovery" and recovery_index is not None:
            user = container.store.consume_recovery_code(
                str(user["id"]),
                str(user["username"]),
                recovery_index,
            )

    payload_out = issue_session(response, container, user)
    container.login_throttle.clear(throttle_key)
    method = "bootstrap" if bootstrap else "password"
    if second_factor_method:
        method += f"+{second_factor_method}"
    container.store.record_system_operation("auth.login", str(user["username"]), {"method": method})
    return payload_out


@router.get("/session")
def current_session(request: Request, identity: Identity = Depends(require_identity)) -> dict:
    user = services(request).store.get_user(identity.user_id) if identity.user_id else None
    return session_payload(identity, user)


@router.delete("/session", status_code=204)
def delete_session(request: Request, response: Response, identity: Identity = Depends(require_identity)) -> Response:
    services(request).store.record_system_operation("auth.logout", identity.actor, {"method": identity.method})
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response
