from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "scripts" / "export-public-release.py"
MANIFEST = "PUBLIC_EXPORT_SHA256SUMS"

SPEC = importlib.util.spec_from_file_location("rtfm_public_export", EXPORTER)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import failure is fatal to tests
    raise RuntimeError("No se pudo cargar el exportador publico")
EXPORT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT_MODULE)


class PublicExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "private-source"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Public Export Test")
        self.git("config", "user.email", "public-export@example.test")
        self.git("config", "core.autocrlf", "false")
        # El modo de trabajo puede ser NTFS; los modos públicos proceden del índice.
        self.git("config", "core.filemode", "false")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *arguments: str, input_data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", "-C", os.fspath(self.repo), *arguments],
            input=input_data,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def commit_files(self, files: dict[str, bytes | str]) -> None:
        for relative_path, content in files.items():
            path = self.repo / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8") if isinstance(content, str) else content
            path.write_bytes(data)
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "fixture")

    def export(self, name: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                os.fspath(EXPORTER),
                "--source",
                os.fspath(self.repo),
                os.fspath(self.root / name),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @staticmethod
    def snapshot(tree: Path) -> list[tuple[str, bytes, int, int]]:
        result: list[tuple[str, bytes, int, int]] = []
        for path in sorted((item for item in tree.rglob("*") if item.is_file())):
            metadata = path.stat()
            result.append(
                (
                    path.relative_to(tree).as_posix(),
                    path.read_bytes(),
                    stat.S_IMODE(metadata.st_mode),
                    int(metadata.st_mtime),
                )
            )
        return result

    def test_exports_only_tracked_blobs_with_reproducible_manifest_and_metadata(self) -> None:
        self.commit_files(
            {
                ".gitignore": ".codex-artifacts/\ntests;C/\n",
                "README.md": "public source\n",
                "bin/check.sh": "#!/bin/sh\nexit 0\n",
            }
        )
        self.git("update-index", "--chmod=+x", "bin/check.sh")
        self.git("commit", "--quiet", "-m", "mark executable")

        for path, content in {
            ".codex-artifacts/evidence.txt": "private evidence",
            "tests;C/diagnostic.txt": "private diagnostic",
            "untracked.txt": "not part of Git",
        }.items():
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        first = self.export("export-one")
        second = self.export("export-two")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_tree = self.root / "export-one"
        second_tree = self.root / "export-two"
        self.assertEqual(self.snapshot(first_tree), self.snapshot(second_tree))
        self.assertFalse((first_tree / ".git").exists())
        self.assertFalse((first_tree / ".codex-artifacts").exists())
        self.assertFalse((first_tree / "tests;C").exists())
        self.assertFalse((first_tree / "untracked.txt").exists())
        self.assertEqual(int((first_tree / "README.md").stat().st_mtime), 315532800)
        self.assertTrue((first_tree / "bin/check.sh").stat().st_mode & stat.S_IXUSR)

        manifest_lines = [
            line
            for line in (first_tree / MANIFEST).read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        ]
        paths = []
        for line in manifest_lines:
            digest, relative_path = line.split("  ", 1)
            paths.append(relative_path)
            self.assertEqual(digest, hashlib.sha256((first_tree / relative_path).read_bytes()).hexdigest())
        self.assertEqual(paths, sorted(paths, key=lambda value: value.encode("utf-8")))
        self.assertNotIn(MANIFEST, paths)

        # El manifiesto generado puede formar parte del commit raíz del repositorio
        # público; al reexportar se ignora como entrada y se regenera como salida.
        subprocess.run(["git", "-C", os.fspath(first_tree), "init", "--quiet"], check=True)
        subprocess.run(
            ["git", "-C", os.fspath(first_tree), "config", "user.name", "Public Re-export Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", os.fspath(first_tree), "config", "user.email", "reexport@example.test"],
            check=True,
        )
        subprocess.run(["git", "-C", os.fspath(first_tree), "add", "--all"], check=True)
        subprocess.run(
            ["git", "-C", os.fspath(first_tree), "commit", "--quiet", "-m", "public root"],
            check=True,
        )
        reexport = subprocess.run(
            [
                sys.executable,
                os.fspath(EXPORTER),
                "--source",
                os.fspath(first_tree),
                os.fspath(self.root / "export-from-public"),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(reexport.returncode, 0, reexport.stderr)
        self.assertTrue((self.root / "export-from-public" / MANIFEST).is_file())

    def test_rejects_denied_tracked_path_without_creating_destination(self) -> None:
        self.commit_files({"README.md": "safe\n", "secrets/runtime.txt": "redacted\n"})
        result = self.export("rejected-path")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ruta excluida", result.stderr)
        self.assertFalse((self.root / "rejected-path").exists())

    def test_rejects_secret_private_network_and_local_machine_material_without_echoing_it(self) -> None:
        sensitive_cases = {
            "credential": "AK" + "IA" + "A" * 16,
            "private-ip": ".".join(("192", "168", "44", "9")),
            "private-ipv6": "fd" + "42::1234",
            "local-path": "C:" + "\\" + "Users" + "\\" + "developer" + "\\" + "Documents" + "\\" + "project",
            "private-host": "builder" + "." + "corp" + "." + "internal",
        }
        expected_rules = {
            "credential": "aws-access-key",
            "private-ip": "non-public-ipv4",
            "private-ipv6": "non-public-ipv6",
            "local-path": "developer-local-path",
            "private-host": "private-hostname",
        }
        for case_name, value in sensitive_cases.items():
            with self.subTest(case=case_name):
                self.commit_files({"README.md": "safe\n", "candidate.txt": value + "\n"})
                result = self.export(f"rejected-{case_name}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_rules[case_name], result.stderr)
                self.assertNotIn(value, result.stderr)
                self.assertFalse((self.root / f"rejected-{case_name}").exists())

    def test_rejects_dirty_tracked_tree_and_existing_destination(self) -> None:
        self.commit_files({"README.md": "committed\n"})
        (self.repo / "README.md").write_text("modified\n", encoding="utf-8")
        dirty = self.export("dirty")
        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn("cambios sin preparar", dirty.stderr)
        self.git("restore", "README.md")

        destination = self.root / "already-there"
        destination.mkdir()
        existing = self.export(destination.name)
        self.assertNotEqual(existing.returncode, 0)
        self.assertIn("destino ya existe", existing.stderr)

    def test_immutable_head_snapshot_is_not_changed_by_a_later_index_update(self) -> None:
        self.commit_files({"README.md": "committed bytes\n"})
        tree_oid = EXPORT_MODULE.assert_repository_ready(self.repo)

        (self.repo / "README.md").write_text("staged after snapshot\n", encoding="utf-8")
        self.git("add", "README.md")
        files = EXPORT_MODULE.committed_files(self.repo, tree_oid)

        exported = {path: data for path, _mode, data in files}
        self.assertEqual(exported["README.md"], b"committed bytes\n")
        self.assertNotEqual(
            EXPORT_MODULE.run_git(self.repo, "diff", "--cached", "--quiet", check=False).returncode,
            0,
        )

    def test_atomic_publish_never_replaces_a_destination_that_appeared(self) -> None:
        staging = self.root / "staging"
        destination = self.root / "claimed"
        staging.mkdir()
        (staging / "README.md").write_text("new export\n", encoding="utf-8")
        destination.mkdir(mode=0o700)

        with self.assertRaises(EXPORT_MODULE.ExportError):
            EXPORT_MODULE.publish_no_replace(staging, destination)

        self.assertTrue(staging.is_dir())
        self.assertTrue(destination.is_dir())
        self.assertFalse((destination / "README.md").exists())

    def test_atomic_publish_fails_closed_on_unsupported_platform(self) -> None:
        staging = self.root / "unsupported-staging"
        destination = self.root / "unsupported-destination"
        staging.mkdir()
        with (
            mock.patch.object(EXPORT_MODULE.sys, "platform", "unsupported"),
            mock.patch.object(EXPORT_MODULE.os, "name", "posix"),
        ):
            with self.assertRaisesRegex(EXPORT_MODULE.ExportError, "no-clobber no soportada"):
                EXPORT_MODULE.publish_no_replace(staging, destination)


if __name__ == "__main__":
    unittest.main()
