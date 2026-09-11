from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.launcher import CONFIG_KEYS, prepare_environment
from app.main import build_services
from app.settings import Settings
from app.setup import (
    SetupError,
    configuration_payload,
    update_configuration,
    validate_and_save,
)


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="rtfm-setup-"))
        secret_dir = self.root / ".rtfm" / "secrets"
        secret_dir.mkdir(parents=True)
        (secret_dir / "session-secret").write_text("session-" + "a" * 48 + "\n", encoding="utf-8")
        (secret_dir / "replication-token").write_text("replication-" + "b" * 48 + "\n", encoding="utf-8")
        for path in secret_dir.iterdir():
            path.chmod(0o600)
        environment = {
            "DATA_DIR": str(self.root), "ROLE_MODE": "active", "RTFM_SETUP_REQUIRED": "1",
            "SESSION_SECRET_FILE": str(secret_dir / "session-secret"),
            "REPLICATION_TOKEN_FILE": str(secret_dir / "replication-token"),
            "GIT_ENABLED": "false",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.settings = Settings.from_env()
        self.container = build_services(self.settings)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def payload() -> dict:
        return {
            "node": "node-a", "role_mode": "active",
            "public": {
                "scheme": "http", "forwarded_allow_ips": "127.0.0.1",
                "floating_ip": "", "floating_url": "", "session_cookie_secure": False,
            },
            "keepalived": {
                "url": "", "api_key": "", "service": "rtfm", "description": "RTFM",
                "claim_id": "", "health_path": "/api/health", "service_ports": [],
                "timeout_seconds": 5, "allow_insecure_http": False, "ca_pem": "",
            },
            "replication": {
                "peers": [], "allow_insecure_http": False, "ca_pem": "", "max_mb": 512,
            },
            "policy": {
                "retention_days": 90, "sync_interval_seconds": 300,
                "max_image_size_mb": 10, "session_hours": 12,
                "login_max_attempts": 5, "login_window_seconds": 300,
                "password_min_length": 12, "totp_issuer": "RTFM",
            },
            "git": {"enabled": True, "author_name": "RTFM", "author_email": "rtfm@localhost"},
            "owner": {
                "username": "owner", "display_name": "Owner",
                "password": "A-unique-owner-password-2026",
            },
            "enrollment_code": "",
        }

    def test_first_node_persists_config_without_credentials(self) -> None:
        result = validate_and_save(self.payload(), self.container)
        self.assertTrue(result["enrollment_code"])
        config = json.loads((self.root / ".rtfm/config.json").read_text(encoding="utf-8"))
        self.assertEqual(set(config["environment"]), CONFIG_KEYS)
        raw = json.dumps(config)
        self.assertNotIn("A-unique-owner-password", raw)
        self.assertNotIn("session-", raw)
        self.assertEqual((self.root / ".rtfm/config.json").stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.container.store.has_users())
        owner = self.container.store.find_user_by_username("owner")
        self.assertFalse(owner["password_change_required"])

    def test_join_node_reuses_shared_secrets_without_creating_owner(self) -> None:
        first = validate_and_save(self.payload(), self.container)
        first_session = (self.root / ".rtfm/secrets/session-secret").read_text()
        first_replication = (self.root / ".rtfm/secrets/replication-token").read_text()
        first_environment = json.loads(
            (self.root / ".rtfm/config.json").read_text(encoding="utf-8")
        )["environment"]

        second_root = Path(tempfile.mkdtemp(prefix="rtfm-setup-join-"))
        self.addCleanup(shutil.rmtree, second_root, True)
        secret_dir = second_root / ".rtfm/secrets"
        secret_dir.mkdir(parents=True)
        (secret_dir / "session-secret").write_text("temporary-" + "c" * 48, encoding="utf-8")
        (secret_dir / "replication-token").write_text("temporary-" + "d" * 48, encoding="utf-8")
        for path in secret_dir.iterdir(): path.chmod(0o600)
        with patch.dict(os.environ, {
            "DATA_DIR": str(second_root), "ROLE_MODE": "passive", "RTFM_SETUP_REQUIRED": "1",
            "SESSION_SECRET_FILE": str(secret_dir / "session-secret"),
            "REPLICATION_TOKEN_FILE": str(secret_dir / "replication-token"),
            "GIT_ENABLED": "false",
        }, clear=True):
            joined_container = build_services(Settings.from_env())
        payload = self.payload()
        payload.update({"node": "node-b", "role_mode": "passive", "owner": None,
                        "enrollment_code": first["enrollment_code"]})
        payload["replication"]["peers"] = [{"name": "node-a", "url": "https://node-a.example:7400"}]
        result = validate_and_save(payload, joined_container)
        self.assertEqual(result["enrollment_code"], "")
        self.assertFalse(joined_container.store.has_users())
        self.assertEqual((secret_dir / "session-secret").read_text(), first_session)
        self.assertEqual((secret_dir / "replication-token").read_text(), first_replication)
        joined_environment = json.loads(
            (second_root / ".rtfm/config.json").read_text(encoding="utf-8")
        )["environment"]
        self.assertEqual(joined_environment["KEEPALIVED_SERVICE"], first_environment["KEEPALIVED_SERVICE"])
        self.assertEqual(joined_environment["KEEPALIVED_CLAIM_ID"], first_environment["KEEPALIVED_CLAIM_ID"])

    def test_active_cluster_is_rejected(self) -> None:
        payload = self.payload()
        payload["replication"]["peers"] = [{"name": "node-b", "url": "https://node-b.example:7400"}]
        with self.assertRaisesRegex(SetupError, "varios nodos como activos"):
            validate_and_save(payload, self.container)

    def test_authenticated_configuration_round_trip_keeps_hidden_token(self) -> None:
        payload = self.payload()
        token = "fip_" + "k" * 40
        payload["keepalived"].update({
            "url": "http://127.0.0.1:6060",
            "api_key": token,
        })
        validate_and_save(payload, self.container)

        current = configuration_payload(self.container)
        self.assertEqual(current["values"]["keepalived"]["api_key"], "")
        self.assertTrue(current["secrets"]["keepalived_api_key_configured"])
        self.assertNotIn(token, json.dumps(current))

        values = current["values"]
        values["policy"]["retention_days"] = 180
        result = update_configuration(values, self.container)
        self.assertTrue(result["ok"])
        environment = json.loads(
            (self.root / ".rtfm/config.json").read_text(encoding="utf-8")
        )["environment"]
        self.assertEqual(environment["RETENTION_DAYS"], "180")
        self.assertEqual(
            (self.root / ".rtfm/secrets/keepalived-api-key").read_text().strip(), token,
        )

    def test_configuration_can_disable_keepalived_and_remove_its_token(self) -> None:
        payload = self.payload()
        payload["keepalived"].update({
            "url": "http://127.0.0.1:6060",
            "api_key": "fip_" + "k" * 40,
        })
        validate_and_save(payload, self.container)
        values = configuration_payload(self.container)["values"]
        values["keepalived"]["url"] = ""
        values["keepalived"]["api_key"] = ""
        update_configuration(values, self.container)
        self.assertFalse((self.root / ".rtfm/secrets/keepalived-api-key").exists())
        environment = json.loads(
            (self.root / ".rtfm/config.json").read_text(encoding="utf-8")
        )["environment"]
        self.assertEqual(environment["KEEPALIVED_API_URL"], "")

    def test_launcher_generates_private_runtime_secrets(self) -> None:
        fresh = Path(tempfile.mkdtemp(prefix="rtfm-launcher-"))
        self.addCleanup(shutil.rmtree, fresh, True)
        with patch.dict(os.environ, {"DATA_DIR": str(fresh), "PORT": "7400"}, clear=True):
            prepare_environment({"DATA_DIR", "PORT"})
            self.assertEqual(os.environ["RTFM_SETUP_REQUIRED"], "1")
            for name in ("session-secret", "replication-token"):
                path = fresh / ".rtfm/secrets" / name
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertGreaterEqual(len(path.read_text().strip()), 32)


if __name__ == "__main__":
    unittest.main()
