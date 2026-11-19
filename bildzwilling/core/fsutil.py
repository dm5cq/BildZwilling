# SPDX-License-Identifier: GPL-3.0-or-later
"""Dateisystem-Hilfen: lange Pfade unter Windows, Cloud-Platzhalter, Pfadprüfungen."""

from __future__ import annotations

import os
import stat
import sys

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# Windows-Dateiattribute
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
_PLACEHOLDER_MASK = (
    FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)

_LP_PREFIX = "\\\\?\\"
_LP_UNC = "\\\\?\\UNC\\"


def lp(path: str) -> str:
    """Pfad für Betriebssystemaufrufe vorbereiten (Windows: >260 Zeichen erlauben)."""
    if not IS_WINDOWS or not path:
        return path
    if path.startswith(_LP_PREFIX):
        return path
    p = os.path.abspath(path)
    if len(p) < 240:
        return p
    if p.startswith("\\\\"):
        return _LP_UNC + p[2:]
    return _LP_PREFIX + p


def unlp(path: str) -> str:
    """Präfix für lange Pfade wieder entfernen (für Anzeige/Vergleich)."""
    if path.startswith(_LP_UNC):
        return "\\\\" + path[len(_LP_UNC):]
    if path.startswith(_LP_PREFIX):
        return path[len(_LP_PREFIX):]
    return path


def norm(path: str) -> str:
    """Normalisierter, absoluter Pfad zum Vergleichen (Groß/Klein unter Windows egal)."""
    return os.path.normcase(os.path.realpath(os.path.abspath(unlp(path))))


def is_within(path: str, parent: str) -> bool:
    """True, wenn path gleich parent ist oder darin liegt (symlink-sicher)."""
    try:
        p, q = norm(path), norm(parent)
        return os.path.commonpath([p, q]) == q
    except ValueError:  # unterschiedliche Laufwerke
        return False


def is_hidden(name: str, st: os.stat_result | None) -> bool:
    if name.startswith("."):
        return True
    if IS_WINDOWS and st is not None:
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    if IS_MAC and st is not None:
        return bool(getattr(st, "st_flags", 0) & getattr(stat, "UF_HIDDEN", 0x8000))
    return False


def is_cloud_placeholder(st: os.stat_result) -> bool:
    """Datei liegt nur online (OneDrive/Nextcloud-VFS „Nur online verfügbar“)?

    Ein Lesezugriff würde den Download auslösen.
    """
    if IS_WINDOWS:
        return bool(getattr(st, "st_file_attributes", 0) & _PLACEHOLDER_MASK)
    if IS_MAC:
        # macOS File Provider: SF_DATALESS = 0x40000000
        return bool(getattr(st, "st_flags", 0) & 0x40000000)
    return False


def same_device(a: str, b: str) -> bool:
    try:
        return os.stat(lp(a)).st_dev == os.stat(lp(b)).st_dev
    except OSError:
        return False


def unique_path(path: str) -> str:
    """Freien Dateinamen finden: "bild.jpg" -> "bild (1).jpg" ..."""
    if not os.path.lexists(lp(path)):
        return path
    base, ext = os.path.splitext(path)
    for i in range(1, 100000):
        cand = f"{base} ({i}){ext}"
        if not os.path.lexists(lp(cand)):
            return cand
    raise OSError(f"Kein freier Dateiname für {path}")


_INVALID = '<>:"/\\|?*'


def safe_name(name: str) -> str:
    out = "".join("_" if (c in _INVALID or ord(c) < 32) else c for c in name).strip(" .")
    return out or "Laufwerk"


def _en() -> bool:
    try:
        from ..i18n import lang

        return lang() == "en"
    except ImportError:
        return False


def num(n: int) -> str:
    """Ganzzahl mit Tausendertrennzeichen: de 12.345 · en 12,345."""
    s = f"{int(n):,}"
    return s if _en() else s.replace(",", ".")


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return f"{n:.0f} {unit}"
            s = f"{n:.1f} {unit}"
            return s if _en() else s.replace(".", ",")
        n /= 1024
    return f"{n} B"


def open_in_file_manager(path: str) -> None:
    """Ordner/Datei im Explorer bzw. Finder anzeigen (ohne Shell-Interpretation)."""
    import subprocess

    path = os.path.abspath(path)
    if IS_WINDOWS:
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", path])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
    elif IS_MAC:
        if os.path.isfile(path):
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
