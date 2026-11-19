# SPDX-License-Identifier: GPL-3.0-or-later
"""Farben & ttk-Stil – Dunkelgrau, weiße Schrift, orange Akzente (Stil FotoRahmen/SyncWerk)."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

PALETTES = {
    "dark": dict(BG="#2b2b2b", PANEL="#333333", FIELD="#3c3c3c", BORDER="#4a4a4a", TEXT="#ffffff",
                 MUTED="#b0b0b0", ACCENT="#ff8c00", ACCENT_HOVER="#ffa333", ACCENT_DARK="#cc7000",
                 ON_ACCENT="#000000", GREEN="#4caf50", RED="#e53935", YELLOW="#fdd835", BLUE="#42a5f5",
                 SELECT="#5a4126", CANVAS="#1e1e1e", COPY="#8a8a8a", HOVER="#4a4a4a", DISABLED="#6e6e6e"),
    "light": dict(BG="#f0f0f0", PANEL="#e3e3e3", FIELD="#ffffff", BORDER="#b9b9b9", TEXT="#1a1a1a",
                  MUTED="#555555", ACCENT="#d96f00", ACCENT_HOVER="#f08000", ACCENT_DARK="#a85600",
                  ON_ACCENT="#ffffff", GREEN="#2e7d32", RED="#c62828", YELLOW="#8a6d00", BLUE="#1565c0",
                  SELECT="#ffd9a8", CANVAS="#d6d6d6", COPY="#666666", HOVER="#d4d4d4", DISABLED="#9a9a9a"),
    "contrast": dict(BG="#000000", PANEL="#000000", FIELD="#000000", BORDER="#ffffff", TEXT="#ffffff",
                     MUTED="#ffffff", ACCENT="#ffb000", ACCENT_HOVER="#ffd060", ACCENT_DARK="#ffb000",
                     ON_ACCENT="#000000", GREEN="#00ff66", RED="#ff4040", YELLOW="#ffff00", BLUE="#00e5ff",
                     SELECT="#0000c0", CANVAS="#000000", COPY="#ffffff", HOVER="#303030", DISABLED="#a0a0a0"),
}
THEME_NAMES = {"dark": "Dunkel (Standard)", "light": "Hell", "contrast": "Hoher Kontrast"}

BG = PANEL = FIELD = BORDER = TEXT = MUTED = ACCENT = ACCENT_HOVER = ACCENT_DARK = ON_ACCENT = ""
GREEN = RED = YELLOW = BLUE = SELECT = CANVAS = COPY = HOVER = DISABLED = ""
SIZE = 10
CURRENT = "dark"


def set_palette(name: str = "dark", large: bool = False) -> None:
    """Farbschema und Schriftgröße setzen (wirkt beim nächsten apply())."""
    global SIZE, CURRENT
    CURRENT = name if name in PALETTES else "dark"
    globals().update(PALETTES[CURRENT])
    SIZE = 12 if large else 10


set_palette("dark")

if sys.platform.startswith("win"):
    FAMILY = "Segoe UI"
elif sys.platform == "darwin":
    FAMILY = "Helvetica Neue"
else:
    FAMILY = "DejaVu Sans"


def apply(root: tk.Tk) -> None:
    z = SIZE - 10  # Zuschlag für große Schrift
    root.configure(bg=BG)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=FAMILY, size=SIZE)
        except tk.TclError:
            pass
    root.option_add("*Font", (FAMILY, SIZE))
    # Listen der Comboboxen
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER, troughcolor=PANEL, focuscolor=ACCENT,
                selectbackground=ACCENT, selectforeground=ON_ACCENT, insertcolor=TEXT,
                font=(FAMILY, 10 + z))
    s.configure("TFrame", background=BG)
    s.configure("Panel.TFrame", background=PANEL)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FAMILY, 9 + z))
    s.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=(FAMILY, 9 + z))
    s.configure("Section.TLabel", background=PANEL, foreground=ACCENT, font=(FAMILY, 11 + z, "bold"))
    s.configure("Title.TLabel", background=BG, foreground=ACCENT, font=(FAMILY, 20 + z, "bold"))
    s.configure("Sub.TLabel", background=BG, foreground=MUTED, font=(FAMILY, 10 + z))
    s.configure("Copy.TLabel", background=BG, foreground=COPY, font=(FAMILY, 8 + z))
    for name, col in (("Green", GREEN), ("Red", RED), ("Yellow", YELLOW), ("Blue", BLUE), ("Orange", ACCENT)):
        s.configure(f"{name}.TLabel", background=BG, foreground=col, font=(FAMILY, 10 + z, "bold"))
        s.configure(f"Panel{name}.TLabel", background=PANEL, foreground=col, font=(FAMILY, 10 + z, "bold"))

    s.configure("TButton", background=FIELD, foreground=TEXT, borderwidth=1, padding=(10, 5),
                relief="flat")
    s.map("TButton", background=[("disabled", PANEL), ("pressed", BORDER), ("active", HOVER)],
          foreground=[("disabled", DISABLED)])
    s.configure("Accent.TButton", background=ACCENT, foreground=ON_ACCENT, font=(FAMILY, 10 + z, "bold"),
                padding=(12, 7))
    s.map("Accent.TButton", background=[("disabled", ACCENT_DARK), ("pressed", ACCENT_DARK),
                                        ("active", ACCENT_HOVER)],
          foreground=[("disabled", BG)])
    s.configure("Danger.TButton", background=RED if CURRENT != "dark" else "#5c2523",
                foreground="#ffffff" if CURRENT != "contrast" else "#000000")
    s.map("Danger.TButton", background=[("disabled", PANEL), ("active", RED)])

    for w in ("TCheckbutton", "TRadiobutton"):
        s.configure(w, background=PANEL, foreground=TEXT, indicatorbackground=FIELD,
                    indicatorforeground=ACCENT)
        s.map(w, background=[("active", PANEL)], indicatorbackground=[("selected", ACCENT)],
              foreground=[("disabled", DISABLED)])
    s.configure("Bg.TCheckbutton", background=BG)
    s.map("Bg.TCheckbutton", background=[("active", BG)])
    s.configure("TEntry",fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT)
    s.configure("TSpinbox", fieldbackground=FIELD, foreground=TEXT, arrowcolor=TEXT,
                background=FIELD)
    s.configure("TCombobox", fieldbackground=FIELD, foreground=TEXT, arrowcolor=TEXT,
                background=FIELD)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
          selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)])

    s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(16, 7),
                font=(FAMILY, 10 + z, "bold"))
    s.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])

    s.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=TEXT,
                rowheight=24, borderwidth=0)
    s.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
    s.configure("TScale", background=PANEL, troughcolor=FIELD)
    s.configure("Horizontal.TScale", background=ACCENT, troughcolor=FIELD, bordercolor=BORDER)
    s.configure("TLabelframe", background=PANEL, bordercolor=BORDER)
    s.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT, font=(FAMILY, 10 + z, "bold"))
    s.configure("Treeview.Heading", background=PANEL, foreground=ACCENT, relief="flat",
                font=(FAMILY, 9 + z, "bold"))
    s.map("Treeview.Heading", background=[("active", BORDER)])

    s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL,
                bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT_DARK)
    s.configure("TScrollbar", background=PANEL, troughcolor=BG, arrowcolor=MUTED, bordercolor=BG)
    s.map("TScrollbar", background=[("active", BORDER)])
    s.configure("TPanedwindow", background=BG)
    s.configure("Sash", sashthickness=6, gripcount=0, background=BG)


def recolor_listbox(lb: tk.Listbox) -> None:
    lb.configure(bg=FIELD, fg=TEXT, selectbackground=ACCENT, selectforeground=ON_ACCENT,
                 highlightbackground=BORDER, highlightcolor=ACCENT, font=(FAMILY, SIZE))


def recolor_text(t: tk.Text) -> None:
    t.configure(bg=FIELD, fg=TEXT, insertbackground=TEXT, font=(FAMILY, SIZE))
    for tag, col in (("info", TEXT), ("ok", GREEN), ("warn", YELLOW), ("error", RED), ("blue", BLUE),
                     ("time", MUTED)):
        t.tag_configure(tag, foreground=col)


def listbox(parent, **kw) -> tk.Listbox:
    return tk.Listbox(parent, bg=FIELD, fg=TEXT, selectbackground=ACCENT, selectforeground=ON_ACCENT,
                      highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
                      relief="flat", activestyle="none", **kw)


def text(parent, **kw) -> tk.Text:
    t = tk.Text(parent, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                highlightthickness=0, wrap="word", **kw)
    t.tag_configure("info", foreground=TEXT)
    t.tag_configure("ok", foreground=GREEN)
    t.tag_configure("warn", foreground=YELLOW)
    t.tag_configure("error", foreground=RED)
    t.tag_configure("blue", foreground=BLUE)
    t.tag_configure("time", foreground=MUTED)
    return t
