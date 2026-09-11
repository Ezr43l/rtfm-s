from __future__ import annotations

from fastapi import HTTPException, Request

from ..auth import Identity
from .dependencies import services
from .schemas import AdminConfirmation


def confirm_admin(request: Request, identity: Identity, payload: AdminConfirmation) -> None:
    """Re-authenticate a human administrator before a sensitive change."""
    container = services(request)
    user = container.store.get_user(str(identity.user_id))
    if not user or not container.account_security.verify_password(
        payload.current_password,
        str(user.get("password_hash", "")),
    ):
        raise HTTPException(status_code=403, detail="La contrasena actual no es valida")
    if not (user.get("totp") or {}).get("enabled"):
        return
    if not payload.otp:
        raise HTTPException(status_code=403, detail="Esta operacion requiere tu codigo 2FA")
    verification = container.account_security.verify_second_factor(user, payload.otp)
    if not verification:
        raise HTTPException(status_code=403, detail="El codigo 2FA o de recuperacion no es valido")
    method, recovery_index = verification
    if method == "recovery" and recovery_index is not None:
        container.store.consume_recovery_code(str(user["id"]), identity.actor, recovery_index)
