# SPDX-License-Identifier: GPL-3.0-or-later
"""Optionale externe Werkzeuge: ExifTool (vollständige Metadaten) und ffmpeg (Video-Vorschau).

Beide werden nur verwendet, wenn sie gefunden werden – neben der EXE, in einem Unterordner
"tools", unter einem in den Einstellungen gewählten Pfad oder im Systempfad (PATH).
Aufrufe erfolgen immer ohne Shell mit Argumentliste und Zeitlimit.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import threading

from .fsutil import IS_WINDOWS, lp
from ..i18n import _ as tr

_CFG = {"exiftool": "", "ffmpeg": "", "use_exiftool": True}
_FOUND: dict[str, str | None] = {}
_LOCK = threading.Lock()

_NAMES = {
    "exiftool": ["exiftool.exe", "exiftool(-k).exe", "exiftool"] if IS_WINDOWS else ["exiftool"],
    "ffmpeg": ["ffmpeg.exe", "ffmpeg"] if IS_WINDOWS else ["ffmpeg"],
}


def configure(**kw) -> None:
    with _LOCK:
        for k, v in kw.items():
            if k in _CFG:
                _CFG[k] = v
        _FOUND.clear()


def _app_dir() -> str:
    from .settings import app_dir

    return app_dir()


def find(tool: str) -> str | None:
    """Pfad zum Werkzeug oder None."""
    with _LOCK:
        if tool in _FOUND:
            return _FOUND[tool]
        custom = _CFG.get(tool) or ""
    cands = []
    if custom:
        cands.append(custom)
    base = _app_dir()
    for sub in ("", "tools", tool, os.path.join("tools", tool)):
        for n in _NAMES[tool]:
            cands.append(os.path.join(base, sub, n))
    # Sicherheit (2.2): Unter Windows werden Werkzeuge NUR aus dem eingestellten Pfad oder dem Programmordner
    # (bzw. „tools“) gestartet – kein Suchen im PATH oder im aktuellen Arbeitsverzeichnis, damit kein
    # untergeschobenes exiftool.exe/ffmpeg.exe ausgeführt wird. macOS/Linux: zusätzlich Systempfad (Homebrew).
    if not IS_WINDOWS:
        for n in _NAMES[tool]:
            w = shutil.which(n)
            if w:
                cands.append(w)
    found = next((c for c in cands if c and os.path.isfile(c)), None)
    with _LOCK:
        _FOUND[tool] = found
    return found


_INFO: dict[str, dict] = {}


def sha256_file(path: str, limit: int = 512 * 1024 * 1024) -> str:
    import hashlib

    h = hashlib.sha256()
    n = 0
    with open(lp(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
            if n > limit:
                return ""
    return h.hexdigest()


def tool_info(tool: str) -> dict:
    """Pfad, Version und SHA-256 eines Werkzeugs (für Einstellungen/Systeminfo; Ergebnis wird gemerkt)."""
    path = find(tool)
    if not path:
        return {"path": "", "version": "", "sha256": ""}
    key = f"{tool}|{path}|{os.path.getmtime(path) if os.path.exists(path) else 0}"
    if key in _INFO:
        return _INFO[key]
    ver = ""
    try:
        args = [path, "-ver"] if tool == "exiftool" else [path, "-version"]
        res = _run(args, timeout=15)
        out = (res.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        ver = out[0][:80] if out else ""
    except (OSError, subprocess.SubprocessError, ValueError):
        ver = "?"
    try:
        digest = sha256_file(path)
    except OSError:
        digest = ""
    info = {"path": path, "version": ver, "sha256": digest}
    _INFO[key] = info
    return info


def _run(args: list[str], timeout: float, data: bytes | None = None) -> subprocess.CompletedProcess:
    kw = {}
    if IS_WINDOWS:
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    if data is None:
        # Standardeingabe schließen: "exiftool(-k).exe" wartet sonst am Ende auf einen Tastendruck
        kw["stdin"] = subprocess.DEVNULL
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout, check=False, **kw)


# --------------------------------------------------------------------------- ExifTool

_PRIO = ["Make", "Model", "LensModel", "LensID", "DateTimeOriginal", "CreateDate", "ExposureTime",
         "FNumber", "ISO", "FocalLength", "FocalLengthIn35mmFormat", "ExposureCompensation",
         "ExposureProgram", "MeteringMode", "Flash", "WhiteBalance", "Orientation", "ImageSize",
         "SerialNumber", "GPSPosition", "GPSAltitude", "Duration", "VideoFrameRate", "AvgBitrate"]


def exiftool_enabled() -> bool:
    return bool(_CFG.get("use_exiftool")) and find("exiftool") is not None


def exiftool_read(path: str, timeout: float = 25) -> list[tuple[str, str]] | None:
    """Alle Metadaten über ExifTool – oder None, wenn nicht verfügbar/fehlgeschlagen."""
    exe = find("exiftool")
    if not exe or not _CFG.get("use_exiftool"):
        return None
    # Pfad über Argumentdatei (UTF-8) übergeben: sicher für Umlaute und führende Minuszeichen
    fd, argf = tempfile.mkstemp(prefix="bz_exif_", suffix=".args")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(os.path.abspath(path) + "\n")
        res = _run([exe, "-j", "-G1", "-a", "-s", "-charset", "filename=utf8", "-@", argf], timeout)
        if res.returncode not in (0, 1) or not res.stdout:
            return None
        data = json.loads(res.stdout.decode("utf-8", "replace"))
        if not data or not isinstance(data, list):
            return None
        rows = []
        for k, v in data[0].items():
            if k == "SourceFile" or k.startswith(("ExifTool:", "System:")):
                continue
            s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            if len(s) > 200:
                s = s[:200] + " …"
            rows.append((k, s))

        def prio(r):
            tag = r[0].split(":")[-1]
            return (_PRIO.index(tag) if tag in _PRIO else len(_PRIO), r[0].lower())

        rows.sort(key=prio)
        return rows
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        try:
            os.remove(argf)
        except OSError:
            pass


# --------------------------------------------------------------------------- ffmpeg

def video_frame(path: str, max_side: int = 1280, timeout: float = 30):
    """Einzelbild aus einem Video (PIL.Image) über ffmpeg – oder Exception."""
    from PIL import Image

    exe = find("ffmpeg")
    if not exe:
        raise FileNotFoundError(tr('Video-Vorschau benötigt ffmpeg (ffmpeg.exe neben die EXE oder in den Ordner tools legen).'))
    src = lp(os.path.abspath(path))  # absolut -> beginnt nie mit "-"
    vf = f"scale='min({int(max_side)},iw)':-2"
    for seek in (["-ss", "1"], []):
        res = _run([exe, "-hide_banner", "-loglevel", "error", *seek, "-i", src, "-frames:v", "1",
                    "-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"], timeout)
        if res.returncode == 0 and res.stdout:
            im = Image.open(io.BytesIO(res.stdout))
            im.load()
            return im
    raise OSError(tr('ffmpeg konnte kein Vorschaubild erzeugen.'))
