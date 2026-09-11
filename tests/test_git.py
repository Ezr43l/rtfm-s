import base64
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.git_repo import GitRepository
from app.storage import DocumentStore


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@unittest.skipUnless(shutil.which("git"), "git no está instalado")
class GitRepositoryTests(unittest.TestCase):
    def test_document_operations_create_auditable_commits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "git"
            git_repo = GitRepository(repository, "Base Documental", "base-documental@localhost")
            store = DocumentStore(root / "data", "test-node", 90, git_repo)

            created = store.create("Arquitectura", "# v1", "operator")
            document_id = created["meta"]["id"]
            store.update(document_id, "operator", content="# v2")
            store.archive(document_id, "operator")

            content_path = repository / "documents" / document_id / "content.md"
            self.assertEqual(content_path.read_text(encoding="utf-8"), "# v2")
            log = subprocess.check_output(["git", "-C", str(repository), "log", "--format=%B"], text=True)
            self.assertIn("docs: archive", log)
            self.assertIn("Actor: operator", log)
            self.assertIn("Operation-ID:", log)
            author_emails = subprocess.check_output(
                ["git", "-C", str(repository), "log", "--format=%ae"], text=True
            ).splitlines()
            self.assertIn("operator@rtfm.invalid", author_emails)

    def test_delete_keeps_git_history_and_removes_current_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "git"
            git_repo = GitRepository(repository, "Base Documental", "base-documental@localhost")
            store = DocumentStore(root / "data", "test-node", 90, git_repo)
            created = store.create("Borrador", "contenido", "operator")
            document_id = created["meta"]["id"]
            store.delete(document_id, "operator")

            current_content = repository / "documents" / document_id / "content.md"
            self.assertFalse(current_content.exists())
            historical = subprocess.check_output(
                ["git", "-C", str(repository), "show", f"HEAD~1:documents/{document_id}/content.md"],
                text=True,
            )
            self.assertEqual(historical, "contenido")

    def test_uploaded_images_are_projected_and_removed_with_a_deleted_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "git"
            store = DocumentStore(
                root / "data",
                "test-node",
                90,
                GitRepository(repository, "Base Documental", "base-documental@localhost"),
            )
            created = store.create("Topología", "![Red](pendiente)", "operator")
            document_id = created["meta"]["id"]
            image = store.add_image(document_id, "red.png", "image/png", TINY_PNG, "operator")
            projected = repository / "documents" / document_id / "images"

            self.assertEqual((projected / f"{image['id']}.png").read_bytes(), TINY_PNG)
            self.assertTrue((projected / f"{image['id']}.json").exists())
            store.delete(document_id, "operator")
            self.assertFalse(projected.exists())
            log = subprocess.check_output(["git", "-C", str(repository), "log", "--format=%s"], text=True)
            self.assertIn("docs: document.image.upload", log)

    def test_catalog_move_and_unarchive_are_projected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "git"
            git_repo = GitRepository(repository, "Base Documental", "base-documental@localhost")
            store = DocumentStore(root / "data", "test-node", 90, git_repo)
            library = store.create_library("Infraestructura", "operator")
            category = store.create_category(library["id"], "Servidores", "operator")
            document = store.create("Nodo de ejemplo", "contenido", "operator", library_id=library["id"])
            document_id = document["meta"]["id"]
            store.move_document(document_id, "operator", library["id"], category["id"])
            store.archive(document_id, "operator")
            store.unarchive(document_id, "operator")

            library_projection = repository / "catalog" / "libraries" / f"{library['id']}.json"
            category_projection = repository / "catalog" / "categories" / f"{category['id']}.json"
            metadata = json.loads((repository / "documents" / document_id / "metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(library_projection.exists())
            self.assertTrue(category_projection.exists())
            self.assertEqual(metadata["category_id"], category["id"])
            self.assertEqual(metadata["status"], "active")
            log = subprocess.check_output(["git", "-C", str(repository), "log", "--format=%s"], text=True)
            self.assertIn("catalog: library.create", log)
            self.assertIn("docs: document.move", log)
            self.assertIn("docs: unarchive", log)

    def test_category_reorder_is_projected_in_one_catalog_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "git"
            store = DocumentStore(
                root / "data",
                "test-node",
                90,
                GitRepository(repository, "Base Documental", "base-documental@localhost"),
            )
            library = store.create_library("Operaciones", "operator")
            first = store.create_category(library["id"], "Primera", "operator")
            second = store.create_category(library["id"], "Segunda", "operator")

            store.reorder_categories(library["id"], None, [second["id"], first["id"]], "operator")

            first_projection = json.loads(
                (repository / "catalog" / "categories" / f"{first['id']}.json").read_text(encoding="utf-8")
            )
            second_projection = json.loads(
                (repository / "catalog" / "categories" / f"{second['id']}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(second_projection["position"], 0)
            self.assertEqual(first_projection["position"], 1)
            subjects = subprocess.check_output(["git", "-C", str(repository), "log", "--format=%s"], text=True)
            self.assertIn("catalog: category.reorder", subjects)


if __name__ == "__main__":
    unittest.main()
