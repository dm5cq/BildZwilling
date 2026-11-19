# SPDX-License-Identifier: GPL-3.0-or-later
"""Großansicht eines Bildes (Klick auf die Vorschau) – mit SCHLIESSEN-Knopf, Esc und Zoom 100 %."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ..core import imaging
from ..core.fsutil import human_size, lp
from ..i18n import _
from . import theme
from .winstyle import style_titlebar


class ImageViewer:
    """Einzelfenster: es gibt immer nur eine Großansicht; erneuter Aufruf zeigt das neue Bild darin."""

    def __init__(self, app):
        self.app = app
        self.path = ""
        self.pil: Image.Image | None = None
        self.photo = None
        self.zoom = "fit"
        self.token = 0
        self.message = ""
        w = self.win = tk.Toplevel(app.root)
        w.withdraw()
        w.title("BildZwilling – " + _("Großansicht"))
        w.configure(bg=theme.BG)
        try:
            sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
            w.geometry(f"{int(sw * 0.85)}x{int(sh * 0.85)}+{int(sw * 0.075)}+{int(sh * 0.05)}")
        except (tk.TclError, TypeError):
            w.geometry("1400x900")
        top = ttk.Frame(w, padding=(12, 10, 12, 6))
        top.pack(fill="x")
        self.title = ttk.Label(top, text="", style="Orange.TLabel")
        self.title.pack(side="left")
        self.info = ttk.Label(top, text="", style="Muted.TLabel")
        self.info.pack(side="left", padx=12)
        self.canvas = tk.Canvas(w, bg=theme.CANVAS, highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True, padx=12)
        bar = ttk.Frame(w, padding=12)
        bar.pack(fill="x")
        self.zoom_btn = ttk.Button(bar, text="🔍 100 %", command=self.toggle_zoom)
        self.zoom_btn.pack(side="left")
        ttk.Label(bar, text=_("Esc = schließen · Doppelklick/Z = Zoom · Ziehen = verschieben"),
                  style="Muted.TLabel").pack(side="left", padx=12)
        self.close_btn = ttk.Button(bar, text=_("SCHLIESSEN"), style="Accent.TButton", command=self.close)
        self.close_btn.pack(side="right")
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Double-Button-1>", lambda e: self.toggle_zoom())
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", self._drag)
        w.bind("<Escape>", lambda e: self.close())
        w.bind("<z>", lambda e: self.toggle_zoom())
        w.protocol("WM_DELETE_WINDOW", self.close)
        style_titlebar(w)

    def show(self, path: str, max_side: int = 4096):
        self.path = path
        self.token += 1
        tok = self.token
        self.pil = None
        self.zoom = "fit"
        self.zoom_btn.configure(text="🔍 100 %")
        self.title.configure(text=os.path.basename(path))
        try:
            size = human_size(os.path.getsize(lp(path)))
        except OSError:
            size = ""
        self.info.configure(text=f"{os.path.dirname(path)}  ·  {size}")
        self.message = _("Lade …")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.close_btn.focus_set()
        self.redraw()

        def done(res):
            if tok == self.token and self.win.winfo_exists():
                self.pil = res[0]
                self.info.configure(text=self.info.cget("text") + f"  ·  {res[0].size[0]}×{res[0].size[1]}  ·  {res[1]}")
                self.redraw()

        def fail(e):
            if tok == self.token and self.win.winfo_exists():
                self.message = str(e)
                self.redraw()

        self.app.run_bg(imaging.load_preview, (path, max_side), done, fail)

    def redraw(self):
        c = self.canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        if self.pil is None:
            c.create_text(w // 2, h // 2, text=self.message, fill=theme.MUTED, width=w - 40,
                          font=(theme.FAMILY, theme.SIZE + 2))
            return
        iw, ih = self.pil.size
        if self.zoom == "fit":
            scale = min(w / iw, h / ih, 1.0)
            img = self.pil.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(img)
            c.create_image(w // 2, h // 2, image=self.photo, anchor="center")
            c.configure(scrollregion=(0, 0, w, h))
        else:
            self.photo = ImageTk.PhotoImage(self.pil)
            c.create_image(0, 0, image=self.photo, anchor="nw")
            c.configure(scrollregion=(0, 0, iw, ih))

    def toggle_zoom(self):
        self.zoom = "100" if self.zoom == "fit" else "fit"
        self.zoom_btn.configure(text="⤢ " + _("Einpassen") if self.zoom == "100" else "🔍 100 %")
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.redraw()

    def _drag(self, e):
        if self.zoom != "fit":
            self.canvas.scan_dragto(e.x, e.y, gain=1)

    def close(self):
        """SCHLIESSEN: Großansicht ausblenden – die kleine Vorschau bleibt wie vorher."""
        self.token += 1
        self.pil = None
        self.photo = None
        self.win.withdraw()
        self.app.root.focus_force()


def open_viewer(app, path: str):
    v = getattr(app, "viewer", None)
    try:
        if v is None or not v.win.winfo_exists():
            v = app.viewer = ImageViewer(app)
    except tk.TclError:
        v = app.viewer = ImageViewer(app)
    v.show(path)
