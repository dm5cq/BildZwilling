# SPDX-License-Identifier: GPL-3.0-or-later
"""Anmeldedaten (Cloud-Token) geschützt speichern.

Windows: DPAPI (CryptProtectData) – nur derselbe Windows-Benutzer kann das Token entschlüsseln.
Andere Systeme: kein dauerhaftes Speichern (Anmeldung gilt nur bis zum Programmende).
Passwörter werden nie gespeichert, nur das vom Anbieter ausgegebene Token.
"""

from __future__ import annotations

import base64
import json
import os
import sys

AVAILABLE = sys.platform.startswith("win")


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    entropy_raw = b"BildZwilling-2.0"
    ebuf = ctypes.create_string_buffer(entropy_raw, len(entropy_raw))
    ent = BLOB(len(entropy_raw), ctypes.cast(ebuf, ctypes.POINTER(ctypes.c_char)))
    crypt32 = ctypes.windll.crypt32  # pyright: ignore[reportAttributeAccessIssue]
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(inp), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out))  # UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI fehlgeschlagen")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)  # pyright: ignore[reportAttributeAccessIssue]


class TokenStore:
    def __init__(self, path: str):
        self.path = path

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, key: str) -> str:
        if not AVAILABLE:
            return ""
        v = self._load().get(key)
        if not isinstance(v, str):
            return ""
        try:
            return _dpapi(base64.b64decode(v), False).decode("utf-8")
        except (OSError, ValueError):
            return ""

    def set(self, key: str, token: str) -> bool:
        """Speichert verschlüsselt; Fehler werden nicht weitergereicht (Anmeldung bleibt gültig)."""
        if not AVAILABLE:
            return False
        try:
            d = self._load()
            if token:
                d[key] = base64.b64encode(_dpapi(token.encode("utf-8"), True)).decode("ascii")
            else:
                d.pop(key, None)
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, self.path)
            return True
        except (OSError, ValueError):
            return False

    def clear(self, key: str) -> None:
        if AVAILABLE:
            self.set(key, "")

    def keys(self) -> list[str]:
        return sorted(self._load().keys())

    def clear_all(self) -> int:
        """Alle gespeicherten Anmeldungen (Tokens, Client-Secret) entfernen. Liefert die Anzahl (2.2, B3)."""
        n = len(self._load())
        for name in (self.path, self.path + ".tmp"):
            try:
                os.remove(name)
            except FileNotFoundError:
                pass
            except OSError:
                # nicht löschbar → leeren
                try:
                    with open(name, "w", encoding="utf-8") as f:
                        f.write("{}")
                except OSError:
                    pass
        return n
