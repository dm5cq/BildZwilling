# SPDX-License-Identifier: GPL-3.0-or-later
"""Ruhezustand während langer Vorgänge verhindern (2.2, C2).

Windows: SetThreadExecutionState (gilt für den aufrufenden Thread – daher im Arbeits-Thread benutzen).
macOS: „caffeinate -i“ für die Dauer des Vorgangs. Linux: keine Aktion.
Der Bildschirm darf weiterhin ausgehen; nur der Ruhezustand des Rechners wird verhindert.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def keep_awake():
    proc = None
    win = sys.platform.startswith("win")
    if win:
        try:
            import ctypes

            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)  # pyright: ignore[reportAttributeAccessIssue]
        except (AttributeError, OSError):
            win = False
    elif sys.platform == "darwin":
        try:
            proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            proc = None
    try:
        yield
    finally:
        if win:
            try:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # pyright: ignore[reportAttributeAccessIssue]
            except (AttributeError, OSError):
                pass
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass
