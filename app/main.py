from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import auth, documents, favorites, libraries, logs, profile, replication, system, users
from .accounts import AccountSecurity
from .auth import LoginThrottle, SessionCodec
from .floating_ip import FloatingIPManager
from .git_repo import GitRepository
from .replication import sync_once_async
from .roles import ROLE_ACTIVE
from .services import Services
from .settings import Settings
from .storage import DocumentStore


STATIC_DIR = Path(__file__).parent / "static"


def build_services(settings: Settings) -> Services:
    git_repository = (
        GitRepository(settings.git_repo_dir, settings.git_author_name, settings.git_author_email)
        if settings.git_enabled
        else None
    )
    store = DocumentStore(settings.data_dir, settings.node_name, settings.retention_days, git_repository)
    return Services(
        settings,
        store,
        SessionCodec(settings.session_secret, settings.session_hours),
        LoginThrottle(settings.login_max_attempts, settings.login_window_seconds),
        AccountSecurity(settings.session_secret, settings.password_min_length, settings.totp_issuer),
        FloatingIPManager(settings),
    )


async def background_loop(container: Services) -> None:
    while True:
        await asyncio.sleep(container.settings.sync_interval_seconds)
        await asyncio.to_thread(container.floating_ip.ensure_claim)
        if container.role().role == ROLE_ACTIVE:
            try:
                await sync_once_async(container.store, container.settings, ROLE_ACTIVE)
                await asyncio.to_thread(container.store.purge_vault)
            except Exception as error:  # pragma: no cover - guardia permanente
                print(f"background operation failed: {error}", flush=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    container = build_services(configured)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.to_thread(container.floating_ip.ensure_claim)
        task = asyncio.create_task(background_loop(container))
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    application = FastAPI(
        title="RTFM API",
        description="API privada para bibliotecas, árboles documentales y alta disponibilidad.",
        version=system.application_version(),
        lifespan=lifespan,
    )
    application.state.services = container

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "")[:100] or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; img-src 'self' data: blob: https:; connect-src 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if configured.public_scheme == "https" and configured.session_cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        detail = error.detail if isinstance(error.detail, dict) else {}
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": str(detail.get("code") or f"HTTP_{error.status_code}"),
                    "message": str(detail.get("message") or error.detail),
                    "details": detail.get("details"),
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
            headers=error.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Los datos enviados no son válidos",
                    "details": jsonable_encoder(error.errors()),
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    api_prefix = "/api/v1"
    application.include_router(auth.router, prefix=api_prefix)
    application.include_router(profile.router, prefix=api_prefix)
    application.include_router(users.router, prefix=api_prefix)
    application.include_router(system.router, prefix=api_prefix)
    application.include_router(libraries.router, prefix=api_prefix)
    application.include_router(libraries.categories_router, prefix=api_prefix)
    application.include_router(documents.router, prefix=api_prefix)
    application.include_router(favorites.router, prefix=api_prefix)
    application.include_router(logs.router, prefix=api_prefix)
    application.include_router(replication.router, prefix=api_prefix)
    application.include_router(replication.internal_router, prefix=api_prefix)

    # Compatibilidad operativa: Keepalived y los nodos que aún ejecutan v0.0.6.
    application.add_api_route("/api/version", system.version, methods=["GET"], include_in_schema=False)
    application.add_api_route("/api/health", system.health, methods=["GET"], include_in_schema=False)
    application.add_api_route("/api/status", system.public_status, methods=["GET"], include_in_schema=False)
    application.include_router(replication.internal_router, prefix="/api", include_in_schema=False)

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Ruta API no encontrada")
        candidate = (STATIC_DIR / path).resolve()
        if path and STATIC_DIR.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=503, detail="La interfaz todavía no está compilada")
        return FileResponse(index)

    return application


app = create_app()
