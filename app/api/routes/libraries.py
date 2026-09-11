from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...auth import Identity
from ...permissions import ROLE_FULL_CONTROL, ROLE_OPERATOR
from ..admin import confirm_admin
from ..dependencies import (
    identity_library_role,
    public_document_meta,
    public_library,
    require_full_control,
    require_human_full_control,
    require_human_full_control_read,
    require_identity,
    require_library_access,
    require_operator,
    services,
)
from ..schemas import (
    CategoryCreate,
    CategoryOrderUpdate,
    CategoryUpdate,
    LibraryCreate,
    LibraryPermissionsUpdate,
    LibraryUpdate,
)


router = APIRouter(prefix="/libraries", tags=["libraries"])
categories_router = APIRouter(prefix="/categories", tags=["categories"])


def _public_tree(request: Request, identity: Identity, tree: dict[str, Any]) -> dict[str, Any]:
    def project_category(category: dict[str, Any]) -> dict[str, Any]:
        return {
            **category,
            "children": [project_category(child) for child in category.get("children", [])],
            "documents": [
                public_document_meta(request, identity, document)
                for document in category.get("documents", [])
            ],
        }

    return {
        "library": public_library(identity, tree["library"]),
        "categories": [project_category(category) for category in tree.get("categories", [])],
        "documents": [
            public_document_meta(request, identity, document)
            for document in tree.get("documents", [])
        ],
    }


@router.get("")
def list_libraries(request: Request, identity: Identity = Depends(require_identity)) -> dict:
    items = [
        public_library(identity, library)
        for library in services(request).store.list_libraries()
        if identity_library_role(identity, library) is not None
    ]
    return {"items": items}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_library(payload: LibraryCreate, request: Request, identity: Identity = Depends(require_operator)) -> dict:
    library = services(request).store.create_library(
        payload.name,
        identity.actor,
        payload.description,
        payload.icon,
        payload.color,
    )
    return public_library(identity, library)


@router.get("/{library_id}/permissions")
def get_library_permissions(
    library_id: str,
    request: Request,
    identity: Identity = Depends(require_human_full_control_read),
) -> dict:
    library = services(request).store.get_library(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada")
    policy = services(request).store.get_library_permissions(library_id)
    users = [
        user for user in services(request).store.list_users()
        if user.get("status") == "active"
    ]
    api_clients = [
        client for client in services(request).store.list_api_clients()
        if client.get("status") == "active" and not client.get("expired")
    ]
    return {
        "library": public_library(identity, library),
        "mode": policy["mode"],
        "grants": policy["grants"],
        "subjects": [*users, *api_clients],
    }


@router.put("/{library_id}/permissions")
def update_library_permissions(
    library_id: str,
    payload: LibraryPermissionsUpdate,
    request: Request,
    identity: Identity = Depends(require_human_full_control),
) -> dict:
    confirm_admin(request, identity, payload)
    try:
        policy = services(request).store.update_library_permissions(
            library_id,
            identity.actor,
            payload.mode,
            [grant.model_dump() for grant in payload.grants],
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"library_id": library_id, **policy}


@router.get("/{library_id}")
def get_library(library_id: str, request: Request, identity: Identity = Depends(require_identity)) -> dict:
    library, _ = require_library_access(request, identity, library_id)
    return public_library(identity, library)


@router.patch("/{library_id}")
def update_library(
    library_id: str,
    payload: LibraryUpdate,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_library_access(request, identity, library_id, ROLE_OPERATOR)
    try:
        library = services(request).store.update_library(
            library_id,
            identity.actor,
            **payload.model_dump(exclude_unset=True),
        )
        return public_library(identity, library)
    except KeyError:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada") from None


@router.delete("/{library_id}")
def delete_library(
    library_id: str,
    request: Request,
    identity: Identity = Depends(require_full_control),
) -> dict:
    require_library_access(request, identity, library_id, ROLE_FULL_CONTROL)
    try:
        library = services(request).store.delete_library(library_id, identity.actor)
        return public_library(identity, library)
    except KeyError:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{library_id}/tree")
def library_tree(library_id: str, request: Request, identity: Identity = Depends(require_identity)) -> dict:
    require_library_access(request, identity, library_id)
    try:
        return _public_tree(request, identity, services(request).store.library_tree(library_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada") from None


@router.post("/{library_id}/categories", status_code=status.HTTP_201_CREATED)
def create_category(
    library_id: str,
    payload: CategoryCreate,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_library_access(request, identity, library_id, ROLE_OPERATOR)
    try:
        return services(request).store.create_category(
            library_id,
            payload.name,
            identity.actor,
            payload.parent_id,
            payload.description,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/{library_id}/categories/order")
def reorder_categories(
    library_id: str,
    payload: CategoryOrderUpdate,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    require_library_access(request, identity, library_id, ROLE_OPERATOR)
    try:
        return services(request).store.reorder_categories(
            library_id,
            payload.parent_id,
            payload.category_ids,
            identity.actor,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@categories_router.patch("/{category_id}")
def update_category(
    category_id: str,
    payload: CategoryUpdate,
    request: Request,
    identity: Identity = Depends(require_operator),
) -> dict:
    category = services(request).store.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    require_library_access(request, identity, str(category["library_id"]), ROLE_OPERATOR)
    values = payload.model_dump(exclude_unset=True)
    parent_supplied = "parent_id" in payload.model_fields_set
    try:
        return services(request).store.update_category(
            category_id,
            identity.actor,
            parent_supplied=parent_supplied,
            **values,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@categories_router.delete("/{category_id}")
def delete_category(
    category_id: str,
    request: Request,
    identity: Identity = Depends(require_full_control),
) -> dict:
    category = services(request).store.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    require_library_access(request, identity, str(category["library_id"]), ROLE_FULL_CONTROL)
    try:
        return services(request).store.delete_category(category_id, identity.actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
