from __future__ import annotations

import ipaddress
import json
import re
import ssl
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .settings import Settings
from .version import USER_AGENT


class FloatingIPError(RuntimeError):
    """A safe-to-display error raised by the Keepalived connector."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class FloatingIPManager:
    """Claims and remembers the VIP assigned to this RTFM installation.

    Every node uses the same service name and idempotency key. Keepalived can
    therefore answer all of them with the same claim without allocating extra
    addresses. A node stopping must not release that shared claim: the other
    replicas still depend on it.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._claimed_ip: str | None = None
        self._claim: dict[str, Any] | None = None
        self._last_attempt_at: str | None = None
        self._last_success_at: str | None = None
        self._error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.keepalived_api_url or self.settings.keepalived_api_key)

    @property
    def effective_ip(self) -> str:
        with self._lock:
            return self._claimed_ip or self.settings.floating_ip

    @property
    def active_url(self) -> str:
        if self.settings.floating_url:
            return self.settings.floating_url
        ip = self.effective_ip
        if not ip:
            return ""
        return f"{self.settings.public_scheme}://{ip}:{self.settings.port}"

    def _base_url(self) -> str:
        raw = self.settings.keepalived_api_url.strip().rstrip("/")
        if not raw:
            raise FloatingIPError("KEEPALIVED_API_URL no está configurada")
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise FloatingIPError("KEEPALIVED_API_URL debe ser una URL HTTP o HTTPS completa")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise FloatingIPError("KEEPALIVED_API_URL no admite credenciales, query ni fragmento")
        if parsed.scheme == "http" and not (
            _is_loopback(parsed.hostname) or self.settings.keepalived_allow_insecure_http
        ):
            raise FloatingIPError(
                "La API de Keepalived usa HTTP fuera del host local; configura HTTPS o "
                "activa KEEPALIVED_ALLOW_INSECURE_HTTP de forma explícita"
            )
        return raw

    def _ssl_context(self) -> ssl.SSLContext | None:
        if urlsplit(self.settings.keepalived_api_url).scheme != "https":
            return None
        ca_file = self.settings.keepalived_ca_file
        if ca_file and not ca_file.is_file():
            raise FloatingIPError(f"No existe la CA configurada para Keepalived: {ca_file}")
        return ssl.create_default_context(cafile=str(ca_file) if ca_file else None)

    def _payload(self) -> dict[str, Any]:
        ports = sorted(set(self.settings.keepalived_service_ports + (self.settings.port,)))
        return {
            "servicio": self.settings.keepalived_service,
            "descripcion": self.settings.keepalived_description,
            "puertos": list(ports),
            "chequeo": {
                "puerto": self.settings.port,
                "ruta": self.settings.keepalived_health_path,
            },
        }

    def _request_claim(self) -> dict[str, Any]:
        if not self.settings.keepalived_api_key:
            raise FloatingIPError("KEEPALIVED_API_KEY no está configurada")
        if not re.fullmatch(r"fip_[A-Za-z0-9_-]{32,128}", self.settings.keepalived_api_key):
            raise FloatingIPError("KEEPALIVED_API_KEY no tiene el formato fip_ esperado")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.settings.keepalived_service):
            raise FloatingIPError("KEEPALIVED_SERVICE no es un identificador válido")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", self.settings.keepalived_claim_id):
            raise FloatingIPError("KEEPALIVED_CLAIM_ID no es un identificador idempotente válido")
        if not self.settings.keepalived_health_path.startswith("/") or any(
            character.isspace() for character in self.settings.keepalived_health_path
        ):
            raise FloatingIPError("KEEPALIVED_HEALTH_PATH debe ser una ruta HTTP absoluta sin espacios")
        body = json.dumps(self._payload(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url()}/api/claims",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.keepalived_api_key}",
                "Content-Type": "application/json; charset=utf-8",
                "Idempotency-Key": self.settings.keepalived_claim_id,
                "User-Agent": USER_AGENT,
            },
        )
        try:
            # _base_url() rejects every scheme except HTTP(S), credentials,
            # queries and fragments before the request is constructed.
            with urllib.request.urlopen(  # nosec B310
                request,
                timeout=self.settings.keepalived_timeout_seconds,
                context=self._ssl_context(),
            ) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise FloatingIPError("La respuesta de Keepalived es demasiado grande")
                result = json.loads(raw.decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            raw = error.read(8192).decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
                detail = parsed.get("error") or parsed.get("detail") or raw
                if isinstance(detail, dict):
                    detail = detail.get("message") or detail.get("code") or str(detail)
            except json.JSONDecodeError:
                detail = raw.strip() or error.reason
            safe_detail = str(detail).replace(self.settings.keepalived_api_key, "[credencial]")[:500]
            raise FloatingIPError(f"Keepalived devolvió HTTP {error.code}: {safe_detail}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise FloatingIPError(f"No se pudo contactar con Keepalived: {error.reason if isinstance(error, urllib.error.URLError) else error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FloatingIPError("Keepalived no devolvió un JSON válido") from error

        if not isinstance(result, dict) or not isinstance(result.get("reclamacion"), dict):
            raise FloatingIPError("La respuesta de Keepalived no contiene una reclamación")
        return result

    def ensure_claim(self) -> dict[str, Any]:
        """Create or revalidate the shared idempotent claim.

        Configuration failures are retained as operational state instead of
        terminating the web process, so `/api/health` can explain why the node
        remains in the safe `unknown` role.
        """
        with self._lock:
            self._last_attempt_at = _utc_now()
        if not self.configured:
            return self.status()
        try:
            response = self._request_claim()
            claim = response["reclamacion"]
            ip = str(ipaddress.IPv4Address(str(claim.get("ip") or "")))
            if claim.get("servicio") != self.settings.keepalived_service:
                raise FloatingIPError("Keepalived devolvió una reclamación de otro servicio")
            with self._lock:
                self._claimed_ip = ip
                self._claim = claim
                self._last_success_at = _utc_now()
                self._error = None
        except (FloatingIPError, ValueError) as error:
            with self._lock:
                self._error = str(error).replace(
                    self.settings.keepalived_api_key, "[credencial]"
                )[:500]
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._claimed_ip:
                state = "ok" if not self._error else "degraded"
                source = "keepalived"
            elif self.settings.floating_ip:
                state = "degraded" if self.configured else "manual"
                source = "manual"
            else:
                state = "unknown" if self.configured else "disabled"
                source = None
            api_url = None
            if self.settings.keepalived_api_url:
                try:
                    parsed = urlsplit(self.settings.keepalived_api_url)
                    host = parsed.hostname or ""
                    if ":" in host and not host.startswith("["):
                        host = f"[{host}]"
                    port = f":{parsed.port}" if parsed.port else ""
                    api_url = f"{parsed.scheme}://{host}{port}{parsed.path}" if parsed.scheme and host else None
                except ValueError:
                    api_url = None
            return {
                "configured": self.configured,
                "state": state,
                "source": source,
                "api_url": api_url,
                "service": self.settings.keepalived_service,
                "claim_id": self.settings.keepalived_claim_id,
                "ip": self._claimed_ip or self.settings.floating_ip or None,
                "last_attempt_at": self._last_attempt_at,
                "last_success_at": self._last_success_at,
                "error": self._error,
            }
