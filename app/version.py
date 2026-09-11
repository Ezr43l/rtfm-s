"""Versión única de RTFM para código, API y agentes HTTP."""

from __future__ import annotations

import os
from pathlib import Path


def current_version() -> str:
    configured = os.getenv("RTFM_VERSION", "").strip()
    if configured:
        return configured
    for filename in (
        Path("/app/VERSION"),
        Path(__file__).resolve().parent.parent / "VERSION",
    ):
        try:
            value = filename.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return "development"


VERSION = current_version()
USER_AGENT = f"rtfm/{VERSION}"
