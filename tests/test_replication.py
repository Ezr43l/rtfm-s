import os
import unittest
from unittest.mock import patch

from app.replication import ReplicationError, validate_incoming_bundle
from app.settings import Settings


def bundle(node: str = "node-b") -> dict:
    return {
        "schema_version": 6,
        "node": node,
        "clock": 1,
        "libraries": [],
        "categories": [],
        "users": [],
        "api_clients": [],
        "documents": [],
        "vault": [],
        "audit": [],
    }


class ReplicationContractTests(unittest.TestCase):
    def settings(self) -> Settings:
        with patch.dict(
            os.environ,
            {
                "NODE_NAME": "node-a",
                "PEERS": "node-b=https://node-b.example:7400",
            },
            clear=True,
        ):
            return Settings.from_env()

    def test_declared_peer_and_schema_are_accepted(self) -> None:
        self.assertEqual(validate_incoming_bundle(bundle(), self.settings())["node"], "node-b")

    def test_unknown_source_is_rejected(self) -> None:
        with self.assertRaises(ReplicationError):
            validate_incoming_bundle(bundle("node-c"), self.settings())

    def test_incomplete_or_old_schema_is_rejected(self) -> None:
        invalid = bundle()
        invalid["schema_version"] = 5
        with self.assertRaises(ReplicationError):
            validate_incoming_bundle(invalid, self.settings())


if __name__ == "__main__":
    unittest.main()
