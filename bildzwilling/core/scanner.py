# SPDX-License-Identifier: GPL-3.0-or-later
"""Duplikatsuche.

Ablauf (Modus "Byte-identisch"):
  1. Ordner rekursiv einlesen (Symlinks/Junctions werden nicht verfolgt, Schleifen erkannt)
  2. Nach Dateigröße gruppieren – nur gleich große Dateien können identisch sein
  3. Vorprüfung: Prüfsumme über Anfang + Ende (je 64 KB)
  4. Vollständige BLAKE2b-256-Prüfsumme (mit Cache)
Zusätzlich im Modus "Bildinhalt (Pixel)":
  5. Bildmaße lesen, gleich große Bilder dekodieren und Pixel-Prüfsumme bilden
     -> findet dasselbe Bild mit anderen Metadaten / anderem Container.
Vor dem Verschieben wird jede Datei nochmals direkt verglichen (siehe archive.py).
"""

from __future__ import annotations

from typing import Any

import hashlib
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import imaging, ratings, rules, similar
from .formats import EXCLUDED_DIR_NAMES, is_image, is_previewable, is_video
from .fsutil import is_cloud_placeholder, is_hidden, is_within, lp, norm, unlp
from ..i18n import _ as tr

BYTE_ALGO = "b2b256"
DIM_ALGO = "dim1"
PARTIAL = 64 * 1024
CHUNK = 1024 * 1024


class ScanCancelled(Exception):
    pass


@dataclass
class FileEntry:
    path: str
    size: int
    mtime_ns: int
    root: str
    root_index: int
    placeholder: bool = False
    digest: str | None = None     # Byte-Prüfsumme
    pdigest: str | None = None    # Pixel-Prüfsumme
    action: str = "archive"       # "keep" | "archive"
    dims: tuple | None = None     # (Breite, Höhe), wenn bekannt
    dhash: int | None = None      # Ähnlichkeits-Hash
    dvariants: tuple = ()         # Hashes der 8 Drehungen/Spiegelungen
    rating: object = None         # ratings.Rating

    @property
    def mtime(self) -> float:
        return self.mtime_ns / 1e9


@dataclass
class DuplicateGroup:
    gid: int
    kind: str                     # "bytes" | "pixels" | "similar"
    files: list[FileEntry] = field(default_factory=list)
    distance: int = 0             # nur "similar": größter Hamming-Abstand zum besten Bild
    transformed: bool = False     # nur "similar": gedrehte/gespiegelte Kopie beteiligt

    @property
    def keepers(self) -> list[FileEntry]:
        return [f for f in self.files if f.action == "keep"]

    @property
    def to_archive(self) -> list[FileEntry]:
        return [f for f in self.files if f.action == "archive"]

    @property
    def savable(self) -> int:
        return sum(f.size for f in self.to_archive)


@dataclass
class ScanOptions:
    roots: list[str]
    archive_dir: str = ""
    mode: str = "bytes"
    images_only: bool = True
    include_hidden: bool = False
    include_placeholders: bool = False
    min_size: int = 1024
    keep_rule: str = "first_root"
    workers: int = 4
    include_videos: bool = False
    similar: bool = False
    similar_threshold: int = 6
    folder_rules: list = field(default_factory=list)
    rotations: bool = True        # ähnliche Bilder auch gedreht/gespiegelt
    use_ratings: bool = True      # Bewertungen (XMP/Lightroom) berücksichtigen
    lrcat: str = ""               # Lightroom-Katalog (optional)


@dataclass
class ScanResult:
    groups: list[DuplicateGroup]
    errors: list[str]
    stats: dict
    similar_items: list = field(default_factory=list)  # Kandidaten für Neugruppierung per Regler


def validate_options(opts: ScanOptions) -> list[str]:
    """Liefert Fehlermeldungen (leer = alles in Ordnung)."""
    problems = []
    if not opts.roots:
        problems.append(tr('Bitte mindestens einen Bildordner hinzufügen.'))
    for r in opts.roots:
        if not os.path.isdir(lp(r)):
            problems.append(tr('Ordner nicht erreichbar: {0}').format(r))
    if opts.archive_dir:
        for r in opts.roots:
            if is_within(r, opts.archive_dir):
                problems.append(tr('Der Bildordner liegt im Archivordner: {0}').format(r))
    return problems


def sort_key(rule: str):
    if rule == "oldest":
        return lambda f: (f.mtime_ns, f.root_index, len(f.path), f.path.lower())
    if rule == "newest":
        return lambda f: (-f.mtime_ns, f.root_index, len(f.path), f.path.lower())
    if rule == "shortest_path":
        return lambda f: (len(f.path), f.root_index, f.mtime_ns, f.path.lower())
    return lambda f: (f.root_index, f.mtime_ns, len(f.path), f.path.lower())


def apply_keep_rule(group: DuplicateGroup, rule: str, folder_rules=()) -> None:
    """Original festlegen. Ähnliche Bilder werden nie automatisch zum Archivieren markiert."""
    if group.kind == "similar":
        group.files.sort(key=similar.quality_key)
        for f in group.files:
            f.action = "keep"
        return
    base = sort_key(rule)
    rank = {"keep": 0, None: 1, "archive": 2}
    dec = {id(f): rules.decide(f.path, folder_rules) for f in group.files}
    group.files.sort(key=lambda f: (rank[dec[id(f)]], -_rscore(f)) + tuple(base(f)))
    for i, f in enumerate(group.files):
        f.action = "keep" if (i == 0 or dec[id(f)] == "keep") else "archive"


def _rscore(f) -> int:
    return f.rating.score() if f.rating is not None else 0


def similar_groups(items, threshold: int, start_gid: int = 1, cancel=None,
                   rotations: bool = True) -> list[DuplicateGroup]:
    out = []
    for n, (lst, dist, transformed) in enumerate(similar.build_groups(items, threshold, cancel, rotations)):
        g = DuplicateGroup(start_gid + n, "similar", lst, dist, transformed)
        apply_keep_rule(g, "")
        out.append(g)
    return out


def hash_file(path: str, cancel=None) -> str:
    h = hashlib.blake2b(digest_size=32)
    with open(lp(path), "rb") as fh:
        while True:
            if cancel is not None and cancel.is_set():
                raise ScanCancelled()
            b = fh.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def partial_hash(path: str, size: int) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode())
    with open(lp(path), "rb") as fh:
        h.update(fh.read(PARTIAL))
        if size > 2 * PARTIAL:
            fh.seek(-PARTIAL, os.SEEK_END)
            h.update(fh.read(PARTIAL))
    return h.hexdigest()


class Scanner:
    def __init__(self, opts: ScanOptions, cache, progress=None, log=None, cancel=None):
        self.o = opts
        self.cache = cache
        self.progress = progress or (lambda phase, done, total: None)
        self.log = log or (lambda level, msg: None)
        self.cancel = cancel
        self.errors: list[str] = []
        self.stats: dict[str, Any] = {"files": 0, "bytes": 0, "placeholders_skipped": 0, "dirs": 0}

    # ------------------------------------------------------------------ helpers
    def _check(self):
        if self.cancel is not None and self.cancel.is_set():
            raise ScanCancelled()

    def _err(self, msg: str):
        self.errors.append(msg)
        if len(self.errors) <= 200:
            self.log("warn", msg)

    # ------------------------------------------------------------------ 1. einlesen
    def walk(self) -> list[FileEntry]:
        excluded = [norm(self.o.archive_dir)] if self.o.archive_dir else []
        seen_dirs: set = set()
        seen_files: set = set()
        files: list[FileEntry] = []
        last = time.monotonic()
        for ri, root in enumerate(self.o.roots):
            root = os.path.abspath(root)
            stack = [root]
            while stack:
                self._check()
                d = stack.pop()
                try:
                    st = os.stat(lp(d))
                    key = (st.st_dev, st.st_ino)
                    if st.st_ino and key in seen_dirs:
                        continue  # Schleife oder überlappende Quellordner
                    seen_dirs.add(key)
                    with os.scandir(lp(d)) as it:
                        entries = list(it)
                except OSError as e:
                    self._err(tr('Ordner nicht lesbar: {0} ({1})').format(d, e.strerror or e))
                    continue
                self.stats["dirs"] += 1
                for e in entries:
                    try:
                        if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                            continue
                        if e.is_dir(follow_symlinks=False):
                            if e.name.lower() in EXCLUDED_DIR_NAMES:
                                continue
                            p = unlp(e.path)
                            if not self.o.include_hidden and is_hidden(e.name, e.stat(follow_symlinks=False)):
                                continue
                            if excluded and norm(p) in excluded:
                                continue
                            stack.append(p)
                        elif e.is_file(follow_symlinks=False):
                            if self.o.images_only and not (is_image(e.name) or
                                                           (self.o.include_videos and is_video(e.name))):
                                continue
                            st = e.stat(follow_symlinks=False)
                            if not self.o.include_hidden and is_hidden(e.name, st):
                                continue
                            if st.st_size < self.o.min_size:
                                continue
                            ph = is_cloud_placeholder(st)
                            if ph and not self.o.include_placeholders:
                                self.stats["placeholders_skipped"] += 1
                                continue
                            p = unlp(e.path)
                            k = os.path.normcase(p)
                            if k in seen_files:
                                continue
                            seen_files.add(k)
                            files.append(FileEntry(p, st.st_size, st.st_mtime_ns, root, ri, ph))
                    except OSError as ex:
                        self._err(tr('Nicht lesbar: {0} ({1})').format(e.path, ex.strerror or ex))
                now = time.monotonic()
                if now - last > 0.25:
                    self.progress("Ordner werden eingelesen", len(files), 0)
                    last = now
        self.stats["files"] = len(files)
        self.stats["bytes"] = sum(f.size for f in files)
        self.log("info", f"{len(files):,} Dateien in {self.stats['dirs']:,} Ordnern gefunden.".replace(",", "."))
        if self.stats["placeholders_skipped"]:
            self.log("warn", tr('{0} Nur-Online-Dateien (Cloud) übersprungen.').format(self.stats['placeholders_skipped']))
        return files

    # ------------------------------------------------------------------ 2.–4. Bytes
    def _parallel(self, items, fn, phase, weight=lambda x: 1):
        """fn(item) parallel ausführen; liefert {item_index: ergebnis} (Fehler -> fehlt)."""
        out = {}
        total = sum(weight(i) for i in items) or 1
        done = 0
        last = 0.0
        with ThreadPoolExecutor(max_workers=max(1, int(self.o.workers))) as ex:
            futs = {ex.submit(fn, it): idx for idx, it in enumerate(items)}
            try:
                for fut in as_completed(futs):
                    idx = futs[fut]
                    item = items[idx]
                    try:
                        out[idx] = fut.result()
                    except ScanCancelled:
                        raise
                    except OSError as e:
                        self._err(tr('Lesefehler: {0} ({1})').format(getattr(item, 'path', item), e.strerror or e))
                    except Exception as e:  # noqa: BLE001
                        self._err(tr('Fehler: {0} ({1})').format(getattr(item, 'path', item), e))
                    done += weight(item)
                    now = time.monotonic()
                    if now - last > 0.2:
                        self.progress(phase, done, total)
                        last = now
                    self._check()
            except ScanCancelled:
                for f in futs:
                    f.cancel()
                raise
        self.progress(phase, total, total)
        return out

    def _full_digest(self, f: FileEntry) -> str:
        key = os.path.normcase(f.path)
        d = self.cache.get(key, BYTE_ALGO, f.size, f.mtime_ns)
        if d:
            return d
        d = hash_file(f.path, self.cancel)
        self.cache.put(key, BYTE_ALGO, f.size, f.mtime_ns, d)
        return d

    def byte_groups(self, files: list[FileEntry]) -> list[list[FileEntry]]:
        by_size = defaultdict(list)
        for f in files:
            by_size[f.size].append(f)
        cand = [f for lst in by_size.values() if len(lst) > 1 for f in lst]
        self.log("info", f"{len(cand):,} Dateien mit gleicher Größe – Vorprüfung …".replace(",", "."))
        if not cand:
            return []

        res = self._parallel(cand, lambda f: partial_hash(f.path, f.size), "Vorprüfung (Anfang/Ende)")
        by_part = defaultdict(list)
        for idx, ph in res.items():
            by_part[(cand[idx].size, ph)].append(cand[idx])
        cand2 = [f for lst in by_part.values() if len(lst) > 1 for f in lst]
        self.log("info", f"{len(cand2):,} Kandidaten – vollständige Prüfsummen …".replace(",", "."))
        if not cand2:
            return []

        res = self._parallel(cand2, self._full_digest, "Prüfsummen (BLAKE2b)",
                             weight=lambda f: max(1, f.size // CHUNK))
        by_full = defaultdict(list)
        for idx, dg in res.items():
            cand2[idx].digest = dg
            by_full[dg].append(cand2[idx])
        return [lst for lst in by_full.values() if len(lst) > 1]

    # ------------------------------------------------------------------ 5. Pixel
    def _dims(self, f: FileEntry):
        key = os.path.normcase(f.path)
        d = self.cache.get(key, DIM_ALGO, f.size, f.mtime_ns)
        if d:
            return d
        s = imaging.image_size(f.path)
        d = f"{s[0]}x{s[1]}" if s else "?"
        self.cache.put(key, DIM_ALGO, f.size, f.mtime_ns, d)
        return d

    def _pix(self, f: FileEntry):
        key = os.path.normcase(f.path)
        d = self.cache.get(key, imaging.PIXEL_ALGO, f.size, f.mtime_ns)
        if d:
            return d
        d = imaging.pixel_digest(f.path, self.cancel)
        self._check()
        if d:
            self.cache.put(key, imaging.PIXEL_ALGO, f.size, f.mtime_ns, d)
        return d

    def pixel_groups(self, files: list[FileEntry]) -> list[list[FileEntry]]:
        cand = [f for f in files if is_previewable(f.path)]
        if not cand:
            return []
        res = self._parallel(cand, self._dims, "Bildmaße lesen")
        by_dim = defaultdict(list)
        for idx, dim in res.items():
            if dim and dim != "?":
                by_dim[dim].append(cand[idx])
        cand2 = [f for lst in by_dim.values() if len(lst) > 1 for f in lst]
        self.log("info", f"{len(cand2):,} Bilder mit gleichen Maßen – Bildinhalt wird verglichen …".replace(",", "."))
        if not cand2:
            return []
        res = self._parallel(cand2, self._pix, "Bildinhalt (Pixel) vergleichen",
                             weight=lambda f: max(1, f.size // CHUNK))
        by_pix = defaultdict(list)
        for idx, pd in res.items():
            if pd:
                cand2[idx].pdigest = pd
                by_pix[pd].append(cand2[idx])
        return [lst for lst in by_pix.values() if len(lst) > 1]

    # ------------------------------------------------------------------ Bewertungen
    def load_ratings(self, files: list[FileEntry]) -> None:
        if not files:
            return
        cat = ratings.open_catalog(self.o.lrcat) if self.o.lrcat else None
        if self.o.lrcat and cat is None:
            self._err(tr('Lightroom-Katalog nicht lesbar: {0}').format(self.o.lrcat))
        res = self._parallel(files, lambda f: ratings.rating_for(f.path, cat), "Bewertungen lesen")
        n = 0
        for idx, r in res.items():
            files[idx].rating = r
            n += 0 if r.empty else 1
        if n:
            self.log("info", tr('{0} bewertete/markierte Dateien berücksichtigt.').format(n))

    # ------------------------------------------------------------------ 6. ähnlich
    def _dh(self, f: FileEntry):
        key = os.path.normcase(f.path)
        d = self.cache.get(key, similar.ALGO, f.size, f.mtime_ns)
        if d is None:
            r = similar.dhash(f.path)
            d = similar.encode(r) if r else "-"
            self.cache.put(key, similar.ALGO, f.size, f.mtime_ns, d)
        self._check()
        if d == "-":
            return None
        return similar.decode(d)

    def similar_candidates(self, files: list[FileEntry], groups) -> list[FileEntry]:
        """Ein Vertreter je identischer Gruppe (das Original) + alle übrigen Bilder."""
        in_group = {id(f) for g in groups for f in g.files}
        reps = [g.files[0] for g in groups]
        cand = [f for f in files if id(f) not in in_group and is_previewable(f.path)]
        cand += [f for f in reps if is_previewable(f.path)]
        if not cand:
            return []
        res = self._parallel(cand, self._dh, "Ähnlichkeit berechnen")
        out = []
        for idx, r in res.items():
            if r:
                f = cand[idx]
                f.dvariants, f.dims = r[0], (r[1], r[2])
                f.dhash = f.dvariants[0]
                out.append(f)
        return out

    # ------------------------------------------------------------------ gesamt
    def run(self) -> ScanResult:
        t0 = time.monotonic()
        files = self.walk()
        groups_raw = self.byte_groups(files)
        if self.o.mode == "pixels":
            groups_raw += self.pixel_groups(files)

        # Union-Find: Byte- und Pixelgruppen zusammenführen
        parent: dict[int, int] = {}

        def find(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        by_id = {}
        for lst in groups_raw:
            first = id(lst[0])
            for f in lst:
                by_id[id(f)] = f
                ra, rb = find(first), find(id(f))
                if ra != rb:
                    parent[rb] = ra
        comps = defaultdict(list)
        for fid, f in by_id.items():
            comps[find(fid)].append(f)

        if self.o.use_ratings and comps:
            self.load_ratings([f for lst in comps.values() if len(lst) > 1 for f in lst])
        groups = []
        for lst in comps.values():
            if len(lst) < 2:
                continue
            digests = {f.digest for f in lst}
            kind = "bytes" if (len(digests) == 1 and None not in digests) else "pixels"
            g = DuplicateGroup(0, kind, lst)
            apply_keep_rule(g, self.o.keep_rule, self.o.folder_rules)
            groups.append(g)
        groups.sort(key=lambda g: (-g.savable, g.files[0].path.lower()))
        for i, g in enumerate(groups, 1):
            g.gid = i

        sim_items = []
        if self.o.similar:
            sim_items = self.similar_candidates(files, groups)
            if self.o.use_ratings:
                self.load_ratings([f for f in sim_items if f.rating is None])
            sim = similar_groups(sim_items, self.o.similar_threshold, len(groups) + 1, self.cancel,
                                 self.o.rotations)
            self._check()
            self.log("info", tr('{0} Gruppen ähnlicher Bilder (Abstand ≤ {1}).').format(len(sim), self.o.similar_threshold))
            groups += sim

        try:
            self.cache.commit()
        except Exception:  # noqa: BLE001
            pass
        self.stats["duration"] = time.monotonic() - t0
        exact = [g for g in groups if g.kind != "similar"]
        self.stats["groups"] = len(exact)
        self.stats["similar_groups"] = len(groups) - len(exact)
        self.stats["duplicates"] = sum(len(g.files) - 1 for g in exact)
        self.stats["savable"] = sum(g.savable for g in exact)
        return ScanResult(groups, self.errors, self.stats, sim_items)
