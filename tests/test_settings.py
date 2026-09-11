import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.settings import ConfigError, Settings


APP_TOKEN = "bootstrap-" + "a" * 30
SESSION_SECRET = "session-" + "b" * 32


class SettingsTests(unittest.TestCase):
    def test_empty_session_secret_falls_back_to_app_token(self) -> None:
        with patch.dict(
            os.environ,
            {"APP_TOKEN": APP_TOKEN, "SESSION_SECRET": ""},
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.app_token, APP_TOKEN)
        self.assertEqual(settings.session_secret, APP_TOKEN)

    def test_explicit_session_secret_takes_precedence(self) -> None:
        with patch.dict(
            os.environ,
            {"APP_TOKEN": APP_TOKEN, "SESSION_SECRET": SESSION_SECRET},
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.session_secret, SESSION_SECRET)

    def test_default_port_is_7400(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.port, 7400)
            self.assertEqual(settings.max_image_size_mb, 10)
            self.assertEqual(settings.keepalived_service, "rtfm")
            self.assertEqual(settings.keepalived_claim_id, "")
            self.assertEqual(settings.totp_issuer, "RTFM")

    def test_image_limit_is_configurable_but_bounded(self) -> None:
        with patch.dict(os.environ, {"MAX_IMAGE_SIZE_MB": "250"}, clear=True):
            self.assertEqual(Settings.from_env().max_image_size_mb, 100)

    def test_account_security_defaults_and_minimum_are_safe(self) -> None:
        with patch.dict(
            os.environ,
            {"PASSWORD_MIN_LENGTH": "6", "TOTP_ISSUER": "  Infra privada  "},
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.password_min_length, 12)
        self.assertEqual(settings.totp_issuer, "Infra privada")

    def test_keepalived_configuration_is_portable(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KEEPALIVED_SERVICE": "manuals",
                "KEEPALIVED_SERVICE_PORTS": "443, 8443,443,invalid,70000",
                "KEEPALIVED_TIMEOUT_SECONDS": "90",
                "PUBLIC_SCHEME": "https",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.keepalived_claim_id, "")
        self.assertEqual(settings.keepalived_service_ports, (443, 8443))
        self.assertEqual(settings.keepalived_timeout_seconds, 30)
        self.assertEqual(settings.public_scheme, "https")

    def test_remote_replication_http_requires_explicit_opt_in(self) -> None:
        with patch.dict(
            os.environ,
            {"PEERS": "node-b=http://192.0.2.20:7400"},
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                Settings.from_env()

    def test_secrets_can_be_loaded_from_files_without_direct_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret_file = Path(directory) / "session-secret"
            secret_file.write_text(SESSION_SECRET + "\n", encoding="utf-8")
            secret_file.chmod(0o600)
            with patch.dict(
                os.environ,
                {"SESSION_SECRET_FILE": str(secret_file)},
                clear=True,
            ):
                settings = Settings.from_env()

        self.assertEqual(settings.session_secret, SESSION_SECRET)

    def test_secret_files_reject_symlinks_hardlinks_and_broad_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.write_text(SESSION_SECRET, encoding="utf-8")
            target.chmod(0o600)

            symlink = root / "symlink"
            symlink.symlink_to(target)
            with patch.dict(os.environ, {"SESSION_SECRET_FILE": str(symlink)}, clear=True):
                with self.assertRaises(ConfigError):
                    Settings.from_env()

            hardlink = root / "hardlink"
            os.link(target, hardlink)
            with patch.dict(os.environ, {"SESSION_SECRET_FILE": str(target)}, clear=True):
                with self.assertRaisesRegex(ConfigError, "exactamente un enlace"):
                    Settings.from_env()
            hardlink.unlink()

            target.chmod(0o644)
            with patch.dict(os.environ, {"SESSION_SECRET_FILE": str(target)}, clear=True):
                with self.assertRaisesRegex(ConfigError, "grupo u otros"):
                    Settings.from_env()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "mkfifo no disponible")
    def test_secret_file_rejects_fifo_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "session-secret"
            os.mkfifo(fifo, 0o600)
            with patch.dict(os.environ, {"SESSION_SECRET_FILE": str(fifo)}, clear=True):
                with self.assertRaisesRegex(ConfigError, "fichero regular"):
                    Settings.from_env()

    def test_replication_secret_must_be_independent(self) -> None:
        with patch.dict(
            os.environ,
            {"SESSION_SECRET": SESSION_SECRET, "REPLICATION_TOKEN": SESSION_SECRET},
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
