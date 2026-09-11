"""Isolated TLS reverse-proxy and client gate for the packaged RTFM image."""

from __future__ import annotations

import http.client
import http.server
import json
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


TLS_DIR = Path("/tls")
CA_FILE = TLS_DIR / "ca.pem"
CERT_FILE = TLS_DIR / "server.pem"
KEY_FILE = TLS_DIR / "server-key.pem"
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_private(path: Path, content: bytes, mode: int) -> None:
    path.write_bytes(content)
    path.chmod(mode)


def generate_test_pki() -> None:
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RTFM isolated test CA")])
    ca_certificate = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "proxy")])
    server_certificate = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("proxy")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    write_private(
        CA_FILE,
        ca_certificate.public_bytes(serialization.Encoding.PEM),
        0o644,
    )
    write_private(
        CERT_FILE,
        server_certificate.public_bytes(serialization.Encoding.PEM),
        0o644,
    )
    write_private(
        KEY_FILE,
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        0o600,
    )


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self.proxy()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self.proxy()

    def proxy(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        require(0 <= length <= 1024 * 1024, "request body outside test limit")
        body = self.rfile.read(length) if length else None
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP and name.lower() != "x-test-client-ip"
        }
        forwarded_client = self.headers.get("X-Test-Client-IP", self.client_address[0])
        headers["X-Forwarded-For"] = forwarded_client
        headers["X-Forwarded-Proto"] = "https"
        headers["Connection"] = "close"

        connection = http.client.HTTPConnection(
            os.getenv("BACKEND_HOST", "rtfm"),
            int(os.getenv("BACKEND_PORT", "7400")),
            timeout=10,
        )
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in HOP_BY_HOP:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
        finally:
            connection.close()


def run_proxy() -> None:
    generate_test_pki()
    # The helper is reachable only from the disposable, unexposed Docker test network.
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8443), ProxyHandler)  # nosec B104
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(CERT_FILE, KEY_FILE)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def tls_request(
    method: str,
    path: str,
    *,
    payload: dict[str, str] | None = None,
    client_ip: str | None = None,
) -> tuple[int, list[tuple[str, str]], bytes, str]:
    context = ssl.create_default_context(cafile=str(CA_FILE))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPSConnection("proxy", 8443, context=context, timeout=10)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if client_ip:
        headers["X-Test-Client-IP"] = client_ip
    try:
        connection.connect()
        require(connection.sock is not None, "TLS socket was not established")
        tls_version = connection.sock.version() or ""
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read(), tls_version
    finally:
        connection.close()


def header_values(headers: list[tuple[str, str]], expected: str) -> list[str]:
    return [value for name, value in headers if name.lower() == expected.lower()]


def run_client() -> None:
    bootstrap = os.environ["APP_TOKEN"]
    status, headers, _body, tls_version = tls_request("GET", "/api/health")
    require(status == 200, f"HTTPS health returned {status}")
    require(tls_version in {"TLSv1.2", "TLSv1.3"}, f"unexpected TLS version: {tls_version}")
    require(
        header_values(headers, "Strict-Transport-Security")
        == ["max-age=31536000; includeSubDomains"],
        "HSTS is missing or unexpected",
    )
    require(header_values(headers, "X-Frame-Options") == ["DENY"], "frame protection missing")
    require(header_values(headers, "Cache-Control") == ["no-store"], "API cache policy missing")

    actor = "proxy-owner"
    invalid = {"actor": actor, "credential": "invalid isolated credential"}
    for _ in range(3):
        attempt, _headers, _payload, _tls = tls_request(
            "POST", "/api/v1/auth/session", payload=invalid, client_ip="198.51.100.10"
        )
        require(attempt == 401, f"trusted client A returned {attempt} before its limit")
    limited, _headers, _payload, _tls = tls_request(
        "POST", "/api/v1/auth/session", payload=invalid, client_ip="198.51.100.10"
    )
    require(limited == 429, f"trusted client A was not rate limited: {limited}")

    independent, _headers, _payload, _tls = tls_request(
        "POST", "/api/v1/auth/session", payload=invalid, client_ip="198.51.100.20"
    )
    require(independent == 401, "forwarded client B did not receive an independent throttle key")

    success, login_headers, _payload, _tls = tls_request(
        "POST",
        "/api/v1/auth/session",
        payload={"actor": actor, "credential": bootstrap},
        client_ip="198.51.100.20",
    )
    require(success == 200, f"HTTPS bootstrap login returned {success}")
    cookies = header_values(login_headers, "Set-Cookie")
    require(len(cookies) == 1 and cookies[0].startswith("rtfm_session="), "session cookie missing")
    normalized_cookie = cookies[0].lower()
    for attribute in ("secure", "httponly", "samesite=strict", "path=/"):
        require(attribute in normalized_cookie, f"session cookie lacks {attribute}")

    print("HTTPS proxy gate: TLS, CA, HSTS, secure cookie and trusted client IPs OK")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode == "proxy":
        run_proxy()
        return 0
    if mode == "client":
        run_client()
        return 0
    print("usage: https_proxy_smoke.py proxy|client", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
