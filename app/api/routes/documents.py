from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from ...auth import Identity
from ...permissions import ROLE_FULL_CONTROL, ROLE_OPERATOR
from ..dependencies import (
    document_effective_role,
    public_document_meta,
    require_document_access,
    require_full_control,
    require_identity,
    require_library_access,
    require_operator,
    services,
)
from ..schemas import DocumentCreate, DocumentImageCreate, DocumentMove, DocumentUpdate


router = APIRouter(prefix="/documents", tags=["documents"])


def _public_record(request: Request, identity: Identity, document: dict) -> dict:
    return {
        **document,
        "meta": public_document_meta(request, identity, document["meta"]),
    }


@router.get("")
def list_documents(
    request: Request,
    include_deleted: bool = Query(False),
    library_id: str | None = None,
    category_id: str | None = None,
    document_status: str | None = Query(default=None, alias="status"),
    query: str | None = None,
    identity: Identity = Depends(require_identity),
) -> dict:
    if library_id is not None:
        require_library_access(request, identity, library_id)
    items = services(request).store.list_documents(
        include_deleted=include_deleted,
        library_id=library_id,
        category_id=category_id,
        status=document_status,
        query=query,
    )
    return {
        "items": [
            public_document_meta(request, identity, item)
            for item in items
            if document_effective_role(request, identity, item) is not None
        ]
    }


@router.get("/{document_id}")
def get_document(document_id: str, request: Request, identity: Identity = Depends(require_identity)) -> dict:
    document, _ = require_document_access(request, identity, document_id)
    return _public_record(request, identity, document)


@router.get("/{document_id}/images")
def list_document_images(
    document_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
) -> dict:
    require_document_access(request, identity, document_id, include_deleted=False)
    try:
        return {"items": services(request).store.list_images(document_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None


@router.post("/{document_id}/images", status_code=status.HTTP_201_CREATED)
def upload_document_image(
    document_id: str,
    payload: DocumentImageCreate,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_document_access(request, identity, document_id, ROLE_OPERATOR, include_deleted=False)
    try:
        content = base64.b64decode(payload.data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="La imagen no contiene datos Base64 validos") from None
    maximum = services(request).settings.max_image_size_mb * 1024 * 1024
    if len(content) > maximum:
        raise HTTPException(
            status_code=413,
            detail=f"La imagen supera el limite configurado de {services(request).settings.max_image_size_mb} MB",
        )
    try:
        return services(request).store.add_image(
            document_id,
            payload.filename,
            payload.media_type,
            content,
            identity.actor,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{document_id}/images/{image_id}", name="document-image")
def get_document_image(
    document_id: str,
    image_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
) -> FileResponse:
    require_document_access(request, identity, document_id, include_deleted=False)
    try:
        path, image = services(request).store.get_image_file(document_id, image_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Imagen no encontrada") from None
    return FileResponse(
        path,
        media_type=image["media_type"],
        filename=image["filename"],
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_library_access(request, identity, payload.library_id, ROLE_OPERATOR)
    try:
        document = services(request).store.create(
            payload.title,
            payload.content,
            identity.actor,
            library_id=payload.library_id,
            category_id=payload.category_id,
            summary=payload.summary,
            tags=payload.tags,
        )
        return _public_record(request, identity, document)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{document_id}")
def update_document(
    document_id: str,
    payload: DocumentUpdate,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_document_access(request, identity, document_id, ROLE_OPERATOR, include_deleted=False)
    try:
        document = services(request).store.update(
            document_id,
            identity.actor,
            **payload.model_dump(exclude_unset=True),
        )
        return _public_record(request, identity, document)
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None


@router.post("/{document_id}/move")
def move_document(
    document_id: str,
    payload: DocumentMove,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_document_access(request, identity, document_id, ROLE_OPERATOR, include_deleted=False)
    require_library_access(request, identity, payload.library_id, ROLE_OPERATOR)
    try:
        document = services(request).store.move_document(
            document_id,
            identity.actor,
            payload.library_id,
            payload.category_id,
            payload.position,
        )
        return _public_record(request, identity, document)
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{document_id}/archive")
def archive_document(
    document_id: str,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_document_access(request, identity, document_id, ROLE_OPERATOR, include_deleted=False)
    try:
        return _public_record(request, identity, services(request).store.archive(document_id, identity.actor))
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None


@router.post("/{document_id}/unarchive")
def unarchive_document(
    document_id: str,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_document_access(request, identity, document_id, ROLE_OPERATOR, include_deleted=False)
    try:
        return _public_record(request, identity, services(request).store.unarchive(document_id, identity.actor))
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento archivado no encontrado") from None


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    request: Request,
    identity: Identity = Depends(require_full_control),
) -> dict:
    require_document_access(request, identity, document_id, ROLE_FULL_CONTROL, include_deleted=False)
    try:
        return _public_record(request, identity, services(request).store.delete(document_id, identity.actor))
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from None


@router.post("/{document_id}/restore")
def restore_document(
    document_id: str,
    request: Request,
    identity: Identity = Depends(require_full_control),
) -> dict:
    require_document_access(request, identity, document_id, ROLE_FULL_CONTROL)
    try:
        return _public_record(request, identity, services(request).store.restore(document_id, identity.actor))
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento eliminado no encontrado") from None
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="El contenido ya no esta disponible en el vault") from None


@router.get("/meta/tags/all")
def list_tags(request: Request, identity: Identity = Depends(require_identity)) -> dict:
    counts: dict[str, int] = {}
    documents = services(request).store.list_documents(include_deleted=False)
    for document in documents:
        if document_effective_role(request, identity, document) is None:
            continue
        for tag in document.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    return {
        "items": [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: item[0].casefold())
        ]
    }
