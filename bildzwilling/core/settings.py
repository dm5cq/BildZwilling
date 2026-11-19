# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen – portabel neben der EXE, sonst im Benutzerprofil."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

from .fsutil import IS_MAC, IS_WINDOWS

DEFAULTS = {
    "roots": [],
    "archive_dir": "",
    "mode": "bytes",               # "bytes" | "pixels"
    "images_only": True,
    "include_hidden": False,
    "include_placeholders": False,  # Nur-Online-Dateien (OneDrive/Nextcloud) einbeziehen
    "min_size_kb": 1,
    "keep_rule": "first_root",      # first_root | oldest | newest | shortest_path
    "move_sidecars": True,
    "use_recycle_bin": True,
    "workers": 4,
    "geometry": "1400x880",
    # 1.5
    "include_videos": False,
    "similar": False,
    "similar_threshold": 6,
    "keep_pairs": True,
    "folder_rules": [],
    "retention_days": 30,
    "theme": "dark",            # dark | light | contrast
    "large_font": False,
    "speech": False,
    "use_exiftool": True,
    "exiftool_path": "",
    "ffmpeg_path": "",
    "page_size": 300,
    # 2.0
    "rotations": True,
    "use_ratings": True,
    "lrcat_path": "",
    "language": "de",          # de | en
    "seestar_dir": "",
    "cloud_provider": "pcloud_eu",
    "cloud_root": "/",
    "cloud_archive": "/BildZwilling_Archiv",
    "onedrive_client_id": "",
    "cloud_remember": False,
    # 2.1
    "pcloud_client_id": "",
    # 2.2
    "disclaimer_ok": "",       # Version, in der der Haftungshinweis bestätigt wurde
    "cache_pruned": "",        # Datum der letzten Cache-Bereinigung (ISO)
}


def app_dir() -> str:
    """Ordner der EXE (gefroren) bzw. des Projekts (Quellcode)."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        if IS_MAC and ".app/Contents/MacOS" in exe:
            # Neben dem .app-Bundle ablegen, nicht im (signierten) Bundle
            return os.path.dirname(exe.split(".app/Contents/MacOS")[0] + ".app")
        return os.path.dirname(exe)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _user_dir() -> str:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "BildZwilling")


def _writable(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=d, prefix=".bz_test_", delete=True):
            pass
        return True
    except OSError:
        return False


def data_dir() -> str:
    """Ordner für settings.json, Cache und Log."""
    portable = os.path.join(app_dir(), "BildZwilling_Daten")
    if _writable(portable):
        return portable
    d = _user_dir()
    os.makedirs(d, exist_ok=True)
    return d


class Settings(dict):
    def __init__(self, path: str | None = None):
        super().__init__(DEFAULTS)
        self.path = path or os.path.join(data_dir(), "settings.json")
        self.load()

    def load(self) -> None:
        """Einstellungen laden. Ist settings.json beschädigt, wird die Sicherung (.bak) verwendet (2.2, C1).

        self.recovered: "" (normal), "backup" (aus Sicherung) oder "defaults" (Standardwerte).
        """
        self.recovered = ""
        data = self._read(self.path)
        if data is None and os.path.exists(self.path):
            data = self._read(self.path + ".bak")
            self.recovered = "backup" if data is not None else "defaults"
            try:  # beschädigte Datei zur Analyse aufheben, nicht überschreiben
                os.replace(self.path, self.path + ".defekt")
            except OSError:
                pass
        if not data:
            return
        for k, v in data.items():
            # nur bekannte Schlüssel mit passendem Typ übernehmen
            if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                self[k] = v

    @staticmethod
    def _read(path: str) -> dict | None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return None

    def save(self) -> None:
        """Atomar speichern (temporäre Datei → ersetzen); die vorige Fassung bleibt als .bak erhalten."""
        d = os.path.dirname(self.path)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".settings_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dict(self), f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            if self._read(self.path) is not None:
                try:
                    shutil.copy2(self.path, self.path + ".bak")
                except OSError:
                    pass
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
