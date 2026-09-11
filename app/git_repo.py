from __future__ import annotations

import base64
import binascii
import json
import re
import shutil
# Subprocess is restricted to fixed argv, no shell and an absolute executable.
import subprocess  # nosec B404
import threading
from pathlib import Path
from typing import Any


GIT_BIN = "/usr/bin/git"


class GitRepositoryError(RuntimeError):
    """The local documental Git repository could not complete an operation."""


class GitRepository:
    """Persistent Git projection for documents and their metadata."""

    def __init__(self, repository_dir: Path, author_name: str, author_email: str) -> None:
        self.repository_dir = repository_dir
        self.author_name = author_name.strip() or "RTFM"
        self.author_email = author_email.strip() or "rtfm@localhost"
        self.lock = threading.RLock()
        self.repository_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _run(self, arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            # Every caller supplies an internal allowlisted Git operation;
            # shell=False and an absolute executable prevent command lookup.
            result = subprocess.run(  # nosec B603
                [GIT_BIN, "-C", str(self.repository_dir), *arguments],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (FileNotFoundError, OSError) as error:
            raise GitRepositoryError(f"Git no está disponible: {error}") from error
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise GitRepositoryError(detail or f"git {' '.join(arguments)} ha fallado")
        return result

    def _initialize(self) -> None:
        with self.lock:
            if not (self.repository_dir / ".git").is_dir():
                self._run(["init"])
                self._run(["branch", "-M", "main"])
            # La proyección ya serializa todas las operaciones. Evitar procesos de
            # mantenimiento en segundo plano impide carreras con backups, migraciones
            # y la retirada de repositorios efímeros durante las pruebas.
            self._run(["config", "maintenance.auto", "false"])
            self._run(["config", "gc.auto", "0"])
            self._run(["config", "user.name", self.author_name])
            self._run(["config", "user.email", self.author_email])
            readme = self.repository_dir / "README.md"
            if not readme.exists():
                readme.write_text(
                    "# RTFM\n\n"
                    "Proyección Git automática de documentos y metadatos. "
                    "El contenido fuente vive en la aplicación; este repositorio "
                    "conserva su historial documental.\n",
                    encoding="utf-8",
                )
            self._run(["add", "-A"])
            self._commit_staged("chore: initialize documental repository", "Source: rtfm\n")

    def _commit_staged(self, subject: str, body: str, actor: str | None = None) -> dict[str, Any]:
        if self._run(["diff", "--cached", "--quiet"], check=False).returncode == 0:
            return {"status": "unchanged", "commit": self.head()}
        arguments = ["commit"]
        if actor:
            safe_actor = re.sub(r"[^A-Za-z0-9 ._-]", "_", actor).strip()[:100] or "unknown"
            email_actor = re.sub(r"[^a-z0-9._-]", "-", actor.casefold()).strip("-")[:60] or "unknown"
            # ``.invalid`` is reserved for documentation and cannot collide with a LAN/mDNS
            # domain when the portable Git projection is moved to another installation.
            arguments.extend(["--author", f"{safe_actor} <{email_actor}@rtfm.invalid>"])
        arguments.extend(["-m", subject, "-m", body])
        self._run(arguments)
        return {"status": "committed", "commit": self.head()}

    def head(self) -> str | None:
        result = self._run(["rev-parse", "--verify", "HEAD"], check=False)
        return result.stdout.strip() or None

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_snapshot(self, snapshot: dict[str, Any]) -> None:
        meta = snapshot.get("meta") or {}
        document_id = str(meta.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", document_id):
            raise GitRepositoryError("Identificador de documento no válido para la proyección Git")
        document_dir = self.repository_dir / "documents" / document_id
        document_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(document_dir / "metadata.json", meta)
        content_path = document_dir / "content.md"
        if meta.get("status") == "deleted" or snapshot.get("content") is None:
            content_path.unlink(missing_ok=True)
        else:
            content_path.write_text(str(snapshot.get("content") or ""), encoding="utf-8")
        images_dir = document_dir / "images"
        if meta.get("status") == "deleted":
            if images_dir.exists():
                shutil.rmtree(images_dir)
            return
        images_dir.mkdir(parents=True, exist_ok=True)
        expected: set[str] = set()
        for image in snapshot.get("images") or []:
            image_id = str(image.get("id", ""))
            stored_name = str(image.get("stored_name", ""))
            if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", image_id) or Path(stored_name).name != stored_name:
                raise GitRepositoryError("Metadatos de imagen no válidos para la proyección Git")
            expected.update({stored_name, f"{image_id}.json"})
            image_data = image.get("data")
            if image_data is not None:
                try:
                    (images_dir / stored_name).write_bytes(base64.b64decode(str(image_data), validate=True))
                except (binascii.Error, ValueError, TypeError) as error:
                    raise GitRepositoryError("Contenido de imagen no válido para la proyección Git") from error
            self._write_json(images_dir / f"{image_id}.json", {key: value for key, value in image.items() if key != "data"})
        for path in images_dir.iterdir():
            if path.name not in expected:
                path.unlink()
        if not expected:
            images_dir.rmdir()

    def commit_document(self, event: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not snapshot:
            return {"status": "skipped", "reason": "documento no disponible"}
        with self.lock:
            self._write_snapshot(snapshot)
            self._run(["add", "-A", "--", "documents"])
            document_id = snapshot["meta"]["id"]
            subject = f"docs: {event.get('action', 'update')} {document_id}"
            body = (
                f"Actor: {event.get('actor', 'unknown')}\n"
                f"Operation-ID: {event.get('operation_id', '')}\n"
                f"Event-ID: {event.get('event_id', '')}\n"
                f"Node: {event.get('node', '')}\n"
            )
            return self._commit_staged(subject, body, str(event.get("actor", "")))

    def commit_catalog_entity(self, event: dict[str, Any], entity_type: str, entity: dict[str, Any]) -> dict[str, Any]:
        if entity_type not in {"library", "category"}:
            raise GitRepositoryError("Tipo de catálogo no válido")
        entity_id = str(entity.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", entity_id):
            raise GitRepositoryError("Identificador de catálogo no válido")
        with self.lock:
            folder = "libraries" if entity_type == "library" else "categories"
            self._write_json(self.repository_dir / "catalog" / folder / f"{entity_id}.json", entity)
            self._run(["add", "-A", "--", "catalog"])
            subject = f"catalog: {event.get('action', 'update')} {entity_id}"
            body = (
                f"Actor: {event.get('actor', 'unknown')}\n"
                f"Operation-ID: {event.get('operation_id', '')}\n"
                f"Event-ID: {event.get('event_id', '')}\n"
                f"Node: {event.get('node', '')}\n"
            )
            return self._commit_staged(subject, body, str(event.get("actor", "")))

    def commit_catalog_entities(self, event: dict[str, Any], entity_type: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
        if entity_type not in {"library", "category"}:
            raise GitRepositoryError("Tipo de catálogo no válido")
        folder = "libraries" if entity_type == "library" else "categories"
        with self.lock:
            for entity in entities:
                entity_id = str(entity.get("id", ""))
                if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", entity_id):
                    raise GitRepositoryError("Identificador de catálogo no válido")
                self._write_json(self.repository_dir / "catalog" / folder / f"{entity_id}.json", entity)
            self._run(["add", "-A", "--", "catalog"])
            subject = f"catalog: {event.get('action', 'update')} {len(entities)} {folder}"
            body = (
                f"Actor: {event.get('actor', 'unknown')}\n"
                f"Operation-ID: {event.get('operation_id', '')}\n"
                f"Event-ID: {event.get('event_id', '')}\n"
                f"Node: {event.get('node', '')}\n"
            )
            return self._commit_staged(subject, body, str(event.get("actor", "")))

    def sync_from_store(self, store: Any, subject: str, body: str) -> dict[str, Any]:
        with self.lock:
            documents_dir = self.repository_dir / "documents"
            documents_dir.mkdir(parents=True, exist_ok=True)
            expected: set[str] = set()
            for meta in store.list_documents(include_deleted=True):
                document_id = str(meta["id"])
                expected.add(document_id)
                snapshot = store.get_document(document_id, include_deleted=True, include_image_data=True)
                if snapshot:
                    self._write_snapshot(snapshot)
            for path in documents_dir.iterdir():
                if path.is_dir() and path.name not in expected:
                    shutil.rmtree(path)
            catalog_dir = self.repository_dir / "catalog"
            for entity_type, folder, items in (
                ("library", "libraries", store.list_libraries(include_deleted=True, include_counts=False)),
                ("category", "categories", store.list_categories(include_deleted=True)),
            ):
                entity_dir = catalog_dir / folder
                entity_dir.mkdir(parents=True, exist_ok=True)
                entity_expected = set()
                for entity in items:
                    entity_id = str(entity["id"])
                    entity_expected.add(f"{entity_id}.json")
                    self._write_json(entity_dir / f"{entity_id}.json", entity)
                for path in entity_dir.glob("*.json"):
                    if path.name not in entity_expected:
                        path.unlink()
            self._run(["add", "-A", "--", "documents", "catalog"])
            return self._commit_staged(subject, body)

    def status(self) -> dict[str, Any]:
        with self.lock:
            try:
                porcelain = self._run(["status", "--porcelain"]).stdout.splitlines()
                return {
                    "enabled": True,
                    "ready": True,
                    "repository": str(self.repository_dir),
                    "branch": self._run(["branch", "--show-current"]).stdout.strip() or "main",
                    "head": self.head(),
                    "clean": not porcelain,
                    "pending": len(porcelain),
                }
            except GitRepositoryError as error:
                return {"enabled": True, "ready": False, "repository": str(self.repository_dir), "error": str(error)}
