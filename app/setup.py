"""Validación y persistencia del asistente inicial de RTFM."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import os
import re
import secrets
import ssl
import stat
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .accounts import normalize_display_name, normalize_username
from .launcher import CONFIG_KEYS, read_persisted_environment


NODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SERVICE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
CLAIM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")
KEEPALIVED_TOKEN_RE = re.compile(r"fip_[A-Za-z0-9_-]{32,128}")
CONFIGURATION_KEYS = {
    "node", "role_mode", "public", "keepalived", "replication", "policy", "git",
}


class SetupError(ValueError):
    pass


def _text(value: Any, name: str, maximum: int = 2048, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise SetupError(f"{name} debe ser texto")
    value = value.strip()
    if required and not value:
        raise SetupError(f"{name} es obligatorio")
    if len(value) > maximum or any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        raise SetupError(f"{name} contiene caracteres no permitidos")
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise SetupError(f"{name} no es válido")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise SetupError(f"{name} no es válido") from error
    if not minimum <= parsed <= maximum:
        raise SetupError(f"{name} debe estar entre {minimum} y {maximum}")
    return parsed


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise SetupError(f"{name} debe ser verdadero o falso")
    return value


def _loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _url(value: Any, name: str, allow_insecure: bool, required: bool = False) -> str:
    raw = _text(value, name, required=required).rstrip("/")
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SetupError(f"{name} debe ser una URL HTTP o HTTPS completa")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SetupError(f"{name} no admite credenciales, query ni fragmento")
    if parsed.scheme == "http" and not (_loopback(parsed.hostname) or allow_insecure):
        raise SetupError(f"{name} usa HTTP remoto; activa expresamente su excepción o usa HTTPS")
    return raw


def _certificate(value: Any, name: str) -> str:
    pem = _text(value, name, 128 * 1024)
    if not pem:
        return ""
    try:
        ssl.create_default_context(cadata=pem)
    except ssl.SSLError as error:
        raise SetupError(f"{name} no contiene certificados PEM válidos") from error
    return pem + ("" if pem.endswith("\n") else "\n")


def _decode_enrollment(code: str) -> dict[str, str]:
    try:
        raw = base64.urlsafe_b64decode((code + "=" * (-len(code) % 4)).encode("ascii"))
        document = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeError, ValueError) as error:
        raise SetupError("El código de incorporación no es válido") from error
    required = {"schema", "session", "replication", "service", "claim_id"}
    if not isinstance(document, dict) or set(document) != required or document.get("schema") != 1:
        raise SetupError("El código de incorporación no pertenece a RTFM")
    result = {key: str(document[key]) for key in required - {"schema"}}
    if len(result["session"]) < 32 or len(result["replication"]) < 32:
        raise SetupError("El código de incorporación contiene credenciales incompletas")
    if result["session"] == result["replication"]:
        raise SetupError("El código de incorporación reutiliza una credencial")
    if not SERVICE_RE.fullmatch(result["service"]) or not CLAIM_RE.fullmatch(result["claim_id"]):
        raise SetupError("El código de incorporación contiene una identidad no válida")
    return result


def _encode_enrollment(session: str, replication: str, service: str, claim_id: str) -> str:
    raw = json.dumps({
        "schema": 1, "session": session, "replication": replication,
        "service": service, "claim_id": claim_id,
    }, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _atomic_write(path: Path, value: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_private(path: Path) -> str:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise SetupError(f"El secreto {path.name} no es un fichero privado válido")
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 32:
        raise SetupError(f"El secreto {path.name} está incompleto")
    return value


def _read_optional_private(path: Path, maximum: int = 128 * 1024) -> str:
    if not path.exists() and not path.is_symlink():
        return ""
    metadata = path.lstat()
    if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1 or metadata.st_size > maximum):
        raise SetupError(f"El fichero privado {path.name} no es válido")
    return path.read_text(encoding="utf-8")


def _remove_private(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise SetupError(f"El fichero privado {path.name} no es válido")
    path.unlink()


def _stored_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def configuration_payload(container: Any) -> dict[str, Any]:
    """Devuelve todos los ajustes editables sin revelar credenciales."""
    root = container.settings.data_dir / ".rtfm"
    environment = read_persisted_environment(container.settings.data_dir)
    keepalived_key = root / "secrets" / "keepalived-api-key"
    keepalived_ca = root / "certificates" / "keepalived-ca.pem"
    replication_ca = root / "certificates" / "replication-ca.pem"
    keepalived_key_configured = bool(
        environment["KEEPALIVED_API_URL"] and _read_optional_private(keepalived_key, 4096).strip()
    )
    peers = []
    for item in environment["PEERS"].split(","):
        if not item:
            continue
        name, url = item.split("=", 1)
        peers.append({"name": name, "url": url})
    ports = [
        int(item) for item in environment["KEEPALIVED_SERVICE_PORTS"].split(",") if item
    ]
    return {
        "values": {
            "node": environment["NODE_NAME"],
            "role_mode": environment["ROLE_MODE"],
            "public": {
                "scheme": environment["PUBLIC_SCHEME"],
                "forwarded_allow_ips": environment["FORWARDED_ALLOW_IPS"],
                "floating_ip": environment["FLOATING_IP"],
                "floating_url": environment["FLOATING_URL"],
                "session_cookie_secure": _stored_bool(environment["SESSION_COOKIE_SECURE"]),
            },
            "keepalived": {
                "url": environment["KEEPALIVED_API_URL"],
                "api_key": "",
                "service": environment["KEEPALIVED_SERVICE"],
                "description": environment["KEEPALIVED_DESCRIPTION"],
                "claim_id": environment["KEEPALIVED_CLAIM_ID"],
                "health_path": environment["KEEPALIVED_HEALTH_PATH"],
                "service_ports": ports,
                "timeout_seconds": int(environment["KEEPALIVED_TIMEOUT_SECONDS"]),
                "allow_insecure_http": _stored_bool(
                    environment["KEEPALIVED_ALLOW_INSECURE_HTTP"]),
                "ca_pem": _read_optional_private(keepalived_ca),
            },
            "replication": {
                "peers": peers,
                "allow_insecure_http": _stored_bool(
                    environment["REPLICATION_ALLOW_INSECURE_HTTP"]),
                "ca_pem": _read_optional_private(replication_ca),
                "max_mb": int(environment["MAX_REPLICATION_MB"]),
            },
            "policy": {
                "retention_days": int(environment["RETENTION_DAYS"]),
                "sync_interval_seconds": int(environment["SYNC_INTERVAL_SECONDS"]),
                "max_image_size_mb": int(environment["MAX_IMAGE_SIZE_MB"]),
                "session_hours": int(environment["SESSION_HOURS"]),
                "login_max_attempts": int(environment["LOGIN_MAX_ATTEMPTS"]),
                "login_window_seconds": int(environment["LOGIN_WINDOW_SECONDS"]),
                "password_min_length": int(environment["PASSWORD_MIN_LENGTH"]),
                "totp_issuer": environment["TOTP_ISSUER"],
            },
            "git": {
                "enabled": _stored_bool(environment["GIT_ENABLED"]),
                "author_name": environment["GIT_AUTHOR_NAME"],
                "author_email": environment["GIT_AUTHOR_EMAIL"],
            },
        },
        "secrets": {"keepalived_api_key_configured": keepalived_key_configured},
    }


def validate_and_save(
    payload: dict[str, Any], container: Any, *, updating: bool = False,
) -> dict[str, Any]:
    settings = container.settings
    root = settings.data_dir / ".rtfm"
    config_file = root / "config.json"
    secret_dir = root / "secrets"
    if updating:
        if not config_file.exists() or not container.store.has_users():
            raise SetupError("Esta instancia de RTFM todavía no está configurada")
    elif not settings.setup_required or config_file.exists() or container.store.has_users():
        raise SetupError("Esta instancia de RTFM ya está configurada")
    if not isinstance(payload, dict) or set(payload) != {
        "node", "role_mode", "public", "keepalived", "replication", "policy",
        "git", "owner", "enrollment_code",
    }:
        raise SetupError("El formulario está incompleto o contiene campos desconocidos")

    node = _text(payload["node"], "Nombre del nodo", 64, True)
    if not NODE_RE.fullmatch(node):
        raise SetupError("El nombre del nodo contiene caracteres no permitidos")
    role_mode = _text(payload["role_mode"], "Modo de rol", 16, True).lower()
    if role_mode not in {"auto", "active", "passive", "unknown"}:
        raise SetupError("El modo de rol no es válido")

    public = payload["public"]
    if not isinstance(public, dict) or set(public) != {
        "scheme", "forwarded_allow_ips", "floating_ip", "floating_url", "session_cookie_secure",
    }:
        raise SetupError("La configuración pública está incompleta")
    scheme = _text(public["scheme"], "Esquema público", 8, True).lower()
    if scheme not in {"http", "https"}:
        raise SetupError("El esquema público debe ser http o https")
    forwarded = _text(public["forwarded_allow_ips"], "Proxies de confianza", 2048, True)
    if forwarded == "*":
        raise SetupError("No se puede confiar en cualquier proxy")
    for item in forwarded.split(","):
        try:
            ipaddress.ip_network(item.strip(), strict=False)
        except ValueError as error:
            raise SetupError("Los proxies de confianza deben ser IPs o redes válidas") from error
    floating_ip = _text(public["floating_ip"], "IP flotante", 64)
    if floating_ip:
        try:
            floating_ip = str(ipaddress.IPv4Address(floating_ip))
        except ipaddress.AddressValueError as error:
            raise SetupError("La IP flotante manual no es IPv4 válida") from error
    floating_url = _url(public["floating_url"], "URL flotante", True)
    cookie_secure = _boolean(public["session_cookie_secure"], "Cookie segura")
    if cookie_secure and scheme != "https":
        raise SetupError("La cookie Secure requiere publicar RTFM mediante HTTPS")

    keepalived = payload["keepalived"]
    if not isinstance(keepalived, dict) or set(keepalived) != {
        "url", "api_key", "service", "description", "claim_id", "health_path",
        "service_ports", "timeout_seconds", "allow_insecure_http", "ca_pem",
    }:
        raise SetupError("La configuración de Keepalived está incompleta")
    keep_insecure = _boolean(keepalived["allow_insecure_http"], "HTTP de Keepalived")
    keep_url = _url(keepalived["url"], "URL de Keepalived", keep_insecure)
    keep_key = _text(keepalived["api_key"], "Token de Keepalived", 1000)
    keepalived_key_path = secret_dir / "keepalived-api-key"
    if updating and keep_url and not keep_key:
        keep_key = _read_optional_private(keepalived_key_path, 4096).strip()
    if bool(keep_url) != bool(keep_key):
        raise SetupError("La URL y el token de Keepalived deben configurarse juntos")
    if keep_key and not KEEPALIVED_TOKEN_RE.fullmatch(keep_key):
        raise SetupError("El token de Keepalived no tiene el formato esperado")
    service = _text(keepalived["service"], "Servicio de Keepalived", 64) or "rtfm"
    if not SERVICE_RE.fullmatch(service):
        raise SetupError("El servicio de Keepalived no es válido")
    claim_id = _text(keepalived["claim_id"], "Identificador de reclamación", 128)
    description = _text(keepalived["description"], "Descripción de Keepalived", 200) or "RTFM"
    health_path = _text(keepalived["health_path"], "Ruta de salud", 256) or "/api/health"
    if not health_path.startswith("/") or any(character.isspace() for character in health_path):
        raise SetupError("La ruta de salud debe ser absoluta y no contener espacios")
    raw_ports = keepalived["service_ports"]
    if not isinstance(raw_ports, list) or len(raw_ports) > 32:
        raise SetupError("Los puertos adicionales de Keepalived no son válidos")
    ports = [_integer(port, "Puerto de Keepalived", 1, 65535) for port in raw_ports]
    if len(set(ports)) != len(ports):
        raise SetupError("Los puertos adicionales de Keepalived están repetidos")
    keep_timeout = _integer(keepalived["timeout_seconds"], "Timeout de Keepalived", 1, 30)
    keep_ca = _certificate(keepalived["ca_pem"], "CA de Keepalived")

    replication = payload["replication"]
    if not isinstance(replication, dict) or set(replication) != {
        "peers", "allow_insecure_http", "ca_pem", "max_mb",
    }:
        raise SetupError("La configuración de réplica está incompleta")
    replication_insecure = _boolean(replication["allow_insecure_http"], "HTTP de réplica")
    raw_peers = replication["peers"]
    if not isinstance(raw_peers, list) or len(raw_peers) > 64:
        raise SetupError("La lista de réplicas no es válida")
    peers: dict[str, str] = {}
    for raw_peer in raw_peers:
        if not isinstance(raw_peer, dict) or set(raw_peer) != {"name", "url"}:
            raise SetupError("Cada réplica debe incluir nombre y URL")
        peer_name = _text(raw_peer["name"], "Nombre de réplica", 64, True)
        if not NODE_RE.fullmatch(peer_name) or peer_name == node or peer_name in peers:
            raise SetupError("La lista contiene un nombre de réplica no válido o repetido")
        peers[peer_name] = _url(raw_peer["url"], f"URL de {peer_name}", replication_insecure, True)
    if len(set(peers.values())) != len(peers):
        raise SetupError("Las URLs de réplica no pueden repetirse")
    replication_ca = _certificate(replication["ca_pem"], "CA de réplica")
    max_replication = _integer(replication["max_mb"], "Tamaño máximo de réplica", 1, 4096)

    enrollment_code = _text(payload["enrollment_code"], "Código de incorporación", 8192)
    if updating and enrollment_code:
        raise SetupError("El código de incorporación sólo se utiliza durante el primer arranque")
    enrollment = _decode_enrollment(enrollment_code) if enrollment_code else None
    if enrollment:
        service = enrollment["service"]
        claim_id = enrollment["claim_id"]
    elif updating and not claim_id:
        claim_id = read_persisted_environment(settings.data_dir)["KEEPALIVED_CLAIM_ID"]
    else:
        claim_id = claim_id or f"rtfm-{secrets.token_hex(16)}"
    if not CLAIM_RE.fullmatch(claim_id):
        raise SetupError("El identificador de reclamación no es válido")
    if peers and role_mode == "active":
        raise SetupError("Un clúster no puede fijar varios nodos como activos; usa auto")
    if role_mode == "auto" and not floating_ip and not keep_url:
        raise SetupError("El modo auto requiere Keepalived o una IP flotante manual")

    policy = payload["policy"]
    if not isinstance(policy, dict) or set(policy) != {
        "retention_days", "sync_interval_seconds", "max_image_size_mb",
        "session_hours", "login_max_attempts", "login_window_seconds",
        "password_min_length", "totp_issuer",
    }:
        raise SetupError("Las políticas de la aplicación están incompletas")
    retention = _integer(policy["retention_days"], "Retención", 1, 36500)
    sync_interval = _integer(policy["sync_interval_seconds"], "Intervalo de réplica", 30, 86400)
    max_image = _integer(policy["max_image_size_mb"], "Tamaño de imagen", 1, 100)
    session_hours = _integer(policy["session_hours"], "Duración de sesión", 1, 8760)
    login_attempts = _integer(policy["login_max_attempts"], "Intentos de acceso", 3, 50)
    login_window = _integer(policy["login_window_seconds"], "Ventana de acceso", 30, 3600)
    password_min = _integer(policy["password_min_length"], "Longitud de contraseña", 12, 256)
    issuer = _text(policy["totp_issuer"], "Nombre 2FA", 120) or "RTFM"

    git = payload["git"]
    if not isinstance(git, dict) or set(git) != {"enabled", "author_name", "author_email"}:
        raise SetupError("La configuración Git está incompleta")
    git_enabled = _boolean(git["enabled"], "Historial Git")
    git_name = _text(git["author_name"], "Autor Git", 200) or "RTFM"
    git_email = _text(git["author_email"], "Correo Git", 320) or "rtfm@localhost"
    if "@" not in git_email or any(character.isspace() for character in git_email):
        raise SetupError("El correo técnico de Git no es válido")

    owner = payload["owner"]
    if updating:
        if owner not in (None, {}):
            raise SetupError("La cuenta propietaria no forma parte de la configuración del sistema")
        session_secret = _read_private(secret_dir / "session-secret")
        replication_secret = _read_private(secret_dir / "replication-token")
        owner_values = None
    elif enrollment:
        if owner not in (None, {}):
            raise SetupError("Los nodos incorporados reciben las cuentas mediante réplica")
        session_secret = enrollment["session"]
        replication_secret = enrollment["replication"]
        owner_values = None
    else:
        if not isinstance(owner, dict) or set(owner) != {"username", "display_name", "password"}:
            raise SetupError("La cuenta propietaria está incompleta")
        try:
            username = normalize_username(_text(owner["username"], "Usuario", 64, True))
            display_name = normalize_display_name(_text(owner["display_name"], "Nombre", 120, True))
            password = owner["password"]
            if not isinstance(password, str) or not password or len(password) > 256:
                raise SetupError("La contraseña no es válida")
            container.account_security.validate_password(password, username)
        except ValueError as error:
            raise SetupError(str(error)) from error
        session_secret = _read_private(secret_dir / "session-secret")
        replication_secret = _read_private(secret_dir / "replication-token")
        owner_values = (username, display_name, password)

    keep_ca_path = root / "certificates" / "keepalived-ca.pem"
    replication_ca_path = root / "certificates" / "replication-ca.pem"
    environment = {
        "NODE_NAME": node, "ROLE_MODE": role_mode, "PUBLIC_SCHEME": scheme,
        "FORWARDED_ALLOW_IPS": forwarded, "FLOATING_IP": floating_ip,
        "FLOATING_URL": floating_url, "KEEPALIVED_API_URL": keep_url,
        "KEEPALIVED_SERVICE": service, "KEEPALIVED_DESCRIPTION": description,
        "KEEPALIVED_CLAIM_ID": claim_id, "KEEPALIVED_HEALTH_PATH": health_path,
        "KEEPALIVED_SERVICE_PORTS": ",".join(str(port) for port in ports),
        "KEEPALIVED_TIMEOUT_SECONDS": str(keep_timeout),
        "KEEPALIVED_ALLOW_INSECURE_HTTP": "true" if keep_insecure else "false",
        "KEEPALIVED_CA_FILE": str(keep_ca_path) if keep_ca else "",
        "SESSION_HOURS": str(session_hours),
        "SESSION_COOKIE_SECURE": "true" if cookie_secure else "false",
        "LOGIN_MAX_ATTEMPTS": str(login_attempts),
        "LOGIN_WINDOW_SECONDS": str(login_window), "PASSWORD_MIN_LENGTH": str(password_min),
        "TOTP_ISSUER": issuer,
        "REPLICATION_ALLOW_INSECURE_HTTP": "true" if replication_insecure else "false",
        "REPLICATION_CA_FILE": str(replication_ca_path) if replication_ca else "",
        "MAX_REPLICATION_MB": str(max_replication),
        "PEERS": ",".join(f"{name}={url}" for name, url in peers.items()),
        "RETENTION_DAYS": str(retention), "SYNC_INTERVAL_SECONDS": str(sync_interval),
        "MAX_IMAGE_SIZE_MB": str(max_image), "GIT_ENABLED": "true" if git_enabled else "false",
        "GIT_REPO_DIR": str(settings.data_dir / "git"), "GIT_AUTHOR_NAME": git_name,
        "GIT_AUTHOR_EMAIL": git_email,
    }
    if set(environment) != CONFIG_KEYS:
        raise SetupError("La configuración interna generada está incompleta")

    _atomic_write(secret_dir / "session-secret", session_secret + "\n")
    _atomic_write(secret_dir / "replication-token", replication_secret + "\n")
    if keep_key:
        _atomic_write(keepalived_key_path, keep_key + "\n")
    elif updating:
        _remove_private(keepalived_key_path)
    if keep_ca:
        _atomic_write(keep_ca_path, keep_ca)
    elif updating:
        _remove_private(keep_ca_path)
    if replication_ca:
        _atomic_write(replication_ca_path, replication_ca)
    elif updating:
        _remove_private(replication_ca_path)
    if owner_values:
        username, display_name, password = owner_values
        password_hash = container.account_security.hash_password(password)
        user = container.store.create_owner(username, display_name, password_hash, username)
        container.store.update_user_password(str(user["id"]), username, password_hash)
    _atomic_write(config_file, json.dumps(
        {"schema": 1, "environment": environment}, ensure_ascii=False,
        indent=2, sort_keys=True,
    ) + "\n")
    enrollment_out = "" if enrollment else _encode_enrollment(
        session_secret, replication_secret, service, claim_id,
    )
    return {"ok": True, "restarting": os.environ.get("RTFM_MANAGED_LAUNCHER") == "1",
            "enrollment_code": enrollment_out}


def update_configuration(payload: dict[str, Any], container: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != CONFIGURATION_KEYS:
        raise SetupError("La configuración está incompleta o contiene campos desconocidos")
    return validate_and_save(
        {**payload, "owner": None, "enrollment_code": ""}, container, updating=True,
    )


def request_restart(data_dir: Path) -> None:
    restart_file = data_dir / ".rtfm" / "restart-required"
    _atomic_write(restart_file, "restart\n")
