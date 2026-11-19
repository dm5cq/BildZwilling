# SPDX-License-Identifier: GPL-3.0-or-later
"""EXIF-/Metadaten auslesen – exifread (kann auch viele RAW-Formate), Fallback Pillow."""

from __future__ import annotations

import datetime as _dt
import os

from . import tools
from . import fits
from .formats import is_fits, is_video
from .fsutil import human_size, lp, num
from ..i18n import _ as tr

try:
    import exifread  # type: ignore

    HAVE_EXIFREAD = True
except Exception:  # noqa: BLE001
    HAVE_EXIFREAD = False

try:
    from PIL import ExifTags, Image

    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

# Wichtige Felder zuerst (Anzeige-Reihenfolge)
PRIORITY = [
    "Image Make", "Image Model", "EXIF LensModel", "EXIF DateTimeOriginal",
    "EXIF ExposureTime", "EXIF FNumber", "EXIF ISOSpeedRatings", "EXIF FocalLength",
    "EXIF FocalLengthIn35mmFilm", "EXIF ExposureBiasValue", "EXIF ExposureProgram",
    "EXIF MeteringMode", "EXIF Flash", "EXIF WhiteBalance", "Image Orientation",
    "EXIF ExifImageWidth", "EXIF ExifImageLength", "Image Software", "Image Artist",
    "Image Copyright", "EXIF BodySerialNumber", "GPS GPSLatitude", "GPS GPSLongitude",
    "GPS GPSAltitude",
]

_SKIP_PREFIX = ("Thumbnail", "MakerNote", "Interoperability")
_SKIP_TAGS = {"JPEGThumbnail", "TIFFThumbnail", "EXIF MakerNote", "Image PrintIM"}
_MAX_LEN = 200


def _clip(v) -> str:
    s = str(v).replace("\x00", "").strip()
    return s if len(s) <= _MAX_LEN else s[:_MAX_LEN] + " …"


def _file_info(path: str) -> list[tuple[str, str]]:
    out = []
    try:
        st = os.stat(lp(path))
        out.append((tr("Datei: Name"), os.path.basename(path)))
        out.append((tr("Datei: Ordner"), os.path.dirname(path)))
        out.append((tr("Datei: Größe"), f"{human_size(st.st_size)} ({num(st.st_size)} Bytes)"))
        out.append((tr("Datei: Geändert"), _dt.datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M:%S")))
    except OSError as e:
        out.append((tr("Datei: Fehler"), str(e)))
    return out


def _exifread_tags(fobj, prefix_map=None) -> dict[str, str]:
    out: dict[str, str] = {}
    raw = exifread.process_file(fobj, details=False, strict=False)
    for k, v in raw.items():
        if k in _SKIP_TAGS or k.startswith(_SKIP_PREFIX):
            continue
        if prefix_map:
            for a, b in prefix_map.items():
                if k.startswith(a):
                    k = b + k[len(a):]
                    break
        out[k] = _clip(v)
    return out


def _embedded_tags(path: str) -> dict[str, str]:
    """Fallback für RAW-Container, die ExifRead nicht direkt erkennt.

    - Canon CR3: EXIF liegt als TIFF in den Boxen CMT1 (IFD0), CMT2 (Exif), CMT4 (GPS)
    - Fujifilm RAF u. a.: eingebettete JPEG-Vorschau mit vollständigem EXIF-Block
    """
    import io
    import struct

    tags: dict[str, str] = {}
    try:
        with open(lp(path), "rb") as f:
            head = f.read(8 * 1024 * 1024)
    except OSError:
        return tags
    boxes = ((b"CMT1", None), (b"CMT2", {"Image ": "EXIF "}), (b"CMT4", {"Image ": "GPS "}))
    for name, pmap in boxes:
        i = head.find(name)
        if i >= 4:
            size = struct.unpack(">I", head[i - 4:i])[0]
            data = head[i + 4:i - 4 + size] if 8 < size < len(head) else b""
            if data[:4] in (b"II*\x00", b"MM\x00*"):
                try:
                    tags.update(_exifread_tags(io.BytesIO(data), pmap))
                except Exception:  # noqa: BLE001
                    pass
    if not tags:
        i = head.find(b"Exif\x00\x00")
        if i >= 0 and head[i + 6:i + 10] in (b"II*\x00", b"MM\x00*"):
            try:
                tags.update(_exifread_tags(io.BytesIO(head[i + 6:])))
            except Exception:  # noqa: BLE001
                pass
    return tags


def read_exif(path: str) -> list[tuple[str, str]]:
    """Liste (Feld, Wert) – Dateiangaben + EXIF, wichtigste Felder zuerst."""
    rows = _file_info(path)
    if is_fits(path):
        try:
            return rows + fits.header_rows(path)
        except (OSError, fits.FitsError) as e:
            return rows + [("FITS", tr("Header nicht lesbar: {0}").format(e))]
    et = tools.exiftool_read(path) if tools.exiftool_enabled() else None
    if et:
        rows.append((tr("Quelle"), "ExifTool"))
        return rows + et
    if is_video(path):
        rows.append(("Video", tr("Metadaten von Videos: ExifTool neben die EXE legen (siehe Einstellungen)")))
        return rows
    tags: dict[str, str] = {}

    if HAVE_EXIFREAD:
        try:
            with open(lp(path), "rb") as f:
                tags = _exifread_tags(f)
        except Exception:  # noqa: BLE001 – defekte/unbekannte Metadaten
            tags = {}
        if not any(k.startswith("EXIF ") for k in tags):
            emb = _embedded_tags(path)
            for k, v in emb.items():
                tags.setdefault(k, v)

    if not tags and HAVE_PIL:
        try:
            with Image.open(lp(path)) as im:
                rows.append((tr("Bild: Format"), f"{im.format} {im.size[0]}×{im.size[1]} {im.mode}"))
                ex = im.getexif()
                for k, v in ex.items():
                    tags["Image " + ExifTags.TAGS.get(k, str(k))] = _clip(v)
                for k, v in ex.get_ifd(ExifTags.IFD.Exif).items():
                    tags["EXIF " + ExifTags.TAGS.get(k, str(k))] = _clip(v)
                for k, v in ex.get_ifd(ExifTags.IFD.GPSInfo).items():
                    tags["GPS " + ExifTags.GPSTAGS.get(k, str(k))] = _clip(v)
        except Exception:  # noqa: BLE001
            pass

    for key in PRIORITY:
        if key in tags:
            rows.append((key, tags.pop(key)))
    for key in sorted(tags):
        if isinstance(tags[key], str) and tags[key].startswith("b'"):
            continue  # Binärdaten auslassen
        rows.append((key, tags[key]))
    if len(rows) <= 4:
        rows.append(("EXIF", "keine Metadaten gefunden"))
    return rows
