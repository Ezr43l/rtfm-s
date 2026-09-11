#!/usr/bin/env python3
from __future__ import annotations

import collections
import pathlib
import re
import sys


SOURCE_REQUIRED_LICENSE = re.compile(
    r"(?:A?GPL|LGPL|MPL|EPL|CDDL|CPL|OSL|EUPL|CECILL)", re.IGNORECASE
)


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(
            "usage: collect-alpine-copyleft-manifest.py OUTPUT_TSV "
            "PLATFORM=INSTALLED_DB [...]"
        )
    groups: dict[tuple[str, str], dict[str, set[str]]] = collections.defaultdict(
        lambda: {
            "platforms": set(),
            "packages": set(),
            "versions": set(),
            "licenses": set(),
        }
    )
    seen_platforms: set[str] = set()
    for source in sys.argv[2:]:
        platform, separator, filename = source.partition("=")
        if separator != "=" or not re.fullmatch(r"linux/(?:amd64|arm64)", platform):
            raise SystemExit(f"invalid platform/database argument: {source}")
        if platform in seen_platforms:
            raise SystemExit(f"duplicate platform: {platform}")
        seen_platforms.add(platform)
        installed = pathlib.Path(filename).read_text(encoding="utf-8")
        for block in installed.split("\n\n"):
            fields: dict[str, list[str]] = collections.defaultdict(list)
            for line in block.splitlines():
                if len(line) >= 2 and line[1] == ":":
                    fields[line[0]].append(line[2:])
            package = (fields.get("P") or [""])[0]
            version = (fields.get("V") or [""])[0]
            license_expression = (fields.get("L") or [""])[0]
            origin = (fields.get("o") or [""])[0]
            commit = (fields.get("c") or [""])[0]
            if not SOURCE_REQUIRED_LICENSE.search(license_expression):
                continue
            if (
                not package
                or not version
                or not origin
                or not re.fullmatch(r"[0-9a-f]{40}", commit)
            ):
                raise SystemExit(
                    f"incomplete source-required APK metadata for {package or '<unknown>'}"
                )
            if not re.fullmatch(r"[A-Za-z0-9+._-]+", origin):
                raise SystemExit(f"unsafe APK origin: {origin}")
            group = groups[(origin, commit)]
            group["platforms"].add(platform)
            group["packages"].add(package)
            group["versions"].add(version)
            group["licenses"].add(license_expression)

    if not groups:
        raise SystemExit("no source-required APK packages found")
    destination = pathlib.Path(sys.argv[1])
    with destination.open("w", encoding="utf-8", newline="\n") as output:
        for (origin, commit), values in sorted(groups.items()):
            columns = [
                ",".join(sorted(values["platforms"])),
                origin,
                commit,
                ",".join(sorted(values["packages"])),
                ",".join(sorted(values["versions"])),
                ";".join(sorted(values["licenses"])),
            ]
            if any("\t" in value or "\n" in value for value in columns):
                raise SystemExit(f"unsafe APK metadata for {origin}")
            output.write("\t".join(columns) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
