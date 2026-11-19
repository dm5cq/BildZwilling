# SPDX-License-Identifier: GPL-3.0-or-later
"""Mehrsprachigkeit (Deutsch = Quelltext, Englisch über Wörterbuch in i18n_en.py).

Verwendung:  from bildzwilling.i18n import _      _("Suche starten")      _("{n} Dateien").format(n=3)
Fehlt eine Übersetzung, wird der deutsche Text angezeigt (nie ein Absturz).
"""

from __future__ import annotations

LANG = "de"
LANGUAGES = {"de": "Deutsch", "en": "English"}
_TABLE: dict[str, str] = {}


def set_language(lang: str) -> None:
    global LANG, _TABLE
    LANG = lang if lang in LANGUAGES else "de"
    if LANG == "en":
        from .i18n_en import EN

        _TABLE = EN
    else:
        _TABLE = {}


def _(text: str) -> str:
    return _TABLE.get(text, text) if _TABLE else text


def lang() -> str:
    return LANG
