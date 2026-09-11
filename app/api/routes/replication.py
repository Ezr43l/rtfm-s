from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ...auth import Identity
from ...replication import ReplicationError, sync_once_async, validate_incoming_bundle
from ...roles import ROLE_ACTIVE
from ..dependencies import require_full_control, require_replication, services
from .system import status_payload


router = APIRouter(prefix="/sync", tags=["replication"])
internal_router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("")
async def manual_sync(request: Request, identity: Identity = Depends(require_full_control)) -> dict[str, Any]:
    container = services(request)
    return await sync_once_async(container.store, container.settings, container.role().role, identity.actor)


@internal_router.post("/receive")
async def receive(request: Request, _: None = Depends(require_replication)) -> dict[str, Any]:
    container = services(request)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="La réplica debe usar application/json")
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            if int(raw_length) > container.settings.max_replication_bytes:
                raise HTTPException(status_code=413, detail="El bundle supera MAX_REPLICATION_MB")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Content-Length no válido") from error
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > container.settings.max_replication_bytes:
            raise HTTPException(status_code=413, detail="El bundle supera MAX_REPLICATION_MB")
    try:
        bundle = validate_incoming_bundle(json.loads(body), container.settings)
    except (json.JSONDecodeError, UnicodeDecodeError, ReplicationError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    declared_source = request.headers.get("X-RTFM-Source-Node")
    if declared_source and declared_source != bundle["node"]:
        raise HTTPException(status_code=400, detail="La identidad de origen no coincide con el bundle")
    if container.role().role == ROLE_ACTIVE:
        raise HTTPException(status_code=409, detail="El receptor es activo; no acepta un snapshot pasivo")
    had_newer = container.store.local_newer_than(bundle)
    result = container.store.merge_bundle(bundle)
    container.store.record_system_operation("receive_replication", "system:replication", {"from": bundle.get("node"), **result})
    response: dict[str, Any] = {"status": "applied", **result}
    if had_newer:
        response["newer_bundle"] = container.store.export_bundle()
    return response


@internal_router.get("/status")
def internal_status(request: Request, _: None = Depends(require_replication)) -> dict[str, Any]:
    return status_payload(request)
