# SPDX-License-Identifier: GPL-3.0-or-later
"""Vergleichsfenster: zwei Bilder nebeneinander, synchroner Zoom/Pan, EXIF-Gegenüberstellung,
Byte- und Pixelprüfung, Original festlegen."""

from __future__ import annotations

import datetime as _dt
import os
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ..core import exifinfo, imaging
from ..core.archive import files_identical
from ..core.fsutil import human_size, lp, open_in_file_manager
from ..i18n import _
from . import theme
from .winstyle import style_titlebar

PREVIEW_SIDE = 4096


class ImagePane:
    def __init__(self, parent, title: str, on_keep, on_reveal):
        self.frame = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        top = ttk.Frame(self.frame, style="Panel.TFrame")
        top.pack(fill="x")
        self.title = ttk.Label(top, text=title, style="PanelOrange.TLabel")
        self.title.pack(side="left")
        self.badge = ttk.Label(top, text="", style="PanelGreen.TLabel")
        self.badge.pack(side="right")
        self.info = ttk.Label(self.frame, text="", style="PanelMuted.TLabel", justify="left")
        self.info.pack(fill="x", pady=(4, 6))
        self.canvas = tk.Canvas(self.frame, bg=theme.CANVAS, highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        bar = ttk.Frame(self.frame, style="Panel.TFrame")
        bar.pack(fill="x", pady=(6, 0))
        self.keep_btn = ttk.Button(bar, text="★ " + _("Als Original behalten"), command=on_keep)
        self.keep_btn.pack(side="left")
        ttk.Button(bar, text=_("Im Ordner zeigen"), command=on_reveal).pack(side="left", padx=6)
        self.pil = None
        self.photo = None
        self._fit_cache = None
        self.zoom = "fit"
        self.message = _("Lade …")
        self.canvas.bind("<Configure>", lambda e: self.redraw())

    def set_image(self, pil, extra: str = ""):
        self.pil = pil
        self._fit_cache = None
        self.message = ""
        if extra:
            self.info.configure(text=self.info.cget("text") + "\n" + _("Vorschau:") + f" {extra}")
        self.redraw()

    def set_message(self, msg: str):
        self.pil = None
        self._fit_cache = None
        self.message = msg
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        if self.pil is None:
            c.create_text(w // 2, h // 2, text=self.message, fill=theme.MUTED, width=w - 40,
                          font=(theme.FAMILY, 11))
            c.configure(scrollregion=(0, 0, w, h))
            return
        iw, ih = self.pil.size
        if self.zoom == "fit":
            scale = min(w / iw, h / ih, 1.0)
            size = (max(1, int(iw * scale)), max(1, int(ih * scale)))
            if not self._fit_cache or self._fit_cache[0] != size:
                img = self.pil.resize(size, Image.Resampling.BILINEAR, reducing_gap=2.0)
                self._fit_cache = (size, ImageTk.PhotoImage(img))
            self.photo = self._fit_cache[1]
            c.create_image(w // 2, h // 2, image=self.photo, anchor="center")
            c.configure(scrollregion=(0, 0, w, h))
            c.xview_moveto(0)
            c.yview_moveto(0)
        else:
            self.photo = ImageTk.PhotoImage(self.pil)
            c.create_image(0, 0, image=self.photo, anchor="nw")
            c.configure(scrollregion=(0, 0, iw, ih))


class CompareWindow:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.title("BildZwilling – " + _("Vergleich"))
        self.win.configure(bg=theme.BG)
        try:
            self.win.iconphoto(False, app._icon)
        except (tk.TclError, AttributeError):
            pass
        self.win.geometry("1400x900")
        self.win.minsize(900, 600)
        self.mode = "group"
        self.gi = 0
        self.li = 0
        self.ri = 1
        self.paths = ("", "")
        self.token = 0
        self.exif = [None, None]
        self._build()
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.bind("<Prior>", lambda e: self.step(-1))
        self.win.bind("<Next>", lambda e: self.step(1))
        self.win.bind("<z>", lambda e: self.toggle_zoom())
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        style_titlebar(self.win)
        self.win.deiconify()

    # ------------------------------------------------------------------ Aufbau
    def _build(self):
        bar = ttk.Frame(self.win, padding=(10, 8))
        bar.pack(fill="x")
        self.prev_btn = ttk.Button(bar, text="◀ " + _("Gruppe"), command=lambda: self.step(-1))
        self.prev_btn.pack(side="left")
        self.pos = ttk.Label(bar, text="", style="Orange.TLabel")
        self.pos.pack(side="left", padx=10)
        self.next_btn = ttk.Button(bar, text=_("Gruppe") + " ▶", command=lambda: self.step(1))
        self.next_btn.pack(side="left")
        ttk.Label(bar, text="  " + _("Links:")).pack(side="left")
        self.cb_l = ttk.Combobox(bar, state="readonly", width=34)
        self.cb_l.pack(side="left", padx=4)
        ttk.Label(bar, text=_("Rechts:")).pack(side="left")
        self.cb_r = ttk.Combobox(bar, state="readonly", width=34)
        self.cb_r.pack(side="left", padx=4)
        self.cb_l.bind("<<ComboboxSelected>>", lambda e: self._pick())
        self.cb_r.bind("<<ComboboxSelected>>", lambda e: self._pick())

        bar2 = ttk.Frame(self.win, padding=(10, 0, 10, 6))
        bar2.pack(fill="x")
        self.zoom_btn = ttk.Button(bar2, text="🔍 100 %", command=self.toggle_zoom)
        self.zoom_btn.pack(side="left")
        ttk.Button(bar2, text=_("Byte-Vergleich"), command=self.byte_check).pack(side="left", padx=6)
        ttk.Button(bar2, text=_("Pixel-Vergleich"), command=self.pixel_check).pack(side="left")
        self.only_diff = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text=_("EXIF: nur Unterschiede"), variable=self.only_diff,
                        command=self._fill_exif, style="Bg.TCheckbutton").pack(side="left", padx=12)
        self.result = ttk.Label(bar2, text="", style="Blue.TLabel")
        self.result.pack(side="left", padx=10)
        ttk.Label(bar2, text=_("Ziehen = verschieben · Doppelklick/Z = Zoom · Bild↑/↓ = Gruppe"),
                  style="Muted.TLabel").pack(side="right")

        pw = ttk.PanedWindow(self.win, orient="vertical")
        pw.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        imgs = ttk.Frame(pw)
        imgs.columnconfigure(0, weight=1, uniform="p")
        imgs.columnconfigure(1, weight=1, uniform="p")
        imgs.rowconfigure(0, weight=1)
        self.panes = [
            ImagePane(imgs, "LINKS", lambda: self.keep(0), lambda: self.reveal(0)),
            ImagePane(imgs, "RECHTS", lambda: self.keep(1), lambda: self.reveal(1)),
        ]
        self.panes[0].frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.panes[1].frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        for p in self.panes:
            p.canvas.bind("<ButtonPress-1>", self._mark)
            p.canvas.bind("<B1-Motion>", self._drag)
            p.canvas.bind("<Double-Button-1>", lambda e: self.toggle_zoom())
        pw.add(imgs, weight=4)

        ex = ttk.Frame(pw)
        cols = ("feld", "links", "rechts")
        self.tree = ttk.Treeview(ex, columns=cols, show="headings", height=8)
        for c, t, wdt in zip(cols, (_("Feld"), _("Links"), _("Rechts")), (230, 420, 420)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=wdt, anchor="w", stretch=(c != "feld"))
        self.tree.tag_configure("diff", foreground=theme.YELLOW)
        self.tree.tag_configure("same", foreground=theme.TEXT)
        sb = ttk.Scrollbar(ex, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        pw.add(ex, weight=1)

    # ------------------------------------------------------------------ Anzeige
    def _label(self, f) -> str:
        return f"{os.path.basename(f.path)}  ({os.path.basename(os.path.dirname(f.path))})"

    def show_group(self, gi: int, li: int = 0, ri: int = 1):
        groups = self.app.groups
        if not groups:
            return
        self.mode = "group"
        self.gi = max(0, min(gi, len(groups) - 1))
        g = groups[self.gi]
        n = len(g.files)
        self.li, self.ri = min(li, n - 1), min(ri, n - 1)
        if self.li == self.ri:
            self.ri = (self.li + 1) % n
        vals = [f"{i + 1}: {self._label(f)}" for i, f in enumerate(g.files)]
        self.cb_l.configure(values=vals, state="readonly")
        self.cb_r.configure(values=vals, state="readonly")
        self.cb_l.current(self.li)
        self.cb_r.current(self.ri)
        kind = {"bytes": _("byte-identisch"), "pixels": _("Bildinhalt identisch")}.get(
            g.kind, _("ÄHNLICH (Abstand {d}) – nicht identisch, bitte genau prüfen").format(d=g.distance))
        view = self.app.view or list(range(len(groups)))
        pos = view.index(self.gi) if self.gi in view else -1
        self.pos.configure(text=_("Gruppe {g} · {p} / {v} · {n} Dateien · {k}").format(
                               g=self.gi + 1, p=pos + 1, v=len(view), n=n, k=kind),
                           style="Blue.TLabel" if g.kind == "similar" else "Orange.TLabel")
        self.prev_btn.state(["!disabled"] if pos > 0 else ["disabled"])
        self.next_btn.state(["!disabled"] if 0 <= pos < len(view) - 1 else ["disabled"])
        for p in self.panes:
            p.keep_btn.state(["!disabled"])
        self.paths = (g.files[self.li].path, g.files[self.ri].path)
        self._load()
        self.win.lift()

    def show_paths(self, a: str, b: str, ta: str, tb: str):
        self.mode = "paths"
        self.paths = (a, b)
        self.cb_l.configure(values=[ta], state="disabled")
        self.cb_r.configure(values=[tb], state="disabled")
        self.cb_l.current(0)
        self.cb_r.current(0)
        self.pos.configure(text=_("Archiv-Vergleich"))
        self.prev_btn.state(["disabled"])
        self.next_btn.state(["disabled"])
        for p in self.panes:
            p.keep_btn.state(["disabled"])
        self.panes[0].title.configure(text=ta.upper())
        self.panes[1].title.configure(text=tb.upper())
        self._load()
        self.win.lift()

    def _valid(self) -> bool:
        groups = self.app.groups
        return (self.mode == "group" and self.gi < len(groups)
                and max(self.li, self.ri) < len(groups[self.gi].files))

    def refresh(self):
        """Nach Änderungen an der Ergebnisliste aufrufen."""
        if self.mode != "group":
            return
        if not self.app.groups:
            self.close()
        elif self._valid() and self.paths == (self.app.groups[self.gi].files[self.li].path,
                                               self.app.groups[self.gi].files[self.ri].path):
            self._badges()
        else:
            self.show_group(min(self.gi, len(self.app.groups) - 1), 0, 1)

    def _badges(self):
        if not self._valid():
            for p in self.panes:
                p.badge.configure(text="")
            return
        g = self.app.groups[self.gi]
        for p, idx in ((self.panes[0], self.li), (self.panes[1], self.ri)):
            f = g.files[idx]
            if f.action == "keep":
                p.badge.configure(text="✔ " + _("BEHALTEN"), style="PanelGreen.TLabel")
            else:
                p.badge.configure(text="➜ " + _("ARCHIV"), style="PanelOrange.TLabel")

    def _file_text(self, path: str) -> str:
        try:
            st = os.stat(lp(path))
            date = _dt.datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M")
            return (f"{os.path.basename(path)}\n{os.path.dirname(path)}\n{human_size(st.st_size)} · "
                    + _("geändert {d}").format(d=date))
        except OSError:
            return f"{path}\n(" + _("nicht erreichbar") + ")"

    def _load(self):
        self.token += 1
        tok = self.token
        self.exif = [None, None]
        self.result.configure(text="", style="Blue.TLabel")
        if self.mode == "group":
            self.panes[0].title.configure(text="LINKS")
            self.panes[1].title.configure(text="RECHTS")
        self._badges()
        self.tree.delete(*self.tree.get_children())
        for side, path in enumerate(self.paths):
            pane = self.panes[side]
            pane.info.configure(text=self._file_text(path))
            pane.canvas.configure(bg=theme.CANVAS)
            pane.set_message(_("Lade Vorschau …"))

            def done_img(res, side=side):
                if tok == self.token and self.win.winfo_exists():
                    self.panes[side].set_image(res[0], res[1])

            def fail_img(err, side=side):
                if tok == self.token and self.win.winfo_exists():
                    self.panes[side].set_message(str(err))

            def done_exif(rows, side=side):
                if tok == self.token and self.win.winfo_exists():
                    self.exif[side] = rows
                    self._fill_exif()

            self.app.run_bg(imaging.load_preview, (path, PREVIEW_SIDE), done_img, fail_img)
            self.app.run_bg(exifinfo.read_exif, (path,), done_exif, lambda e: None)

    def _fill_exif(self):
        self.tree.delete(*self.tree.get_children())
        if self.exif[0] is None and self.exif[1] is None:
            return
        left = dict(self.exif[0] or [])
        right = dict(self.exif[1] or [])
        keys = [k for k, _v in (self.exif[0] or [])]
        keys += [k for k, _v in (self.exif[1] or []) if k not in left]
        for k in keys:
            a, b = left.get(k, "—"), right.get(k, "—")
            diff = a != b
            if self.only_diff.get() and not diff:
                continue
            self.tree.insert("", "end", values=(k, a, b), tags=("diff" if diff else "same",))

    # ------------------------------------------------------------------ Aktionen
    def _pick(self):
        if self.mode == "group":
            self.show_group(self.gi, self.cb_l.current(), self.cb_r.current())

    def step(self, d: int):
        if self.mode == "group" and self.app.groups:
            view = self.app.view or list(range(len(self.app.groups)))
            pos = view.index(self.gi) if self.gi in view else -1
            np_ = pos + d
            if 0 <= np_ < len(view):
                self.show_group(view[np_], 0, 1)

    def toggle_zoom(self):
        z = "100" if self.panes[0].zoom == "fit" else "fit"
        for p in self.panes:
            p.zoom = z
            p.redraw()
            p.canvas.xview_moveto(0)
            p.canvas.yview_moveto(0)
        self.zoom_btn.configure(text="⤢ " + _("Einpassen") if z == "100" else "🔍 100 %")

    def _mark(self, e):
        for p in self.panes:
            p.canvas.scan_mark(e.x, e.y)

    def _drag(self, e):
        if self.panes[0].zoom == "fit":
            return
        for p in self.panes:
            p.canvas.scan_dragto(e.x, e.y, gain=1)

    def keep(self, side: int):
        if not self._valid():
            return
        g = self.app.groups[self.gi]
        idx = self.li if side == 0 else self.ri
        self.app.set_original(self.gi, idx)
        self._badges()
        self.result.configure(text=_("„{n}“ wird behalten, übrige Dateien der Gruppe → Archiv").format(
            n=os.path.basename(g.files[idx].path)), style="Green.TLabel")

    def reveal(self, side: int):
        try:
            open_in_file_manager(self.paths[side])
        except OSError as e:
            self.result.configure(text=_("Öffnen nicht möglich: {e}").format(e=e), style="Red.TLabel")

    def _result(self, text, style):
        self.result.configure(text=text, style=style)
        self.app.speaker.say(text.lstrip("✔✖ "))

    def byte_check(self):
        a, b = self.paths
        tok = self.token
        self.result.configure(text=_("Byte-Vergleich läuft …"), style="Blue.TLabel")

        def done(same):
            if tok == self.token and self.win.winfo_exists():
                self._result("✔ " + _("Dateien sind Byte für Byte identisch") if same
                             else "✖ " + _("Dateien unterscheiden sich (Bytes)"), "Green.TLabel" if same else "Red.TLabel")

        def fail(err):
            if tok == self.token and self.win.winfo_exists():
                self.result.configure(text=_("Fehler: {e}").format(e=err), style="Red.TLabel")

        self.app.run_bg(files_identical, (a, b), done, fail)

    def pixel_check(self):
        a, b = self.paths
        tok = self.token
        self.result.configure(text=_("Pixel-Vergleich läuft …"), style="Blue.TLabel")

        def done(res):
            if tok == self.token and self.win.winfo_exists():
                ok, msg = res
                style = "Green.TLabel" if ok else ("Yellow.TLabel" if ok is None else "Red.TLabel")
                self._result(("✔ " if ok else "✖ ") + _(msg), style)

        self.app.run_bg(imaging.compare_pixels, (a, b), done,
                        lambda e: self.result.configure(text=_("Fehler: {e}").format(e=e), style="Red.TLabel"))

    def close(self):
        self.token += 1
        self.app.compare_win = None
        self.win.destroy()
