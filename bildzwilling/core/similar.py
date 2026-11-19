# SPDX-License-Identifier: GPL-3.0-or-later
"""Ähnliche Bilder (dHash, 64 Bit) – z. B. verkleinerte Kopien, WhatsApp-Versionen, Serienbilder.

Ähnliche Bilder sind NICHT identisch. Sie werden deshalb als eigene Kategorie angezeigt und
nie automatisch zum Archivieren markiert – die Entscheidung trifft immer der Benutzer.
"""

from __future__ import annotations

from .formats import is_fits, is_raw
from .fsutil import lp

try:
    from PIL import Image, ImageOps, ImageStat

    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

ALGO = "dh3"
MIN_CONTRAST = 3.0      # nahezu einfarbige Bilder (z. B. schwarz) nicht vergleichen
MAX_ASPECT_DIFF = 0.04  # Seitenverhältnis muss ±4 % übereinstimmen


def dhash(path: str):
    """(hash:int, breite, höhe) oder None. Ausrichtung laut EXIF wird berücksichtigt."""
    if not HAVE_PIL:
        return None
    try:
        if is_fits(path):
            from . import fits

            im, _ = fits.preview(path, 256)
            size = fits.image_size(path) or im.size
        elif is_raw(path):
            from . import imaging

            im, _ = imaging._raw_preview(path, 256)  # eingebettete Vorschau, schnell
            size = imaging.image_size(path) or im.size
            im = ImageOps.exif_transpose(im) or im
        else:
            with Image.open(lp(path)) as src:
                size = src.size
                try:
                    src.seek(0)
                except EOFError:
                    pass
                src.draft("RGB", (128, 128))  # JPEG: schnelles Herunterskalieren beim Dekodieren
                im = ImageOps.exif_transpose(src) or src
                im = im.convert("L")
                im.load()
        g0 = im.convert("L")
        g0.thumbnail((128, 128))
        if ImageStat.Stat(g0.resize((9, 8), Image.Resampling.LANCZOS)).stddev[0] < MIN_CONTRAST:
            return None
        variants = tuple(_hash(g0 if t is None else g0.transpose(t)) for t in TRANSFORMS)
        # bei 90°-Drehung (EXIF) Maße tauschen, damit sie zur Anzeige passen
        w, ht = size
        if (im.size[0] > im.size[1]) != (w > ht) and w != ht:
            w, ht = ht, w
        return variants, int(w), int(ht)
    except Exception:  # noqa: BLE001
        return None


# Reihenfolge: Original, 90°, 180°, 270°, horizontal gespiegelt, vertikal gespiegelt, transponiert, transversal
if HAVE_PIL:
    T = Image.Transpose
    TRANSFORMS: tuple = (None, T.ROTATE_90, T.ROTATE_180, T.ROTATE_270, T.FLIP_LEFT_RIGHT, T.FLIP_TOP_BOTTOM,
                         T.TRANSPOSE, T.TRANSVERSE)
else:
    TRANSFORMS = (None,)
SWAPS_ASPECT = {1, 3, 6, 7}


def _hash(g) -> int:
    px = list(g.resize((9, 8), Image.Resampling.LANCZOS).tobytes())
    h = 0
    for row in range(8):
        for col in range(8):
            h = (h << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return h


def encode(r) -> str:
    variants, w, h = r
    return ",".join(f"{v:016x}" for v in variants) + f"|{w}|{h}"


def decode(d: str):
    v, w, h = d.split("|")
    return tuple(int(x, 16) for x in v.split(",")), int(w), int(h)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class BKTree:
    """Burkhard-Keller-Baum für schnelle Suche nach Hashes mit kleinem Hamming-Abstand."""

    def __init__(self):
        self.root = None

    def add(self, h: int) -> None:
        if self.root is None:
            self.root = [h, {}]
            return
        node = self.root
        while True:
            d = hamming(h, node[0])
            if d == 0:
                return
            nxt = node[1].get(d)
            if nxt is None:
                node[1][d] = [h, {}]
                return
            node = nxt

    def query(self, h: int, t: int) -> list[int]:
        out = []
        if self.root is None:
            return out
        stack = [self.root]
        while stack:
            node = stack.pop()
            d = hamming(h, node[0])
            if d <= t:
                out.append(node[0])
            for k, child in node[1].items():
                if d - t <= k <= d + t:
                    stack.append(child)
        return out


def _aspect_ok(a, b, swapped: bool = False) -> bool:
    if not a.dims or not b.dims or not a.dims[1] or not b.dims[1] or not a.dims[0] or not b.dims[0]:
        return True
    ra, rb = a.dims[0] / a.dims[1], b.dims[0] / b.dims[1]
    if swapped:
        ra = 1 / ra
    return abs(ra - rb) / max(ra, rb) <= MAX_ASPECT_DIFF


def quality_key(f):
    w, h = f.dims or (0, 0)
    score = f.rating.score() if getattr(f, "rating", None) is not None else 0
    return (-score, -(w * h), -f.size, f.root_index, f.mtime_ns, f.path.lower())


def build_groups(items, threshold: int, cancel=None, rotations: bool = True):
    """items: FileEntry mit .dhash/.dvariants/.dims.

    Liefert (Dateien, größter Abstand, gedreht/gespiegelt beteiligt) je Gruppe (>= 2 Dateien).
    """
    by_hash: dict[int, list] = {}
    for f in items:
        if f.dhash is not None:
            by_hash.setdefault(f.dhash, []).append(f)
    tree = BKTree()
    for h in by_hash:
        tree.add(h)
    parent: dict[int, int] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    files = [f for lst in by_hash.values() for f in lst]
    idx = {id(f): i for i, f in enumerate(files)}
    dist: dict[tuple, int] = {}
    flagged: set[int] = set()
    for n, a in enumerate(files):
        if cancel is not None and n % 500 == 0 and cancel.is_set():
            return []
        variants = a.dvariants if (rotations and a.dvariants) else (a.dhash,)
        for k, hv in enumerate(variants):
            for h2 in tree.query(hv, threshold):
                for b in by_hash[h2]:
                    if a is b or not _aspect_ok(a, b, k in SWAPS_ASPECT):
                        continue
                    d = hamming(hv, h2)
                    key = (min(id(a), id(b)), max(id(a), id(b)))
                    if d < dist.get(key, 99):
                        dist[key] = d
                    if k:
                        flagged.update((id(a), id(b)))
                    ra, rb = find(idx[id(a)]), find(idx[id(b)])
                    if ra != rb:
                        parent[rb] = ra
    comps: dict[int, list] = {}
    for i, f in enumerate(files):
        comps.setdefault(find(i), []).append(f)
    out = []
    for lst in comps.values():
        if len(lst) >= 2:
            lst.sort(key=quality_key)
            first = lst[0]
            dmax = 0
            for f in lst[1:]:
                key = (min(id(first), id(f)), max(id(first), id(f)))
                dmax = max(dmax, dist.get(key, threshold))
            out.append((lst, dmax, any(id(f) in flagged for f in lst)))
    return out
