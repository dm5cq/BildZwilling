# SPDX-License-Identifier: GPL-3.0-or-later
"""Bewertungen, Farbmarkierungen und Markierungen (Pick/Reject).

Quellen (in dieser Reihenfolge, spätere ergänzen fehlende Werte):
  1. Lightroom-Katalog (.lrcat, nur lesend): Sterne, Farbmarkierung, Flagge (markiert/abgelehnt)
  2. XMP-Begleitdatei (bild.xmp / bild.cr3.xmp) – Lightroom, darktable, Capture One, digiKam …
  3. In die Datei eingebettetes XMP (JPEG, TIFF, DNG, HEIC …)
Wird verwendet, um bewertete Bilder bevorzugt zu behalten und abgelehnte bevorzugt zu archivieren.
"""

from __future__ import annotations

import os
import pathlib
import re
import sqlite3
from dataclasses import dataclass

from .fsutil import lp

_RATING = re.compile(rb'xmp:Rating\s*=\s*["\'](-?\d+)["\']|<xmp:Rating>\s*(-?\d+)\s*</xmp:Rating>')
_LABEL = re.compile(rb'xmp:Label\s*=\s*["\']([^"\']{1,40})["\']|<xmp:Label>\s*([^<]{1,40})\s*</xmp:Label>')
_PICK = re.compile(rb'(?:xmpDM|lr|xmp|digiKam):(?:pick|Pick|PickLabel)\s*=\s*["\'](-?\d+)["\']')
_HEAD = 4 * 1024 * 1024


@dataclass
class Rating:
    stars: int | None = None   # -1 = abgelehnt, 0..5
    label: str = ""            # Farbmarkierung (Red, Yellow, Green, Blue, Purple …)
    pick: int = 0              # 1 = markiert, -1 = abgelehnt

    @property
    def rejected(self) -> bool:
        return self.pick < 0 or (self.stars is not None and self.stars < 0)

    @property
    def empty(self) -> bool:
        return self.stars in (None, 0) and not self.label and self.pick == 0

    def score(self) -> int:
        """Höher = eher behalten."""
        if self.rejected:
            return -100
        return (self.stars or 0) * 10 + (5 if self.pick > 0 else 0) + (2 if self.label else 0)

    def text(self) -> str:
        if self.rejected:
            return "✖"
        out = "★" * max(0, self.stars or 0)
        if self.pick > 0:
            out += "⚑"
        if self.label:
            out += f" {self.label}"
        return out.strip()

    def merge(self, other: "Rating") -> "Rating":
        return Rating(self.stars if self.stars is not None else other.stars,
                      self.label or other.label, self.pick or other.pick)


def _parse(data: bytes) -> Rating:
    r = Rating()
    m = _RATING.search(data)
    if m:
        try:
            r.stars = max(-1, min(5, int(m.group(1) or m.group(2))))
        except ValueError:
            pass
    m = _LABEL.search(data)
    if m:
        r.label = (m.group(1) or m.group(2) or b"").decode("utf-8", "replace").strip()
    m = _PICK.search(data)
    if m:
        try:
            r.pick = max(-1, min(1, int(m.group(1))))
        except ValueError:
            pass
    return r


def _sidecars(path: str) -> list[str]:
    folder, name = os.path.split(path)
    stem = os.path.splitext(name)[0]
    try:
        names = {n.lower(): n for n in os.listdir(lp(folder))}
    except OSError:
        return []
    out = []
    for cand in (name + ".xmp", stem + ".xmp"):
        n = names.get(cand.lower())
        if n:
            out.append(os.path.join(folder, n))
    return out


def read_xmp(path: str) -> Rating:
    r = Rating()
    for sc in _sidecars(path):
        try:
            with open(lp(sc), "rb") as f:
                r = r.merge(_parse(f.read(1024 * 1024)))
        except OSError:
            pass
    if r.stars is None or not r.label:
        try:
            with open(lp(path), "rb") as f:
                head = f.read(_HEAD)
            i = head.find(b"<x:xmpmeta")
            if i >= 0:
                j = head.find(b"</x:xmpmeta>", i)
                r = r.merge(_parse(head[i:j + 12 if j > 0 else i + 200_000]))
        except OSError:
            pass
    return r


class LightroomCatalog:
    """Liest Bewertungen aus einem Lightroom-Classic-Katalog (nur lesend, auch wenn Lightroom geöffnet ist)."""

    SQL = """
        SELECT rf.absolutePath, fo.pathFromRoot, fi.baseName, fi.extension,
               im.rating, im.colorLabels, im.pick
        FROM Adobe_images im
        JOIN AgLibraryFile fi ON im.rootFile = fi.id_local
        JOIN AgLibraryFolder fo ON fi.folder = fo.id_local
        JOIN AgLibraryRootFolder rf ON fo.rootFolder = rf.id_local
    """

    def __init__(self, path: str):
        self.path = path
        self.map: dict[str, Rating] = {}
        # Windows-taugliche URI (file:///C:/...), Sonderzeichen werden kodiert
        uri = pathlib.Path(os.path.abspath(path)).as_uri() + "?mode=ro&immutable=1"
        con = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            for root, rel, base, ext, rating, label, pick in con.execute(self.SQL):
                full = f"{root or ''}{rel or ''}{base or ''}" + (f".{ext}" if ext else "")
                key = os.path.normcase(os.path.normpath(full))
                try:
                    stars = int(rating) if rating is not None else None
                except (TypeError, ValueError):
                    stars = None
                try:
                    p = int(float(pick or 0))
                except (TypeError, ValueError):
                    p = 0
                self.map[key] = Rating(stars, str(label or ""), max(-1, min(1, p)))
        finally:
            con.close()

    def get(self, path: str) -> Rating:
        return self.map.get(os.path.normcase(os.path.normpath(os.path.abspath(path))), Rating())


def open_catalog(path: str):
    if not path:
        return None
    try:
        return LightroomCatalog(path)
    except (sqlite3.Error, OSError):
        return None


def rating_for(path: str, catalog=None) -> Rating:
    r = catalog.get(path) if catalog is not None else Rating()
    return r.merge(read_xmp(path))
