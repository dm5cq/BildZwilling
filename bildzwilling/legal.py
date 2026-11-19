# SPDX-License-Identifier: GPL-3.0-or-later
"""Lizenz- und Haftungstexte (GPL v3) – eine Quelle für Programm, Kommandozeile und Dokumentation."""

from __future__ import annotations

import os
import sys

from .i18n import _ as tr


def license_notice() -> str:
    """Kurzer GPL-Hinweis (Abschnitt „How to Apply These Terms“ der GPL v3)."""
    return tr(
        "BildZwilling ist freie Software: Sie können es unter den Bedingungen der GNU General Public License, "
        "wie von der Free Software Foundation veröffentlicht, weitergeben und/oder verändern – entweder gemäß "
        "Version 3 der Lizenz oder (nach Ihrer Wahl) jeder späteren Version.\n\n"
        "BildZwilling wird in der Hoffnung verbreitet, dass es nützlich ist, aber OHNE JEDE GEWÄHRLEISTUNG – "
        "sogar ohne die implizite Gewährleistung der MARKTREIFE oder der EIGNUNG FÜR EINEN BESTIMMTEN ZWECK. "
        "Einzelheiten stehen in der GNU General Public License (Datei LICENSE).\n\n"
        "Den Quellcode erhalten Sie zusammen mit dem Programm (Projekt-ZIP) bzw. beim Herausgeber.")


def disclaimer_short() -> str:
    return tr("Nutzung auf eigene Verantwortung und ohne Gewährleistung. Vor dem Aufräumen eine Datensicherung "
              "anlegen. Einzelheiten im Lizenztext (GPL v3, Abschnitte 15–16).")


def disclaimer_full() -> str:
    return tr(
        "Haftungsausschluss\n\n"
        "BildZwilling verschiebt Dateien und kann sie nach Ihrer ausdrücklichen Freigabe löschen. Das Programm "
        "wurde sorgfältig entwickelt und getestet; Fehler lassen sich dennoch nie ganz ausschließen – etwa durch "
        "defekte Datenträger, Netzwerk- oder Cloud-Störungen, Fremdprogramme oder Bedienfehler.\n\n"
        "• Die Nutzung erfolgt auf eigene Verantwortung.\n"
        "• Legen Sie vor dem Aufräumen eine aktuelle Datensicherung an.\n"
        "• Prüfen Sie archivierte Dateien, bevor Sie sie endgültig löschen.\n"
        "• Soweit gesetzlich zulässig, wird keine Gewährleistung übernommen und keine Haftung für Datenverlust, "
        "entgangenen Nutzen oder sonstige Schäden (GNU GPL v3, Abschnitte 15 und 16). Zwingende gesetzliche "
        "Haftung – etwa bei Vorsatz – bleibt unberührt.\n\n"
        "Cloud-Anbieter (pCloud, Microsoft OneDrive) sind eigenständige Dienste; für deren Verfügbarkeit und "
        "Schnittstellen wird keine Gewähr übernommen. Marken sind Eigentum ihrer Inhaber.")


def _resource_dirs() -> list[str]:
    dirs = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.append(base)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
    dirs.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return dirs


def read_text_file(name: str) -> str:
    """LICENSE bzw. THIRD_PARTY_LICENSES.txt aus EXE, EXE-Ordner oder Projekt lesen."""
    for d in _resource_dirs():
        p = os.path.join(d, name)
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return ""
