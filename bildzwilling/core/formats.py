# SPDX-License-Identifier: GPL-3.0-or-later
"""Unterstützte Dateiformate.

Für die Duplikatsuche im Modus "Byte-identisch" ist das Format egal – es wird der
Dateiinhalt verglichen. Die Listen hier steuern, welche Dateien überhaupt
berücksichtigt werden und wie die Vorschau dekodiert wird.
"""

from __future__ import annotations

import os

# Standard-Bildformate (Dekodierung über Pillow, ggf. Plugins)
STANDARD_EXT = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".apng", ".gif", ".bmp", ".dib",
    ".tif", ".tiff", ".webp", ".heic", ".heif", ".hif", ".avif", ".jxl",
    ".jp2", ".j2k", ".jpf", ".jpx", ".ico", ".icns", ".psd", ".tga", ".ppm",
    ".pgm", ".pbm", ".pnm", ".pcx", ".dds", ".qoi", ".sgi",
    ".insp",  # Insta360-Foto (intern JPEG)
}

# Formate ohne Rastervorschau (werden trotzdem byteweise verglichen)
OTHER_IMAGE_EXT = {".svg", ".svgz", ".eps", ".ai", ".xcf", ".exr", ".hdr"}

# RAW-Formate nach Hersteller (Dekodierung über rawpy/LibRaw)
RAW_BY_VENDOR = {
    "Fujifilm": {".raf"},
    "Nikon": {".nef", ".nrw"},
    "Canon": {".cr2", ".cr3", ".crw"},
    "Panasonic / Lumix": {".rw2", ".raw"},
    "OM System / Olympus": {".orf", ".ori"},
    "Leica": {".rwl", ".dng"},
    "Hasselblad": {".3fr", ".fff"},
    "DJI": {".dng"},
    "Insta360": {".dng"},
    "Sony": {".arw", ".srf", ".sr2"},
    "Pentax / Ricoh": {".pef", ".dng"},
    "Samsung": {".srw"},
    "Sigma": {".x3f"},
    "Phase One / Leaf / Mamiya": {".iiq", ".mos", ".mef"},
    "Kodak / Minolta / Epson": {".dcr", ".kdc", ".mrw", ".erf"},
}

RAW_EXT = set().union(*RAW_BY_VENDOR.values())

# Smart-Teleskope / Astrofotografie: FITS (ZWO Seestar S50/S30, DWARFLAB DWARF u. a.)
ASTRO_EXT = {".fit", ".fits", ".fts"}
OTHER_IMAGE_EXT_ASTRO = {".xisf", ".fz"}  # PixInsight / komprimiertes FITS: nur Byte-Vergleich

IMAGE_EXT = STANDARD_EXT | RAW_EXT | ASTRO_EXT | OTHER_IMAGE_EXT | OTHER_IMAGE_EXT_ASTRO

# Videos (Byte-Vergleich; Vorschau über ffmpeg, Metadaten über ExifTool)
VIDEO_EXT = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts", ".3gp", ".wmv", ".webm",
    ".insv",  # Insta360
    ".lrv",   # Insta360/GoPro Proxy
    ".360",   # GoPro MAX
}

# Partner eines RAW-Bildes in einem RAW+JPEG-Paar
PAIR_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".hif"}

# Begleitdateien, die mit einem Duplikat mitwandern können
SIDECAR_EXT = (".xmp", ".XMP", ".pp3", ".dop")

# Ordner, die nie durchsucht werden (System, Papierkorb, NAS-Thumbnails, Sync-Metadaten)
EXCLUDED_DIR_NAMES = {
    "$recycle.bin", "system volume information", ".trash", ".trashes",
    ".trash-1000", "@eadir", "#recycle", ".thumbnails", ".spotlight-v100",
    ".fseventsd", ".documentrevisions-v100", ".temporaryitems",
    ".sync", ".owncloudsync.log", "_bildzwilling_cache",
}


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_image(path: str) -> bool:
    return ext_of(path) in IMAGE_EXT


def is_raw(path: str) -> bool:
    return ext_of(path) in RAW_EXT


def is_fits(path: str) -> bool:
    return ext_of(path) in ASTRO_EXT


def is_video(path: str) -> bool:
    return ext_of(path) in VIDEO_EXT


def file_type(path: str) -> str:
    """Grobe Kategorie für Filter: RAW, JPEG, HEIC, Video, Andere."""
    e = ext_of(path)
    if e in RAW_EXT:
        return "RAW"
    if e in ASTRO_EXT:
        return "FITS"
    if e in (".jpg", ".jpeg", ".jpe", ".jfif", ".insp"):
        return "JPEG"
    if e in (".heic", ".heif", ".hif", ".avif"):
        return "HEIC"
    if e in VIDEO_EXT:
        return "Video"
    return "Andere"


def is_previewable(path: str) -> bool:
    e = ext_of(path)
    return e in STANDARD_EXT or e in RAW_EXT or e in ASTRO_EXT
