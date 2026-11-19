# SPDX-License-Identifier: GPL-3.0-or-later
"""Eigene Meldungsfenster im App-Stil (statt der weißen Windows-Standarddialoge).

Gleiche Aufrufform wie tkinter.messagebox: showinfo, showwarning, showerror, askyesno.
Grauer Hintergrund, weiße Schrift, App-Icon; die Art (Info blau, Warnung gelb, Fehler rot, Frage orange)
zeigt nur das farbige Symbol – ohne Farbrand (2.2). Enter = Standardknopf, Esc = Abbrechen/Nein.
Fehlermeldungen können Details mitbringen („Details kopieren“). Mit Sprachausgabe.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from ..i18n import _ as tr
from . import theme
from .winstyle import style_titlebar

_CFG = {"root": None, "icon": "", "speaker": None}
TEST_ANSWER = None  # nur für automatische Tests: feste Antwort ohne Fenster
_IMG_CACHE: dict = {}


def setup(root, icon_path: str = "", speaker=None) -> None:
    _CFG.update(root=root, icon=icon_path, speaker=speaker)


def _icon(size: int = 64):
    key = (_CFG["icon"], size)
    if key not in _IMG_CACHE:
        try:
            img = tk.PhotoImage(file=_CFG["icon"])
            f = max(1, img.width() // size)
            _IMG_CACHE[key] = img.subsample(f, f) if f > 1 else img
        except (tk.TclError, TypeError):
            _IMG_CACHE[key] = None
    return _IMG_CACHE[key]


_KIND = {
    "info": ("BLUE", "ℹ"),
    "warning": ("YELLOW", "⚠"),
    "error": ("RED", "✖"),
    "question": ("ACCENT", "?"),
}


def _visible(win) -> bool:
    """Elternfenster sichtbar? (Beim Start ist das Hauptfenster noch verborgen – dann nicht „transient“,
    sonst bliebe die Meldung unter Windows unsichtbar.)"""
    try:
        return win is not None and bool(win.winfo_viewable())
    except (tk.TclError, AttributeError):
        return False


def center(w, parent) -> None:
    w.update_idletasks()
    try:
        if _visible(parent):
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + max(0, (pw - w.winfo_reqwidth()) // 2)
            y = py + max(0, (ph - w.winfo_reqheight()) // 3)
        else:
            x = max(0, (w.winfo_screenwidth() - w.winfo_reqwidth()) // 2)
            y = max(0, (w.winfo_screenheight() - w.winfo_reqheight()) // 3)
        w.geometry(f"+{x}+{y}")
    except (tk.TclError, AttributeError, TypeError):
        pass


def copy_to_clipboard(widget, text: str) -> bool:
    try:
        widget.clipboard_clear()
        widget.clipboard_append(text)
        widget.update_idletasks()
        return True
    except tk.TclError:
        return False


def _show(title: str, message: str, kind: str, buttons, parent=None, heading: str = "", danger=False,
          details: str = ""):
    if TEST_ANSWER is not None:
        return TEST_ANSWER
    parent = parent or _CFG["root"]
    sp = _CFG.get("speaker")
    if sp is not None:
        sp.say(message)
    color = getattr(theme, _KIND[kind][0])
    w = tk.Toplevel(parent)
    w.withdraw()
    w.title(title)
    w.configure(bg=theme.BG)
    w.resizable(False, False)
    if _visible(parent):
        w.transient(parent)
    result = {"v": buttons[-1][1]}  # Esc/Schließen = letzter Knopf (Nein/OK)

    inner = tk.Frame(w, bg=theme.BG, padx=20, pady=16)
    inner.pack(fill="both", expand=True)
    top = tk.Frame(inner, bg=theme.BG)
    top.pack(fill="x")
    img = _icon(64)
    if img is not None:
        tk.Label(top, image=img, bg=theme.BG).pack(side="left", anchor="n", padx=(0, 16))
    txt = tk.Frame(top, bg=theme.BG)
    txt.pack(side="left", fill="both", expand=True)
    hrow = tk.Frame(txt, bg=theme.BG)
    hrow.pack(fill="x")
    tk.Label(hrow, text=_KIND[kind][1], bg=theme.BG, fg=color,
             font=(theme.FAMILY, theme.SIZE + 4, "bold")).pack(side="left", padx=(0, 8))
    tk.Label(hrow, text=heading or title, bg=theme.BG, fg=theme.ACCENT,
             font=(theme.FAMILY, theme.SIZE + 4, "bold"), anchor="w", justify="left").pack(side="left", fill="x")
    tk.Label(txt, text=message, bg=theme.BG, fg=theme.TEXT, font=(theme.FAMILY, theme.SIZE),
             wraplength=520, justify="left", anchor="w").pack(fill="x", pady=(10, 0))

    bar = tk.Frame(inner, bg=theme.BG)
    bar.pack(fill="x", pady=(18, 0))

    def close(v):
        result["v"] = v
        w.destroy()

    # Bei gefährlichen Fragen ist „Nein“ vorausgewählt (Enter löscht nie versehentlich)
    default_value = buttons[-1][1] if danger else buttons[0][1]
    focus_btn = None
    if details:
        info = tk.Label(bar, text="", bg=theme.BG, fg=theme.MUTED)

        def do_copy():
            info.configure(text=tr("Kopiert") if copy_to_clipboard(w, details) else "–")

        ttk.Button(bar, text=tr("Details kopieren"), command=do_copy).pack(side="left")
        info.pack(side="left", padx=8)
    for i, (label, value) in enumerate(reversed(buttons)):
        primary = i == len(buttons) - 1
        style = ("Danger.TButton" if danger else "Accent.TButton") if primary else "TButton"
        b = ttk.Button(bar, text=label, style=style, command=lambda v=value: close(v))
        b.pack(side="right", padx=(8, 0))
        if value == default_value:
            focus_btn = b
    w.bind("<Return>", lambda e: close(default_value))
    w.bind("<KP_Enter>", lambda e: close(default_value))
    w.bind("<Escape>", lambda e: close(buttons[-1][1]))
    w.protocol("WM_DELETE_WINDOW", lambda: close(buttons[-1][1]))

    center(w, parent)
    style_titlebar(w)
    w.deiconify()
    w.lift()
    try:
        w.grab_set()
    except tk.TclError:
        pass
    if focus_btn is not None:
        focus_btn.focus_set()
    w.wait_window()
    return result["v"]


def showinfo(title, message, parent=None, heading: str = "", **_):
    _show(title, message, "info", [("OK", True)], parent, heading)


def showwarning(title, message, parent=None, **_):
    _show(title, message, "warning", [("OK", True)], parent)


def showerror(title, message, parent=None, details: str = "", **_):
    _show(title, message, "error", [("OK", True)], parent, details=details)


def askyesno(title, message, parent=None, icon=None, **_) -> bool:
    danger = icon == "warning"
    return bool(_show(title, message, "warning" if danger else "question", [(tr("Ja"), True), (tr("Nein"), False)],
                      parent, danger=danger))


def icon_path_default() -> str:
    import sys

    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, "assets", "icon.png")
