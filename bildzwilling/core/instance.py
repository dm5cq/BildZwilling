# SPDX-License-Identifier: GPL-3.0-or-later
"""Nur eine Instanz gleichzeitig (2.2, B1).

Zwei gleichzeitig laufende Programme könnten sich beim Archiv-Journal, Cache und den Einstellungen
in die Quere kommen. Die Sperre ist eine vom Betriebssystem gehaltene Dateisperre: Sie verschwindet
automatisch, wenn das Programm endet oder abstürzt – es bleibt keine „tote“ Sperrdatei zurück.
"""

from __future__ import annotations

import os
import sys

LOCK_NAME = "BildZwilling.lock"


class InstanceLock:
    def __init__(self, directory: str, name: str = LOCK_NAME):
        self.path = os.path.join(directory, name)
        self._f = None

    def acquire(self) -> bool:
        if self._f is not None:
            return True
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            f = open(self.path, "a+")
        except OSError:
            return True  # Ordner nicht beschreibbar: nicht blockieren
        try:
            if sys.platform == "win32":
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)  # pyright: ignore[reportAttributeAccessIssue]
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        try:
            f.seek(0)
            f.truncate()
            f.write(str(os.getpid()))
            f.flush()
        except OSError:
            pass
        self._f = f
        return True

    def release(self) -> None:
        f, self._f = self._f, None
        if f is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)  # pyright: ignore[reportAttributeAccessIssue]
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
