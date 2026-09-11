import tempfile
import unittest
from pathlib import Path

from app.storage import DocumentStore


class AuditLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = DocumentStore(Path(self.directory.name), "test-node", 90)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_page_cursor_and_filter(self) -> None:
        for index in range(5):
            self.store.record_system_operation("sync", f"system:test-{index}", {"index": index})

        first = self.store.read_audit_page(limit=2)
        self.assertEqual(len(first["items"]), 2)
        self.assertTrue(first["has_more"])
        second = self.store.read_audit_page(limit=2, cursor=first["next_cursor"])
        self.assertEqual(len(second["items"]), 2)
        self.assertTrue({item["event_id"] for item in first["items"]}.isdisjoint(item["event_id"] for item in second["items"]))

        filtered = self.store.read_audit_page(actor="system:test-3")
        self.assertEqual(len(filtered["items"]), 1)
        self.assertEqual(filtered["items"][0]["actor"], "system:test-3")


if __name__ == "__main__":
    unittest.main()
