from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...auth import Identity
from ..dependencies import (
    document_effective_role,
    public_document_meta,
    require_document_access,
    require_human_mutation,
    require_identity,
    services,
)


router = APIRouter(prefix="/favorites", tags=["favorites"])


def _personal_identity(identity: Identity) -> str:
    if identity.identity_type != "person" or not identity.user_id:
        raise HTTPException(status_code=403, detail="Los favoritos pertenecen a perfiles personales")
    return identity.user_id


@router.get("")
def list_favorites(request: Request, identity: Identity = Depends(require_identity)) -> dict:
    items = services(request).store.list_favorite_documents(_personal_identity(identity))
    return {
        "items": [
            public_document_meta(request, identity, item)
            for item in items
            if document_effective_role(request, identity, item) is not None
        ]
    }


@router.put("/{document_id}")
def add_favorite(
    document_id: str,
    request: Request,
    identity: Identity = Depends(require_human_mutation),
) -> dict:
    require_document_access(request, identity, document_id, include_deleted=False)
    try:
        result = services(request).store.set_document_favorite(
            _personal_identity(identity), document_id, True, identity.actor
        )
        result["document"] = public_document_meta(request, identity, result["document"])
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None


@router.delete("/{document_id}")
def remove_favorite(
    document_id: str,
    request: Request,
    identity: Identity = Depends(require_human_mutation),
) -> dict:
    require_document_access(request, identity, document_id, include_deleted=False)
    try:
        result = services(request).store.set_document_favorite(
            _personal_identity(identity), document_id, False, identity.actor
        )
        result["document"] = public_document_meta(request, identity, result["document"])
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None
