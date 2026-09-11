from __future__ import annotations

from dataclasses import dataclass

from .accounts import AccountSecurity
from .auth import LoginThrottle, SessionCodec
from .floating_ip import FloatingIPManager
from .roles import RoleInfo, detect_role
from .settings import Settings
from .storage import DocumentStore


@dataclass(frozen=True)
class Services:
    settings: Settings
    store: DocumentStore
    sessions: SessionCodec
    login_throttle: LoginThrottle
    account_security: AccountSecurity
    floating_ip: FloatingIPManager

    def role(self) -> RoleInfo:
        return detect_role(self.settings, self.floating_ip.effective_ip)
