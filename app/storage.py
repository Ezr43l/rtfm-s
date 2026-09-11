from __future__ import annotations

import json
import hmac
import binascii
import re
import shutil
import threading
import unicodedata
import uuid
from base64 import b64decode, b64encode, urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .permissions import (
    LIBRARY_ACCESS_OPEN,
    ROLE_FULL_CONTROL,
    normalize_access_role,
    normalize_library_access,
    validate_access_role,
    validate_library_access,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _version_key(version: dict[str, Any] | None) -> tuple[int, str, str]:
    version = version or {}
    return (int(version.get("clock", 0)), str(version.get("timestamp", "")), str(version.get("node", "")))


def _safe_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9-]{1,80}", value))


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    return slug[:120] or "sin-titulo"


IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def validate_image_content(media_type: str, content: bytes) -> str:
    normalized = media_type.strip().casefold()
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if normalized not in IMAGE_EXTENSIONS:
        raise ValueError("Formato no permitido. Utiliza PNG, JPEG, WebP o GIF")
    if not content or not signatures[normalized]:
        raise ValueError("El contenido no corresponde al formato de imagen declarado")
    return normalized


class DocumentStore:
    """Markdown files plus metadata, tombstones and append-only audit events."""

    def __init__(self, data_dir: Path, node_name: str, retention_days: int, git_repo: Any | None = None) -> None:
        self.data_dir = data_dir
        self.node_name = node_name
        self.retention_days = retention_days
        self.git_repo = git_repo
        self.docs_dir = data_dir / "docs"
        self.meta_dir = data_dir / "meta"
        self.images_dir = data_dir / "images"
        self.libraries_dir = data_dir / "catalog" / "libraries"
        self.categories_dir = data_dir / "catalog" / "categories"
        self.users_dir = data_dir / "auth" / "users"
        self.api_clients_dir = data_dir / "auth" / "api-clients"
        self.vault_dir = data_dir / "vault"
        self.audit_path = data_dir / "audit.jsonl"
        self.state_path = data_dir / "state.json"
        self.lock = threading.RLock()
        self.init()

    def init(self) -> None:
        for directory in (
            self.data_dir,
            self.docs_dir,
            self.meta_dir,
            self.images_dir,
            self.libraries_dir,
            self.categories_dir,
            self.users_dir,
            self.api_clients_dir,
            self.vault_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_json(self.state_path, {"clock": 0, "last_sync_at": None, "peers": {}})
        if self.git_repo:
            self.git_repo.sync_from_store(
                self,
                "chore: synchronize documental projection",
                f"Node: {self.node_name}\nSource: rtfm\n",
            )

    @staticmethod
    def _read_json(path: Path, default: Any = None) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def _state(self) -> dict[str, Any]:
        return self._read_json(self.state_path, {"clock": 0, "last_sync_at": None, "peers": {}})

    def _save_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_path, state)

    def _next_version(self) -> dict[str, Any]:
        state = self._state()
        state["clock"] = int(state.get("clock", 0)) + 1
        timestamp = utc_now()
        state["last_operation_at"] = timestamp
        self._save_state(state)
        return {"clock": state["clock"], "timestamp": timestamp, "node": self.node_name}

    def _observe_clock(self, remote_clock: int) -> None:
        state = self._state()
        if remote_clock > int(state.get("clock", 0)):
            state["clock"] = remote_clock
            self._save_state(state)

    def _meta_path(self, document_id: str) -> Path:
        return self.meta_dir / f"{document_id}.json"

    def _doc_path(self, document_id: str) -> Path:
        return self.docs_dir / f"{document_id}.md"

    def _document_images_dir(self, document_id: str) -> Path:
        if not _safe_identifier(document_id):
            raise ValueError("Identificador de documento no válido")
        return self.images_dir / document_id

    def _read_meta(self, document_id: str) -> dict[str, Any] | None:
        return self._read_json(self._meta_path(document_id))

    def _write_meta(self, meta: dict[str, Any]) -> None:
        self._write_json(self._meta_path(meta["id"]), meta)

    def _append_audit(self, event: dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _audit(
        self,
        action: str,
        actor: str,
        document_id: str | None,
        version: dict[str, Any],
        before: Any,
        after: Any,
        entity_type: str = "document",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        source = "replication" if action.startswith("receive_") or actor.startswith("system:replication") else "system" if actor.startswith("system:") else "api" if actor.startswith("api:") else "user"
        event = {
            "event_id": str(uuid.uuid4()),
            "operation_id": f"{version['node']}:{version['clock']}:{uuid.uuid4().hex[:8]}",
            "action": action,
            "source": source,
            "level": "info",
            "actor": actor,
            "document_id": document_id,
            "entity_type": entity_type,
            "entity_id": entity_id or document_id,
            "timestamp": version["timestamp"],
            "node": version["node"],
            "version": version,
            "before": before,
            "after": after,
            "result": "ok",
        }
        if self.git_repo and action in {"create", "update", "archive", "unarchive", "delete", "restore", "document.move", "document.image.upload"} and document_id:
            snapshot = self.get_document(document_id, include_deleted=True, include_image_data=True)
            try:
                event["git"] = self.git_repo.commit_document(event, snapshot)
            except Exception as error:
                event["git"] = {"status": "failed", "error": str(error)}
        elif self.git_repo and entity_type in {"library", "category"} and entity_id and after:
            try:
                event["git"] = self.git_repo.commit_catalog_entity(event, entity_type, after)
            except Exception as error:
                event["git"] = {"status": "failed", "error": str(error)}
        elif self.git_repo and entity_type == "category_order" and after:
            try:
                event["git"] = self.git_repo.commit_catalog_entities(event, "category", after.get("items") or [])
            except Exception as error:
                event["git"] = {"status": "failed", "error": str(error)}
        self._append_audit(event)
        return event

    def record_system_operation(self, action: str, actor: str, details: Any) -> dict[str, Any]:
        with self.lock:
            version = self._next_version()
            return self._audit(action, actor, None, version, None, details)

    def _entity_path(self, entity_type: str, entity_id: str) -> Path:
        if not _safe_identifier(entity_id):
            raise ValueError("Identificador no válido")
        directories = {
            "library": self.libraries_dir,
            "category": self.categories_dir,
            "user": self.users_dir,
            "api_client": self.api_clients_dir,
        }
        if entity_type not in directories:
            raise ValueError("Tipo de entidad no válido")
        return directories[entity_type] / f"{entity_id}.json"

    def _read_entity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        return self._read_json(self._entity_path(entity_type, entity_id))

    def _write_entity(self, entity_type: str, entity: dict[str, Any]) -> None:
        self._write_json(self._entity_path(entity_type, entity["id"]), entity)

    def _list_entities(self, entity_type: str, include_deleted: bool = False) -> list[dict[str, Any]]:
        directories = {
            "library": self.libraries_dir,
            "category": self.categories_dir,
            "user": self.users_dir,
            "api_client": self.api_clients_dir,
        }
        if entity_type not in directories:
            raise ValueError("Tipo de entidad no válido")
        directory = directories[entity_type]
        items: list[dict[str, Any]] = []
        for path in directory.glob("*.json"):
            entity = self._read_json(path)
            if not entity or (entity.get("status") == "deleted" and not include_deleted):
                continue
            items.append(entity)
        return sorted(
            items,
            key=lambda item: (
                int(item.get("position", 0)),
                str(item.get("name") or item.get("username") or "").casefold(),
            ),
        )

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        totp = user.get("totp") or {}
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "display_name": user.get("display_name"),
            "role": normalize_access_role(user.get("role", "owner")),
            "identity_type": "person",
            "status": user.get("status", "active"),
            "two_factor_enabled": bool(totp.get("enabled")),
            "two_factor_pending": bool(totp.get("pending_secret")),
            "recovery_codes_remaining": len(totp.get("recovery_code_hashes") or []),
            "password_change_required": bool(user.get("password_change_required", False)),
            "password_changed_at": user.get("password_changed_at"),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "updated_by": user.get("updated_by"),
            "session_version": int(user.get("session_version", 1)),
            "version": user.get("version"),
            "favorite_count": len(user.get("favorites") or {}),
        }

    def list_users(self, include_deleted: bool = False, public: bool = True) -> list[dict[str, Any]]:
        with self.lock:
            users = self._list_entities("user", include_deleted=include_deleted)
            return [self.public_user(user) for user in users] if public else users

    def has_users(self) -> bool:
        return bool(self.list_users(include_deleted=False, public=False))

    def get_user(self, user_id: str, include_deleted: bool = False, public: bool = False) -> dict[str, Any] | None:
        with self.lock:
            user = self._read_entity("user", user_id)
            if not user or (user.get("status") == "deleted" and not include_deleted):
                return None
            return self.public_user(user) if public else user

    def find_user_by_username(self, username: str) -> dict[str, Any] | None:
        expected = username.strip().casefold()
        with self.lock:
            for user in self._list_entities("user", include_deleted=False):
                if str(user.get("username", "")).casefold() == expected:
                    return user
        return None

    def _active_full_control_users(self) -> list[dict[str, Any]]:
        return [
            user
            for user in self._list_entities("user", include_deleted=False)
            if user.get("status", "active") == "active"
            and normalize_access_role(user.get("role")) == ROLE_FULL_CONTROL
        ]

    def create_user(
        self,
        username: str,
        display_name: str,
        password_hash: str,
        role: str,
        actor: str,
    ) -> dict[str, Any]:
        with self.lock:
            if self.find_user_by_username(username):
                raise ValueError("Ese nombre de usuario ya esta en uso")
            role = validate_access_role(role)
            version = self._next_version()
            user = {
                "id": str(uuid.uuid4()),
                "username": username,
                "display_name": display_name,
                "role": role,
                "status": "active",
                "password_hash": password_hash,
                "password_change_required": True,  # nosec B105
                "password_changed_at": version["timestamp"],
                "session_version": 1,
                "favorites": {},
                "totp": {
                    "enabled": False,
                    "secret": None,  # nosec B105
                    "pending_secret": None,  # nosec B105
                    "recovery_code_hashes": [],
                },
                "created_at": version["timestamp"],
                "updated_at": version["timestamp"],
                "updated_by": actor,
                "version": version,
            }
            self._write_entity("user", user)
            self._audit("user.created", actor, None, version, None, self.public_user(user), "user", user["id"])
            return self.public_user(user)

    def update_user_access(
        self,
        user_id: str,
        actor: str,
        username: str | None = None,
        display_name: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        if role is not None:
            role = validate_access_role(role)
        if status is not None and status not in {"active", "disabled"}:
            raise ValueError("El estado de la cuenta no es valido")

        def mutate(user: dict[str, Any]) -> None:
            if username is not None and username != str(user.get("username", "")):
                existing = self.find_user_by_username(username)
                if existing and existing.get("id") != user_id:
                    raise ValueError("Ese nombre de usuario ya esta en uso")
                user["username"] = username
            if display_name is not None:
                user["display_name"] = display_name
            current_is_last_admin = (
                user.get("status", "active") == "active"
                and normalize_access_role(user.get("role")) == ROLE_FULL_CONTROL
                and len(self._active_full_control_users()) == 1
            )
            next_role = role if role is not None else normalize_access_role(user.get("role"))
            next_status = status if status is not None else str(user.get("status", "active"))
            if current_is_last_admin and (next_role != ROLE_FULL_CONTROL or next_status != "active"):
                raise ValueError("No se puede desactivar o degradar la ultima cuenta con control total")
            user["role"] = next_role
            user["status"] = next_status

        return self.public_user(
            self._mutate_user(user_id, actor, "user.access_updated", mutate, invalidate_sessions=True)
        )

    def reset_user_password(self, user_id: str, actor: str, password_hash: str) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            user["password_hash"] = password_hash
            user["password_change_required"] = True
            user["password_changed_at"] = utc_now()

        return self.public_user(
            self._mutate_user(user_id, actor, "user.password_reset", mutate, invalidate_sessions=True)
        )

    def create_owner(self, username: str, display_name: str, password_hash: str, actor: str) -> dict[str, Any]:
        with self.lock:
            if self.has_users():
                raise ValueError("La cuenta propietaria ya está configurada")
            version = self._next_version()
            user = {
                "id": str(uuid.uuid4()),
                "username": username,
                "display_name": display_name,
                "role": ROLE_FULL_CONTROL,
                "status": "active",
                "password_hash": password_hash,
                "password_change_required": True,  # nosec B105
                "password_changed_at": version["timestamp"],
                "session_version": 1,
                "favorites": {},
                "totp": {
                    "enabled": False,
                    "secret": None,  # nosec B105
                    "pending_secret": None,  # nosec B105
                    "recovery_code_hashes": [],
                },
                "created_at": version["timestamp"],
                "updated_at": version["timestamp"],
                "updated_by": actor,
                "version": version,
            }
            self._write_entity("user", user)
            public = self.public_user(user)
            self._audit("user.bootstrap", actor, None, version, None, public, "user", user["id"])
            return user

    def _mutate_user(
        self,
        user_id: str,
        actor: str,
        action: str,
        mutation: Callable[[dict[str, Any]], None],
        invalidate_sessions: bool = False,
    ) -> dict[str, Any]:
        with self.lock:
            user = self.get_user(user_id)
            if not user:
                raise ValueError("El perfil de usuario no existe")
            before = self.public_user(user)
            mutation(user)
            if invalidate_sessions:
                user["session_version"] = int(user.get("session_version", 1)) + 1
            version = self._next_version()
            user["updated_at"] = version["timestamp"]
            user["updated_by"] = actor
            user["version"] = version
            self._write_entity("user", user)
            after = self.public_user(user)
            self._audit(action, actor, None, version, before, after, "user", user_id)
            return user

    def update_user_profile(
        self,
        user_id: str,
        actor: str,
        username: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            if username is not None and username != str(user.get("username", "")):
                existing = self.find_user_by_username(username)
                if existing and existing.get("id") != user_id:
                    raise ValueError("Ese nombre de usuario ya está en uso")
                user["username"] = username
            if display_name is not None:
                user["display_name"] = display_name

        return self._mutate_user(user_id, actor, "user.profile_updated", mutate)

    def update_user_password(self, user_id: str, actor: str, password_hash: str) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            user["password_hash"] = password_hash
            user["password_change_required"] = False
            user["password_changed_at"] = utc_now()

        return self._mutate_user(user_id, actor, "user.password_changed", mutate, invalidate_sessions=True)

    def set_pending_totp(self, user_id: str, actor: str, encrypted_secret: str | None) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            user.setdefault("totp", {})["pending_secret"] = encrypted_secret

        action = "user.2fa_setup_started" if encrypted_secret else "user.2fa_setup_cancelled"
        return self._mutate_user(user_id, actor, action, mutate)

    def enable_totp(self, user_id: str, actor: str, recovery_hashes: list[str]) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            totp = user.setdefault("totp", {})
            if not totp.get("pending_secret"):
                raise ValueError("No hay una configuración 2FA pendiente")
            totp["secret"] = totp["pending_secret"]
            totp["pending_secret"] = None
            totp["enabled"] = True
            totp["recovery_code_hashes"] = recovery_hashes

        return self._mutate_user(user_id, actor, "user.2fa_enabled", mutate, invalidate_sessions=True)

    def disable_totp(self, user_id: str, actor: str) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            user["totp"] = {
                "enabled": False,
                "secret": None,  # nosec B105
                "pending_secret": None,  # nosec B105
                "recovery_code_hashes": [],
            }

        return self._mutate_user(user_id, actor, "user.2fa_disabled", mutate, invalidate_sessions=True)

    def replace_recovery_codes(self, user_id: str, actor: str, recovery_hashes: list[str]) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            user.setdefault("totp", {})["recovery_code_hashes"] = recovery_hashes

        return self._mutate_user(user_id, actor, "user.recovery_codes_regenerated", mutate)

    def consume_recovery_code(self, user_id: str, actor: str, index: int) -> dict[str, Any]:
        def mutate(user: dict[str, Any]) -> None:
            hashes = list(user.setdefault("totp", {}).get("recovery_code_hashes") or [])
            if index < 0 or index >= len(hashes):
                raise ValueError("El código de recuperación ya no está disponible")
            hashes.pop(index)
            user["totp"]["recovery_code_hashes"] = hashes

        return self._mutate_user(user_id, actor, "user.recovery_code_consumed", mutate)

    @staticmethod
    def public_api_client(client: dict[str, Any]) -> dict[str, Any]:
        expires_at = str(client.get("expires_at") or "")
        return {
            "id": client.get("id"),
            "name": client.get("name"),
            "description": client.get("description", ""),
            "role": normalize_access_role(client.get("role")),
            "identity_type": "api",
            "status": client.get("status", "active"),
            "token_prefix": client.get("token_prefix"),
            "expires_at": client.get("expires_at"),
            "expired": bool(expires_at and expires_at <= utc_now()),
            "last_used_at": client.get("last_used_at"),
            "last_used_ip": client.get("last_used_ip"),
            "created_at": client.get("created_at"),
            "updated_at": client.get("updated_at"),
            "updated_by": client.get("updated_by"),
            "version": client.get("version"),
        }

    def list_api_clients(self, include_deleted: bool = False, public: bool = True) -> list[dict[str, Any]]:
        with self.lock:
            clients = self._list_entities("api_client", include_deleted=include_deleted)
            return [self.public_api_client(client) for client in clients] if public else clients

    def get_api_client(self, client_id: str, public: bool = False) -> dict[str, Any] | None:
        with self.lock:
            client = self._read_entity("api_client", client_id)
            if not client or client.get("status") == "deleted":
                return None
            return self.public_api_client(client) if public else client

    def find_api_client_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        now = utc_now()
        with self.lock:
            for client in self._list_entities("api_client", include_deleted=False):
                if client.get("status") != "active":
                    continue
                expires_at = str(client.get("expires_at") or "")
                if expires_at and expires_at <= now:
                    continue
                expected = str(client.get("token_hash") or "")
                if expected and hmac.compare_digest(token_hash, expected):
                    return client
        return None

    def create_api_client(
        self,
        client_id: str,
        name: str,
        description: str,
        role: str,
        token_hash: str,
        token_prefix: str,
        expires_at: str | None,
        actor: str,
    ) -> dict[str, Any]:
        with self.lock:
            cleaned_name = name.strip()
            if not cleaned_name:
                raise ValueError("El nombre del acceso API no puede estar vacio")
            expected = cleaned_name.casefold()
            if any(str(client.get("name", "")).casefold() == expected for client in self.list_api_clients(public=False)):
                raise ValueError("Ya existe un acceso API con ese nombre")
            version = self._next_version()
            client = {
                "id": client_id,
                "name": cleaned_name,
                "description": description.strip(),
                "role": validate_access_role(role),
                "status": "active",
                "token_hash": token_hash,
                "token_prefix": token_prefix,
                "expires_at": expires_at,
                "last_used_at": None,
                "last_used_ip": None,
                "created_at": version["timestamp"],
                "updated_at": version["timestamp"],
                "updated_by": actor,
                "version": version,
            }
            self._write_entity("api_client", client)
            public = self.public_api_client(client)
            self._audit("api_client.created", actor, None, version, None, public, "api_client", client_id)
            return public

    def _mutate_api_client(
        self,
        client_id: str,
        actor: str,
        action: str,
        mutation: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        with self.lock:
            client = self.get_api_client(client_id)
            if not client:
                raise ValueError("El acceso API no existe")
            before = self.public_api_client(client)
            mutation(client)
            version = self._next_version()
            client["updated_at"] = version["timestamp"]
            client["updated_by"] = actor
            client["version"] = version
            self._write_entity("api_client", client)
            after = self.public_api_client(client)
            self._audit(action, actor, None, version, before, after, "api_client", client_id)
            return after

    def update_api_client(
        self,
        client_id: str,
        actor: str,
        name: str | None = None,
        description: str | None = None,
        role: str | None = None,
        status: str | None = None,
        expires_at: str | None = None,
        expires_at_supplied: bool = False,
    ) -> dict[str, Any]:
        if role is not None:
            role = validate_access_role(role)
        if status is not None and status not in {"active", "disabled"}:
            raise ValueError("El estado del acceso API no es valido")

        def mutate(client: dict[str, Any]) -> None:
            if client.get("status") == "revoked" and status is not None:
                raise ValueError("Un acceso revocado solo puede reactivarse rotando su token")
            if name is not None:
                cleaned_name = name.strip()
                if not cleaned_name:
                    raise ValueError("El nombre del acceso API no puede estar vacio")
                expected = cleaned_name.casefold()
                duplicate = any(
                    other.get("id") != client_id and str(other.get("name", "")).casefold() == expected
                    for other in self.list_api_clients(public=False)
                )
                if duplicate:
                    raise ValueError("Ya existe un acceso API con ese nombre")
                client["name"] = cleaned_name
            if description is not None:
                client["description"] = description.strip()
            if role is not None:
                client["role"] = role
            if status is not None:
                client["status"] = status
            if expires_at_supplied:
                client["expires_at"] = expires_at

        return self._mutate_api_client(client_id, actor, "api_client.updated", mutate)

    def rotate_api_client_token(
        self,
        client_id: str,
        actor: str,
        token_hash: str,
        token_prefix: str,
    ) -> dict[str, Any]:
        def mutate(client: dict[str, Any]) -> None:
            client["token_hash"] = token_hash
            client["token_prefix"] = token_prefix
            client["status"] = "active"
            client["last_used_at"] = None
            client["last_used_ip"] = None
            expires_at = str(client.get("expires_at") or "")
            if expires_at and expires_at <= utc_now():
                client["expires_at"] = None

        return self._mutate_api_client(client_id, actor, "api_client.token_rotated", mutate)

    def revoke_api_client(self, client_id: str, actor: str) -> dict[str, Any]:
        def mutate(client: dict[str, Any]) -> None:
            client["status"] = "revoked"
            client["token_hash"] = ""  # nosec B105

        return self._mutate_api_client(client_id, actor, "api_client.revoked", mutate)

    def mark_api_client_used(self, client_id: str, remote_ip: str | None) -> None:
        with self.lock:
            client = self.get_api_client(client_id)
            if not client:
                return
            now = datetime.now(timezone.utc)
            try:
                previous = datetime.fromisoformat(str(client.get("last_used_at")).replace("Z", "+00:00"))
                if (now - previous).total_seconds() < 60:
                    return
            except (TypeError, ValueError):
                pass
            version = self._next_version()
            client["last_used_at"] = version["timestamp"]
            client["last_used_ip"] = (remote_ip or "")[:80] or None
            client["updated_at"] = version["timestamp"]
            client["version"] = version
            self._write_entity("api_client", client)

    def list_libraries(self, include_deleted: bool = False, include_counts: bool = True) -> list[dict[str, Any]]:
        with self.lock:
            libraries = self._list_entities("library", include_deleted)
            if not include_counts:
                return libraries
            categories = self._list_entities("category", include_deleted=True)
            documents = self.list_documents(include_deleted=True)
            for library in libraries:
                library_id = library["id"]
                library["counts"] = {
                    "categories": sum(1 for item in categories if item.get("library_id") == library_id and item.get("status") != "deleted"),
                    "documents": sum(1 for item in documents if item.get("library_id") == library_id and item.get("status") != "deleted"),
                }
            return libraries

    def get_library(self, library_id: str, include_deleted: bool = False) -> dict[str, Any] | None:
        with self.lock:
            library = self._read_entity("library", library_id)
            if not library or (library.get("status") == "deleted" and not include_deleted):
                return None
            return library

    def create_library(
        self,
        name: str,
        actor: str,
        description: str = "",
        icon: str = "library",
        color: str = "indigo",
    ) -> dict[str, Any]:
        with self.lock:
            version = self._next_version()
            library_id = str(uuid.uuid4())
            siblings = self._list_entities("library", include_deleted=False)
            entity = {
                "id": library_id,
                "name": name.strip() or "Biblioteca sin nombre",
                "slug": slugify(name),
                "description": description.strip(),
                "icon": icon,
                "color": color,
                "position": len(siblings),
                "category_sort": "manual",
                "access": {"mode": LIBRARY_ACCESS_OPEN, "grants": []},
                "status": "active",
                "created_at": version["timestamp"],
                "created_by": actor,
                "updated_at": version["timestamp"],
                "updated_by": actor,
                "version": version,
            }
            self._write_entity("library", entity)
            self._audit("library.create", actor, None, version, None, entity, "library", library_id)
            return entity

    def update_library(
        self,
        library_id: str,
        actor: str,
        name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        position: int | None = None,
        category_sort: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            entity = self.get_library(library_id)
            if not entity:
                raise KeyError(library_id)
            before = dict(entity)
            version = self._next_version()
            if name is not None:
                entity["name"] = name.strip() or "Biblioteca sin nombre"
                entity["slug"] = slugify(name)
            if description is not None:
                entity["description"] = description.strip()
            if icon is not None:
                entity["icon"] = icon
            if color is not None:
                entity["color"] = color
            if position is not None:
                entity["position"] = max(0, position)
            if category_sort is not None:
                if category_sort not in {"manual", "alphabetical"}:
                    raise ValueError("Modo de orden de categorías no válido")
                entity["category_sort"] = category_sort
            entity.update({"updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_entity("library", entity)
            self._audit("library.update", actor, None, version, before, entity, "library", library_id)
            return entity

    def get_library_permissions(self, library_id: str) -> dict[str, Any]:
        with self.lock:
            library = self.get_library(library_id)
            if not library:
                raise KeyError(library_id)
            return normalize_library_access(library.get("access"))

    def update_library_permissions(
        self,
        library_id: str,
        actor: str,
        mode: str,
        grants: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self.lock:
            library = self.get_library(library_id)
            if not library:
                raise KeyError(library_id)
            policy = validate_library_access(mode, grants)
            for grant in policy["grants"]:
                subject_id = grant["subject_id"]
                if grant["subject_type"] == "user":
                    subject = self.get_user(subject_id)
                    valid = bool(subject and subject.get("status", "active") == "active")
                else:
                    subject = self.get_api_client(subject_id)
                    expires_at = str((subject or {}).get("expires_at") or "")
                    valid = bool(
                        subject
                        and subject.get("status", "active") == "active"
                        and (not expires_at or expires_at > utc_now())
                    )
                if not valid:
                    raise ValueError("Un permiso hace referencia a una identidad inexistente o inactiva")

            before = dict(library)
            version = self._next_version()
            library["access"] = policy
            library.update({
                "updated_at": version["timestamp"],
                "updated_by": actor,
                "version": version,
            })
            self._write_entity("library", library)
            self._audit(
                "library.permissions.update",
                actor,
                None,
                version,
                before,
                library,
                "library",
                library_id,
            )
            return policy

    def delete_library(self, library_id: str, actor: str) -> dict[str, Any]:
        with self.lock:
            entity = self.get_library(library_id)
            if not entity:
                raise KeyError(library_id)
            has_categories = bool(self.list_categories(library_id))
            has_documents = any(
                item.get("library_id") == library_id and item.get("status") != "deleted"
                for item in self.list_documents(include_deleted=True)
            )
            if has_categories or has_documents:
                raise ValueError("La biblioteca no está vacía")
            before = dict(entity)
            version = self._next_version()
            entity.update({"status": "deleted", "deleted_at": version["timestamp"], "updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_entity("library", entity)
            self._audit("library.delete", actor, None, version, before, entity, "library", library_id)
            return entity

    def list_categories(self, library_id: str | None = None, include_deleted: bool = False) -> list[dict[str, Any]]:
        with self.lock:
            items = self._list_entities("category", include_deleted)
            if library_id:
                items = [item for item in items if item.get("library_id") == library_id]
            return items

    def get_category(self, category_id: str, include_deleted: bool = False) -> dict[str, Any] | None:
        with self.lock:
            category = self._read_entity("category", category_id)
            if not category or (category.get("status") == "deleted" and not include_deleted):
                return None
            return category

    def _validate_parent(self, library_id: str, parent_id: str | None, category_id: str | None = None) -> None:
        if parent_id is None:
            return
        parent = self.get_category(parent_id)
        if not parent or parent.get("library_id") != library_id:
            raise ValueError("La categoría padre no pertenece a esta biblioteca")
        visited = {category_id} if category_id else set()
        current = parent
        while current:
            current_id = current.get("id")
            if current_id in visited:
                raise ValueError("El movimiento crearía un ciclo de categorías")
            visited.add(current_id)
            next_parent = current.get("parent_id")
            current = self.get_category(next_parent) if next_parent else None

    def create_category(
        self,
        library_id: str,
        name: str,
        actor: str,
        parent_id: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        with self.lock:
            if not self.get_library(library_id):
                raise KeyError(library_id)
            self._validate_parent(library_id, parent_id)
            siblings = [item for item in self.list_categories(library_id) if item.get("parent_id") == parent_id]
            version = self._next_version()
            category_id = str(uuid.uuid4())
            entity = {
                "id": category_id,
                "library_id": library_id,
                "parent_id": parent_id,
                "name": name.strip() or "Categoría sin nombre",
                "slug": slugify(name),
                "description": description.strip(),
                "position": len(siblings),
                "status": "active",
                "created_at": version["timestamp"],
                "created_by": actor,
                "updated_at": version["timestamp"],
                "updated_by": actor,
                "version": version,
            }
            self._write_entity("category", entity)
            self._audit("category.create", actor, None, version, None, entity, "category", category_id)
            return entity

    def update_category(
        self,
        category_id: str,
        actor: str,
        name: str | None = None,
        description: str | None = None,
        parent_id: str | None = None,
        parent_supplied: bool = False,
        position: int | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            entity = self.get_category(category_id)
            if not entity:
                raise KeyError(category_id)
            if parent_supplied:
                self._validate_parent(entity["library_id"], parent_id, category_id)
            before = dict(entity)
            version = self._next_version()
            if name is not None:
                entity["name"] = name.strip() or "Categoría sin nombre"
                entity["slug"] = slugify(name)
            if description is not None:
                entity["description"] = description.strip()
            if parent_supplied:
                entity["parent_id"] = parent_id
            if position is not None:
                entity["position"] = max(0, position)
            entity.update({"updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_entity("category", entity)
            self._audit("category.update", actor, None, version, before, entity, "category", category_id)
            return entity

    def reorder_categories(
        self,
        library_id: str,
        parent_id: str | None,
        category_ids: list[str],
        actor: str,
    ) -> dict[str, Any]:
        with self.lock:
            library = self.get_library(library_id)
            if not library:
                raise KeyError(library_id)
            if library.get("category_sort", "manual") != "manual":
                raise ValueError("Cambia la biblioteca a orden manual antes de reordenar")
            if parent_id is not None:
                parent = self.get_category(parent_id)
                if not parent or parent.get("library_id") != library_id:
                    raise ValueError("La categoría padre no pertenece a esta biblioteca")
            siblings = [
                item for item in self.list_categories(library_id)
                if item.get("parent_id") == parent_id
            ]
            expected = {str(item["id"]) for item in siblings}
            received = [str(item) for item in category_ids]
            if len(received) != len(set(received)) or set(received) != expected:
                raise ValueError("El orden debe incluir una sola vez todas las categorías de este nivel")
            before = [{"id": item["id"], "position": item.get("position", 0)} for item in siblings]
            version = self._next_version()
            by_id = {str(item["id"]): item for item in siblings}
            ordered: list[dict[str, Any]] = []
            for position, category_id in enumerate(received):
                category = by_id[category_id]
                category.update({
                    "position": position,
                    "updated_at": version["timestamp"],
                    "updated_by": actor,
                    "version": version,
                })
                self._write_entity("category", category)
                ordered.append(category)
            after = {
                "library_id": library_id,
                "parent_id": parent_id,
                "items": ordered,
            }
            self._audit(
                "category.reorder",
                actor,
                None,
                version,
                before,
                after,
                "category_order",
                library_id,
            )
            return {"library_id": library_id, "parent_id": parent_id, "items": ordered}

    def delete_category(self, category_id: str, actor: str) -> dict[str, Any]:
        with self.lock:
            entity = self.get_category(category_id)
            if not entity:
                raise KeyError(category_id)
            has_categories = any(item.get("parent_id") == category_id for item in self.list_categories(entity["library_id"]))
            has_documents = any(
                item.get("category_id") == category_id and item.get("status") != "deleted"
                for item in self.list_documents(include_deleted=True)
            )
            if has_categories or has_documents:
                raise ValueError("La categoría no está vacía")
            before = dict(entity)
            version = self._next_version()
            entity.update({"status": "deleted", "deleted_at": version["timestamp"], "updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_entity("category", entity)
            self._audit("category.delete", actor, None, version, before, entity, "category", category_id)
            return entity

    def library_tree(self, library_id: str) -> dict[str, Any]:
        with self.lock:
            library = self.get_library(library_id)
            if not library:
                raise KeyError(library_id)
            categories = self.list_categories(library_id)
            documents = [
                item for item in self.list_documents(include_deleted=False)
                if item.get("library_id") == library_id and item.get("status") != "archived"
            ]
            category_nodes = {item["id"]: {**item, "type": "category", "children": [], "documents": []} for item in categories}
            roots: list[dict[str, Any]] = []
            for category in category_nodes.values():
                parent = category_nodes.get(category.get("parent_id"))
                (parent["children"] if parent else roots).append(category)
            root_documents: list[dict[str, Any]] = []
            for document in documents:
                summary = {**document, "type": "document"}
                category = category_nodes.get(document.get("category_id"))
                (category["documents"] if category else root_documents).append(summary)

            category_sort = library.get("category_sort", "manual")

            def alphabetical_key(item: dict[str, Any]) -> str:
                normalized = unicodedata.normalize("NFKD", str(item.get("name", "")))
                return "".join(character for character in normalized if not unicodedata.combining(character)).casefold()

            def order(nodes: list[dict[str, Any]]) -> None:
                if category_sort == "alphabetical":
                    nodes.sort(key=lambda item: (alphabetical_key(item), str(item.get("id", ""))))
                else:
                    nodes.sort(key=lambda item: (int(item.get("position", 0)), item.get("name", "").casefold()))
                for node in nodes:
                    node["documents"].sort(key=lambda item: (int(item.get("position", 0)), item.get("title", "").casefold()))
                    order(node["children"])

            order(roots)
            root_documents.sort(key=lambda item: (int(item.get("position", 0)), item.get("title", "").casefold()))
            return {"library": library, "categories": roots, "documents": root_documents}

    @staticmethod
    def _user_favorites(user: dict[str, Any]) -> dict[str, str]:
        raw = user.get("favorites") or {}
        if isinstance(raw, list):
            return {str(document_id): "" for document_id in raw}
        if not isinstance(raw, dict):
            return {}
        return {str(document_id): str(added_at or "") for document_id, added_at in raw.items()}

    def list_favorite_documents(self, user_id: str) -> list[dict[str, Any]]:
        with self.lock:
            user = self.get_user(user_id)
            if not user:
                raise KeyError(user_id)
            favorites = self._user_favorites(user)
            items: list[dict[str, Any]] = []
            for document_id, added_at in favorites.items():
                document = self._read_meta(document_id)
                if not document or document.get("status") == "deleted":
                    continue
                items.append({**document, "favorited_at": added_at})
            return sorted(
                items,
                key=lambda item: (str(item.get("favorited_at", "")), str(item.get("title", "")).casefold()),
                reverse=True,
            )

    def set_document_favorite(self, user_id: str, document_id: str, favorite: bool, actor: str) -> dict[str, Any]:
        with self.lock:
            user = self.get_user(user_id)
            document = self._read_meta(document_id)
            if not user or not document or document.get("status") == "deleted":
                raise KeyError(document_id)
            favorites = self._user_favorites(user)
            before = document_id in favorites
            if before == favorite:
                return {
                    "favorite": favorite,
                    "document": {**document, "favorited_at": favorites.get(document_id)},
                }
            version = self._next_version()
            if favorite:
                favorites[document_id] = version["timestamp"]
            else:
                favorites.pop(document_id, None)
            user["favorites"] = favorites
            user.update({"updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_entity("user", user)
            self._audit(
                "favorite.add" if favorite else "favorite.remove",
                actor,
                document_id,
                version,
                {"favorite": before},
                {"favorite": favorite},
                "favorite",
                f"{user_id}:{document_id}",
            )
            return {
                "favorite": favorite,
                "document": {**document, "favorited_at": favorites.get(document_id)},
            }

    def list_documents(
        self,
        include_deleted: bool = False,
        library_id: str | None = None,
        category_id: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.lock:
            items = []
            for path in sorted(self.meta_dir.glob("*.json")):
                meta = self._read_json(path)
                if not meta or (meta.get("status") == "deleted" and not include_deleted):
                    continue
                if library_id is not None and meta.get("library_id") != library_id:
                    continue
                if category_id is not None and meta.get("category_id") != category_id:
                    continue
                if status and meta.get("status") != status:
                    continue
                if query:
                    haystack = f"{meta.get('title', '')} {meta.get('summary', '')} {' '.join(meta.get('tags', []))}".casefold()
                    if query.casefold() not in haystack:
                        continue
                items.append(dict(meta))
            return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)

    @staticmethod
    def _public_image(image: dict[str, Any]) -> dict[str, Any]:
        result = {key: value for key, value in image.items() if key not in {"stored_name", "data"}}
        result["url"] = f"/api/v1/documents/{image['document_id']}/images/{image['id']}"
        return result

    def _read_image_directory(self, directory: Path, include_data: bool = False) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        if not directory.is_dir():
            return images
        for metadata_path in sorted(directory.glob("*.json")):
            image = self._read_json(metadata_path)
            if not image or not _safe_identifier(str(image.get("id", ""))):
                continue
            stored_name = str(image.get("stored_name", ""))
            if not stored_name or Path(stored_name).name != stored_name:
                continue
            content_path = directory / stored_name
            if not content_path.is_file():
                continue
            item = dict(image)
            if include_data:
                item["data"] = b64encode(content_path.read_bytes()).decode("ascii")
            images.append(item)
        return sorted(images, key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))))

    def _replace_image_directory(self, directory: Path, images: list[dict[str, Any]]) -> None:
        if directory.exists():
            shutil.rmtree(directory)
        if not images:
            return
        directory.mkdir(parents=True, exist_ok=True)
        for source in images:
            image_id = str(source.get("id", ""))
            document_id = str(source.get("document_id", ""))
            if not _safe_identifier(image_id) or not _safe_identifier(document_id):
                continue
            try:
                content = b64decode(str(source.get("data", "")), validate=True)
                media_type = validate_image_content(str(source.get("media_type", "")), content)
            except (binascii.Error, ValueError, TypeError):
                continue
            stored_name = f"{image_id}{IMAGE_EXTENSIONS[media_type]}"
            image = {
                **{key: value for key, value in source.items() if key != "data"},
                "media_type": media_type,
                "stored_name": stored_name,
                "size": len(content),
            }
            temporary = (directory / stored_name).with_suffix(IMAGE_EXTENSIONS[media_type] + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(directory / stored_name)
            self._write_json(directory / f"{image_id}.json", image)

    def list_images(self, document_id: str, include_data: bool = False) -> list[dict[str, Any]]:
        with self.lock:
            document = self._read_meta(document_id)
            if not document or document.get("status") == "deleted":
                raise KeyError(document_id)
            images = self._read_image_directory(self._document_images_dir(document_id), include_data)
            return images if include_data else [self._public_image(image) for image in images]

    def add_image(self, document_id: str, filename: str, media_type: str, content: bytes, actor: str) -> dict[str, Any]:
        with self.lock:
            current = self._read_meta(document_id)
            if not current or current.get("status") == "deleted":
                raise KeyError(document_id)
            normalized_type = validate_image_content(media_type, content)
            clean_name = re.sub(r"[\x00-\x1f\x7f]", "", Path(filename).name).strip()[:255] or f"imagen{IMAGE_EXTENSIONS[normalized_type]}"
            image_id = str(uuid.uuid4())
            version = self._next_version()
            stored_name = f"{image_id}{IMAGE_EXTENSIONS[normalized_type]}"
            image = {
                "id": image_id,
                "document_id": document_id,
                "filename": clean_name,
                "media_type": normalized_type,
                "stored_name": stored_name,
                "size": len(content),
                "created_at": version["timestamp"],
                "created_by": actor,
                "version": version,
            }
            directory = self._document_images_dir(document_id)
            directory.mkdir(parents=True, exist_ok=True)
            temporary = (directory / stored_name).with_suffix(IMAGE_EXTENSIONS[normalized_type] + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(directory / stored_name)
            self._write_json(directory / f"{image_id}.json", image)
            before = dict(current)
            current.update({"updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_meta(current)
            self._audit("document.image.upload", actor, document_id, version, before, self._public_image(image))
            return self._public_image(image)

    def get_image_file(self, document_id: str, image_id: str) -> tuple[Path, dict[str, Any]]:
        with self.lock:
            document = self._read_meta(document_id)
            if not document or document.get("status") == "deleted" or not _safe_identifier(image_id):
                raise KeyError(image_id)
            image = self._read_json(self._document_images_dir(document_id) / f"{image_id}.json")
            if not image:
                raise KeyError(image_id)
            stored_name = str(image.get("stored_name", ""))
            if not stored_name or Path(stored_name).name != stored_name:
                raise KeyError(image_id)
            path = self._document_images_dir(document_id) / stored_name
            if not path.is_file():
                raise KeyError(image_id)
            return path, self._public_image(image)

    def get_document(
        self,
        document_id: str,
        include_deleted: bool = True,
        include_image_data: bool = False,
    ) -> dict[str, Any] | None:
        with self.lock:
            meta = self._read_meta(document_id)
            if not meta or (meta.get("status") == "deleted" and not include_deleted):
                return None
            content_path = self._doc_path(document_id)
            content = content_path.read_text(encoding="utf-8") if content_path.exists() else None
            images = self._read_image_directory(self._document_images_dir(document_id), include_image_data)
            return {
                "meta": dict(meta),
                "content": content,
                "images": images if include_image_data else [self._public_image(image) for image in images],
            }

    def create(
        self,
        title: str,
        content: str,
        actor: str,
        slug: str | None = None,
        library_id: str | None = None,
        category_id: str | None = None,
        summary: str = "",
        tags: list[str] | None = None,
        position: int | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            if library_id and not self.get_library(library_id):
                raise ValueError("La biblioteca indicada no existe")
            if category_id:
                category = self.get_category(category_id)
                if not category or category.get("library_id") != library_id:
                    raise ValueError("La categoría indicada no pertenece a la biblioteca")
            document_id = str(uuid.uuid4())
            version = self._next_version()
            now = version["timestamp"]
            siblings = [
                item for item in self.list_documents(include_deleted=False)
                if item.get("library_id") == library_id and item.get("category_id") == category_id
            ]
            meta = {
                "id": document_id,
                "title": title.strip() or "Sin título",
                "slug": slugify(slug or title),
                "summary": summary.strip(),
                "library_id": library_id,
                "category_id": category_id,
                "position": max(0, position) if position is not None else len(siblings),
                "tags": sorted({item.strip() for item in (tags or []) if item.strip()}, key=str.casefold),
                "status": "active",
                "author": actor,
                "created_at": now,
                "updated_at": now,
                "updated_by": actor,
                "version": version,
            }
            self._doc_path(document_id).write_text(content, encoding="utf-8")
            self._write_meta(meta)
            self._audit("create", actor, document_id, version, None, dict(meta))
            return {"meta": meta, "content": content, "images": []}

    def update(
        self,
        document_id: str,
        actor: str,
        title: str | None = None,
        content: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            current = self._read_meta(document_id)
            if not current or current.get("status") == "deleted":
                raise KeyError(document_id)
            before = dict(current)
            version = self._next_version()
            if title is not None:
                current["title"] = title.strip() or "Sin título"
                current["slug"] = slugify(title)
            if content is not None:
                self._doc_path(document_id).write_text(content, encoding="utf-8")
            if summary is not None:
                current["summary"] = summary.strip()
            if tags is not None:
                current["tags"] = sorted({item.strip() for item in tags if item.strip()}, key=str.casefold)
            current.update({"updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_meta(current)
            self._audit("update", actor, document_id, version, before, dict(current))
            return self.get_document(document_id)  # type: ignore[return-value]

    def move_document(
        self,
        document_id: str,
        actor: str,
        library_id: str,
        category_id: str | None,
        position: int | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            current = self._read_meta(document_id)
            if not current or current.get("status") == "deleted":
                raise KeyError(document_id)
            if not self.get_library(library_id):
                raise ValueError("La biblioteca indicada no existe")
            if category_id:
                category = self.get_category(category_id)
                if not category or category.get("library_id") != library_id:
                    raise ValueError("La categoría indicada no pertenece a la biblioteca")
            before = dict(current)
            version = self._next_version()
            current.update(
                {
                    "library_id": library_id,
                    "category_id": category_id,
                    "position": max(0, position) if position is not None else 0,
                    "updated_at": version["timestamp"],
                    "updated_by": actor,
                    "version": version,
                }
            )
            self._write_meta(current)
            self._audit("document.move", actor, document_id, version, before, current)
            return self.get_document(document_id)  # type: ignore[return-value]

    def archive(self, document_id: str, actor: str) -> dict[str, Any]:
        with self.lock:
            current = self._read_meta(document_id)
            if not current or current.get("status") == "deleted":
                raise KeyError(document_id)
            before = dict(current)
            version = self._next_version()
            current.update({"status": "archived", "archived_at": version["timestamp"], "updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_meta(current)
            self._audit("archive", actor, document_id, version, before, dict(current))
            return self.get_document(document_id)  # type: ignore[return-value]

    def unarchive(self, document_id: str, actor: str) -> dict[str, Any]:
        with self.lock:
            current = self._read_meta(document_id)
            if not current or current.get("status") != "archived":
                raise KeyError(document_id)
            before = dict(current)
            version = self._next_version()
            current.update({"status": "active", "updated_at": version["timestamp"], "updated_by": actor, "version": version})
            current.pop("archived_at", None)
            self._write_meta(current)
            self._audit("unarchive", actor, document_id, version, before, dict(current))
            return self.get_document(document_id)  # type: ignore[return-value]

    def delete(self, document_id: str, actor: str) -> dict[str, Any]:
        with self.lock:
            current = self._read_meta(document_id)
            if not current or current.get("status") == "deleted":
                raise KeyError(document_id)
            before = dict(current)
            version = self._next_version()
            vault_item = self.vault_dir / document_id / str(version["clock"])
            vault_item.mkdir(parents=True, exist_ok=True)
            content_path = self._doc_path(document_id)
            if content_path.exists():
                shutil.copy2(content_path, vault_item / "content.md")
                content_path.unlink()
            image_directory = self._document_images_dir(document_id)
            if image_directory.is_dir():
                shutil.copytree(image_directory, vault_item / "images")
                shutil.rmtree(image_directory)
            self._write_json(vault_item / "meta.json", {"deleted_at": version["timestamp"], "version": version, "title": current.get("title")})
            current.update({"status": "deleted", "deleted_at": version["timestamp"], "updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_meta(current)
            self._audit("delete", actor, document_id, version, before, dict(current))
            return {"meta": current, "content": None, "images": []}

    def restore(self, document_id: str, actor: str) -> dict[str, Any]:
        with self.lock:
            current = self._read_meta(document_id)
            if not current or current.get("status") != "deleted":
                raise KeyError(document_id)
            def vault_revision(path: Path) -> int:
                try:
                    return int(path.parent.name)
                except ValueError:
                    return -1

            candidates = sorted((self.vault_dir / document_id).glob("*/content.md"), key=vault_revision, reverse=True)
            if not candidates:
                raise FileNotFoundError(document_id)
            before = dict(current)
            version = self._next_version()
            shutil.copy2(candidates[0], self._doc_path(document_id))
            source_images = candidates[0].parent / "images"
            destination_images = self._document_images_dir(document_id)
            if destination_images.exists():
                shutil.rmtree(destination_images)
            if source_images.is_dir():
                shutil.copytree(source_images, destination_images)
            current.update({"status": "active", "restored_at": version["timestamp"], "updated_at": version["timestamp"], "updated_by": actor, "version": version})
            self._write_meta(current)
            self._audit("restore", actor, document_id, version, before, dict(current))
            return self.get_document(document_id)  # type: ignore[return-value]

    def purge_vault(self, actor: str = "system:retention") -> int:
        from datetime import timedelta

        with self.lock:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            purged = 0
            for document_dir in self.vault_dir.iterdir():
                if not document_dir.is_dir():
                    continue
                for item in list(document_dir.iterdir()):
                    metadata = self._read_json(item / "meta.json", {})
                    deleted_at = metadata.get("deleted_at")
                    try:
                        old = datetime.fromisoformat(str(deleted_at).replace("Z", "+00:00")) < cutoff
                    except (TypeError, ValueError):
                        old = False
                    if old:
                        document_id = document_dir.name
                        version = self._next_version()
                        shutil.rmtree(item, ignore_errors=True)
                        self._audit("purge", actor, document_id, version, {"vault_item": item.name}, None)
                        purged += 1
                if not any(document_dir.iterdir()):
                    document_dir.rmdir()
            return purged

    def read_audit(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.read_audit_page(limit=limit)["items"]

    @staticmethod
    def _cursor_encode(event: dict[str, Any]) -> str:
        value = json.dumps([event.get("timestamp", ""), event.get("event_id", "")], ensure_ascii=False).encode("utf-8")
        return urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _cursor_decode(cursor: str) -> tuple[str, str]:
        padded = cursor + "=" * (-len(cursor) % 4)
        timestamp, event_id = json.loads(urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return str(timestamp), str(event_id)

    def read_audit_page(
        self,
        limit: int = 50,
        cursor: str | None = None,
        from_at: str | None = None,
        to_at: str | None = None,
        level: str | None = None,
        actor: str | None = None,
        node: str | None = None,
        action: str | None = None,
        source: str | None = None,
        result: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            events = self._all_audit()
            filtered: list[dict[str, Any]] = []
            for event in events:
                timestamp = str(event.get("timestamp", ""))
                if from_at and timestamp < from_at:
                    continue
                if to_at and timestamp > to_at:
                    continue
                if level and str(event.get("level", "info")).lower() != level.lower():
                    continue
                if actor and actor.casefold() not in str(event.get("actor", "")).casefold():
                    continue
                if node and str(event.get("node", "")).casefold() != node.casefold():
                    continue
                if action and action.casefold() not in str(event.get("action", "")).casefold():
                    continue
                if source and str(event.get("source", "audit")).casefold() != source.casefold():
                    continue
                if result and str(event.get("result", "")).casefold() != result.casefold():
                    continue
                filtered.append(event)

            filtered.sort(key=lambda event: (str(event.get("timestamp", "")), str(event.get("event_id", ""))), reverse=True)
            if cursor:
                try:
                    cursor_key = self._cursor_decode(cursor)
                except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
                    raise ValueError("cursor de logs no válido") from None
                filtered = [event for event in filtered if (str(event.get("timestamp", "")), str(event.get("event_id", ""))) < cursor_key]

            safe_limit = max(1, min(int(limit), 200))
            page = filtered[:safe_limit]
            has_more = len(filtered) > safe_limit
            return {
                "items": page,
                "next_cursor": self._cursor_encode(page[-1]) if has_more and page else None,
                "has_more": has_more,
                "count": len(page),
            }

    def _all_audit(self) -> list[dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        events = []
        for line in self.audit_path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return events

    def export_bundle(self) -> dict[str, Any]:
        with self.lock:
            documents = []
            for meta in self.list_documents(include_deleted=True):
                snapshot = self.get_document(meta["id"], include_deleted=True, include_image_data=True)
                if snapshot:
                    documents.append(snapshot)
            vault: list[dict[str, Any]] = []
            for document_dir in self.vault_dir.iterdir():
                if not document_dir.is_dir():
                    continue
                for item in document_dir.iterdir():
                    if not item.is_dir():
                        continue
                    entry = {"document_id": document_dir.name, "item": item.name, "meta": self._read_json(item / "meta.json", {})}
                    content_path = item / "content.md"
                    entry["content"] = content_path.read_text(encoding="utf-8") if content_path.exists() else None
                    entry["images"] = self._read_image_directory(item / "images", include_data=True)
                    vault.append(entry)
            state = self._state()
            return {
                "schema_version": 6,
                "node": self.node_name,
                "clock": state.get("clock", 0),
                "libraries": self._list_entities("library", include_deleted=True),
                "categories": self._list_entities("category", include_deleted=True),
                "users": self._list_entities("user", include_deleted=True),
                "api_clients": self._list_entities("api_client", include_deleted=True),
                "documents": documents,
                "vault": vault,
                "audit": self._all_audit(),
            }

    def local_newer_than(self, bundle: dict[str, Any]) -> bool:
        for entity_type, bundle_key in (
            ("library", "libraries"),
            ("category", "categories"),
            ("user", "users"),
            ("api_client", "api_clients"),
        ):
            remote_versions = {item.get("id"): item.get("version") for item in bundle.get(bundle_key, [])}
            for local in self._list_entities(entity_type, include_deleted=True):
                if _version_key(local.get("version")) > _version_key(remote_versions.get(local.get("id"))):
                    return True
        remote_versions = {
            (item.get("meta") or {}).get("id"): (item.get("meta") or {}).get("version")
            for item in bundle.get("documents", [])
        }
        for local in self.list_documents(include_deleted=True):
            remote = remote_versions.get(local.get("id"))
            if _version_key(local.get("version")) > _version_key(remote):
                return True
        return False

    def merge_bundle(self, bundle: dict[str, Any]) -> dict[str, int]:
        with self.lock:
            applied = 0
            ignored = 0
            audit_added = 0
            for entity_type, bundle_key in (
                ("library", "libraries"),
                ("category", "categories"),
                ("user", "users"),
                ("api_client", "api_clients"),
            ):
                for remote_entity in bundle.get(bundle_key, []):
                    entity_id = remote_entity.get("id")
                    if not entity_id or not _safe_identifier(str(entity_id)):
                        continue
                    local_entity = self._read_entity(entity_type, entity_id)
                    if _version_key(remote_entity.get("version")) <= _version_key(local_entity.get("version") if local_entity else None):
                        ignored += 1
                        continue
                    self._observe_clock(int((remote_entity.get("version") or {}).get("clock", 0)))
                    self._write_entity(entity_type, remote_entity)
                    applied += 1
            for item in bundle.get("documents", []):
                remote_meta = item.get("meta") or {}
                document_id = remote_meta.get("id")
                if not document_id or not _safe_identifier(str(document_id)):
                    continue
                local_meta = self._read_meta(document_id)
                if _version_key(remote_meta.get("version")) <= _version_key(local_meta.get("version") if local_meta else None):
                    ignored += 1
                    continue
                self._observe_clock(int((remote_meta.get("version") or {}).get("clock", 0)))
                if remote_meta.get("status") == "deleted":
                    self._doc_path(document_id).unlink(missing_ok=True)
                    image_directory = self._document_images_dir(document_id)
                    if image_directory.exists():
                        shutil.rmtree(image_directory)
                else:
                    self._doc_path(document_id).write_text(item.get("content") or "", encoding="utf-8")
                    if "images" in item:
                        self._replace_image_directory(self._document_images_dir(document_id), item.get("images") or [])
                self._write_meta(remote_meta)
                applied += 1

            for item in bundle.get("vault", []):
                document_id = item.get("document_id")
                item_name = item.get("item")
                if not document_id or not _safe_identifier(str(document_id)) or not item_name or item_name in {".", ".."} or "/" in item_name or "\\" in item_name:
                    continue
                destination = self.vault_dir / document_id / item_name
                destination.mkdir(parents=True, exist_ok=True)
                if item.get("content") is not None:
                    (destination / "content.md").write_text(item["content"], encoding="utf-8")
                if "images" in item:
                    self._replace_image_directory(destination / "images", item.get("images") or [])
                self._write_json(destination / "meta.json", item.get("meta") or {})

            existing_ids = {event.get("event_id") for event in self._all_audit()}
            for event in bundle.get("audit", []):
                if event.get("event_id") and event["event_id"] not in existing_ids:
                    self._append_audit(event)
                    existing_ids.add(event["event_id"])
                    audit_added += 1
            self._observe_clock(int(bundle.get("clock", 0)))
            state = self._state()
            state["last_applied_at"] = utc_now()
            state["last_applied_from"] = bundle.get("node")
            self._save_state(state)
            result = {"applied": applied, "ignored": ignored, "audit_added": audit_added}
            if self.git_repo and applied:
                try:
                    result["git"] = self.git_repo.sync_from_store(
                        self,
                        f"replication: apply {applied} document(s)",
                        f"Source: {bundle.get('node', 'unknown')}\nApplied: {applied}\n",
                    )
                except Exception as error:
                    result["git"] = {"status": "failed", "error": str(error)}
            return result

    def set_peer_status(self, peer: str, status: dict[str, Any]) -> None:
        with self.lock:
            state = self._state()
            state.setdefault("peers", {})[peer] = status
            state["last_sync_at"] = utc_now()
            self._save_state(state)

    def git_status(self) -> dict[str, Any]:
        if not self.git_repo:
            return {"enabled": False, "ready": False, "reason": "Git no configurado"}
        return self.git_repo.status()

    def sync_status(self) -> dict[str, Any]:
        with self.lock:
            state = self._state()
            return {
                "clock": state.get("clock", 0),
                "last_sync_at": state.get("last_sync_at"),
                "last_applied_at": state.get("last_applied_at"),
                "last_applied_from": state.get("last_applied_from"),
                "peers": state.get("peers", {}),
                "documents": len(self.list_documents(include_deleted=True)),
                "active_documents": len(self.list_documents(include_deleted=False)),
            }
