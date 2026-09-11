from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...accounts import normalize_display_name, normalize_username
from ...auth import Identity
from ..dependencies import require_identity, require_mutation, services
from ..schemas import (
    PasswordChange,
    ProfileUpdate,
    RecoveryCodesRegenerate,
    TwoFactorDisable,
    TwoFactorEnable,
    TwoFactorSetup,
)
from ..session import issue_session
from .auth import problem


router = APIRouter(prefix="/profile", tags=["profile"])


def session_user(request: Request, identity: Identity) -> tuple[object, dict]:
    if identity.method != "session" or not identity.user_id:
        raise problem(403, "SESSION_REQUIRED", "Esta operación requiere una sesión de usuario")
    container = services(request)
    user = container.store.get_user(identity.user_id)
    if not user:
        raise problem(404, "PROFILE_NOT_FOUND", "El perfil de usuario no existe")
    return container, user


def profile_payload(container: object, user: dict) -> dict:
    public = container.store.public_user(user)
    public["password_policy"] = {
        "minimum_length": container.settings.password_min_length,
        "maximum_length": 256,
    }
    return public


def verify_password(container: object, user: dict, password: str) -> None:
    if not container.account_security.verify_password(password, str(user.get("password_hash", ""))):
        raise problem(401, "CURRENT_PASSWORD_INVALID", "La contraseña actual no es válida")


def verify_sensitive_second_factor(container: object, user: dict, code: str | None, actor: str) -> dict:
    if not (user.get("totp") or {}).get("enabled"):
        return user
    if not code:
        raise problem(401, "TWO_FACTOR_REQUIRED", "Esta operación requiere un código 2FA")
    verification = container.account_security.verify_second_factor(user, code)
    if not verification:
        raise problem(401, "INVALID_SECOND_FACTOR", "El código de verificación no es válido")
    method, recovery_index = verification
    if method == "recovery" and recovery_index is not None:
        return container.store.consume_recovery_code(str(user["id"]), actor, recovery_index)
    return user


@router.get("")
def get_profile(request: Request, identity: Identity = Depends(require_identity)) -> dict:
    container, user = session_user(request, identity)
    return profile_payload(container, user)


@router.patch("")
def update_profile(
    payload: ProfileUpdate,
    request: Request,
    identity: Identity = Depends(require_mutation),
) -> dict:
    container, user = session_user(request, identity)
    try:
        username = normalize_username(payload.username) if payload.username is not None else None
        display_name = normalize_display_name(payload.display_name) if payload.display_name is not None else None
    except ValueError as error:
        raise problem(422, "INVALID_PROFILE", str(error)) from error
    if username is None and display_name is None:
        raise problem(422, "PROFILE_UNCHANGED", "No se ha indicado ningún dato para modificar")
    if username is not None and username.casefold() != str(user.get("username", "")).casefold():
        if not payload.current_password:
            raise problem(401, "CURRENT_PASSWORD_REQUIRED", "Confirma tu contraseña para cambiar el usuario")
        verify_password(container, user, payload.current_password)
    try:
        updated = container.store.update_user_profile(
            str(user["id"]),
            identity.actor,
            username=username,
            display_name=display_name,
        )
    except ValueError as error:
        raise problem(409, "PROFILE_CONFLICT", str(error)) from error
    return profile_payload(container, updated)


@router.post("/password")
def change_password(
    payload: PasswordChange,
    request: Request,
    response: Response,
    identity: Identity = Depends(require_mutation),
) -> dict:
    container, user = session_user(request, identity)
    verify_password(container, user, payload.current_password)
    user = verify_sensitive_second_factor(container, user, payload.otp, identity.actor)
    try:
        container.account_security.validate_password(payload.new_password, str(user.get("username", "")))
    except ValueError as error:
        raise problem(422, "WEAK_PASSWORD", str(error)) from error
    if container.account_security.verify_password(payload.new_password, str(user.get("password_hash", ""))):
        raise problem(422, "PASSWORD_UNCHANGED", "La nueva contraseña debe ser distinta de la actual")
    updated = container.store.update_user_password(
        str(user["id"]),
        identity.actor,
        container.account_security.hash_password(payload.new_password),
    )
    return {
        "profile": profile_payload(container, updated),
        "session": issue_session(response, container, updated),
    }


@router.post("/2fa/setup")
def setup_two_factor(
    payload: TwoFactorSetup,
    request: Request,
    identity: Identity = Depends(require_mutation),
) -> dict:
    container, user = session_user(request, identity)
    verify_password(container, user, payload.current_password)
    if (user.get("totp") or {}).get("enabled"):
        raise problem(409, "TWO_FACTOR_ALREADY_ENABLED", "La autenticación en dos pasos ya está activa")
    secret = container.account_security.generate_totp_secret()
    container.store.set_pending_totp(str(user["id"]), identity.actor, container.account_security.encrypt(secret))
    uri = container.account_security.provisioning_uri(str(user["username"]), secret)
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_data_url": container.account_security.qr_data_url(uri),
        "issuer": container.settings.totp_issuer,
    }


@router.delete("/2fa/setup", status_code=204)
def cancel_two_factor_setup(
    request: Request,
    identity: Identity = Depends(require_mutation),
) -> Response:
    container, user = session_user(request, identity)
    container.store.set_pending_totp(str(user["id"]), identity.actor, None)
    return Response(status_code=204)


@router.post("/2fa/enable")
def enable_two_factor(
    payload: TwoFactorEnable,
    request: Request,
    response: Response,
    identity: Identity = Depends(require_mutation),
) -> dict:
    container, user = session_user(request, identity)
    totp = user.get("totp") or {}
    pending = totp.get("pending_secret")
    if not pending:
        raise problem(409, "TWO_FACTOR_SETUP_MISSING", "Inicia primero la configuración 2FA")
    try:
        secret = container.account_security.decrypt(pending)
    except ValueError as error:
        raise problem(409, "TWO_FACTOR_SETUP_INVALID", str(error)) from error
    if not container.account_security.verify_totp(secret, payload.code):
        raise problem(401, "INVALID_SECOND_FACTOR", "El código no coincide; comprueba la hora del dispositivo")
    recovery_codes = container.account_security.generate_recovery_codes()
    hashes = [container.account_security.hash_recovery_code(code) for code in recovery_codes]
    updated = container.store.enable_totp(str(user["id"]), identity.actor, hashes)
    return {
        "profile": profile_payload(container, updated),
        "session": issue_session(response, container, updated),
        "recovery_codes": recovery_codes,
    }


@router.post("/2fa/disable")
def disable_two_factor(
    payload: TwoFactorDisable,
    request: Request,
    response: Response,
    identity: Identity = Depends(require_mutation),
) -> dict:
    container, user = session_user(request, identity)
    verify_password(container, user, payload.current_password)
    if not (user.get("totp") or {}).get("enabled"):
        raise problem(409, "TWO_FACTOR_NOT_ENABLED", "La autenticación en dos pasos no está activa")
    verify_sensitive_second_factor(container, user, payload.code, identity.actor)
    updated = container.store.disable_totp(str(user["id"]), identity.actor)
    return {
        "profile": profile_payload(container, updated),
        "session": issue_session(response, container, updated),
    }


@router.post("/2fa/recovery-codes")
def regenerate_recovery_codes(
    payload: RecoveryCodesRegenerate,
    request: Request,
    identity: Identity = Depends(require_mutation),
) -> dict:
    container, user = session_user(request, identity)
    verify_password(container, user, payload.current_password)
    if not (user.get("totp") or {}).get("enabled"):
        raise problem(409, "TWO_FACTOR_NOT_ENABLED", "La autenticación en dos pasos no está activa")
    user = verify_sensitive_second_factor(container, user, payload.code, identity.actor)
    recovery_codes = container.account_security.generate_recovery_codes()
    hashes = [container.account_security.hash_recovery_code(code) for code in recovery_codes]
    updated = container.store.replace_recovery_codes(str(user["id"]), identity.actor, hashes)
    return {
        "profile": profile_payload(container, updated),
        "recovery_codes": recovery_codes,
    }
