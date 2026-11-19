# SPDX-License-Identifier: GPL-3.0-or-later
"""FITS-Dateien von Smart-Teleskopen (ZWO Seestar S50/S30, DWARFLAB DWARF u. a.).

- Einzelbilder (Subs): 2D, 16 Bit, Bayer-Mosaik (Kopfzeile BAYERPAT, z. B. GRBG/RGGB)
- Gestapelte Bilder: 3 Ebenen (RGB), bereits entbayert – BAYERPAT wird dann ignoriert
Vorschau: Superpixel-Entbayerung + automatischer Stretch (Astrobilder sind linear und dunkel).
Für die Pixel-Prüfsumme werden nur die Bilddaten verwendet (unabhängig vom Header).
Benötigt numpy; ohne numpy bleibt der Byte-Vergleich voll funktionsfähig.
"""

from __future__ import annotations

import hashlib

from .fsutil import lp
from ..i18n import _ as tr

try:
    import numpy as np

    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False

BLOCK = 2880
_DTYPES = {8: ">u1", 16: ">i2", 32: ">i4", 64: ">i8", -32: ">f4", -64: ">f8"}

# Wichtige Kopfzeilen zuerst
PRIORITY = ["OBJECT", "DATE-OBS", "EXPTIME", "EXPOSURE", "STACKCNT", "TOTALEXP", "GAIN", "OFFSET",
            "CCD-TEMP", "FILTER", "INSTRUME", "TELESCOP", "FOCALLEN", "APERTURE", "XPIXSZ", "YPIXSZ",
            "XBINNING", "BAYERPAT", "RA", "DEC", "OBJCTRA", "OBJCTDEC", "SITELAT", "SITELONG", "CREATOR"]


class FitsError(Exception):
    pass


def read_header(path: str, max_blocks: int = 40):
    """(header-dict in Reihenfolge, Datenoffset). Nur primäre HDU."""
    hdr: dict[str, str] = {}
    with open(lp(path), "rb") as f:
        first = f.read(BLOCK)
        if not first.startswith(b"SIMPLE  ="):
            raise FitsError(tr('keine FITS-Datei'))
        blocks = 1
        buf = first
        while True:
            for i in range(0, BLOCK, 80):
                card = buf[i:i + 80].decode("ascii", "replace")
                key = card[:8].strip()
                if key == "END":
                    return hdr, blocks * BLOCK
                if card[8:10] == "= " and key:
                    val = card[10:]
                    if val.lstrip().startswith("'"):
                        v = val.lstrip()[1:]
                        end = v.find("'")
                        val = v[:end] if end >= 0 else v
                    else:
                        val = val.split("/")[0]
                    hdr.setdefault(key, val.strip())
            if blocks >= max_blocks:
                raise FitsError(tr('Header zu lang/beschädigt'))
            buf = f.read(BLOCK)
            if len(buf) < BLOCK:
                raise FitsError(tr('Header unvollständig'))
            blocks += 1


def _geom(hdr):
    try:
        bitpix = int(hdr.get("BITPIX", "0"))
        naxis = int(hdr.get("NAXIS", "0"))
        axes = [int(hdr.get(f"NAXIS{i}", "0")) for i in range(1, naxis + 1)]
    except ValueError as e:
        raise FitsError(tr('ungültige Geometrie')) from e
    if bitpix not in _DTYPES or naxis not in (2, 3) or any(a <= 0 for a in axes):
        raise FitsError(tr('nicht unterstützte FITS-Struktur'))
    if naxis == 3 and axes[2] not in (1, 3):
        raise FitsError(tr('nicht unterstützte Ebenenzahl'))
    if axes[0] * axes[1] > 400_000_000:
        raise FitsError(tr('Bild zu groß'))
    return bitpix, axes


def image_size(path: str):
    try:
        hdr, _ = read_header(path)
        _, axes = _geom(hdr)
        return axes[0], axes[1]
    except (OSError, FitsError):
        return None


def _load(path: str):
    if not HAVE_NUMPY:
        raise FitsError(tr('numpy fehlt'))
    hdr, off = read_header(path)
    bitpix, axes = _geom(hdr)
    count = 1
    for a in axes:
        count *= a
    dt = np.dtype(_DTYPES[bitpix])
    with open(lp(path), "rb") as f:
        f.seek(off)
        raw = f.read(count * dt.itemsize)
    if len(raw) < count * dt.itemsize:
        raise FitsError(tr('Datei unvollständig'))
    data = np.frombuffer(raw, dtype=dt)
    shape = (axes[2], axes[1], axes[0]) if len(axes) == 3 else (axes[1], axes[0])
    return hdr, bitpix, raw, data.reshape(shape)


def load_array(path: str):
    """(header, float32-Array mit BZERO/BSCALE). 2D oder 3D (Ebenen, Zeilen, Spalten)."""
    hdr, _, _, data = _load(path)
    bzero = float(hdr.get("BZERO", "0") or 0)
    bscale = float(hdr.get("BSCALE", "1") or 1)
    return hdr, data.astype(np.float32) * bscale + bzero


def pixel_digest(path: str) -> str | None:
    """Prüfsumme nur über Geometrie + Bilddaten (Header-Änderungen egal)."""
    try:
        hdr, off = read_header(path)
        bitpix, axes = _geom(hdr)
        n = abs(bitpix) // 8
        for a in axes:
            n *= a
        h = hashlib.blake2b(digest_size=32)
        h.update(f"FITS|{bitpix}|{axes}|".encode())
        with open(lp(path), "rb") as f:
            f.seek(off)
            left = n
            while left > 0:
                b = f.read(min(left, 1 << 20))
                if not b:
                    return None
                h.update(b)
                left -= len(b)
        return h.hexdigest()
    except (OSError, FitsError):
        return None


def _stretch(ch):
    """Auto-Stretch: Hintergrund abziehen, Mitteltöne so anheben, dass der Median bei 25 % liegt."""
    lo, hi = np.percentile(ch, 0.5), np.percentile(ch, 99.95)
    if hi <= lo:
        hi = lo + 1
    x = np.clip((ch - lo) / (hi - lo), 0, 1)
    med = float(np.median(x))
    t = 0.25
    if 0 < med < t:
        m = med * (1 - t) / (med - 2 * t * med + t)
        x = ((m - 1) * x) / ((2 * m - 1) * x - m)
    return np.clip(x * 255 + 0.5, 0, 255).astype(np.uint8)


def preview(path: str, max_side: int = 2400):
    """(PIL.Image, Info-Text)."""
    from PIL import Image

    hdr, bitpix, _, data = _load(path)
    bzero = float(hdr.get("BZERO", "0") or 0)
    bscale = float(hdr.get("BSCALE", "1") or 1)
    a = data.astype(np.float32) * bscale + bzero
    bayer = hdr.get("BAYERPAT", "").strip().upper()
    info = "FITS"
    if a.ndim == 3:
        rgb = np.moveaxis(a, 0, -1) if a.shape[0] == 3 else a[0]
        info = "FITS gestackt (RGB)" if a.shape[0] == 3 else "FITS"
    elif bayer in ("RGGB", "BGGR", "GRBG", "GBRG") and a.shape[0] >= 2 and a.shape[1] >= 2:
        h, w = (a.shape[0] // 2) * 2, (a.shape[1] // 2) * 2
        a = a[:h, :w]
        q = {(0, 0): a[0::2, 0::2], (0, 1): a[0::2, 1::2], (1, 0): a[1::2, 0::2], (1, 1): a[1::2, 1::2]}
        layout = [(0, 0), (0, 1), (1, 0), (1, 1)]
        pos = {}
        for c, p in zip(bayer, layout):
            pos.setdefault(c, []).append(p)
        r = q[pos["R"][0]]
        b = q[pos["B"][0]]
        g = (q[pos["G"][0]] + q[pos["G"][1]]) / 2
        rgb = np.stack([r, g, b], axis=-1)
        info = f"FITS Einzelbild (Bayer {bayer}, Superpixel)"
    else:
        rgb = a
    # Für große Bilder vor dem Stretch verkleinern (Schrittweite)
    step = max(1, int(max(rgb.shape[0], rgb.shape[1]) / max_side))
    if step > 1:
        rgb = rgb[::step, ::step]
    if rgb.ndim == 3:
        out = np.stack([_stretch(rgb[..., i]) for i in range(3)], axis=-1)
        im = Image.fromarray(out, "RGB")
    else:
        im = Image.fromarray(_stretch(rgb), "L").convert("RGB")
    if hdr.get("ROWORDER", "").strip().upper() != "TOP-DOWN":
        im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)  # FITS-Standard: erste Zeile unten
    im.thumbnail((max_side, max_side))
    return im, info + " · Auto-Stretch"


def header_rows(path: str) -> list[tuple[str, str]]:
    hdr, _ = read_header(path)
    rows = []
    for k in PRIORITY:
        if k in hdr:
            rows.append((f"FITS {k}", hdr[k]))
    for k, v in hdr.items():
        if k not in PRIORITY and k not in ("SIMPLE", "EXTEND", "COMMENT", "HISTORY"):
            rows.append((f"FITS {k}", v[:200]))
    return rows
