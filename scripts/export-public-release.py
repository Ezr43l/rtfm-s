#!/usr/bin/env python3
"""Export a deterministic, public-safe tree from an immutable Git commit.

The source is the tree object of ``HEAD`` captured after verifying a clean tracked tree.
Every path and byte is subsequently read from that immutable object, so a concurrent index
change cannot alter the export. Untracked/ignored files and repository history are never
copied. The exporter deliberately fails closed when its public policy detects a forbidden
path, credential-shaped material, private infrastructure or a dirty tracked tree.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import ipaddress
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata


MANIFEST_NAME = "PUBLIC_EXPORT_SHA256SUMS"
NORMALIZED_MTIME = 315532800  # 1980-01-01T00:00:00Z

DENIED_COMPONENTS = {
    ".codex-artifacts",
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "data",
    "dist",
    "local-data",
    "node_modules",
    "secrets",
    "tests;c",
}
DENIED_BASENAMES = {
    ".dockerconfigjson",
    ".ds_store",
    ".env",
    "authorized_keys",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "known_hosts",
}
DENIED_SUFFIXES = {
    ".bak",
    ".crt",
    ".db",
    ".der",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}
WINDOWS_RESERVED = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}

SECRET_PATTERNS = (
    ("private-key", re.compile(rb"-----BEGIN (?:DSA |EC |OPENSSH |PGP |RSA )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])")),
    ("github-token", re.compile(rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,}(?![A-Za-z0-9])")),
    ("github-pat", re.compile(rb"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,}(?![A-Za-z0-9_])")),
    ("gitlab-token", re.compile(rb"(?<![A-Za-z0-9_-])glpat-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")),
    ("google-api-key", re.compile(rb"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])")),
    ("slack-token", re.compile(rb"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,}(?![A-Za-z0-9-])")),
    ("stripe-live-key", re.compile(rb"(?<![A-Za-z0-9_])(?:rk|sk)_live_[A-Za-z0-9]{16,}(?![A-Za-z0-9])")),
    (
        "keepalived-api-key",
        re.compile(rb"(?<![A-Za-z0-9_-])fip_[0-9a-f]{32}_[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_-])"),
    ),
    (
        "rtfm-api-token",
        re.compile(rb"(?<![A-Za-z0-9_-])rtfm_[0-9a-f]{8}_[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_-])"),
    ),
    (
        "literal-bearer-token",
        re.compile(rb"(?i)\bauthorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    ),
)

IPV4_PATTERN = re.compile(rb"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
IPV6_PATTERN = re.compile(
    rb"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Fa-f:])"
)
# Integer network addresses keep the scanner's own source free of the values it rejects.
NON_PUBLIC_V4 = tuple(
    ipaddress.ip_network((address, prefix))
    for address, prefix in (
        (10 << 24, 8),
        ((100 << 24) | (64 << 16), 10),
        ((169 << 24) | (254 << 16), 16),
        ((172 << 24) | (16 << 16), 12),
        ((192 << 24) | (168 << 16), 16),
    )
)
NON_PUBLIC_V6 = tuple(
    ipaddress.ip_network((address, prefix))
    for address, prefix in ((0xFC00 << 112, 7), (0xFE80 << 112, 10))
)
LOCAL_PATH_PATTERNS = (
    re.compile(rb"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/](?:Documents and Settings|Users)[\\/]"),
    re.compile(rb"(?i)(?<![A-Za-z0-9])/mnt/[A-Z]/(?:Documents and Settings|Users)/"),
    re.compile(rb"(?<![A-Za-z0-9_])/(?:Users)/[^/\x00\r\n\t ]+/"),
    re.compile(
        rb"(?<![A-Za-z0-9_])/home/[^/\x00\r\n\t ]+/(?:Desktop|Documents|Downloads|Projects|repos?|workspace)/"
    ),
    re.compile(rb"(?i)\bfile:///(?:[A-Z]:/|Users/|home/|mnt/[A-Z]/Users/)"),
)
PRIVATE_HOST_PATTERN = re.compile(
    rb"(?i)(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9-]+\.)+(?:internal|lan|local|home\.arpa)(?![A-Za-z0-9_.-])"
)
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1\n"


class ExportError(RuntimeError):
    """A safe, user-facing export failure."""


def run_git(source: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", os.fspath(source), *arguments],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def assert_repository_ready(source: Path) -> str:
    try:
        root = Path(os.fsdecode(run_git(source, "rev-parse", "--show-toplevel").stdout.strip())).resolve()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExportError("el origen no es un repositorio Git accesible") from error
    if root != source:
        raise ExportError("--source debe apuntar exactamente a la raiz del repositorio")
    if run_git(source, "diff", "--quiet", check=False).returncode != 0:
        raise ExportError("hay cambios sin preparar en archivos versionados")
    if run_git(source, "diff", "--cached", "--quiet", check=False).returncode != 0:
        raise ExportError("el indice contiene cambios sin commit")
    try:
        commit = run_git(source, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
        tree = run_git(source, "rev-parse", "--verify", f"{commit.decode('ascii')}^{{tree}}").stdout.strip()
        tree_text = tree.decode("ascii")
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
        raise ExportError("HEAD no identifica un commit y arbol Git validos") from error
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tree_text):
        raise ExportError("HEAD no expone un OID de arbol Git valido")
    return tree_text


def validate_path(path: str) -> None:
    if not path or path == MANIFEST_NAME:
        raise ExportError(f"ruta reservada o vacia en el indice: {path!r}")
    if path != unicodedata.normalize("NFC", path):
        raise ExportError(f"ruta no normalizada en NFC: {path!r}")
    if any(ord(character) < 32 or character == "\\" for character in path):
        raise ExportError(f"ruta no portable en el indice: {path!r}")

    pure_path = PurePosixPath(path)
    if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise ExportError(f"ruta insegura en el indice: {path!r}")

    for component in pure_path.parts:
        lowered = component.casefold()
        stem = lowered.split(".", 1)[0]
        if lowered in DENIED_COMPONENTS or lowered in DENIED_BASENAMES:
            raise ExportError(f"ruta excluida por la politica publica: {path}")
        if stem in WINDOWS_RESERVED or component.endswith((" ", ".")):
            raise ExportError(f"ruta no portable en el indice: {path}")
        if any(character in component for character in '<>:"|?*'):
            raise ExportError(f"ruta no portable en el indice: {path}")
    if pure_path.name.casefold().startswith(".env.") and pure_path.name.casefold() != ".env.example":
        raise ExportError(f"variante de entorno excluida por la politica publica: {path}")
    if pure_path.suffix.casefold() in DENIED_SUFFIXES:
        raise ExportError(f"tipo de archivo excluido por la politica publica: {path}")


def content_violations(data: bytes) -> list[str]:
    violations: set[str] = set()
    if data.startswith(LFS_POINTER):
        violations.add("git-lfs-pointer")
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            violations.add(name)
    for match in IPV4_PATTERN.finditer(data):
        try:
            address = ipaddress.IPv4Address(match.group().decode("ascii"))
        except ipaddress.AddressValueError:
            continue
        if any(address in network for network in NON_PUBLIC_V4):
            violations.add("non-public-ipv4")
            break
    for match in IPV6_PATTERN.finditer(data):
        try:
            address = ipaddress.IPv6Address(match.group().decode("ascii"))
        except ipaddress.AddressValueError:
            continue
        if any(address in network for network in NON_PUBLIC_V6):
            violations.add("non-public-ipv6")
            break
    if any(pattern.search(data) for pattern in LOCAL_PATH_PATTERNS):
        violations.add("developer-local-path")
    if PRIVATE_HOST_PATTERN.search(data):
        violations.add("private-hostname")
    return sorted(violations)


def committed_files(source: Path, tree_oid: str) -> list[tuple[str, str, bytes]]:
    try:
        raw_entries = run_git(source, "ls-tree", "-r", "-z", "--full-tree", tree_oid).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExportError("no se pudo enumerar el snapshot inmutable de HEAD") from error

    files: list[tuple[str, str, bytes]] = []
    seen: set[str] = set()
    for raw_entry in raw_entries.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ")
            path = raw_path.decode("utf-8", "strict")
        except (UnicodeDecodeError, ValueError) as error:
            raise ExportError("entrada invalida o no UTF-8 en el arbol Git") from error
        if path in seen:
            raise ExportError(f"ruta duplicada en el arbol Git: {path}")
        seen.add(path)
        # A public export may itself have been committed as the clean root of the
        # shared repository. Its generated manifest is an output, never an input.
        if path == MANIFEST_NAME:
            continue
        if object_type != "blob" or mode not in {"100644", "100755"}:
            kind = "enlace simbolico" if mode == "120000" else f"modo {mode}"
            raise ExportError(f"{kind} no permitido en la exportacion publica: {path}")
        validate_path(path)
        try:
            data = run_git(source, "cat-file", "blob", object_id).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            raise ExportError(f"no se pudo leer el blob indexado: {path}") from error
        violations = content_violations(data)
        if violations:
            raise ExportError(f"contenido rechazado en {path}: {', '.join(violations)}")
        files.append((path, mode, data))
    if not files:
        raise ExportError("el indice no contiene archivos exportables")
    return sorted(files, key=lambda item: item[0].encode("utf-8"))


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def publish_no_replace(staging: Path, destination: Path) -> None:
    """Atomically publish *staging* without ever replacing *destination*.

    Linux uses ``renameat2(RENAME_NOREPLACE)`` against an already-open parent
    directory. Windows' ``os.rename`` has the required no-replace contract. Other
    platforms fail closed instead of emulating the operation with a racy pre-check.
    """

    if staging.parent != destination.parent:
        raise ExportError("staging y destino deben compartir el mismo directorio padre")
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            raise ExportError("renameat2(RENAME_NOREPLACE) no esta disponible en este Linux")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        parent_descriptor = os.open(staging.parent, directory_flags)
        try:
            result = renameat2(
                parent_descriptor,
                os.fsencode(staging.name),
                parent_descriptor,
                os.fsencode(destination.name),
                1,  # RENAME_NOREPLACE
            )
            if result != 0:
                error_number = ctypes.get_errno()
                if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise ExportError("el destino aparecio durante la exportacion; no se sobrescribe")
                if error_number in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
                    raise ExportError("el filesystem no admite publicacion atomica RENAME_NOREPLACE")
                raise OSError(error_number, os.strerror(error_number), os.fspath(destination))
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        return
    if os.name == "nt":
        try:
            os.rename(staging, destination)
        except FileExistsError as error:
            raise ExportError("el destino aparecio durante la exportacion; no se sobrescribe") from error
        return
    raise ExportError("publicacion atomica no-clobber no soportada; ejecuta el exportador en Linux")


def write_export(destination: Path, files: list[tuple[str, str, bytes]]) -> None:
    if destination.exists() or destination.is_symlink():
        raise ExportError("el destino ya existe; no se sobrescribe ni se mezcla una exportacion")
    parent = destination.parent.resolve()
    if not parent.is_dir():
        raise ExportError("el directorio padre del destino no existe")

    destination = parent / destination.name
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.public-export-", dir=parent))
    os.chmod(staging, 0o700)

    # Keep strictly to sha256sum's portable ``digest<two spaces>path`` format.
    manifest_lines: list[str] = []
    try:
        created_directories = {staging}
        for path, mode, data in files:
            target = staging.joinpath(*PurePosixPath(path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            current = target.parent
            while is_within(current, staging) and current not in created_directories:
                created_directories.add(current)
                if current == staging:
                    break
                current = current.parent
            with target.open("xb") as exported_file:
                exported_file.write(data)
            os.chmod(target, 0o755 if mode == "100755" else 0o644)
            os.utime(target, (NORMALIZED_MTIME, NORMALIZED_MTIME), follow_symlinks=False)
            manifest_lines.append(f"{hashlib.sha256(data).hexdigest()}  {path}")

        manifest = ("\n".join(manifest_lines) + "\n").encode("utf-8")
        manifest_path = staging / MANIFEST_NAME
        with manifest_path.open("xb") as exported_manifest:
            exported_manifest.write(manifest)
        os.chmod(manifest_path, 0o644)
        os.utime(manifest_path, (NORMALIZED_MTIME, NORMALIZED_MTIME), follow_symlinks=False)

        for directory in sorted(created_directories, key=lambda item: len(item.parts), reverse=True):
            os.chmod(directory, 0o755)
            os.utime(directory, (NORMALIZED_MTIME, NORMALIZED_MTIME), follow_symlinks=False)
        publish_no_replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta un arbol publico determinista desde blobs versionados en Git."
    )
    parser.add_argument("destination", type=Path, help="directorio nuevo que recibira el arbol")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.cwd(),
        help="raiz del repositorio (predeterminado: directorio actual)",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    source = options.source.resolve()
    destination = options.destination.absolute()
    try:
        tree_oid = assert_repository_ready(source)
        resolved_destination = destination.resolve(strict=False)
        if is_within(resolved_destination, source) or is_within(source, resolved_destination):
            raise ExportError("el destino debe quedar fuera del repositorio de origen")
        files = committed_files(source, tree_oid)
        write_export(destination, files)
    except ExportError as error:
        print(f"public-export: ERROR: {error}", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError) as error:
        print(f"public-export: ERROR operativo: {error}", file=sys.stderr)
        return 1
    print(f"public-export: OK ({len(files)} archivos + {MANIFEST_NAME})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
