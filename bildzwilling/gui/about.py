# SPDX-License-Identifier: GPL-3.0-or-later
"""Info-Fenster, Lizenz-/Drittanbieter-Anzeige und Haftungshinweis beim ersten Start (2.2, A1/A3–A5).

Eigenes Fenster im App-Stil ohne Farbrand: Kopf mit Icon, Name und Version, darunter eine
zweispaltige Übersicht (Beschriftung links, Wert rechts), Haftungshinweis, Fußzeile mit Knöpfen.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from .. import APP_NAME, AUTHOR, BUILD_DATE, COPYRIGHT_SHORT, IMPLEMENTATION, LICENSE_NAME, VERSION
from ..core import imaging
from ..core.fsutil import open_in_file_manager
from ..core.sysinfo import system_info
from ..i18n import _
from ..legal import disclaimer_full, disclaimer_short, license_notice, read_text_file
from . import dialogs, theme
from .winstyle import style_titlebar

TEST_HOOK: dict = {"last": None}  # für automatische Tests: zuletzt geöffnetes Fenster


def _short_path(p: str, n: int = 48) -> str:
    if len(p) <= n:
        return p
    head, tail = os.path.splitdrive(p)[0], p[-(n - 6):]
    cut = tail.find(os.sep)
    return f"{head}{os.sep}…{tail[cut:] if 0 <= cut < 20 else tail}"


def _window(parent, title: str) -> tk.Toplevel:
    w = tk.Toplevel(parent)
    w.withdraw()
    w.title(title)
    w.configure(bg=theme.BG)
    w.resizable(False, False)
    if dialogs._visible(parent):  # noqa: SLF001
        w.transient(parent)
    return w


def _center(w, parent):
    dialogs.center(w, parent)
    style_titlebar(w)
    w.deiconify()
    w.lift()


def show_text(parent, title: str, text: str, heading: str = "") -> tk.Toplevel:
    """Längeren Text (Lizenz, Drittanbieter) in einem lesbaren, scrollbaren Fenster zeigen."""
    w = _window(parent, title)
    w.resizable(True, True)
    outer = tk.Frame(w, bg=theme.BG, padx=22, pady=18)
    outer.pack(fill="both", expand=True)
    tk.Label(outer, text=heading or title, bg=theme.BG, fg=theme.ACCENT,
             font=(theme.FAMILY, theme.SIZE + 5, "bold"), anchor="w").pack(fill="x", pady=(0, 10))
    box = tk.Frame(outer, bg=theme.BG)
    box.pack(fill="both", expand=True)
    t = tk.Text(box, wrap="word", width=92, height=30, bg=theme.FIELD, fg=theme.TEXT, relief="flat",
                padx=12, pady=10, font=(theme.FAMILY, theme.SIZE), insertbackground=theme.TEXT,
                highlightthickness=0, borderwidth=0)
    sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.insert("1.0", text or _("Text nicht gefunden – siehe Projektordner."))
    t.configure(state="disabled")
    sb.pack(side="right", fill="y")
    t.pack(side="left", fill="both", expand=True)
    bar = tk.Frame(outer, bg=theme.BG)
    bar.pack(fill="x", pady=(14, 0))
    ttk.Button(bar, text=_("Schließen"), style="Accent.TButton", command=w.destroy).pack(side="right")
    w.bind("<Escape>", lambda e: w.destroy())
    _center(w, parent)
    TEST_HOOK["last"] = w
    return w


class AboutDialog:
    def __init__(self, app):
        self.app = app
        parent = app.root
        w = self.win = _window(parent, _("Über {a}").format(a=APP_NAME))
        pad = 26
        body = tk.Frame(w, bg=theme.BG)
        body.pack(fill="both", expand=True)

        # Kopf
        head = tk.Frame(body, bg=theme.BG, padx=pad, pady=22)
        head.pack(fill="x")
        img = dialogs._icon(64)  # noqa: SLF001 – gleiches Icon wie in den Meldungen
        if img is not None:
            tk.Label(head, image=img, bg=theme.BG).pack(side="left", padx=(0, 18))
        ht = tk.Frame(head, bg=theme.BG)
        ht.pack(side="left", fill="x")
        tk.Label(ht, text=APP_NAME, bg=theme.BG, fg=theme.ACCENT, font=(theme.FAMILY, theme.SIZE + 12, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(ht, text=_("Version {v} · {d}").format(v=VERSION, d=BUILD_DATE), bg=theme.BG, fg=theme.MUTED,
                 font=(theme.FAMILY, theme.SIZE), anchor="w").pack(fill="x")
        tk.Label(ht, text=_("Doppelte Fotos finden – sicher archivieren."), bg=theme.BG, fg=theme.TEXT,
                 font=(theme.FAMILY, theme.SIZE + 1), anchor="w").pack(fill="x", pady=(4, 0))

        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", padx=pad)

        # Übersicht: Beschriftung links, Wert rechts
        grid = tk.Frame(body, bg=theme.BG, padx=pad, pady=16)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        r = 0

        def row(label: str, widget_factory):
            nonlocal r
            tk.Label(grid, text=label, bg=theme.BG, fg=theme.MUTED, font=(theme.FAMILY, theme.SIZE),
                     anchor="nw").grid(row=r, column=0, sticky="nw", padx=(0, 18), pady=4)
            widget_factory(grid).grid(row=r, column=1, sticky="w", pady=4)
            r += 1

        def text(t, color=None):
            return lambda p: tk.Label(p, text=t, bg=theme.BG, fg=color or theme.TEXT,
                                      font=(theme.FAMILY, theme.SIZE), anchor="w", justify="left")

        def with_link(t, link, cmd):
            def make(p):
                f = tk.Frame(p, bg=theme.BG)
                tk.Label(f, text=t, bg=theme.BG, fg=theme.TEXT, font=(theme.FAMILY, theme.SIZE)).pack(side="left")
                lk = tk.Label(f, text=link, bg=theme.BG, fg=theme.ACCENT, cursor="hand2",
                              font=(theme.FAMILY, theme.SIZE, "underline"))
                lk.pack(side="left", padx=(10, 0))
                lk.bind("<Button-1>", lambda e: cmd())
                return f
            return make

        def comps(p):
            f = tk.Frame(p, bg=theme.BG)
            caps = imaging.capabilities()
            names = {"Pillow": "Pillow", "HEIC/HEIF": "HEIC", "JPEG XL": "JPEG XL", "RAW (rawpy)": "RAW",
                     "FITS (Seestar & Co.)": "FITS", "ExifTool": "ExifTool", "ffmpeg (Video)": "Video"}
            for i, (k, v) in enumerate(caps.items()):
                col, row_ = i % 4, i // 4
                tk.Label(f, text=("✔ " if v else "– ") + str(names.get(k, k)), bg=theme.BG,
                         fg=theme.GREEN if v else theme.MUTED, font=(theme.FAMILY, theme.SIZE),
                         anchor="w").grid(row=row_, column=col, sticky="w", padx=(0, 16))
            return f

        row(_("Idee, Konzept & Prompt"), text(AUTHOR))
        row(_("Umsetzung"), text(IMPLEMENTATION))
        row(_("Lizenz"), with_link(_("{l} oder später").format(l=LICENSE_NAME), _("Lizenztext anzeigen"),
                                   self.show_license))
        row(_("Komponenten"), comps)
        row(_("Datenordner"), with_link(_short_path(app.data_dir), _("Öffnen"),
                                        lambda: open_in_file_manager(app.data_dir)))

        # Haftungshinweis
        disc = tk.Frame(body, bg=theme.PANEL, padx=14, pady=10)
        disc.pack(fill="x", padx=pad, pady=(2, 0))
        tk.Label(disc, text=_("Haftungsausschluss"), bg=theme.PANEL, fg=theme.TEXT,
                 font=(theme.FAMILY, theme.SIZE, "bold"), anchor="w").pack(fill="x")
        tk.Label(disc, text=disclaimer_short(), bg=theme.PANEL, fg=theme.MUTED, font=(theme.FAMILY, theme.SIZE - 1),
                 wraplength=500, justify="left", anchor="w").pack(fill="x", pady=(2, 0))

        # Fuß
        foot = tk.Frame(body, bg=theme.BG, padx=pad, pady=18)
        foot.pack(fill="x")
        tk.Label(foot, text=COPYRIGHT_SHORT, bg=theme.BG, fg=theme.COPY,
                 font=(theme.FAMILY, theme.SIZE - 1)).pack(side="left")
        self.ok_btn = ttk.Button(foot, text="OK", style="Accent.TButton", command=self.close)
        self.ok_btn.pack(side="right")
        ttk.Button(foot, text=_("Drittanbieter"), command=self.show_third_party).pack(side="right", padx=(0, 8))
        self.copy_btn = ttk.Button(foot, text=_("Systeminfo kopieren"), command=self.copy_info)
        self.copy_btn.pack(side="right", padx=(0, 8))

        w.bind("<Escape>", lambda e: self.close())
        w.bind("<Return>", lambda e: self.close())
        w.protocol("WM_DELETE_WINDOW", self.close)
        _center(w, parent)
        try:
            w.grab_set()
        except tk.TclError:
            pass
        self.ok_btn.focus_set()
        TEST_HOOK["last"] = self

    # ------------------------------------------------------------------
    def info_text(self) -> str:
        return system_info(self.app.data_dir, imaging.capabilities())

    def copy_info(self):
        ok = dialogs.copy_to_clipboard(self.win, self.info_text())
        self.copy_btn.configure(text=_("Kopiert ✔") if ok else _("Systeminfo kopieren"))

    def show_license(self):
        text = license_notice() + "\n\n" + disclaimer_full() + "\n\n" + "─" * 60 + "\n\n" + read_text_file("LICENSE")
        show_text(self.win, _("Lizenz"), text, _("Lizenz: {l} oder später").format(l=LICENSE_NAME))

    def show_third_party(self):
        show_text(self.win, _("Drittanbieter"), read_text_file("THIRD_PARTY_LICENSES.txt"),
                  _("Drittanbieter-Komponenten und Lizenzen"))

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass


def show_about(app) -> AboutDialog:
    return AboutDialog(app)


# ---------------------------------------------------------------------------- Haftungshinweis beim ersten Start

DISCLAIMER_TEST_ANSWER: bool | None = None  # für automatische Tests


def ask_disclaimer(parent) -> bool:
    """Haftungshinweis einmalig bestätigen lassen. True = zugestimmt, False = Programm beenden."""
    if DISCLAIMER_TEST_ANSWER is not None:
        return DISCLAIMER_TEST_ANSWER
    if dialogs.TEST_ANSWER is not None:
        return bool(dialogs.TEST_ANSWER)
    w = _window(parent, _("Willkommen bei {a}").format(a=APP_NAME))
    res = {"ok": False}
    outer = tk.Frame(w, bg=theme.BG, padx=26, pady=22)
    outer.pack(fill="both", expand=True)
    head = tk.Frame(outer, bg=theme.BG)
    head.pack(fill="x")
    img = dialogs._icon(64)  # noqa: SLF001
    if img is not None:
        tk.Label(head, image=img, bg=theme.BG).pack(side="left", padx=(0, 16))
    tk.Label(head, text=_("Bitte vor der ersten Nutzung lesen"), bg=theme.BG, fg=theme.ACCENT,
             font=(theme.FAMILY, theme.SIZE + 6, "bold"), anchor="w").pack(side="left")
    tk.Label(outer, text=disclaimer_full(), bg=theme.BG, fg=theme.TEXT, font=(theme.FAMILY, theme.SIZE),
             wraplength=560, justify="left", anchor="w").pack(fill="x", pady=(16, 8))
    tk.Label(outer, text=_("Lizenz: {l} oder später – freie Software, Quellcode im Projekt-ZIP.").format(
        l=LICENSE_NAME), bg=theme.BG, fg=theme.MUTED, font=(theme.FAMILY, theme.SIZE - 1), anchor="w",
        justify="left").pack(fill="x")
    var = tk.BooleanVar(value=False)
    cb = ttk.Checkbutton(outer, text=_("Gelesen und verstanden"), variable=var)
    cb.pack(anchor="w", pady=(14, 0))
    msg = tk.Label(outer, text="", bg=theme.BG, fg=theme.YELLOW, font=(theme.FAMILY, theme.SIZE - 1), anchor="w")
    msg.pack(fill="x")
    bar = tk.Frame(outer, bg=theme.BG)
    bar.pack(fill="x", pady=(12, 0))

    def agree():
        if not var.get():
            msg.configure(text=_("Bitte zuerst „Gelesen und verstanden“ ankreuzen."))
            return
        res["ok"] = True
        w.destroy()

    def quit_():
        res["ok"] = False
        w.destroy()

    ttk.Button(bar, text=_("Zustimmen und starten"), style="Accent.TButton", command=agree).pack(side="right")
    ttk.Button(bar, text=_("Beenden"), command=quit_).pack(side="right", padx=(0, 8))
    ttk.Button(bar, text=_("Lizenztext anzeigen"),
               command=lambda: show_text(w, _("Lizenz"), license_notice() + "\n\n" + read_text_file("LICENSE"))
               ).pack(side="left")
    w.protocol("WM_DELETE_WINDOW", quit_)
    w.bind("<Escape>", lambda e: quit_())
    _center(w, parent)
    try:
        w.grab_set()
    except tk.TclError:
        pass
    cb.focus_set()
    w.wait_window()
    return res["ok"]
