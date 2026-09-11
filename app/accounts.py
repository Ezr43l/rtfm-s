from __future__ import annotations

import base64
import hashlib
import hmac
import io
import re
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken


USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}")
COMMON_PASSWORDS = {
    "123456789012",
    "administrador",
    "base-documental",
    "rtfm",
    "changeme1234",
    "password1234",
}


def normalize_username(value: str) -> str:
    username = value.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "El usuario debe tener entre 3 y 64 caracteres y usar únicamente letras, números, punto, guion o guion bajo"
        )
    return username


def normalize_display_name(value: str) -> str:
    display_name = " ".join(value.split())
    if not display_name or len(display_name) > 120:
        raise ValueError("El nombre debe tener entre 1 y 120 caracteres")
    return display_name


class AccountSecurity:
    """Password hashing, TOTP and encrypted account secrets."""

    SCRYPT_N = 2**15
    SCRYPT_R = 8
    SCRYPT_P = 1

    def __init__(self, secret: str, password_min_length: int = 12, issuer: str = "RTFM") -> None:
        self.password_min_length = max(12, password_min_length)
        self.issuer = issuer.strip() or "RTFM"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self.fernet = Fernet(key) if secret else None
        self.recovery_key = hashlib.sha256(("recovery:" + secret).encode("utf-8")).digest()
        self.api_token_key = hashlib.sha256(("api-token:" + secret).encode("utf-8")).digest()

    @property
    def available(self) -> bool:
        return self.fernet is not None

    def validate_password(self, password: str, username: str = "") -> None:
        if len(password) < self.password_min_length:
            raise ValueError(f"La contraseña debe tener al menos {self.password_min_length} caracteres")
        if len(password) > 256:
            raise ValueError("La contraseña no puede superar los 256 caracteres")
        compact = password.strip().casefold()
        if compact in COMMON_PASSWORDS:
            raise ValueError("La contraseña elegida es demasiado común")
        if username and compact == username.strip().casefold():
            raise ValueError("La contraseña no puede coincidir con el nombre de usuario")

    @classmethod
    def hash_password(cls, password: str) -> str:
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=cls.SCRYPT_N,
            r=cls.SCRYPT_R,
            p=cls.SCRYPT_P,
            dklen=32,
            maxmem=64 * 1024 * 1024,
        )
        return "$".join(
            (
                "scrypt",
                str(cls.SCRYPT_N),
                str(cls.SCRYPT_R),
                str(cls.SCRYPT_P),
                base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
                base64.urlsafe_b64encode(derived).decode("ascii").rstrip("="),
            )
        )

    @classmethod
    def verify_password(cls, password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt_value, expected_value = encoded.split("$", 5)
            if algorithm != "scrypt":
                return False
            salt = cls._decode(salt_value)
            expected = cls._decode(expected_value)
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(expected),
                maxmem=64 * 1024 * 1024,
            )
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))

    def encrypt(self, value: str) -> str:
        if not self.fernet:
            raise RuntimeError("El cifrado de credenciales no está configurado")
        return "fernet:" + self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str | None) -> str:
        if not self.fernet or not value or not value.startswith("fernet:"):
            raise ValueError("El secreto 2FA almacenado no es válido")
        try:
            return self.fernet.decrypt(value.removeprefix("fernet:").encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as error:
            raise ValueError("No se ha podido descifrar el secreto 2FA") from error

    @staticmethod
    def generate_totp_secret() -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

    @staticmethod
    def _totp(secret: str, counter: int, digits: int = 6) -> str:
        padding = "=" * (-len(secret) % 8)
        key = base64.b32decode((secret + padding).encode("ascii"), casefold=True)
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(value % (10**digits)).zfill(digits)

    @classmethod
    def verify_totp(cls, secret: str, code: str, timestamp: int | None = None, window: int = 1) -> bool:
        candidate = re.sub(r"\s+", "", code)
        if not re.fullmatch(r"\d{6}", candidate):
            return False
        counter = int(timestamp if timestamp is not None else time.time()) // 30
        return any(hmac.compare_digest(candidate, cls._totp(secret, counter + offset)) for offset in range(-window, window + 1))

    def provisioning_uri(self, username: str, secret: str) -> str:
        label = quote(f"{self.issuer}:{username}", safe="")
        query = urlencode(
            {
                "secret": secret,
                "issuer": self.issuer,
                "algorithm": "SHA1",
                "digits": "6",
                "period": "30",
            }
        )
        return f"otpauth://totp/{label}?{query}"

    @staticmethod
    def qr_data_url(uri: str) -> str:
        import qrcode
        from qrcode.image.svg import SvgPathFillImage

        image = qrcode.make(uri, image_factory=SvgPathFillImage, box_size=8, border=4)
        output = io.BytesIO()
        image.save(output)
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    @staticmethod
    def generate_recovery_codes(amount: int = 10) -> list[str]:
        codes: list[str] = []
        for _ in range(amount):
            raw = base64.b32encode(secrets.token_bytes(10)).decode("ascii").rstrip("=")
            codes.append("-".join(raw[index : index + 4] for index in range(0, 16, 4)))
        return codes

    @staticmethod
    def normalize_recovery_code(code: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", code).upper()

    def hash_recovery_code(self, code: str) -> str:
        normalized = self.normalize_recovery_code(code)
        return hmac.new(self.recovery_key, normalized.encode("ascii"), hashlib.sha256).hexdigest()

    def recovery_code_index(self, code: str, hashes: list[str]) -> int | None:
        candidate = self.hash_recovery_code(code)
        for index, expected in enumerate(hashes):
            if hmac.compare_digest(candidate, expected):
                return index
        return None

    def verify_second_factor(self, user: dict, code: str) -> tuple[str, int | None] | None:
        totp = user.get("totp") or {}
        if not totp.get("enabled"):
            return None
        try:
            secret = self.decrypt(totp.get("secret"))
        except ValueError:
            return None
        if self.verify_totp(secret, code):
            return ("totp", None)
        recovery_index = self.recovery_code_index(code, list(totp.get("recovery_code_hashes") or []))
        if recovery_index is not None:
            return ("recovery", recovery_index)
        return None

    def hash_api_token(self, token: str) -> str:
        return hmac.new(self.api_token_key, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def generate_api_token(self, client_id: str) -> tuple[str, str, str]:
        token = f"rtfm_{client_id.replace('-', '')[:8]}_{secrets.token_urlsafe(32)}"
        return token, self.hash_api_token(token), token[:19]
