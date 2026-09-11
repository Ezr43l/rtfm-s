import unittest

from app.auth import LoginThrottle, SessionCodec


class SessionCodecTests(unittest.TestCase):
    def test_signed_session_round_trip_and_tamper_rejection(self) -> None:
        codec = SessionCodec("a-long-test-secret", 12)
        token, created = codec.create("operator", "user-1", 4, "Test Operator")
        parsed = codec.parse(token)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.actor, "operator")
        self.assertEqual(parsed.user_id, "user-1")
        self.assertEqual(parsed.session_version, 4)
        self.assertEqual(parsed.display_name, "Test Operator")
        self.assertEqual(parsed.csrf_token, created.csrf_token)
        self.assertIsNone(codec.parse(token + "tampered"))

    def test_credential_comparison_requires_configured_secret(self) -> None:
        self.assertTrue(SessionCodec.credential_matches("correcta", "correcta"))
        self.assertFalse(SessionCodec.credential_matches("incorrecta", "correcta"))
        self.assertFalse(SessionCodec.credential_matches("", ""))

    def test_login_throttle_blocks_and_can_be_cleared(self) -> None:
        throttle = LoginThrottle(3, 300)
        key = throttle.key("192.0.2.10", "operator")
        for _ in range(3):
            throttle.record_failure(key)
        self.assertGreater(throttle.retry_after(key), 0)
        throttle.clear(key)
        self.assertEqual(throttle.retry_after(key), 0)


if __name__ == "__main__":
    unittest.main()
