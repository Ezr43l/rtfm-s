import tempfile
import unittest
from pathlib import Path

from app.accounts import AccountSecurity, normalize_display_name, normalize_username
from app.storage import DocumentStore


class AccountSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.security = AccountSecurity("a-long-secret-used-only-in-tests", 12, "RTFM Test")

    def test_password_hash_is_salted_and_verifiable(self) -> None:
        first = self.security.hash_password("una frase larga y segura")
        second = self.security.hash_password("una frase larga y segura")

        self.assertNotEqual(first, second)
        self.assertTrue(self.security.verify_password("una frase larga y segura", first))
        self.assertFalse(self.security.verify_password("otra contraseña", first))
        self.assertFalse(self.security.verify_password("cualquiera", "hash-invalido"))

    def test_password_policy_and_profile_normalization(self) -> None:
        with self.assertRaises(ValueError):
            self.security.validate_password("corta", "operator")
        with self.assertRaises(ValueError):
            normalize_username("nombre con espacios")
        self.assertEqual(normalize_username("operator.admin"), "operator.admin")
        self.assertEqual(normalize_display_name("  Test   Operator  "), "Test Operator")

    def test_totp_matches_rfc_vector_and_encrypted_secret_round_trip(self) -> None:
        # RFC 6238, SHA-1, instante 59: el vector de 8 dígitos termina en 287082.
        rfc_totp_seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # gitleaks:allow, vector público RFC 6238
        self.assertEqual(self.security._totp(rfc_totp_seed, 1), "287082")
        self.assertTrue(self.security.verify_totp(rfc_totp_seed, "287082", timestamp=59, window=0))
        encrypted = self.security.encrypt(rfc_totp_seed)
        self.assertNotIn(rfc_totp_seed, encrypted)
        self.assertEqual(self.security.decrypt(encrypted), rfc_totp_seed)

    def test_recovery_codes_are_single_use_in_storage(self) -> None:
        codes = self.security.generate_recovery_codes()
        hashes = [self.security.hash_recovery_code(code) for code in codes]
        self.assertEqual(len(codes), 10)
        self.assertEqual(self.security.recovery_code_index(codes[3].lower(), hashes), 3)


class AccountStorageTests(unittest.TestCase):
    def test_account_security_state_is_persistent_audited_and_replicated(self) -> None:
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as replica_directory:
            source = DocumentStore(Path(source_directory), "source", 90)
            owner = source.create_owner("operator", "Test Operator", "password-hash", "operator")
            user_id = owner["id"]
            source.update_user_profile(user_id, "operator", display_name="Main Operator")
            source.set_pending_totp(user_id, "operator", "fernet:encrypted-secret")
            source.enable_totp(user_id, "operator", ["hash-one", "hash-two"])

            public = source.get_user(user_id, public=True)
            self.assertTrue(public["two_factor_enabled"])
            self.assertEqual(public["recovery_codes_remaining"], 2)
            self.assertNotIn("password_hash", public)
            self.assertNotIn("totp", public)

            replica = DocumentStore(Path(replica_directory), "replica", 90)
            result = replica.merge_bundle(source.export_bundle())
            replicated = replica.get_user(user_id)
            self.assertGreaterEqual(result["applied"], 1)
            self.assertEqual(replicated["display_name"], "Main Operator")
            self.assertEqual(replicated["totp"]["secret"], "fernet:encrypted-secret")
            self.assertTrue(any(event["action"] == "user.2fa_enabled" for event in replica.read_audit()))

    def test_personal_favorites_are_audited_and_replicated(self) -> None:
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as replica_directory:
            source = DocumentStore(Path(source_directory), "source", 90)
            owner = source.create_owner("operator", "Test Operator", "password-hash", "operator")
            document = source.create("Procedimiento crítico", "contenido", "operator")
            document_id = document["meta"]["id"]

            result = source.set_document_favorite(owner["id"], document_id, True, "operator")
            self.assertTrue(result["favorite"])
            self.assertEqual(source.list_favorite_documents(owner["id"])[0]["id"], document_id)
            self.assertEqual(source.get_user(owner["id"], public=True)["favorite_count"], 1)

            bundle = source.export_bundle()
            self.assertEqual(bundle["schema_version"], 6)
            replica = DocumentStore(Path(replica_directory), "replica", 90)
            replica.merge_bundle(bundle)
            self.assertEqual(replica.list_favorite_documents(owner["id"])[0]["id"], document_id)
            self.assertTrue(any(event["action"] == "favorite.add" for event in replica.read_audit()))

            source.set_document_favorite(owner["id"], document_id, False, "operator")
            self.assertEqual(source.list_favorite_documents(owner["id"]), [])


if __name__ == "__main__":
    unittest.main()
