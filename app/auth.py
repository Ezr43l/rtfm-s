from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass


COOKIE_NAME = "rtfm_session"


class LoginThrottle:
    """Límite de intentos por origen y usuario sin almacenar contraseñas."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def key(remote_ip: str | None, actor: str) -> str:
        return f"{(remote_ip or 'unknown')[:80]}:{actor.strip().casefold()[:80]}"

    def _recent(self, key: str, now: float) -> list[float]:
        threshold = now - self.window_seconds
        recent = [value for value in self._failures.get(key, []) if value > threshold]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) < self.max_attempts:
                return 0
            return max(1, int(self.window_seconds - (now - recent[0])))

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = self._recent(key, now)
            recent.append(now)
            self._failures[key] = recent[-self.max_attempts :]
            if len(self._failures) > 10_000:
                self._failures.pop(next(iter(self._failures)))

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def _encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


@dataclass(frozen=True)
class Identity:
    actor: str
    csrf_token: str
    expires_at: int
    method: str = "session"
    user_id: str | None = None
    session_version: int = 0
    display_name: str = ""
    role: str = "reader"
    identity_type: str = "person"
    api_client_id: str | None = None


class SessionCodec:
    def __init__(self, secret: str, lifetime_hours: int) -> None:
        self.secret = secret.encode("utf-8")
        self.lifetime_seconds = lifetime_hours * 3600

    @property
    def available(self) -> bool:
        return bool(self.secret)

    def create(
        self,
        actor: str,
        user_id: str | None = None,
        session_version: int = 0,
        display_name: str = "",
        role: str = "reader",
    ) -> tuple[str, Identity]:
        if not self.available:
            raise RuntimeError("Las sesiones no están configuradas")
        now = int(time.time())
        payload = {
            "actor": actor.strip()[:200],
            "csrf": secrets.token_urlsafe(24),
            "iat": now,
            "exp": now + self.lifetime_seconds,
            "nonce": secrets.token_hex(12),
            "uid": user_id,
            "sv": session_version,
            "name": display_name.strip()[:120],
            "role": role,
        }
        encoded = _encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        signature = _encode(hmac.new(self.secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"{encoded}.{signature}", Identity(
            payload["actor"],
            payload["csrf"],
            payload["exp"],
            user_id=payload["uid"],
            session_version=payload["sv"],
            display_name=payload["name"],
            role=payload["role"],
        )

    def parse(self, token: str | None) -> Identity | None:
        if not token or not self.available or "." not in token:
            return None
        encoded, signature = token.split(".", 1)
        expected = _encode(hmac.new(self.secret, encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(_decode(encoded).decode("utf-8"))
            expires_at = int(payload["exp"])
            actor = str(payload["actor"]).strip()
            csrf = str(payload["csrf"])
            user_id = str(payload.get("uid") or "").strip() or None
            session_version = int(payload.get("sv", 0))
            display_name = str(payload.get("name") or "").strip()
            role = str(payload.get("role") or "reader").strip()
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if expires_at <= int(time.time()) or not actor or not csrf:
            return None
        return Identity(
            actor[:200],
            csrf,
            expires_at,
            user_id=user_id,
            session_version=session_version,
            display_name=display_name[:120],
            role=role,
        )

    @staticmethod
    def credential_matches(candidate: str, expected: str) -> bool:
        return bool(expected) and hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))
