# SPDX-License-Identifier: GPL-3.0-or-later
"""Fensterleiste (Titelleiste) im App-Stil färben.

Windows 11: exakte Farbe (Grau) und weiße Titelschrift über DwmSetWindowAttribute.
Windows 10 (ab 1809): dunkle Titelleiste über den „Immersive Dark Mode“.
macOS/Linux: Titelleiste folgt dem System – hier nichts zu tun.
"""

from __future__ import annotations

import sys

from . import theme

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _colorref(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def style_titlebar(win) -> None:
    """Titelleiste des Fensters an das aktuelle Farbschema anpassen (Fehler werden ignoriert)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes

        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()  # pyright: ignore[reportAttributeAccessIssue]
        dwm = ctypes.windll.dwmapi  # pyright: ignore[reportAttributeAccessIssue]
        dark = theme.CURRENT != "light"

        def setattr_(attr, value) -> bool:
            v = wintypes.DWORD(value)
            return dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), wintypes.DWORD(attr),
                                             ctypes.byref(v), ctypes.sizeof(v)) == 0

        if not setattr_(_DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0):
            setattr_(_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1 if dark else 0)
        # Windows 11: exakte Farben (unter Windows 10 wirkungslos)
        setattr_(_DWMWA_CAPTION_COLOR, _colorref(theme.BG))
        setattr_(_DWMWA_TEXT_COLOR, _colorref(theme.TEXT))
        setattr_(_DWMWA_BORDER_COLOR, _colorref(theme.ACCENT if theme.CURRENT == "contrast" else theme.BORDER))
    except Exception:  # noqa: BLE001 – ältere Windows-Versionen
        pass
