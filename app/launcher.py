"""Prepara la configuración persistente y supervisa el proceso web de RTFM."""

from __future__ import annotations

import json
import os
import secrets
import signal
import stat
# The launcher executes only a fixed Python module with separate arguments.
import subprocess  # nosec B404
import sys
from pathlib import Path


CONFIG_KEYS = {
    "NODE_NAME", "ROLE_MODE", "PUBLIC_SCHEME", "FORWARDED_ALLOW_IPS",
    "FLOATING_IP", "FLOATING_URL", "KEEPALIVED_API_URL",
    "KEEPALIVED_SERVICE", "KEEPALIVED_DESCRIPTION", "KEEPALIVED_CLAIM_ID",
    "KEEPALIVED_HEALTH_PATH", "KEEPALIVED_SERVICE_PORTS",
    "KEEPALIVED_TIMEOUT_SECONDS", "KEEPALIVED_ALLOW_INSECURE_HTTP",
    "KEEPALIVED_CA_FILE", "SESSION_HOURS", "SESSION_COOKIE_SECURE",
    "LOGIN_MAX_ATTEMPTS", "LOGIN_WINDOW_SECONDS", "PASSWORD_MIN_LENGTH",
    "TOTP_ISSUER", "REPLICATION_ALLOW_INSECURE_HTTP", "REPLICATION_CA_FILE",
    "MAX_REPLICATION_MB", "PEERS", "RETENTION_DAYS", "SYNC_INTERVAL_SECONDS",
    "MAX_IMAGE_SIZE_MB", "GIT_ENABLED", "GIT_REPO_DIR", "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
}
LEGACY_MARKERS = CONFIG_KEYS | {
    "APP_TOKEN", "APP_TOKEN_FILE", "SESSION_SECRET", "SESSION_SECRET_FILE",
    "REPLICATION_TOKEN", "REPLICATION_TOKEN_FILE", "KEEPALIVED_API_KEY",
    "KEEPALIVED_API_KEY_FILE",
}


def _paths() -> tuple[Path, Path, Path]:
    root = Path(os.environ.get("DATA_DIR", "/data")) / ".rtfm"
    return root / "config.json", root / "secrets", root / "restart-required"


def _read_config(path: Path) -> dict[str, str]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("La configuración persistente de RTFM no es un fichero regular")
    if metadata.st_size > 256 * 1024:
        raise RuntimeError("La configuración persistente de RTFM supera 256 KiB")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"schema", "environment"}:
        raise RuntimeError("La configuración persistente de RTFM tiene un contrato desconocido")
    environment = document.get("environment")
    if document.get("schema") != 1 or not isinstance(environment, dict):
        raise RuntimeError("La configuración persistente de RTFM usa otro esquema")
    if set(environment) != CONFIG_KEYS or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise RuntimeError("La configuración persistente de RTFM está incompleta")
    return environment


def read_persisted_environment(data_dir: Path) -> dict[str, str]:
    """Lee el contrato persistente sin depender del entorno del proceso."""
    return _read_config(Path(data_dir) / ".rtfm" / "config.json")


def _write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists():
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"La ruta privada no es un fichero regular: {path.name}")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


def prepare_environment(explicit: set[str]) -> Path:
    config_file, secret_dir, restart_file = _paths()
    if config_file.exists():
        for key, value in _read_config(config_file).items():
            if key not in explicit:
                os.environ[key] = value
        session_file = secret_dir / "session-secret"
        replication_file = secret_dir / "replication-token"
        keepalived_file = secret_dir / "keepalived-api-key"
        if not ({"SESSION_SECRET", "SESSION_SECRET_FILE"} & explicit):
            os.environ["SESSION_SECRET_FILE"] = str(session_file)
        if not ({"REPLICATION_TOKEN", "REPLICATION_TOKEN_FILE"} & explicit):
            os.environ["REPLICATION_TOKEN_FILE"] = str(replication_file)
        if keepalived_file.exists() and not ({"KEEPALIVED_API_KEY", "KEEPALIVED_API_KEY_FILE"} & explicit):
            os.environ["KEEPALIVED_API_KEY_FILE"] = str(keepalived_file)
        os.environ["RTFM_SETUP_REQUIRED"] = "0"
        return restart_file

    if any(key in explicit for key in LEGACY_MARKERS):
        os.environ["RTFM_SETUP_REQUIRED"] = "0"
        return restart_file

    _write_private(secret_dir / "session-secret", secrets.token_urlsafe(48))
    _write_private(secret_dir / "replication-token", secrets.token_urlsafe(48))
    os.environ["SESSION_SECRET_FILE"] = str(secret_dir / "session-secret")
    os.environ["REPLICATION_TOKEN_FILE"] = str(secret_dir / "replication-token")
    os.environ["RTFM_SETUP_REQUIRED"] = "1"
    return restart_file


def main() -> int:
    explicit = set(os.environ)
    child: subprocess.Popen | None = None

    def stop_child(signum, _frame) -> None:
        if child and child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)

    while True:
        restart_file = prepare_environment(explicit)
        restart_file.unlink(missing_ok=True)
        os.environ["RTFM_MANAGED_LAUNCHER"] = "1"
        command = [
            sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",  # nosec B104: escucha deliberada dentro del contenedor
            "--port", os.environ.get("PORT", "7400"),
        ]
        child = subprocess.Popen(command)  # nosec B603
        code = child.wait()
        child = None
        if restart_file.exists():
            restart_file.unlink(missing_ok=True)
            continue
        return code


if __name__ == "__main__":
    raise SystemExit(main())
