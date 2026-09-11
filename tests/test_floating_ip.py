import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from app.floating_ip import FloatingIPManager
from app.settings import Settings


# Se construye por fragmentos para que el propio árbol exportable no contenga una
# credencial completa con formato válido. Sigue ejercitando exactamente el contrato real.
API_KEY = "fip_" + "0123456789abcdef" * 2 + "_" + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO"
LEGACY_API_KEY = "fip_" + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"


class FakeResponse:
    status = 201

    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _: int = -1) -> bytes:
        return self.body


class FloatingIPManagerTests(unittest.TestCase):
    def settings(self, **overrides: str) -> Settings:
        environment = {
            "KEEPALIVED_API_URL": "http://127.0.0.1:6060",
            "KEEPALIVED_API_KEY": API_KEY,
            "KEEPALIVED_SERVICE": "rtfm",
            "KEEPALIVED_CLAIM_ID": "provision:rtfm:test",
            "PORT": "7400",
            **overrides,
        }
        with patch.dict(os.environ, environment, clear=True):
            return Settings.from_env()

    def test_claim_uses_bearer_idempotency_and_returned_ip(self) -> None:
        response = FakeResponse({
            "reclamacion": {
                "ip": "192.0.2.50",
                "servicio": "rtfm",
                "puertos": [7400],
                "chequeo": {"puerto": 7400, "ruta": "/api/health"},
            },
            "repetida": False,
        })
        manager = FloatingIPManager(self.settings(KEEPALIVED_SERVICE_PORTS="443,7400"))

        with patch("app.floating_ip.urllib.request.urlopen", return_value=response) as open_url:
            status = manager.ensure_claim()

        request = open_url.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://127.0.0.1:6060/api/claims")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {API_KEY}")
        self.assertEqual(request.get_header("Idempotency-key"), "provision:rtfm:test")
        self.assertEqual(payload["puertos"], [443, 7400])
        self.assertEqual(payload["chequeo"], {"puerto": 7400, "ruta": "/api/health"})
        self.assertEqual(manager.effective_ip, "192.0.2.50")
        self.assertEqual(manager.active_url, "http://192.0.2.50:7400")
        self.assertEqual(status["state"], "ok")
        self.assertNotIn("api_key", status)

    def test_accepts_token_generated_by_keepalived_0_14_1(self) -> None:
        manager = FloatingIPManager(self.settings(KEEPALIVED_API_KEY=LEGACY_API_KEY))
        self.assertEqual(manager.settings.keepalived_api_key, LEGACY_API_KEY)

    def test_remote_http_requires_explicit_opt_in(self) -> None:
        manager = FloatingIPManager(self.settings(KEEPALIVED_API_URL="http://192.0.2.20:6060"))

        with patch("app.floating_ip.urllib.request.urlopen") as open_url:
            status = manager.ensure_claim()

        open_url.assert_not_called()
        self.assertEqual(status["state"], "unknown")
        self.assertIn("KEEPALIVED_ALLOW_INSECURE_HTTP", status["error"])

    def test_manual_ip_remains_a_safe_fallback(self) -> None:
        with patch.dict(os.environ, {"FLOATING_IP": "192.0.2.70", "PORT": "7400"}, clear=True):
            manager = FloatingIPManager(Settings.from_env())

        self.assertEqual(manager.status()["state"], "manual")
        self.assertEqual(manager.effective_ip, "192.0.2.70")
        self.assertEqual(manager.active_url, "http://192.0.2.70:7400")

    def test_http_error_never_exposes_the_bearer(self) -> None:
        error = urllib.error.HTTPError(
            "http://127.0.0.1:6060/api/claims",
            401,
            "Unauthorized",
            None,
            io.BytesIO(json.dumps({"error": f"bad token {API_KEY}"}).encode("utf-8")),
        )
        manager = FloatingIPManager(self.settings())

        with patch("app.floating_ip.urllib.request.urlopen", side_effect=error):
            status = manager.ensure_claim()

        self.assertNotIn(API_KEY, status["error"])
        self.assertIn("[credencial]", status["error"])

    def test_status_sanitizes_credentials_from_a_bad_url(self) -> None:
        manager = FloatingIPManager(self.settings(
            KEEPALIVED_API_URL="https://user:password@keepalived.example:6060/panel"
        ))

        status = manager.ensure_claim()

        self.assertEqual(status["api_url"], "https://keepalived.example:6060/panel")
        self.assertNotIn("password", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
