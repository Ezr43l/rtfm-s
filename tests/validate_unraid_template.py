from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "unraid" / "my-RTFM.xml"
README = ROOT / "README.md"
GUIDE = ROOT / "docs" / "UNRAID-INSTALLATION.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_template() -> None:
    raw = TEMPLATE.read_text(encoding="utf-8")
    root = ET.fromstring(raw)
    require(root.tag == "Container", "La raíz XML debe ser Container")
    configs = root.findall("Config")
    targets = [config.get("Target") for config in configs]
    require(targets == ["PORT", "/data"], "La plantilla debe contener sólo puerto y datos")
    require(len(set(targets)) == 2, "La plantilla contiene Target duplicados")
    require(configs[0].get("Type") == "Variable", "PORT debe ser una variable por usar red host")
    require(configs[1].get("Type") == "Path" and configs[1].get("Mode") == "rw", "/data debe ser un mount escribible")
    require("/run/secrets" not in raw, "La plantilla nueva no debe montar secretos externos")
    for secret in ("APP_TOKEN", "SESSION_SECRET", "REPLICATION_TOKEN", "KEEPALIVED_API_KEY"):
        require(secret not in targets, f"La plantilla no debe exponer {secret}")
    require(
        not re.search(r"(?:10\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.)", raw),
        "La plantilla contiene una IP privada incrustada",
    )
    require("__" not in raw, "La plantilla contiene un marcador sin resolver")
    extra = root.findtext("ExtraParams", default="")
    for contract in ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges"):
        require(contract in extra, f"Falta endurecimiento: {contract}")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    require(root.findtext("Repository") == f"ghcr.io/ezr43l/rtfm-s:{version}", "Repositorio o versión incorrectos")


def validate_documentation() -> None:
    readme = README.read_text(encoding="utf-8")
    guide = GUIDE.read_text(encoding="utf-8")
    for fragment in ("exactamente dos campos", "/data/.rtfm", "código de incorporación", "un único mount `/data`"):
        require(fragment in readme + guide, f"La documentación no explica: {fragment}")
    require("docker inspect" in guide, "La guía no incluye la comprobación de Docker")
    require("10001:10001" in guide, "La guía no explica los permisos de datos")


def main() -> int:
    try:
        validate_template()
        validate_documentation()
    except (AssertionError, ET.ParseError, OSError) as error:
        print(f"unraid-template: ERROR: {error}", file=sys.stderr)
        return 1
    print("unraid-template: dos campos, un volumen y configuración interna OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
