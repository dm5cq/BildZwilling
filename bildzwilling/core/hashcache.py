# SPDX-License-Identifier: GPL-3.0-or-later
"""Prüfsummen-Cache (SQLite) – beschleunigt erneute Suchen, v. a. auf Cloud-/Netzlaufwerken.

Ein Eintrag gilt nur, solange Pfad, Größe und Änderungszeit unverändert sind.
"""

from __future__ import annotations

import os
import sqlite3
import threading


class HashCache:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        try:
            self._db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS h (path TEXT, algo TEXT, size INTEGER, "
            "mtime INTEGER, digest TEXT, PRIMARY KEY(path, algo))"
        )
        self._db.commit()
        self._pending = 0

    def get(self, path: str, algo: str, size: int, mtime_ns: int) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT size, mtime, digest FROM h WHERE path=? AND algo=?", (path, algo)
            ).fetchone()
        if row and row[0] == size and row[1] == mtime_ns:
            return row[2]
        return None

    def put(self, path: str, algo: str, size: int, mtime_ns: int, digest: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO h VALUES (?,?,?,?,?)", (path, algo, size, mtime_ns, digest)
            )
            self._pending += 1
            if self._pending >= 500:
                self._db.commit()
                self._pending = 0

    def commit(self) -> None:
        with self._lock:
            try:
                self._db.commit()
                self._pending = 0
            except sqlite3.Error:
                pass

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM h")
            self._db.commit()
            self._db.execute("VACUUM")

    def count(self) -> int:
        with self._lock:
            try:
                return int(self._db.execute("SELECT COUNT(*) FROM h").fetchone()[0])
            except sqlite3.Error:
                return 0

    def prune(self, exists=os.path.exists, cancel=None, limit: int = 2_000_000) -> int:
        """Einträge gelöschter Dateien entfernen (2.2, C7/R1).

        Nur Einträge, deren ORDNER noch erreichbar ist, die Datei aber nicht mehr – Einträge auf gerade
        nicht verbundenen Laufwerken/Cloud-Ordnern bleiben erhalten. Danach VACUUM.
        """
        with self._lock:
            rows = self._db.execute("SELECT DISTINCT path FROM h LIMIT ?", (limit,)).fetchall()
        dead, dir_ok = [], {}
        for (p,) in rows:
            if cancel is not None and cancel.is_set():
                break
            d = os.path.dirname(p)
            if d not in dir_ok:
                dir_ok[d] = exists(d)
            if dir_ok[d] and not exists(p):
                dead.append((p,))
        if dead:
            with self._lock:
                self._db.executemany("DELETE FROM h WHERE path=?", dead)
                self._db.commit()
        with self._lock:
            try:
                self._db.execute("VACUUM")
            except sqlite3.Error:
                pass
        return len(dead)

    def close(self) -> None:
        with self._lock:
            try:
                self._db.commit()
                self._db.close()
            except sqlite3.Error:
                pass


class NullCache:
    """Platzhalter, wenn der Cache nicht geöffnet werden kann."""

    def get(self, *a, **k):
        return None

    def put(self, *a, **k):
        pass

    def clear(self):
        pass

    def count(self):
        return 0

    def prune(self, *a, **k):
        return 0

    def commit(self):
        pass

    def close(self):
        pass


def open_cache(path: str):
    try:
        return HashCache(path)
    except (sqlite3.Error, OSError):
        return NullCache()
