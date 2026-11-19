# SPDX-License-Identifier: GPL-3.0-or-later
"""Archivierungsplan: welches Duplikat wird gegen welches Original geprüft,
und wie werden RAW+JPEG-Paare zusammengehalten.

Regeln für Paare (Option „RAW+JPEG-Paare zusammenhalten“):
  a) Partner wird ebenfalls archiviert                  -> beide normal verschieben
  b) Partner ist kein Duplikat und das behaltene Original
     hat ebenfalls einen Partner gleichen Typs          -> Partner wandert mit (wiederherstellbar)
  c) sonst (Partner wird behalten / Original ohne Paar) -> Duplikat überspringen, Paar bleibt ganz
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..i18n import _ as tr
from .formats import ASTRO_EXT, PAIR_EXT, ext_of
from .formats import RAW_EXT as _RAW
from .fsutil import lp

if TYPE_CHECKING:
    from .scanner import FileEntry

RAW_EXT = _RAW | ASTRO_EXT  # FITS (Seestar) + JPG gilt ebenfalls als Paar


@dataclass
class PlanItem:
    dup: "FileEntry"
    keep: "FileEntry"
    kind: str
    companions: list[str] = field(default_factory=list)
    skip: str = ""


class PairFinder:
    """Findet den Paarpartner (gleicher Name, gleicher Ordner, RAW <-> JPEG/HEIF)."""

    def __init__(self):
        self._dirs: dict[str, dict[str, list[str]]] = {}

    def _listing(self, folder: str) -> dict[str, list[str]]:
        if folder not in self._dirs:
            m: dict[str, list[str]] = {}
            try:
                for n in os.listdir(lp(folder)):
                    m.setdefault(os.path.splitext(n)[0].lower(), []).append(n)
            except OSError:
                pass
            self._dirs[folder] = m
        return self._dirs[folder]

    def partner(self, path: str) -> str | None:
        folder, name = os.path.split(path)
        e = ext_of(name)
        if e in RAW_EXT:
            want = PAIR_EXT
        elif e in PAIR_EXT:
            want = RAW_EXT
        else:
            return None
        for n in self._listing(folder).get(os.path.splitext(name)[0].lower(), []):
            if n.lower() != name.lower() and ext_of(n) in want:
                return os.path.join(folder, n)
        return None


def _key(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def plan_archive(groups, keep_pairs: bool = True, include_similar: bool = True) -> list[PlanItem]:
    member: dict[int, list] = {}
    for g in groups:
        for f in g.files:
            member.setdefault(id(f), []).append(g)

    todo, seen = [], set()
    for g in groups:
        if g.kind == "similar" and not include_similar:
            continue
        for f in g.to_archive:
            if id(f) not in seen:
                seen.add(id(f))
                todo.append(f)

    items: list[PlanItem] = []
    for f in todo:
        gs = member.get(id(f), [])
        # identische Gruppe bevorzugen (Inhaltsprüfung möglich), dann ähnliche
        gs = sorted(gs, key=lambda g: g.kind == "similar")
        chosen = None
        for g in gs:
            if g.kind == "similar" and not include_similar:
                continue
            ks = [k for k in g.keepers if k is not f]
            if ks:
                chosen = (g, ks[0])
                break
        if chosen is None:
            items.append(PlanItem(f, f, "", skip=tr('kein behaltenes Original in der Gruppe')))
            continue
        items.append(PlanItem(f, chosen[1], chosen[0].kind))

    if not keep_pairs:
        return items

    finder = PairFinder()
    keepers = {_key(f.path) for g in groups for f in g.keepers}
    in_groups = {_key(f.path) for g in groups for f in g.files}
    base_skip = {id(it): it.skip for it in items}
    # Mehrere Durchläufe, bis stabil: ein übersprungenes Element kann den Partner betreffen
    for _ in range(10):
        archived = {_key(it.dup.path) for it in items if not it.skip}
        changed = False
        for it in items:
            if base_skip[id(it)]:
                continue
            old_state = (it.skip, tuple(it.companions))
            it.skip, it.companions = "", []
            p = finder.partner(it.dup.path)
            if p:
                kp = _key(p)
                if kp in archived:
                    pass                                    # a)
                elif kp in keepers:
                    it.skip = tr('RAW+JPEG-Paar würde getrennt (Partner {0} wird behalten)').format(os.path.basename(p))
                else:
                    keep_partner = finder.partner(it.keep.path)
                    same_type = keep_partner and ((ext_of(keep_partner) in RAW_EXT) == (ext_of(p) in RAW_EXT))
                    if kp not in in_groups and same_type:
                        it.companions = [p]                 # b)
                    else:
                        it.skip = (tr('RAW+JPEG-Paar würde getrennt (Partner {0} hat kein Gegenstück beim Original) – Tipp: dieses Paar als Original wählen').format(os.path.basename(p)))
            if (it.skip, tuple(it.companions)) != old_state:
                changed = True
        if not changed:
            break
    return items
