# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt THIRD_PARTY_LICENSES.txt aus den installierten Paketen (wird von build-exe.bat/build-mac.sh aufgerufen).

Übersicht + vollständige Lizenztexte aus den dist-info-Ordnern der Pakete, die in die EXE eingebunden werden.
"""

from __future__ import annotations

import importlib.metadata as md
import os
import platform
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (Paket, Anzeigename, Lizenz, enthaltene Bibliotheken, Projektseite)
PACKAGES = [
    ("Pillow", "Pillow", "MIT-CMU (HPND)", "libjpeg-turbo, libpng, zlib, libtiff, libwebp, openjpeg, freetype u. a.",
     "https://python-pillow.github.io"),
    ("pillow_heif", "pillow-heif", "BSD-3-Clause", "libheif (LGPL-3.0), libde265 (LGPL-3.0), x265 (GPL-2.0+), aom",
     "https://github.com/bigcat88/pillow_heif"),
    ("rawpy", "rawpy", "MIT", "LibRaw (LGPL-2.1 oder CDDL-1.0)", "https://github.com/letmaik/rawpy"),
    ("numpy", "NumPy", "BSD-3-Clause", "OpenBLAS (BSD-3-Clause) u. a.", "https://numpy.org"),
    ("ExifRead", "ExifRead", "BSD-3-Clause", "", "https://github.com/ianare/exif-py"),
    ("Send2Trash", "Send2Trash", "BSD-3-Clause", "", "https://github.com/arsenetar/send2trash"),
    ("pyinstaller", "PyInstaller (Startprogramm)", "GPL-2.0 mit Bootloader-Ausnahme", "",
     "https://pyinstaller.org"),
]

HEADER = """Drittanbieter-Komponenten in BildZwilling
=========================================

BildZwilling selbst steht unter der GNU General Public License v3 oder später (Datei LICENSE).
Die ausführbaren Dateien enthalten außerdem die folgenden freien Komponenten. Alle Lizenzen
sind mit der GPL v3 vereinbar. Die Rechte liegen bei den jeweiligen Urhebern.

Python ({py})  – Python Software Foundation License 2.0 – https://www.python.org
Tcl/Tk (tkinter) – BSD-artige Tcl/Tk-Lizenz – https://www.tcl-lang.org

"""

NOT_BUNDLED = """
Nicht enthalten (vom Anwender optional in den Ordner „tools“ gelegt, eigene Lizenzen):
  ExifTool (Phil Harvey) – Perl Artistic License / GPL – https://exiftool.org
  FFmpeg – LGPL-2.1+/GPL-2.0+ je nach Build – https://ffmpeg.org
"""


def license_files(dist) -> list[str]:
    out = []
    for f in dist.files or []:
        s = str(f)
        name = os.path.basename(s).upper()
        if any(k in name for k in ("LICENSE", "LICENCE", "COPYING", "NOTICE")) and ".dist-info" in s:
            try:
                out.append(f"--- {s} ---\n" + f.read_text(encoding="utf-8").strip())
            except (OSError, UnicodeError, AttributeError, TypeError):
                pass
    return out


def build() -> str:
    parts = [HEADER.format(py=platform.python_version())]
    texts = []
    for pkg, name, lic, inner, url in PACKAGES:
        try:
            ver = md.version(pkg)
        except md.PackageNotFoundError:
            ver = "(Version beim Build)"
        parts.append(f"{name} {ver} – {lic} – {url}")
        if inner:
            parts.append(f"    enthält: {inner}")
        try:
            lt = license_files(md.distribution(pkg))
        except md.PackageNotFoundError:
            lt = []
        if lt:
            texts.append(f"\n\n========== {name} {ver} ==========\n" + "\n\n".join(lt))
    parts.append(NOT_BUNDLED)
    parts.append("\nVollständige Lizenztexte\n========================" + "".join(texts) + "\n")
    return "\n".join(parts)


def main() -> int:
    out = os.path.join(HERE, "THIRD_PARTY_LICENSES.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build())
    print("geschrieben:", out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
