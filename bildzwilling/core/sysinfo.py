# SPDX-License-Identifier: GPL-3.0-or-later
"""Systeminformationen für „Systeminfo kopieren“ und Fehlerdetails (2.2, C6) – ohne persönliche Daten."""

from __future__ import annotations

import platform
import sys

from .. import APP_NAME, BUILD_DATE, LICENSE_SPDX, SOURCE_URL, VERSION
from . import tools
from .logutil import anonymize_paths, redact


def system_info(data_dir: str = "", caps: dict | None = None) -> str:
    lines = [f"{APP_NAME} {VERSION} ({BUILD_DATE}) · {LICENSE_SPDX}",
             f"System: {platform.system()} {platform.release()} ({platform.version()}) · {platform.machine()}",
             f"Quellcode: {SOURCE_URL}",
             f"Python: {platform.python_version()} · {'EXE' if getattr(sys, 'frozen', False) else 'Quellcode'}"]
    try:
        import tkinter

        lines.append(f"Tk: {getattr(tkinter, 'TkVersion', '?')}")
    except ImportError:
        pass
    if caps:
        lines.append("Komponenten: " + ", ".join(f"{k} {'✔' if v else '–'}" for k, v in caps.items()))
    for t in ("exiftool", "ffmpeg"):
        try:
            i = tools.tool_info(t)
        except Exception:  # noqa: BLE001
            i = {"path": ""}
        if i.get("path"):
            lines.append(f"{t}: {i.get('version', '')} · SHA-256 {i.get('sha256', '')[:16]}… · {i['path']}")
        else:
            lines.append(f"{t}: –")
    if data_dir:
        lines.append(f"Daten: {data_dir}")
    return anonymize_paths(redact("\n".join(lines)))
