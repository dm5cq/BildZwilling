# SPDX-License-Identifier: GPL-3.0-or-later
"""CSV-Bericht (Excel-tauglich: Semikolon, UTF-8 mit BOM)."""

from __future__ import annotations

import csv
import datetime as _dt

from ..i18n import _ as tr


def _formula_safe(v) -> str:
    """Schutz vor CSV-/Formel-Injection beim Öffnen in Excel."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def export_groups_csv(groups, path: str) -> int:
    n = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([tr("Gruppe"), tr("Art"), tr("Aktion"), tr("Pfad"), tr("Größe (Bytes)"), tr("Geändert"),
                    tr("Prüfsumme")])
        kinds = {"bytes": tr("Byte-identisch"), "pixels": tr("Bildinhalt identisch"), "similar": tr("ähnlich")}
        for g in groups:
            for fe in g.files:
                w.writerow([
                    g.gid, kinds.get(g.kind, g.kind),
                    tr("BEHALTEN") if fe.action == "keep" else tr("ARCHIVIEREN"),
                    _formula_safe(fe.path), fe.size,
                    _dt.datetime.fromtimestamp(fe.mtime).strftime("%d.%m.%Y %H:%M:%S"),
                    fe.digest or fe.pdigest or "",
                ])
                n += 1
    return n


def export_archive_csv(entries, path: str) -> int:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([tr("Archiviert am"), tr("Originalpfad"), tr("Archivpfad"), tr("Behaltenes Original"),
                    tr("Größe (Bytes)")])
        for r in entries:
            w.writerow([r.get("time", ""), _formula_safe(r.get("src", "")), _formula_safe(r.get("dst", "")),
                        _formula_safe(r.get("keep", "")), r.get("size", "")])
    return len(entries)
