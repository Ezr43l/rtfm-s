from __future__ import annotations

import hmac
from typing import Any

from fastapi import Header, HTTPException, Request

from ..auth import COOKIE_NAME, Identity
from ..permissions import (
    ROLE_FULL_CONTROL,
    ROLE_OPERATOR,
    ROLE_READER,
    effective_library_role,
    library_role_allows,
    normalize_access_role,
    normalize_library_access,
    role_allows,
)
from ..roles import ROLE_ACTIVE


def services(request: Request):
    return request.app.state.services


def identity_library_role(identity: Identity, library: dict[str, Any]) -> str | None:
    return effective_library_role(
        identity.role,
        identity.identity_type,
        identity.user_id,
        identity.api_client_id,
        library,
    )


def public_library(identity: Identity, library: dict[str, Any]) -> dict[str, Any]:
    policy = normalize_library_access(library.get("access"))
    result = {key: value for key, value in library.items() if key != "access"}
    result["access_mode"] = policy["mode"]
    result["effective_role"] = identity_library_role(identity, library)
    return result


def require_library_access(
    request: Request,
    identity: Identity,
    library_id: str,
    required: str = ROLE_READER,
) -> tuple[dict[str, Any], str]:
    library = services(request).store.get_library(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada")
    effective_role = identity_library_role(identity, library)
    if effective_role is None:
        # Deliberately hide restricted library identifiers from non-members.
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada")
    if not library_role_allows(effective_role, required):
        raise HTTPException(status_code=403, detail="Tu permiso en esta biblioteca no permite la operacion")
    return library, effective_role


def visible_library_ids(request: Request, identity: Identity) -> set[str]:
    return {
        str(library["id"])
        for library in services(request).store.list_libraries(include_counts=False)
        if identity_library_role(identity, library) is not None
    }


def document_effective_role(request: Request, identity: Identity, meta: dict[str, Any]) -> str | None:
    library_id = str(meta.get("library_id") or "")
    if not library_id:
        return normalize_access_role(identity.role)
    library = services(request).store.get_library(library_id)
    return identity_library_role(identity, library) if library else None


def public_document_meta(request: Request, identity: Identity, meta: dict[str, Any]) -> dict[str, Any]:
    result = dict(meta)
    result["effective_role"] = document_effective_role(request, identity, meta)
    return result


def require_document_access(
    request: Request,
    identity: Identity,
    document_id: str,
    required: str = ROLE_READER,
    *,
    include_deleted: bool = True,
) -> tuple[dict[str, Any], str]:
    document = services(request).store.get_document(document_id, include_deleted=include_deleted)
    if not document:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    effective_role = document_effective_role(request, identity, document["meta"])
    if effective_role is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if not library_role_allows(effective_role, required):
        raise HTTPException(status_code=403, detail="Tu permiso en esta biblioteca no permite la operacion")
    return document, effective_role


def require_identity(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> Identity:
    container = services(request)
    if authorization and authorization.startswith("Bearer "):
        candidate = authorization.removeprefix("Bearer ").strip()
        if container.settings.app_token and hmac.compare_digest(candidate, container.settings.app_token):
            actor = (x_actor or "").strip()
            if not actor:
                raise HTTPException(status_code=400, detail="X-Actor es obligatorio para clientes API")
            actor = f"api:{actor}"[:200]
            if container.role().role == ROLE_ACTIVE:
                container.store.record_system_operation(
                    "api.request",
                    actor,
                    {"client_id": "legacy", "method": request.method, "path": request.url.path},
                )
            return Identity(
                actor,
                "",
                0,
                "legacy_bearer",
                role=ROLE_FULL_CONTROL,
                identity_type="api",
            )
        token_hash = container.account_security.hash_api_token(candidate)
        client = container.store.find_api_client_by_token_hash(token_hash)
        if not client:
            if container.role().role == ROLE_ACTIVE:
                container.store.record_system_operation(
                    "api.authentication_rejected",
                    "api:unknown",
                    {"method": request.method, "path": request.url.path},
                )
            raise HTTPException(status_code=401, detail="El token API no es valido, ha caducado o esta revocado")
        actor = f"api:{client.get('name', client.get('id'))}"[:200]
        if container.role().role == ROLE_ACTIVE:
            container.store.mark_api_client_used(str(client["id"]), request.client.host if request.client else None)
            container.store.record_system_operation(
                "api.request",
                actor,
                {"client_id": client["id"], "method": request.method, "path": request.url.path},
            )
        return Identity(
            actor,
            "",
            0,
            "api_token",
            role=normalize_access_role(client.get("role")),
            identity_type="api",
            api_client_id=str(client["id"]),
        )
    identity = container.sessions.parse(request.cookies.get(COOKIE_NAME))
    if not identity:
        raise HTTPException(status_code=401, detail="La sesión no es válida o ha caducado")
    if not identity.user_id:
        raise HTTPException(status_code=401, detail="La sesión pertenece al sistema de acceso anterior; vuelve a identificarte")
    user = container.store.get_user(identity.user_id)
    if not user or user.get("status") != "active":
        raise HTTPException(status_code=401, detail="La cuenta asociada a la sesión ya no está disponible")
    if int(user.get("session_version", 1)) != identity.session_version:
        raise HTTPException(status_code=401, detail="La sesión fue invalidada por un cambio de seguridad")
    return Identity(
        str(user.get("username", identity.actor))[:200],
        identity.csrf_token,
        identity.expires_at,
        identity.method,
        identity.user_id,
        identity.session_version,
        str(user.get("display_name", ""))[:120],
        normalize_access_role(user.get("role")),
        "person",
    )


def require_mutation(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Identity:
    identity = require_identity(request, authorization, x_actor)
    if identity.method == "session" and (not x_csrf_token or not hmac.compare_digest(x_csrf_token, identity.csrf_token)):
        raise HTTPException(status_code=403, detail="Protección CSRF: token ausente o no válido")
    role = services(request).role()
    if role.role != ROLE_ACTIVE:
        raise HTTPException(status_code=409, detail="Este nodo es pasivo; utiliza la IP flotante para escribir")
    return identity


def require_operator(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Identity:
    identity = require_mutation(request, authorization, x_actor, x_csrf_token)
    if not role_allows(identity.role, ROLE_OPERATOR):
        raise HTTPException(status_code=403, detail="Esta operacion requiere permisos de operador")
    return identity


def require_full_control(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Identity:
    identity = require_mutation(request, authorization, x_actor, x_csrf_token)
    if not role_allows(identity.role, ROLE_FULL_CONTROL):
        raise HTTPException(status_code=403, detail="Esta operacion requiere control total")
    return identity


def require_human_full_control(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Identity:
    identity = require_full_control(request, authorization, x_actor, x_csrf_token)
    if identity.identity_type != "person" or not identity.user_id:
        raise HTTPException(status_code=403, detail="La administracion de identidades requiere una cuenta personal")
    return identity


def require_human_mutation(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Identity:
    identity = require_mutation(request, authorization, x_actor, x_csrf_token)
    if identity.identity_type != "person" or not identity.user_id:
        raise HTTPException(status_code=403, detail="Esta operación pertenece a un perfil personal")
    return identity


def require_human_full_control_read(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> Identity:
    identity = require_identity(request, authorization, x_actor)
    if not role_allows(identity.role, ROLE_FULL_CONTROL):
        raise HTTPException(status_code=403, detail="Esta operacion requiere control total")
    if identity.identity_type != "person" or not identity.user_id:
        raise HTTPException(status_code=403, detail="La administracion de identidades requiere una cuenta personal")
    return identity


def require_replication(
    request: Request,
    x_replication_token: str | None = Header(default=None, alias="X-Replication-Token"),
) -> None:
    expected = services(request).settings.replication_token
    if not expected or not x_replication_token or not hmac.compare_digest(x_replication_token, expected):
        raise HTTPException(status_code=401, detail="Token de replicación no válido")
