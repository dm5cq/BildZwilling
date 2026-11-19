# SPDX-License-Identifier: GPL-3.0-or-later
"""Datensparsames Protokoll (2.2, B4): E-Mail-Adressen, Tokens, Passwörter und Codes werden geschwärzt."""

from __future__ import annotations

import logging
import os
import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_KV = re.compile(r"(?i)\b(auth|access_token|refresh_token|token|password|passwort|client_secret|secret|code|"
                 r"tfa_token|authorization)(\s*[=:]\s*)([^\s&,;\"']+)")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")


def redact(text: str) -> str:
    text = _EMAIL.sub("<E-Mail>", text)
    text = _BEARER.sub(r"\1 ***", text)
    text = _KV.sub(lambda m: m.group(1) + m.group(2) + "***", text)
    return text


def anonymize_paths(text: str) -> str:
    """Benutzerordner durch Platzhalter ersetzen (für „Systeminfo kopieren“ / Fehlerdetails)."""
    home = os.path.expanduser("~")
    if home and len(home) > 3:
        text = re.sub(re.escape(home), "%USERPROFILE%" if os.name == "nt" else "~", text, flags=re.I)
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if len(user) >= 3:
        text = re.sub(r"(?i)([\\/])" + re.escape(user) + r"([\\/])", r"\1<Benutzer>\2", text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except (TypeError, ValueError):
            return True
        record.msg = redact(msg)
        record.args = ()
        return True
