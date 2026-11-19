# SPDX-License-Identifier: GPL-3.0-or-later
"""Bilder laden (Vorschau), Bildmaße lesen und Bildinhalt (Pixel) vergleichen.

- Standardformate über Pillow (+ pillow-heif für HEIC/HEIF, + Pillow-AVIF ab Pillow 11.3)
- RAW über rawpy (LibRaw): Fujifilm, Nikon, Canon (inkl. CR3), Panasonic, OM System,
  Leica, Hasselblad, DJI, Insta360 (DNG), Sony, Pentax …
"""

from __future__ import annotations

import hashlib
import io
import threading

from . import fits, tools
from .formats import is_fits, is_raw, is_video
from .fsutil import lp
from ..i18n import _ as tr

try:
    from PIL import Image, ImageOps

    # Große Panoramen (Insta360, Hasselblad 100 MP) erlauben, Dekompressionsbomben aber begrenzen
    Image.MAX_IMAGE_PIXELS = 600_000_000
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    HAVE_HEIF = True
except Exception:  # noqa: BLE001 – optionales Plugin
    HAVE_HEIF = False

try:
    import pillow_jxl  # type: ignore  # noqa: F401  (registriert sich selbst)

    HAVE_JXL = True
except Exception:  # noqa: BLE001
    HAVE_JXL = False

try:
    import rawpy  # type: ignore

    HAVE_RAWPY = True
except Exception:  # noqa: BLE001
    HAVE_RAWPY = False

# LibRaw ist nicht durchgängig threadsicher -> RAW-Dekodierung serialisieren
_RAW_LOCK = threading.Lock()


class ImageLoadError(Exception):
    pass


def capabilities() -> dict:
    return {"Pillow": HAVE_PIL, "HEIC/HEIF": HAVE_HEIF, "JPEG XL": HAVE_JXL, "RAW (rawpy)": HAVE_RAWPY,
            "FITS (Seestar & Co.)": fits.HAVE_NUMPY,
            "ExifTool": tools.find("exiftool") is not None, "ffmpeg (Video)": tools.find("ffmpeg") is not None}


# --------------------------------------------------------------------------- Vorschau

def _raw_preview(path: str, max_side: int):
    if not HAVE_RAWPY:
        raise ImageLoadError(tr('RAW-Unterstützung (rawpy) ist nicht installiert.'))
    with _RAW_LOCK:
        with rawpy.imread(lp(path)) as raw:
            # 1. eingebettetes JPEG – schnell und farbtreu wie in der Kamera
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    im = Image.open(io.BytesIO(thumb.data))
                    im.load()
                else:
                    im = Image.fromarray(thumb.data)
                if max(im.size) >= min(max_side, 1000):
                    return im, "eingebettete Vorschau"
            except Exception:  # noqa: BLE001 – kein/defektes Thumbnail
                pass
            # 2. echte Entwicklung in halber Auflösung
            rgb = raw.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=False,
                                  output_bps=8)
            return Image.fromarray(rgb), "RAW entwickelt (halbe Auflösung)"


def _embedded_jpeg(path: str, limit: int = 64 * 1024 * 1024):
    """Universeller Fallback für (neue) RAW-Formate: größtes eingebettetes JPEG suchen."""
    with open(lp(path), "rb") as f:
        data = f.read(limit)
    best = None
    pos = data.find(b"\xff\xd8\xff")
    tries = 0
    while pos >= 0 and tries < 24:
        tries += 1
        try:
            im = Image.open(io.BytesIO(data[pos:]))
            if im.format == "JPEG" and (best is None or im.size[0] * im.size[1] > best.size[0] * best.size[1]):
                im.load()
                best = im
        except Exception:  # noqa: BLE001
            pass
        pos = data.find(b"\xff\xd8\xff", pos + 3)
    if best is None:
        raise ImageLoadError(tr('Keine eingebettete Vorschau gefunden.'))
    return best


# Grenze für die Vorschau (2.2, C3): darüber gibt es eine klare Meldung statt Speicherüberlauf.
# Die Duplikatsuche per Byte-Vergleich ist davon nicht betroffen.
MAX_PREVIEW_PIXELS = 600_000_000


def too_big_message(w: int, h: int) -> str:
    return tr('Bild zu groß für die Vorschau ({mp} MP, Grenze {lim} MP). Die Duplikatsuche per '
              'Byte-Vergleich funktioniert trotzdem.').format(mp=round(w * h / 1e6), lim=MAX_PREVIEW_PIXELS // 1_000_000)


def check_preview_size(path: str) -> None:
    # RAW: Vorschau kommt aus dem eingebetteten JPEG bzw. halber Auflösung – keine Prüfung nötig
    sz = image_size(path) if not (is_video(path) or is_raw(path)) else None
    if sz and sz[0] * sz[1] > MAX_PREVIEW_PIXELS:
        raise ImageLoadError(too_big_message(*sz))


def load_preview(path: str, max_side: int = 2400):
    """Gibt (PIL.Image RGB, Info-Text) zurück. Ausrichtung laut EXIF wird angewendet."""
    if not HAVE_PIL:
        raise ImageLoadError(tr('Pillow fehlt.'))
    check_preview_size(path)
    info = ""
    if is_video(path):
        try:
            im = tools.video_frame(path, max_side)
            return im.convert("RGB"), "Videobild (ffmpeg)"
        except FileNotFoundError as e:
            raise ImageLoadError(str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise ImageLoadError(tr('Video-Vorschau nicht möglich: {0}').format(e)) from e
    if is_fits(path):
        try:
            return fits.preview(path, max_side)
        except Exception as e:  # noqa: BLE001
            raise ImageLoadError(tr('FITS-Vorschau nicht möglich: {0}').format(e)) from e
    try:
        if is_raw(path):
            try:
                im, info = _raw_preview(path, max_side)
            except Exception:  # noqa: BLE001 – rawpy fehlt oder Kamera zu neu für LibRaw
                try:
                    im, info = _embedded_jpeg(path), "eingebettetes JPEG"
                except Exception:  # noqa: BLE001 – manche DNG/TIFF-RAW kann Pillow selbst
                    im = Image.open(lp(path))
                    im.load()
                    info = "Pillow"
        else:
            im = Image.open(lp(path))
            try:
                im.seek(0)
            except EOFError:
                pass
            im.load()
            info = im.format or ""
        im = ImageOps.exif_transpose(im) or im
        if im.mode not in ("RGB", "RGBA"):
            if im.mode in ("I;16", "I;16B", "I", "F"):
                im = ImageOps.autocontrast(im.convert("I").point(lambda v: v / 256).convert("L"))
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return im, info
    except ImageLoadError:
        raise
    except Image.DecompressionBombError as e:
        raise ImageLoadError(tr('Bild zu groß (Schutz vor Dekompressionsbomben): {0}').format(e)) from e
    except MemoryError as e:
        raise ImageLoadError(tr('Nicht genug Arbeitsspeicher für die Vorschau dieses Bildes.')) from e
    except Exception as e:  # noqa: BLE001
        raise ImageLoadError(tr('Vorschau nicht möglich: {0}').format(e)) from e


def image_size(path: str):
    """(Breite, Höhe) ohne komplettes Dekodieren – oder None."""
    if is_fits(path):
        return fits.image_size(path)
    try:
        if is_raw(path) and HAVE_RAWPY:
            with _RAW_LOCK:
                with rawpy.imread(lp(path)) as raw:
                    s = raw.sizes
                    return (int(s.raw_width), int(s.raw_height))
        with Image.open(lp(path)) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- Pixel-Prüfsumme

PIXEL_ALGO = "pix1"


def pixel_digest(path: str, cancel=None) -> str | None:
    """Prüfsumme über die dekodierten Bilddaten (nicht über die Datei).

    Findet z. B. dasselbe Foto mit anderen/entfernten Metadaten. Bei RAW wird über die
    unveränderten Sensordaten gerechnet. Rückgabe None, wenn nicht dekodierbar.
    """
    if is_fits(path):
        return fits.pixel_digest(path)
    h = hashlib.blake2b(digest_size=32)
    try:
        if is_raw(path) and HAVE_RAWPY:
            with _RAW_LOCK:
                with rawpy.imread(lp(path)) as raw:
                    data = raw.raw_image_visible
                    h.update(b"RAW|%d|%d|%s|" % (data.shape[1], data.shape[0], str(data.dtype).encode()))
                    h.update(memoryview(data.copy(order="C")).cast("B"))
            return h.hexdigest()
        if not HAVE_PIL:
            return None
        with Image.open(lp(path)) as im:
            frames = getattr(im, "n_frames", 1) or 1
            for fi in range(min(frames, 64)):
                if cancel is not None and cancel.is_set():
                    return None
                if frames > 1:
                    im.seek(fi)
                fr = im
                fr.load()
                w, hgt = fr.size
                h.update(b"IMG|%d|%d|%s|" % (w, hgt, fr.mode.encode()))
                if fr.mode == "P":
                    pal = fr.getpalette() or []
                    h.update(bytes(min(max(v, 0), 255) for v in pal))
                # in Streifen hashen, damit kein zweiter Vollbild-Puffer entsteht
                step = max(1, 4_000_000 // max(w, 1))
                for y in range(0, hgt, step):
                    h.update(fr.crop((0, y, w, min(y + step, hgt))).tobytes())
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


def compare_pixels(a: str, b: str) -> tuple[bool | None, str]:
    """Vergleicht den Bildinhalt zweier Dateien. (True/False/None, Erklärung)."""
    da, db = pixel_digest(a), pixel_digest(b)
    if da is None or db is None:
        return None, tr('Bildinhalt konnte nicht dekodiert werden.')
    if da == db:
        return True, tr('Bildinhalt (Pixel) ist identisch.')
    return False, tr('Bildinhalt unterscheidet sich.')
