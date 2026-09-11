from __future__ import annotations

import ipaddress
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """La configuración impide arrancar o replicar de forma segura."""


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _peers(value: str, allow_insecure_http: bool) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ConfigError("PEERS debe usar el formato nombre=https://host:puerto")
        name, url = item.split("=", 1)
        name = name.strip()
        url = url.strip().rstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
            raise ConfigError(f"PEERS contiene un nombre de nodo no válido: {name or '[vacío]'}")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ConfigError(f"PEERS contiene una URL no válida para {name}")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigError(f"La URL de {name} no admite credenciales, query ni fragmento")
        if parsed.scheme == "http" and not (_is_loopback(parsed.hostname) or allow_insecure_http):
            raise ConfigError(
                f"La réplica hacia {name} usa HTTP remoto; configura HTTPS o activa "
                "REPLICATION_ALLOW_INSECURE_HTTP de forma explícita"
            )
        result[name] = url
    return result


def _secret_env(name: str) -> str:
    direct = os.getenv(name, "").strip()
    filename = os.getenv(f"{name}_FILE", "").strip()
    if direct and filename:
        raise ConfigError(f"Configura sólo {name} o {name}_FILE, no ambos")
    if not filename:
        return direct
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ConfigError(f"{name}_FILE requiere un runtime con apertura O_NOFOLLOW")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(filename, flags)
    except OSError as error:
        raise ConfigError(f"No se puede leer {name}_FILE: {type(error).__name__}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ConfigError(f"{name}_FILE debe ser un fichero regular")
        if metadata.st_nlink != 1:
            raise ConfigError(f"{name}_FILE debe tener exactamente un enlace")
        mode = stat.S_IMODE(metadata.st_mode)
        effective_uid = os.geteuid() if hasattr(os, "geteuid") else metadata.st_uid
        if metadata.st_uid == effective_uid:
            if mode not in {0o400, 0o600}:
                raise ConfigError(
                    f"{name}_FILE requiere modo 0400 o 0600 y no puede conceder "
                    "permisos a grupo u otros"
                )
        elif metadata.st_uid == 0:
            # Docker/Swarm secrets are commonly mounted root:root 0444. They are
            # immutable inside this single-process container; permit read bits but
            # never group/other write or any executable bit.
            if mode & 0o7133 or not (mode & 0o044):
                raise ConfigError(f"{name}_FILE root-owned tiene permisos inseguros")
        else:
            raise ConfigError(f"{name}_FILE pertenece a un UID no permitido")
        if metadata.st_size > 64 * 1024:
            raise ConfigError(f"{name}_FILE supera 64 KiB")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(8192, 64 * 1024 + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > 64 * 1024:
                raise ConfigError(f"{name}_FILE supera 64 KiB")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ConfigError(f"{name}_FILE no contiene UTF-8 válido") from error


def _ports_env(name: str) -> tuple[int, ...]:
    result: list[int] = []
    for raw in os.getenv(name, "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            port = int(raw)
        except ValueError:
            continue
        if 1 <= port <= 65535 and port not in result:
            result.append(port)
    return tuple(result)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    node_name: str
    role_mode: str
    floating_ip: str
    floating_url: str
    public_scheme: str
    keepalived_api_url: str
    keepalived_api_key: str
    keepalived_service: str
    keepalived_description: str
    keepalived_claim_id: str
    keepalived_health_path: str
    keepalived_service_ports: tuple[int, ...]
    keepalived_timeout_seconds: int
    keepalived_allow_insecure_http: bool
    keepalived_ca_file: Path | None
    app_token: str
    session_secret: str
    session_hours: int
    session_cookie_secure: bool
    login_max_attempts: int
    login_window_seconds: int
    password_min_length: int
    totp_issuer: str
    replication_token: str
    replication_allow_insecure_http: bool
    replication_ca_file: Path | None
    max_replication_mb: int
    peers: dict[str, str]
    retention_days: int
    sync_interval_seconds: int
    max_image_size_mb: int
    port: int
    git_enabled: bool
    git_repo_dir: Path
    git_author_name: str
    git_author_email: str
    setup_required: bool = False

    @property
    def max_replication_bytes(self) -> int:
        return self.max_replication_mb * 1024 * 1024

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.node_name):
            raise ConfigError("NODE_NAME debe tener entre 1 y 64 caracteres seguros")
        if self.role_mode not in {"auto", "active", "passive", "unknown"}:
            raise ConfigError("ROLE_MODE debe ser auto, active, passive o unknown")
        if not 1 <= self.port <= 65535:
            raise ConfigError("PORT debe estar entre 1 y 65535")
        if self.node_name in self.peers:
            raise ConfigError("PEERS no debe incluir el NODE_NAME local")
        if self.app_token and len(self.app_token) < self.password_min_length:
            raise ConfigError(
                f"APP_TOKEN debe tener al menos {self.password_min_length} caracteres"
            )
        if self.session_secret and len(self.session_secret) < 32:
            raise ConfigError("SESSION_SECRET debe tener al menos 32 caracteres")
        if self.replication_token and len(self.replication_token) < 32:
            raise ConfigError("REPLICATION_TOKEN debe tener al menos 32 caracteres")
        if self.replication_token and self.replication_token in {
            self.app_token,
            self.session_secret,
        }:
            raise ConfigError("REPLICATION_TOKEN debe ser distinto de los demás secretos")

    @classmethod
    def from_env(cls) -> "Settings":
        app_token = _secret_env("APP_TOKEN")
        # DockerMan conserva las variables opcionales aunque su valor este vacio.
        # En ese caso tambien debemos aplicar la compatibilidad documentada y no
        # deshabilitar por accidente todas las sesiones web.
        explicit_session_secret = _secret_env("SESSION_SECRET")
        session_secret = explicit_session_secret or app_token
        if explicit_session_secret and app_token and explicit_session_secret == app_token:
            raise ConfigError("SESSION_SECRET debe ser distinto de APP_TOKEN")
        service = os.getenv("KEEPALIVED_SERVICE", "rtfm").strip() or "rtfm"
        ca_file = os.getenv("KEEPALIVED_CA_FILE", "").strip()
        replication_ca_file = os.getenv("REPLICATION_CA_FILE", "").strip()
        replication_allow_insecure_http = _bool_env("REPLICATION_ALLOW_INSECURE_HTTP", False)
        public_scheme = os.getenv("PUBLIC_SCHEME", "http").strip().lower()
        if public_scheme not in {"http", "https"}:
            raise ConfigError("PUBLIC_SCHEME debe ser http o https")
        configured = cls(
            data_dir=Path(os.getenv("DATA_DIR", "/data")),
            node_name=os.getenv("NODE_NAME", "local"),
            role_mode=os.getenv("ROLE_MODE", "auto").lower(),
            floating_ip=os.getenv("FLOATING_IP", "").strip(),
            floating_url=os.getenv("FLOATING_URL", "").strip(),
            public_scheme=public_scheme,
            keepalived_api_url=os.getenv("KEEPALIVED_API_URL", "").strip().rstrip("/"),
            keepalived_api_key=_secret_env("KEEPALIVED_API_KEY"),
            keepalived_service=service,
            keepalived_description=os.getenv("KEEPALIVED_DESCRIPTION", "RTFM").strip() or "RTFM",
            keepalived_claim_id=os.getenv("KEEPALIVED_CLAIM_ID", "").strip(),
            keepalived_health_path=os.getenv("KEEPALIVED_HEALTH_PATH", "/api/health").strip()
            or "/api/health",
            keepalived_service_ports=_ports_env("KEEPALIVED_SERVICE_PORTS"),
            keepalived_timeout_seconds=max(1, min(30, _int_env("KEEPALIVED_TIMEOUT_SECONDS", 5))),
            keepalived_allow_insecure_http=_bool_env("KEEPALIVED_ALLOW_INSECURE_HTTP", False),
            keepalived_ca_file=Path(ca_file) if ca_file else None,
            app_token=app_token,
            session_secret=session_secret,
            session_hours=max(1, _int_env("SESSION_HOURS", 12)),
            session_cookie_secure=_bool_env("SESSION_COOKIE_SECURE", False),
            login_max_attempts=max(3, min(50, _int_env("LOGIN_MAX_ATTEMPTS", 5))),
            login_window_seconds=max(30, min(3600, _int_env("LOGIN_WINDOW_SECONDS", 300))),
            password_min_length=max(12, _int_env("PASSWORD_MIN_LENGTH", 12)),
            totp_issuer=os.getenv("TOTP_ISSUER", "RTFM").strip() or "RTFM",
            replication_token=_secret_env("REPLICATION_TOKEN"),
            replication_allow_insecure_http=replication_allow_insecure_http,
            replication_ca_file=Path(replication_ca_file) if replication_ca_file else None,
            max_replication_mb=max(1, min(4096, _int_env("MAX_REPLICATION_MB", 512))),
            peers=_peers(os.getenv("PEERS", ""), replication_allow_insecure_http),
            retention_days=max(1, _int_env("RETENTION_DAYS", 90)),
            sync_interval_seconds=max(30, _int_env("SYNC_INTERVAL_SECONDS", 300)),
            max_image_size_mb=max(1, min(100, _int_env("MAX_IMAGE_SIZE_MB", 10))),
            port=_int_env("PORT", 7400),
            git_enabled=_bool_env("GIT_ENABLED", False),
            git_repo_dir=Path(os.getenv("GIT_REPO_DIR", "/data/git")),
            git_author_name=os.getenv("GIT_AUTHOR_NAME", "RTFM").strip(),
            git_author_email=os.getenv("GIT_AUTHOR_EMAIL", "rtfm@localhost").strip(),
            setup_required=_bool_env("RTFM_SETUP_REQUIRED", False),
        )
        configured.validate()
        return configured
