from __future__ import annotations

import re
import socket
# Subprocess is restricted to fixed argv, no shell and an absolute executable.
import subprocess  # nosec B404
from dataclasses import dataclass

from .settings import Settings


ROLE_ACTIVE = "active"
ROLE_PASSIVE = "passive"
ROLE_UNKNOWN = "unknown"
IP_BIN = "/sbin/ip"


@dataclass(frozen=True)
class RoleInfo:
    role: str
    node_name: str
    owns_floating_ip: bool | None
    reason: str


def _local_ips() -> set[str]:
    addresses: set[str] = {"127.0.0.1"}
    try:
        _, _, resolved = socket.gethostbyname_ex(socket.gethostname())
        addresses.update(resolved)
    except OSError:
        pass
    try:
        output = subprocess.check_output(  # nosec B603
            [IP_BIN, "-o", "-4", "addr", "show"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        addresses.update(re.findall(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", output))
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return addresses


def detect_role(settings: Settings, floating_ip: str | None = None) -> RoleInfo:
    mode = settings.role_mode
    if mode == ROLE_ACTIVE:
        return RoleInfo(ROLE_ACTIVE, settings.node_name, True, "ROLE_MODE=active")
    if mode == ROLE_PASSIVE:
        return RoleInfo(ROLE_PASSIVE, settings.node_name, False, "ROLE_MODE=passive")
    if mode == ROLE_UNKNOWN:
        return RoleInfo(ROLE_UNKNOWN, settings.node_name, None, "ROLE_MODE=unknown")
    effective_ip = settings.floating_ip if floating_ip is None else floating_ip
    if not effective_ip:
        return RoleInfo(ROLE_UNKNOWN, settings.node_name, None, "No hay una IP flotante configurada ni reclamada")
    owns = effective_ip in _local_ips()
    if owns:
        return RoleInfo(ROLE_ACTIVE, settings.node_name, True, "La IP flotante está presente localmente")
    return RoleInfo(ROLE_PASSIVE, settings.node_name, False, "La IP flotante no está presente localmente")
