from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from .roles import ROLE_ACTIVE
from .settings import Settings
from .storage import DocumentStore, utc_now
from .version import USER_AGENT


class ReplicationError(ValueError):
    """Un bundle o transporte de réplica no cumple el contrato seguro."""


def validate_incoming_bundle(bundle: Any, settings: Settings) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise ReplicationError("El bundle debe ser un objeto JSON")
    if bundle.get("schema_version") != 6:
        raise ReplicationError("Versión de esquema de réplica no compatible")
    source = bundle.get("node")
    if not isinstance(source, str) or source not in settings.peers:
        raise ReplicationError("El bundle no procede de un nodo declarado en PEERS")
    if source == settings.node_name:
        raise ReplicationError("El nodo local no puede replicarse a sí mismo")
    for field in (
        "libraries",
        "categories",
        "users",
        "api_clients",
        "documents",
        "vault",
        "audit",
    ):
        value = bundle.get(field)
        if not isinstance(value, list):
            raise ReplicationError(f"El campo {field} debe ser una lista")
    try:
        clock = int(bundle.get("clock", 0))
    except (TypeError, ValueError) as error:
        raise ReplicationError("El reloj lógico del bundle no es válido") from error
    if clock < 0:
        raise ReplicationError("El reloj lógico del bundle no puede ser negativo")
    return bundle


def _ssl_context(settings: Settings, url: str) -> ssl.SSLContext | None:
    if urlsplit(url).scheme != "https":
        return None
    ca_file = settings.replication_ca_file
    if ca_file and not ca_file.is_file():
        raise ReplicationError("No existe la CA configurada para la réplica")
    return ssl.create_default_context(cafile=str(ca_file) if ca_file else None)


def _post_json(
    url: str,
    payload: dict[str, Any],
    settings: Settings,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) > settings.max_replication_bytes:
        return 0, {"detail": "El bundle supera MAX_REPLICATION_MB"}
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Replication-Token": settings.replication_token,
            "X-RTFM-Source-Node": settings.node_name,
            "User-Agent": USER_AGENT,
        },
    )
    response_limit = 2 * 1024 * 1024
    try:
        # Settings._peers validates the complete base URL as HTTP(S) and
        # rejects credentials, queries and fragments at startup.
        with urllib.request.urlopen(  # nosec B310
            request,
            timeout=30,
            context=_ssl_context(settings, url),
        ) as response:
            raw = response.read(response_limit + 1)
            if len(raw) > response_limit:
                return 0, {"detail": "La respuesta de réplica supera 2 MiB"}
            return response.status, json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        raw = error.read(response_limit + 1).decode("utf-8", errors="replace")
        if len(raw) > response_limit:
            raw = "respuesta de error demasiado grande"
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"detail": raw[:2000]}
        return error.code, detail
    except (OSError, TimeoutError, ReplicationError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return 0, {"detail": f"{type(error).__name__}: {str(error)[:500]}"}


def sync_once(
    store: DocumentStore,
    settings: Settings,
    role: str,
    actor: str = "system:replication",
) -> dict[str, Any]:
    if role != ROLE_ACTIVE:
        return {"status": "skipped", "reason": "el nodo no es activo"}
    if not settings.peers:
        return {"status": "skipped", "reason": "no hay pares configurados"}
    if not settings.replication_token:
        return {"status": "blocked", "reason": "REPLICATION_TOKEN no configurado"}

    bundle = store.export_bundle()
    results: dict[str, Any] = {}
    for peer, base_url in settings.peers.items():
        status_code, response = _post_json(
            f"{base_url}/api/internal/receive",
            bundle,
            settings,
        )
        result = {
            "at": utc_now(),
            "status_code": status_code,
            "ok": 200 <= status_code < 300,
            "response": response,
        }
        newer_bundle = response.get("newer_bundle") if isinstance(response, dict) else None
        if newer_bundle:
            try:
                validate_incoming_bundle(newer_bundle, settings)
                result["reconciled_from_peer"] = store.merge_bundle(newer_bundle)
            except ReplicationError as error:
                result["reconciliation_error"] = str(error)
                result["ok"] = False
        store.set_peer_status(peer, result)
        results[peer] = result
    outcome = {"status": "completed", "peers": results}
    store.record_system_operation("sync", actor, outcome)
    return outcome


async def sync_once_async(
    store: DocumentStore,
    settings: Settings,
    role: str,
    actor: str = "system:replication",
) -> dict[str, Any]:
    return await asyncio.to_thread(sync_once, store, settings, role, actor)
