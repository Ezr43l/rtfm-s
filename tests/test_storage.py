import base64
import tempfile
import unittest
from pathlib import Path

from app.storage import DocumentStore


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class DocumentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = DocumentStore(Path(self.directory.name), "test-node", 90)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_delete_keeps_tombstone_and_restore_uses_vault(self) -> None:
        created = self.store.create("Arquitectura", "# Hola", "operator")
        document_id = created["meta"]["id"]
        deleted = self.store.delete(document_id, "operator")
        self.assertEqual(deleted["meta"]["status"], "deleted")
        self.assertIsNone(self.store.get_document(document_id, include_deleted=False))
        restored = self.store.restore(document_id, "operator")
        self.assertEqual(restored["content"], "# Hola")
        self.assertEqual(restored["meta"]["status"], "active")

    def test_bundle_merge_is_last_version_wins(self) -> None:
        source = self.store.create("Origen", "v1", "operator")
        source_id = source["meta"]["id"]
        bundle = self.store.export_bundle()
        replica_dir = tempfile.TemporaryDirectory()
        try:
            replica = DocumentStore(Path(replica_dir.name), "replica", 90)
            result = replica.merge_bundle(bundle)
            self.assertEqual(result["applied"], 1)
            self.assertEqual(replica.get_document(source_id)["content"], "v1")
        finally:
            replica_dir.cleanup()

    def test_private_images_are_versioned_and_replicated_with_the_document(self) -> None:
        created = self.store.create("Esquema", "# Red", "operator")
        document_id = created["meta"]["id"]
        image = self.store.add_image(document_id, "topologia.png", "image/png", TINY_PNG, "operator")

        document = self.store.get_document(document_id)
        self.assertEqual(document["images"][0]["id"], image["id"])
        self.assertNotIn("data", document["images"][0])
        image_path, served = self.store.get_image_file(document_id, image["id"])
        self.assertEqual(image_path.read_bytes(), TINY_PNG)
        self.assertEqual(served["media_type"], "image/png")

        replica_dir = tempfile.TemporaryDirectory()
        try:
            replica = DocumentStore(Path(replica_dir.name), "replica", 90)
            replica.merge_bundle(self.store.export_bundle())
            replicated_path, _ = replica.get_image_file(document_id, image["id"])
            self.assertEqual(replicated_path.read_bytes(), TINY_PNG)
            self.assertEqual(replica.get_document(document_id)["images"][0]["filename"], "topologia.png")
        finally:
            replica_dir.cleanup()

    def test_document_delete_and_restore_moves_its_images_through_the_vault(self) -> None:
        created = self.store.create("Procedimiento", "contenido", "operator")
        document_id = created["meta"]["id"]
        image = self.store.add_image(document_id, "captura.png", "image/png", TINY_PNG, "operator")

        self.store.delete(document_id, "operator")
        with self.assertRaises(KeyError):
            self.store.get_image_file(document_id, image["id"])
        restored = self.store.restore(document_id, "operator")

        self.assertEqual(restored["images"][0]["id"], image["id"])
        restored_path, _ = self.store.get_image_file(document_id, image["id"])
        self.assertEqual(restored_path.read_bytes(), TINY_PNG)

    def test_restore_chooses_latest_numeric_vault_revision(self) -> None:
        created = self.store.create("Revisiones", "primera", "operator")
        document_id = created["meta"]["id"]
        self.store.delete(document_id, "operator")
        self.store.restore(document_id, "operator")
        for index in range(10):
            self.store.update(document_id, "operator", content=f"revision-{index}")
        self.store.delete(document_id, "operator")
        restored = self.store.restore(document_id, "operator")
        self.assertEqual(restored["content"], "revision-9")


if __name__ == "__main__":
    unittest.main()
