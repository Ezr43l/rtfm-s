#!/usr/bin/env python3
"""Create a deterministic inventory of licenses shipped by Python wheels."""

from __future__ import annotations

import hashlib
import importlib.metadata
import pathlib
import re
import sys


MAX_TEXT_BYTES = 2 * 1024 * 1024
LICENSE_NAME = re.compile(r"^(?:licen[cs]e|copying|notice)(?:[._-].*)?$", re.IGNORECASE)


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"python third-party license gate: {message}")


def read_regular_text(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, RuntimeError, ValueError):
        fail(f"license path escapes the Python installation: {path}")
    if path.is_symlink() or not resolved.is_file():
        fail(f"license artifact is not a regular file: {path}")
    size = resolved.stat().st_size
    if size <= 0 or size > MAX_TEXT_BYTES:
        fail(f"license artifact has an invalid size: {path}")
    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        fail(f"license artifact is not UTF-8 text: {path}")
    if "\x00" in text or "\ufffd" in text:
        fail(f"license artifact is not plain text: {path}")
    return text if text.endswith("\n") else f"{text}\n"


def declared_license(metadata: importlib.metadata.PackageMetadata) -> str:
    expression = (metadata.get("License-Expression") or "").strip()
    if expression:
        return expression
    legacy = (metadata.get("License") or "").strip()
    if legacy:
        return legacy
    classifiers = sorted(
        value.removeprefix("License :: ").strip()
        for value in metadata.get_all("Classifier", [])
        if value.startswith("License :: ")
    )
    return "; ".join(classifiers) or "NOASSERTION (see bundled license text)"


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: collect-python-third-party-licenses.py OUTPUT")
    output = pathlib.Path(sys.argv[1]).resolve()
    distributions = []
    texts: dict[str, dict[str, object]] = {}

    for distribution in importlib.metadata.distributions():
        name = (distribution.metadata.get("Name") or "").strip()
        version = distribution.version.strip()
        if not name or not version:
            fail("installed distribution has incomplete identity")
        root = pathlib.Path(distribution.locate_file("")).resolve(strict=True)
        license_paths = sorted(
            (
                pathlib.Path(distribution.locate_file(entry))
                for entry in (distribution.files or [])
                if LICENSE_NAME.fullmatch(pathlib.PurePath(str(entry)).name)
            ),
            key=lambda item: str(item),
        )
        if not license_paths:
            fail(f"{name}@{version} does not carry a license or NOTICE text")

        hashes = []
        for path in license_paths:
            text = read_regular_text(path, root)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            hashes.append(digest)
            record = texts.setdefault(digest, {"text": text, "consumers": []})
            relative_path = path.resolve(strict=True).relative_to(root)
            consumers = record["consumers"]
            if not isinstance(consumers, list):
                fail("internal consumer inventory is malformed")
            consumers.append(f"{name}@{version} ({relative_path.as_posix()})")

        distributions.append(
            {
                "name": name,
                "version": version,
                "license": declared_license(distribution.metadata),
                "hashes": sorted(set(hashes)),
            }
        )

    distributions.sort(key=lambda item: (str(item["name"]).casefold(), str(item["version"])))
    if not distributions:
        fail("no installed Python distributions were found")

    lines = [
        "RTFM PYTHON THIRD-PARTY LICENSES",
        "",
        "Generated deterministically from the distributions installed in the runtime image.",
        "Do not edit this artifact by hand; change the requirements or collector and rebuild.",
        "",
        f"Installed distributions: {len(distributions)}",
        f"Unique license/NOTICE texts: {len(texts)}",
        "",
        "PACKAGE INVENTORY",
        "",
    ]
    for item in distributions:
        lines.append(
            f"{item['name']}@{item['version']} | declared={item['license']} | "
            f"texts={','.join(item['hashes'])}"
        )
    for digest, record in sorted(texts.items()):
        consumers = record["consumers"]
        text = record["text"]
        if not isinstance(consumers, list) or not isinstance(text, str):
            fail("internal license text inventory is malformed")
        lines.extend(
            [
                "",
                f"===== BEGIN THIRD-PARTY TEXT sha256:{digest} =====",
                f"Packages: {'; '.join(sorted(consumers, key=str.casefold))}",
                "",
                text.rstrip(),
                f"===== END THIRD-PARTY TEXT sha256:{digest} =====",
            ]
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(
        f"wrote {output}: {len(distributions)} distributions, "
        f"{len(texts)} unique texts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
