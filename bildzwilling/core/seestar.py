# SPDX-License-Identifier: GPL-3.0-or-later
"""Seestar-Assistent: Einzelbilder (Subs) ihrem Stack zuordnen und Ausschuss erkennen.

Dateinamen der ZWO Seestar (S50/S30):
  Subs:   <Objekt>_sub/ bzw. <Objekt>-sub/Light_<Objekt>_<Belichtung>s_<Filter>_<JJJJMMTT>-<hhmmss>.fit
          (+ gleichnamige .jpg und _thn.jpg)
  Stacks: <Objekt>/Stacked_[<Anzahl>_]<Objekt>_<Belichtung>s_<Filter>_<JJJJMMTT>-<hhmmss>.fit
Fehlen Angaben im Namen, werden die FITS-Kopfzeilen (OBJECT, EXPTIME, FILTER, DATE-OBS, STACKCNT) genutzt.

Qualitätsmerkmale je Sub (numpy):
  Sterne      Anzahl lokaler Maxima > Hintergrund + 5 σ (Hotpixel ausgeschlossen)
  FWHM        mittlere Sterngröße in Pixeln (Schärfe, Fokus, Seeing)
  Elongation  Verhältnis der Sternachsen (1 = rund; groß = Nachführfehler, Wind, Erschütterung)
  Hintergrund Helligkeit des Himmels (Wolken, Dämmerung, Mond, Licht)
Bewertet wird relativ zum Median derselben Aufnahmesitzung. Es wird nie automatisch etwas verschoben.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import fits
from .formats import ASTRO_EXT, ext_of
from .fsutil import lp
from ..i18n import _ as tr

try:
    import numpy as np

    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False

ALGO = "sq1"
NAME_RE = re.compile(
    r"^(?P<kind>Light|DSO_Stacked|Stacked)(?:_(?P<count>\d+))?_(?P<obj>.+?)_(?P<exp>\d+(?:\.\d+)?)s_"
    r"(?P<filt>[^_]+)_(?P<date>\d{8})-(?P<time>\d{6})", re.IGNORECASE)

# Strenge: Faktoren (wenige Sterne, unscharf, länglich, heller Hintergrund)
STRICTNESS = {
    "locker": dict(stars=0.35, fwhm=1.8, elong=1.45, bg_sigma=5.0),
    "normal": dict(stars=0.5, fwhm=1.5, elong=1.3, bg_sigma=3.5),
    "streng": dict(stars=0.65, fwhm=1.3, elong=1.2, bg_sigma=2.5),
}


@dataclass
class Frame:
    path: str
    is_stack: bool
    obj: str = ""
    exposure: float = 0.0
    filt: str = ""
    time: _dt.datetime | None = None
    count: int = 0                   # nur Stack: Anzahl laut Name/Header
    size: int = 0
    companions: list[str] = field(default_factory=list)   # .jpg, _thn.jpg
    metrics: dict | None = None
    verdict: str = ""                # "ok" | "reject" | "" (nicht analysiert)
    reasons: list[str] = field(default_factory=list)
    stack: "Frame | None" = None
    subs: list["Frame"] = field(default_factory=list)
    action: str = "keep"             # "keep" | "archive" (für Archivierung)

    @property
    def key(self):
        return (re.sub(r"[\s_-]+", " ", self.obj).strip().lower(), round(self.exposure, 2), self.filt.lower())

    @property
    def total_size(self) -> int:
        n = self.size
        for c in self.companions:
            try:
                n += os.path.getsize(lp(c))
            except OSError:
                pass
        return n


def _parse_time(date: str, time: str):
    try:
        return _dt.datetime.strptime(date + time, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _header_time(v: str):
    v = (v or "").strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _listing(folder: str) -> dict[str, str]:
    """Dateinamen eines Ordners: klein geschrieben -> tatsächlicher Name (Windows/macOS: Groß/Klein egal)."""
    try:
        return {n.lower(): n for n in os.listdir(lp(folder))}
    except OSError:
        return {}


def read_frame(path: str, names: dict[str, str] | None = None) -> Frame | None:
    name = os.path.basename(path)
    try:
        hdr, _ = fits.read_header(path)
        naxis = int(hdr.get("NAXIS", "0") or 0)
    except (OSError, fits.FitsError, ValueError):
        return None
    m = NAME_RE.match(name)
    stackcnt = 0
    try:
        stackcnt = int(float(hdr.get("STACKCNT", "0") or 0))
    except ValueError:
        pass
    is_stack = bool(m and "stack" in m.group("kind").lower()) or naxis == 3 or stackcnt > 1
    f = Frame(path, is_stack)
    try:
        f.size = os.path.getsize(lp(path))
    except OSError:
        pass
    if m:
        f.obj = m.group("obj")
        f.exposure = float(m.group("exp"))
        f.filt = m.group("filt")
        f.time = _parse_time(m.group("date"), m.group("time"))
        f.count = int(m.group("count") or 0)
    f.obj = f.obj or hdr.get("OBJECT", "")
    try:
        f.exposure = f.exposure or float(hdr.get("EXPTIME", hdr.get("EXPOSURE", "0")) or 0)
    except ValueError:
        pass
    f.filt = f.filt or hdr.get("FILTER", "")
    f.time = f.time or _header_time(hdr.get("DATE-OBS", ""))
    f.count = f.count or stackcnt
    # Begleitdateien der Seestar: <name>.jpg und <name>_thn.jpg – Schreibweise egal, jede Datei nur einmal
    folder = os.path.dirname(path)
    if names is None:
        names = _listing(folder)
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    seen = set()
    for suffix in (".jpg", ".jpeg", "_thn.jpg", "_thn.jpeg"):
        real = names.get(stem + suffix)
        if real and real.lower() not in seen:
            seen.add(real.lower())
            f.companions.append(os.path.join(folder, real))
    return f


def find_frames(folder: str, cancel=None) -> list[Frame]:
    frames = []
    for dirpath, dirnames, filenames in os.walk(lp(folder)):
        if cancel is not None and cancel.is_set():
            break
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "_BildZwilling"))]
        names = {n.lower(): n for n in filenames}
        for n in filenames:
            if ext_of(n) in ASTRO_EXT:
                fr = read_frame(os.path.join(dirpath, n), names)
                if fr is not None:
                    frames.append(fr)
    return frames


# --------------------------------------------------------------------------- Qualität

def _shift_max(a, r: int):
    out = a.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy or dx:
                np.maximum(out, np.roll(np.roll(a, dy, 0), dx, 1), out=out)
    return out


def analyze(path: str) -> dict:
    """Qualitätsmerkmale eines Einzelbilds."""
    if not HAVE_NUMPY:
        raise RuntimeError(tr('numpy fehlt'))
    hdr, a = fits.load_array(path)
    scale = 1
    if a.ndim == 3:
        lum = a.mean(axis=0)
        full = lum
    elif hdr.get("BAYERPAT", "").strip() and a.shape[0] >= 4 and a.shape[1] >= 4:
        h, w = (a.shape[0] // 2) * 2, (a.shape[1] // 2) * 2
        full = a[:h, :w]
        lum = full[0::2, 0::2] + full[0::2, 1::2] + full[1::2, 0::2] + full[1::2, 1::2]  # 2×2-Binning
        scale = 2
    else:
        lum = full = a
    lum = lum.astype(np.float32)
    sample = lum[::4, ::4]
    bg = float(np.median(sample))
    noise = float(np.median(np.abs(sample - bg)) * 1.4826) or 1.0
    thr = bg + 5 * noise
    peaks = (lum >= _shift_max(lum, 2)) & (lum > thr)
    # Hotpixel ausschließen: mindestens 3 Nachbarn über bg + 3σ
    above = (lum > bg + 3 * noise).astype(np.int8)
    neigh = sum(np.roll(np.roll(above, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)) - above
    peaks &= neigh >= 3
    b = 8
    peaks[:b, :] = False
    peaks[-b:, :] = False
    peaks[:, :b] = False
    peaks[:, -b:] = False
    ys, xs = np.nonzero(peaks)
    stars = int(len(ys))
    fwhm = elong = 0.0
    if stars:
        # Form in voller Auflösung messen (Bayer: Mosaik direkt, Sterne sind nahezu farbneutral)
        fsample = full[::4, ::4]
        fbg = float(np.median(fsample))
        fnoise = float(np.median(np.abs(fsample - fbg)) * 1.4826) or 1.0
        vmax = float(full.max())
        order = np.argsort(lum[ys, xs])[::-1]
        fw, el = [], []
        r = 7
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        for i in order[:300]:
            y0, x0 = int(ys[i]) * scale, int(xs[i]) * scale
            win0 = full[max(0, y0 - 2):y0 + 4, max(0, x0 - 2):x0 + 4]
            if win0.size == 0:
                continue
            dy, dx = np.unravel_index(int(np.argmax(win0)), win0.shape)
            y, x = max(0, y0 - 2) + dy, max(0, x0 - 2) + dx
            if full[y, x] > 0.95 * vmax:
                continue  # gesättigt
            win = full[y - r:y + r + 1, x - r:x + r + 1] - fbg
            if win.shape != yy.shape:
                continue
            win = np.where(win > 3 * fnoise, win, 0.0)
            m = float(win.sum())
            if m <= 0 or np.count_nonzero(win) < 4:
                continue
            cx, cy = float((win * xx).sum() / m), float((win * yy).sum() / m)
            sxx = float((win * (xx - cx) ** 2).sum() / m)
            syy = float((win * (yy - cy) ** 2).sum() / m)
            sxy = float((win * (xx - cx) * (yy - cy)).sum() / m)
            trace, det = sxx + syy, sxx * syy - sxy * sxy
            disc = max(0.0, trace * trace / 4 - det)
            l1, l2 = trace / 2 + disc ** 0.5, max(1e-6, trace / 2 - disc ** 0.5)
            fw.append(2.3548 * ((l1 + l2) / 2) ** 0.5)
            el.append((l1 / l2) ** 0.5)
            if len(fw) >= 40:
                break
        if fw:
            fwhm, elong = float(np.median(fw)), float(np.median(el))
    return {"stars": stars, "fwhm": round(fwhm, 2), "elong": round(elong, 2), "bg": round(bg, 1),
            "noise": round(noise, 2)}


def analyze_all(frames: list[Frame], cache=None, workers: int = 4, progress=None, cancel=None) -> None:
    subs = [f for f in frames if not f.is_stack]

    def one(f: Frame):
        key = os.path.normcase(f.path)
        try:
            st = os.stat(lp(f.path))
        except OSError:
            return None
        if cache is not None:
            d = cache.get(key, ALGO, st.st_size, st.st_mtime_ns)
            if d:
                return json.loads(d)
        m = analyze(f.path)
        if cache is not None:
            cache.put(key, ALGO, st.st_size, st.st_mtime_ns, json.dumps(m))
        return m

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(one, f): f for f in subs}
        for n, fut in enumerate(futs, 1):
            if cancel is not None and cancel.is_set():
                for x in futs:
                    x.cancel()
                break
            try:
                futs[fut].metrics = fut.result()
            except Exception as e:  # noqa: BLE001
                futs[fut].metrics = None
                futs[fut].reasons = [f"nicht lesbar: {e}"]
            if progress:
                progress("Seestar: Einzelbilder analysieren", n, len(subs))


# --------------------------------------------------------------------------- Zuordnung & Bewertung

def sessions_of(subs: list[Frame]) -> list[list[Frame]]:
    """Subs gleicher Aufnahme (Objekt, Belichtung, Filter) in Sitzungen teilen (Lücke > 30 min)."""
    groups: dict[tuple, list[Frame]] = {}
    for f in subs:
        groups.setdefault(f.key, []).append(f)
    out = []
    for lst in groups.values():
        lst.sort(key=lambda f: f.time or _dt.datetime.min)
        cur = [lst[0]]
        for f in lst[1:]:
            gap = max(_dt.timedelta(minutes=30), _dt.timedelta(seconds=20 * (f.exposure or 10)))
            if f.time and cur[-1].time and f.time - cur[-1].time > gap:
                out.append(cur)
                cur = [f]
            else:
                cur.append(f)
        out.append(cur)
    return out


def assign(frames: list[Frame]) -> list[list[Frame]]:
    """Ordnet jede Sitzung dem passenden Stack zu (gleiche Aufnahme, zeitlich nächster)."""
    stacks = [f for f in frames if f.is_stack]
    subs = [f for f in frames if not f.is_stack]
    for s in stacks:
        s.subs = []
    for f in subs:
        f.stack = None
    sess = sessions_of(subs) if subs else []
    for ses in sess:
        start = ses[0].time
        end = ses[-1].time
        cands = [s for s in stacks if s.key == ses[0].key]
        if not cands:
            continue

        def dist(s):
            if not (s.time and start and end):
                return 0
            if start - _dt.timedelta(minutes=10) <= s.time <= end + _dt.timedelta(hours=2):
                return 0 if s.time >= end - _dt.timedelta(minutes=5) else 1
            return 2 + abs((s.time - end).total_seconds())

        best = min(cands, key=lambda s: (dist(s), -(s.time.timestamp() if s.time else 0)))
        if dist(best) <= 2 + 6 * 3600:
            best.subs.extend(ses)
            for f in ses:
                f.stack = best
    return sess


def evaluate(sessions: list[list[Frame]], strictness: str = "normal") -> None:
    k = STRICTNESS.get(strictness, STRICTNESS["normal"])
    for ses in sessions:
        ms = [f.metrics for f in ses if f.metrics]
        rel = len(ms) >= 5
        if ms:
            med_stars = float(np.median([m["stars"] for m in ms]))
            fws = [m["fwhm"] for m in ms if m["fwhm"] > 0]
            med_fwhm = float(np.median(fws)) if fws else 0.0
            els = [m["elong"] for m in ms if m["elong"] > 0]
            med_el = float(np.median(els)) if els else 1.0
            bgs = np.array([m["bg"] for m in ms])
            med_bg = float(np.median(bgs))
            mad_bg = float(np.median(np.abs(bgs - med_bg)) * 1.4826)
            med_noise = float(np.median([m["noise"] for m in ms])) or 1.0
        for f in ses:
            m = f.metrics
            if not m:
                f.verdict = "reject" if f.reasons else ""
                continue
            reasons = []
            if m["stars"] == 0:
                reasons.append(tr('keine Sterne'))
            elif rel and m["stars"] < k["stars"] * med_stars:
                reasons.append(tr('wenige Sterne ({0} statt ~{1:.0f}) – Wolken/Dunst?').format(m['stars'], med_stars))
            elif not rel and m["stars"] < 5:
                reasons.append(tr('kaum Sterne'))
            if rel and med_fwhm and m["fwhm"] > k["fwhm"] * med_fwhm:
                reasons.append(tr('unscharf (FWHM {0:.1f} statt ~{1:.1f} px)').format(m['fwhm'], med_fwhm))
            if m["elong"] > max(k["elong"] * (med_el if rel else 1.0), 1.25 if rel else 1.8):
                reasons.append(tr('längliche Sterne ({0:.2f}) – Nachführfehler/Wind?').format(m['elong']))
            if rel and m["bg"] > med_bg + max(k["bg_sigma"] * mad_bg, 3 * med_noise):
                reasons.append(tr('heller Hintergrund – Wolken/Dämmerung/Licht?'))
            f.reasons = reasons
            f.verdict = "reject" if reasons else "ok"
            f.action = "archive" if reasons else "keep"


def run(folder: str, cache=None, strictness: str = "normal", workers: int = 4, progress=None, cancel=None):
    """Kompletter Ablauf. Liefert (Stacks, nicht zugeordnete Subs, alle Frames)."""
    frames = find_frames(folder, cancel)
    analyze_all(frames, cache, workers, progress, cancel)
    sessions = assign(frames)
    evaluate(sessions, strictness)
    stacks = sorted([f for f in frames if f.is_stack], key=lambda f: (f.obj.lower(), f.time or _dt.datetime.min))
    orphans = [f for f in frames if not f.is_stack and f.stack is None]
    return stacks, orphans, frames
