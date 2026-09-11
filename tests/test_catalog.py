import tempfile
import unittest
from pathlib import Path

from app.storage import DocumentStore


class CatalogStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = DocumentStore(Path(self.directory.name), "node-test", 90)
        self.library = self.store.create_library("Infraestructura", "operator", "Servidores y red")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_recursive_categories_and_documents_at_any_level(self) -> None:
        servers = self.store.create_category(self.library["id"], "Servidores", "operator")
        unraid = self.store.create_category(self.library["id"], "Unraid", "operator", servers["id"])
        root_document = self.store.create("Mapa de red", "# Red", "operator", library_id=self.library["id"])
        nested_document = self.store.create(
            "Nodo de ejemplo",
            "# Nodo de ejemplo",
            "operator",
            library_id=self.library["id"],
            category_id=unraid["id"],
        )

        tree = self.store.library_tree(self.library["id"])
        self.assertEqual(tree["documents"][0]["id"], root_document["meta"]["id"])
        nested = tree["categories"][0]["children"][0]
        self.assertEqual(nested["id"], unraid["id"])
        self.assertEqual(nested["documents"][0]["id"], nested_document["meta"]["id"])

    def test_category_cycle_is_rejected(self) -> None:
        parent = self.store.create_category(self.library["id"], "Padre", "operator")
        child = self.store.create_category(self.library["id"], "Hija", "operator", parent["id"])
        with self.assertRaisesRegex(ValueError, "ciclo"):
            self.store.update_category(parent["id"], "operator", parent_id=child["id"], parent_supplied=True)

    def test_library_and_category_text_can_be_edited_after_creation(self) -> None:
        library = self.store.create_library("Proyectos", "operator")
        category = self.store.create_category(library["id"], "Docker", "operator")

        updated_library = self.store.update_library(
            library["id"], "operator", name="Proyectos", description="Aplicaciones y servicios internos"
        )
        updated_category = self.store.update_category(
            category["id"], "operator", name="Contenedores", description="Despliegues y mantenimiento"
        )

        self.assertEqual(updated_library["name"], "Proyectos")
        self.assertEqual(updated_library["description"], "Aplicaciones y servicios internos")
        self.assertEqual(updated_category["name"], "Contenedores")
        self.assertEqual(updated_category["description"], "Despliegues y mantenimiento")
        actions = [event["action"] for event in self.store.read_audit(limit=20)]
        self.assertIn("library.update", actions)
        self.assertIn("category.update", actions)

    def test_categories_support_alphabetical_and_manual_order(self) -> None:
        zulu = self.store.create_category(self.library["id"], "Zulu", "operator")
        tree_category = self.store.create_category(self.library["id"], "Árbol", "operator")
        docker = self.store.create_category(self.library["id"], "Docker", "operator")
        nested_tree = self.store.create_category(self.library["id"], "Ábaco", "operator", docker["id"])
        nested_zulu = self.store.create_category(self.library["id"], "Zeta", "operator", docker["id"])

        self.store.update_library(self.library["id"], "operator", category_sort="alphabetical")
        alphabetical = self.store.library_tree(self.library["id"])
        self.assertEqual([item["name"] for item in alphabetical["categories"]], ["Árbol", "Docker", "Zulu"])
        self.assertEqual(
            [item["name"] for item in alphabetical["categories"][1]["children"]],
            ["Ábaco", "Zeta"],
        )

        self.store.update_library(self.library["id"], "operator", category_sort="manual")
        self.store.reorder_categories(
            self.library["id"], None, [docker["id"], zulu["id"], tree_category["id"]], "operator"
        )
        self.store.reorder_categories(
            self.library["id"], docker["id"], [nested_zulu["id"], nested_tree["id"]], "operator"
        )
        manual = self.store.library_tree(self.library["id"])
        self.assertEqual([item["name"] for item in manual["categories"]], ["Docker", "Zulu", "Árbol"])
        self.assertEqual([item["name"] for item in manual["categories"][0]["children"]], ["Zeta", "Ábaco"])
        self.assertTrue(any(event["action"] == "category.reorder" for event in self.store.read_audit()))

        with self.assertRaisesRegex(ValueError, "todas las categorías"):
            self.store.reorder_categories(self.library["id"], None, [docker["id"]], "operator")

    def test_non_empty_category_cannot_be_deleted(self) -> None:
        category = self.store.create_category(self.library["id"], "Docker", "operator")
        self.store.create("Contenedores", "contenido", "operator", library_id=self.library["id"], category_id=category["id"])
        with self.assertRaisesRegex(ValueError, "no está vacía"):
            self.store.delete_category(category["id"], "operator")

    def test_catalog_is_part_of_replication_bundle(self) -> None:
        category = self.store.create_category(self.library["id"], "Red", "operator")
        bundle = self.store.export_bundle()
        with tempfile.TemporaryDirectory() as destination:
            replica = DocumentStore(Path(destination), "replica", 90)
            result = replica.merge_bundle(bundle)
            self.assertGreaterEqual(result["applied"], 2)
            self.assertEqual(replica.get_library(self.library["id"])["name"], "Infraestructura")
            self.assertEqual(replica.get_category(category["id"])["name"], "Red")


if __name__ == "__main__":
    unittest.main()
