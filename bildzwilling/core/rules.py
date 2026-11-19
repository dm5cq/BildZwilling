# SPDX-License-Identifier: GPL-3.0-or-later
"""Ordnerregeln: „immer behalten“ / „immer archivieren“.

Eine Regel ist ein dict {"pattern": str, "action": "keep" | "archive"}.
- Absoluter Pfad (z. B. D:\\Fotos\\Best) -> gilt für diesen Ordner und alle Unterordner.
- Sonst Textmuster, das im Pfad vorkommen muss, Groß/Klein egal, "/" und "\\" gleichwertig
  (z. B. "WhatsApp" oder "Fotos/Best").
Bei mehreren Treffern gewinnt „behalten“ (sichere Seite).
"""

from __future__ import annotations

import os

from .fsutil import is_within

ACTIONS = {"keep": "immer behalten", "archive": "immer archivieren"}


def valid_rules(rules) -> list[dict]:
    out = []
    for r in rules or []:
        if isinstance(r, dict) and isinstance(r.get("pattern"), str) and r.get("action") in ACTIONS:
            p = r["pattern"].strip()
            if p:
                out.append({"pattern": p, "action": r["action"]})
    return out


def _norm(s: str) -> str:
    return s.replace("\\", "/").lower()


def matches(path: str, pattern: str) -> bool:
    if os.path.isabs(pattern) or pattern.startswith("\\\\"):
        return is_within(path, pattern)
    return _norm(pattern).strip("/") in _norm(path)


def decide(path: str, rules) -> str | None:
    hit = None
    for r in rules or []:
        if matches(path, r["pattern"]):
            if r["action"] == "keep":
                return "keep"
            hit = "archive"
    return hit
