import tempfile
import unittest
import uuid
from pathlib import Path

from app.accounts import AccountSecurity
from app.permissions import (
    LIBRARY_ACCESS_OPEN,
    LIBRARY_ACCESS_RESTRICTED,
    ROLE_FULL_CONTROL,
    ROLE_OPERATOR,
    ROLE_READER,
    effective_library_role,
    normalize_library_access,
    normalize_access_role,
    role_allows,
)
from app.storage import DocumentStore


class PermissionModelTests(unittest.TestCase):
    def test_role_hierarchy_and_historical_owner_mapping(self) -> None:
        self.assertEqual(normalize_access_role("owner"), ROLE_FULL_CONTROL)
        self.assertTrue(role_allows(ROLE_FULL_CONTROL, ROLE_OPERATOR))
        self.assertTrue(role_allows(ROLE_OPERATOR, ROLE_READER))
        self.assertFalse(role_allows(ROLE_READER, ROLE_OPERATOR))

    def test_last_active_full_control_person_is_protected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DocumentStore(Path(directory), "node", 90)
            owner = store.create_owner("owner", "Owner", "hash", "owner")
            operator = store.create_user("operator", "Operator", "hash", ROLE_OPERATOR, "owner")

            with self.assertRaises(ValueError):
                store.update_user_access(owner["id"], "owner", role=ROLE_READER)
            with self.assertRaises(ValueError):
                store.update_user_access(owner["id"], "owner", status="disabled")

            store.update_user_access(operator["id"], "owner", role=ROLE_FULL_CONTROL)
            changed = store.update_user_access(owner["id"], "owner", role=ROLE_READER)
            self.assertEqual(changed["role"], ROLE_READER)
            with self.assertRaises(ValueError):
                store.update_user_access(operator["id"], "operator", status="disabled")

    def test_library_policy_is_compatible_and_fails_closed_when_malformed(self) -> None:
        legacy = {"id": "legacy"}
        self.assertEqual(normalize_library_access(legacy.get("access"))["mode"], LIBRARY_ACCESS_OPEN)
        self.assertEqual(
            effective_library_role(ROLE_OPERATOR, "person", "person-1", None, legacy),
            ROLE_OPERATOR,
        )

        malformed = {"id": "bad", "access": {"mode": "unexpected", "grants": []}}
        self.assertEqual(normalize_library_access(malformed["access"])["mode"], LIBRARY_ACCESS_RESTRICTED)
        self.assertIsNone(effective_library_role(ROLE_OPERATOR, "person", "person-1", None, malformed))

    def test_restricted_library_uses_global_role_as_ceiling_and_human_admin_as_recovery(self) -> None:
        library = {
            "access": {
                "mode": LIBRARY_ACCESS_RESTRICTED,
                "grants": [
                    {"subject_type": "user", "subject_id": "reader-1", "role": ROLE_FULL_CONTROL},
                    {"subject_type": "api_client", "subject_id": "api-1", "role": ROLE_OPERATOR},
                ],
            }
        }
        self.assertEqual(
            effective_library_role(ROLE_READER, "person", "reader-1", None, library),
            ROLE_READER,
        )
        self.assertEqual(
            effective_library_role(ROLE_FULL_CONTROL, "api", None, "api-1", library),
            ROLE_OPERATOR,
        )
        self.assertIsNone(effective_library_role(ROLE_FULL_CONTROL, "api", None, None, library))
        self.assertEqual(
            effective_library_role(ROLE_FULL_CONTROL, "person", "admin-1", None, library),
            ROLE_FULL_CONTROL,
        )

    def test_library_permissions_are_validated_audited_and_replicated_in_schema_six(self) -> None:
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as replica_directory:
            source = DocumentStore(Path(source_directory), "source", 90)
            reader = source.create_user("reader", "Reader", "hash", ROLE_READER, "owner")
            library = source.create_library("Restricted", "owner")
            self.assertEqual(source.get_library_permissions(library["id"])["mode"], LIBRARY_ACCESS_OPEN)

            policy = source.update_library_permissions(
                library["id"],
                "owner",
                LIBRARY_ACCESS_RESTRICTED,
                [{"subject_type": "user", "subject_id": reader["id"], "role": ROLE_READER}],
            )
            self.assertEqual(policy["mode"], LIBRARY_ACCESS_RESTRICTED)
            self.assertEqual(policy["grants"][0]["subject_id"], reader["id"])
            with self.assertRaises(ValueError):
                source.update_library_permissions(
                    library["id"],
                    "owner",
                    LIBRARY_ACCESS_RESTRICTED,
                    [{"subject_type": "user", "subject_id": "missing", "role": ROLE_READER}],
                )

            events = source.read_audit(200)
            self.assertTrue(any(event.get("action") == "library.permissions.update" for event in events))
            bundle = source.export_bundle()
            self.assertEqual(bundle["schema_version"], 6)
            replica = DocumentStore(Path(replica_directory), "replica", 90)
            replica.merge_bundle(bundle)
            self.assertEqual(replica.get_library_permissions(library["id"]), policy)


class ApiClientSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.security = AccountSecurity("a-long-secret-used-only-in-tests")

    def test_token_is_returned_once_hashed_rotatable_and_revocable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DocumentStore(Path(directory), "source", 90)
            client_id = str(uuid.uuid4())
            token, token_hash, prefix = self.security.generate_api_token(client_id)
            public = store.create_api_client(
                client_id, "Example integration", "Integration", ROLE_OPERATOR, token_hash, prefix, None, "owner"
            )

            self.assertTrue(token.startswith("rtfm_"))
            self.assertNotIn("token_hash", public)
            self.assertNotIn(token, (Path(directory) / "auth" / "api-clients" / f"{client_id}.json").read_text())
            self.assertEqual(store.find_api_client_by_token_hash(self.security.hash_api_token(token))["id"], client_id)

            replacement, replacement_hash, replacement_prefix = self.security.generate_api_token(client_id)
            store.rotate_api_client_token(client_id, "owner", replacement_hash, replacement_prefix)
            self.assertIsNone(store.find_api_client_by_token_hash(self.security.hash_api_token(token)))
            self.assertIsNotNone(store.find_api_client_by_token_hash(self.security.hash_api_token(replacement)))

            store.revoke_api_client(client_id, "owner")
            self.assertIsNone(store.find_api_client_by_token_hash(self.security.hash_api_token(replacement)))

    def test_api_clients_are_part_of_schema_six_replication(self) -> None:
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as replica_directory:
            source = DocumentStore(Path(source_directory), "source", 90)
            client_id = str(uuid.uuid4())
            _, token_hash, prefix = self.security.generate_api_token(client_id)
            source.create_api_client(client_id, "Collector", "Read only", ROLE_READER, token_hash, prefix, None, "owner")

            bundle = source.export_bundle()
            self.assertEqual(bundle["schema_version"], 6)
            self.assertEqual(len(bundle["api_clients"]), 1)

            replica = DocumentStore(Path(replica_directory), "replica", 90)
            result = replica.merge_bundle(bundle)
            self.assertGreaterEqual(result["applied"], 1)
            self.assertEqual(replica.get_api_client(client_id, public=True)["name"], "Collector")


if __name__ == "__main__":
    unittest.main()
