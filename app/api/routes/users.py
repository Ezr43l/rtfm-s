from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...accounts import normalize_display_name, normalize_username
from ...auth import Identity
from ..admin import confirm_admin
from ..dependencies import require_human_full_control, require_human_full_control_read, services
from ..schemas import (
    ApiClientCreate,
    ApiClientTokenAction,
    ApiClientUpdate,
    UserAccessUpdate,
    UserCreate,
    UserPasswordReset,
)


router = APIRouter(prefix="/users", tags=["users and API access"])


def expires_value(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if value <= datetime.now(timezone.utc):
        raise ValueError("La caducidad del acceso API debe estar en el futuro")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("")
def list_users(request: Request, _: Identity = Depends(require_human_full_control_read)) -> dict:
    return {"items": services(request).store.list_users()}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, request: Request, identity: Identity = Depends(require_human_full_control)) -> dict:
    container = services(request)
    confirm_admin(request, identity, payload)
    try:
        username = normalize_username(payload.username)
        display_name = normalize_display_name(payload.display_name)
        container.account_security.validate_password(payload.password, username)
        return container.store.create_user(
            username,
            display_name,
            container.account_security.hash_password(payload.password),
            payload.role,
            identity.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{user_id}")
def update_user_access(
    user_id: str,
    payload: UserAccessUpdate,
    request: Request,
    identity: Identity = Depends(require_human_full_control),
) -> dict:
    confirm_admin(request, identity, payload)
    if payload.username is None and payload.display_name is None and payload.role is None and payload.status is None:
        raise HTTPException(status_code=422, detail="No se ha indicado ningun cambio")
    try:
        username = normalize_username(payload.username) if payload.username is not None else None
        display_name = normalize_display_name(payload.display_name) if payload.display_name is not None else None
        return services(request).store.update_user_access(
            user_id,
            identity.actor,
            username=username,
            display_name=display_name,
            role=payload.role,
            status=payload.status,
        )
    except ValueError as error:
        message = str(error)
        raise HTTPException(status_code=404 if "no existe" in message else 409, detail=message) from error


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: str,
    payload: UserPasswordReset,
    request: Request,
    identity: Identity = Depends(require_human_full_control),
) -> dict:
    container = services(request)
    confirm_admin(request, identity, payload)
    user = container.store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="La cuenta no existe")
    try:
        container.account_security.validate_password(payload.new_password, str(user.get("username", "")))
        return container.store.reset_user_password(
            user_id,
            identity.actor,
            container.account_security.hash_password(payload.new_password),
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/api-clients")
def list_api_clients(request: Request, _: Identity = Depends(require_human_full_control_read)) -> dict:
    return {"items": services(request).store.list_api_clients()}


@router.post("/api-clients", status_code=status.HTTP_201_CREATED)
def create_api_client(
    payload: ApiClientCreate,
    request: Request,
    identity: Identity = Depends(require_human_full_control),
) -> dict:
    container = services(request)
    confirm_admin(request, identity, payload)
    client_id = str(uuid.uuid4())
    token, token_hash, token_prefix = container.account_security.generate_api_token(client_id)
    try:
        item = container.store.create_api_client(
            client_id,
            payload.name,
            payload.description,
            payload.role,
            token_hash,
            token_prefix,
            expires_value(payload.expires_at),
            identity.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"item": item, "token": token}


@router.patch("/api-clients/{client_id}")
def update_api_client(
    client_id: str,
    payload: ApiClientUpdate,
    request: Request,
    identity: Identity = Depends(require_human_full_control),
) -> dict:
    confirm_admin(request, identity, payload)
    try:
        return services(request).store.update_api_client(
            client_id,
            identity.actor,
            name=payload.name,
            description=payload.description,
            role=payload.role,
            status=payload.status,
            expires_at=expires_value(payload.expires_at),
            expires_at_supplied="expires_at" in payload.model_fields_set,
        )
    except ValueError as error:
        message = str(error)
        raise HTTPException(status_code=404 if "no existe" in message else 409, detail=message) from error


@router.post("/api-clients/{client_id}/rotate")
def rotate_api_client(
    client_id: str,
    payload: ApiClientTokenAction,
    request: Request,
    identity: Identity = Depends(require_human_full_control),
) -> dict:
    container = services(request)
    confirm_admin(request, identity, payload)
    if not container.store.get_api_client(client_id):
        raise HTTPException(status_code=404, detail="El acceso API no existe")
    token, token_hash, token_prefix = container.account_security.generate_api_token(client_id)
    item = container.store.rotate_api_client_token(client_id, identity.actor, token_hash, token_prefix)
    return {"item": item, "token": token}


@router.post("/api-clients/{client_id}/revoke")
def revoke_api_client(
    client_id: str,
    payload: ApiClientTokenAction,
    request: Request,
    identity: Identity = Depends(require_human_full_control),
) -> dict:
    confirm_admin(request, identity, payload)
    try:
        return services(request).store.revoke_api_client(client_id, identity.actor)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
