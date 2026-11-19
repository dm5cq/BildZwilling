# SPDX-License-Identifier: GPL-3.0-or-later
"""Aufräumen beim Start (2.2, C7): alte Vorschau-Ordner im Temp, Prüfsummen-Cache monatlich bereinigen."""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import tempfile
import time

TEMP_PREFIXES = ("bz_cloud_", "bz_thumbs_", "bz_tmp_")


def cleanup_temp(max_age_h: float = 24, base: str | None = None) -> int:
    """Liegengebliebene BildZwilling-Temp-Ordner (z. B. nach Absturz) löschen. Nur eigene Präfixe."""
    base = base or tempfile.gettempdir()
    n = 0
    now = time.time()
    try:
        names = os.listdir(base)
    except OSError:
        return 0
    for name in names:
        if not name.startswith(TEMP_PREFIXES):
            continue
        p = os.path.join(base, name)
        try:
            if os.path.islink(p) or not os.path.isdir(p):
                continue
            if now - os.path.getmtime(p) < max_age_h * 3600:
                continue  # evtl. von einer laufenden Instanz benutzt
            shutil.rmtree(p, ignore_errors=True)
            n += 1
        except OSError:
            continue
    return n


def prune_due(last: str, days: int = 30) -> bool:
    if not last:
        return True
    try:
        return (_dt.date.today() - _dt.date.fromisoformat(last)).days >= days
    except ValueError:
        return True


def today() -> str:
    return _dt.date.today().isoformat()
