# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungsdialog: Darstellung & Sprache, Ordnerregeln, Bewertungen, Archiv, Werkzeuge, Leistung."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk

from .. import APP_NAME
from ..core import rules as rules_mod
from ..core import tools
from ..core.archive import HAVE_TRASH
from ..core.fsutil import open_in_file_manager
from ..i18n import LANGUAGES, _
from . import dialogs, theme
from .winstyle import style_titlebar


def THEME_NAMES():
    return {"dark": _("Dunkel (Standard)"), "light": _("Hell"), "contrast": _("Hoher Kontrast")}


class SettingsDialog:
    def _show_tool(self, name: str, info: dict) -> None:
        lbl = self._tool_labels.get(name)
        if lbl is None:
            return
        try:
            sha = info.get("sha256", "")
            lbl.configure(text=_("Version: {v} · SHA-256: {h}").format(v=info.get("version") or "?",
                                                                     h=(sha[:16] + "…" + sha[-8:]) if sha else "–"))
        except tk.TclError:
            pass

    def __init__(self, app):
        self.app = app
        self._tool_labels: dict = {}
        st = app.settings
        w = self.win = tk.Toplevel(app.root)
        w.withdraw()
        w.title(f"{APP_NAME} – " + _("Einstellungen"))
        w.configure(bg=theme.BG)
        w.transient(app.root)
        w.minsize(680, 580)

        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        # ------------------------------------------------ Darstellung, Sprache, Barrierefreiheit
        t = ttk.Frame(nb, style="Panel.TFrame", padding=12)
        nb.add(t, text=_("Darstellung"))
        ttk.Label(t, text=_("Sprache / Language"), style="Section.TLabel").pack(anchor="w")
        self.lang = tk.StringVar(value=st["language"])
        lr = ttk.Frame(t, style="Panel.TFrame")
        lr.pack(anchor="w")
        for k, v in LANGUAGES.items():
            ttk.Radiobutton(lr, text=v, value=k, variable=self.lang).pack(side="left", padx=(0, 12))
        ttk.Label(t, text=_("Farbschema"), style="Section.TLabel").pack(anchor="w", pady=(12, 0))
        self.theme = tk.StringVar(value=st["theme"])
        for k, v in THEME_NAMES().items():
            ttk.Radiobutton(t, text=v, value=k, variable=self.theme).pack(anchor="w")
        ttk.Label(t, text=_("Barrierefreiheit"), style="Section.TLabel").pack(anchor="w", pady=(12, 0))
        self.large = tk.BooleanVar(value=st["large_font"])
        ttk.Checkbutton(t, text=_("Große Schrift"), variable=self.large).pack(anchor="w")
        self.speech = tk.BooleanVar(value=st["speech"])
        sp = ttk.Frame(t, style="Panel.TFrame")
        sp.pack(fill="x")
        ttk.Checkbutton(sp, text=_("Sprachausgabe (Statusmeldungen und Auswahl vorlesen)"),
                        variable=self.speech).pack(side="left")
        ttk.Button(sp, text=_("Testen"), command=self._test_speech).pack(side="left", padx=8)
        if not app.speaker.available:
            ttk.Label(t, text=_("Hinweis: Auf diesem System wurde keine Sprachausgabe gefunden."),
                      style="PanelYellow.TLabel").pack(anchor="w")
        ttk.Label(t, text=_("Tastatur: Tab/Pfeiltasten bewegen · Enter = Vergleich · Leertaste = Behalten ⇄ Archiv · "
                            "F5 = Suche · Strg+F = Filter · Strg+Z = Rückgängig · Bild↑/↓ = Seite"),
                  style="PanelMuted.TLabel", wraplength=600, justify="left").pack(anchor="w", pady=(10, 0))

        # ------------------------------------------------ Ordnerregeln
        t = ttk.Frame(nb, style="Panel.TFrame", padding=12)
        nb.add(t, text=_("Ordnerregeln"))
        ttk.Label(t, text=_("Regeln gelten für identische Duplikate. „Behalten“ gewinnt immer; mindestens eine "
                            "Datei pro Gruppe bleibt erhalten. Ähnliche Bilder werden nie automatisch archiviert."),
                  style="PanelMuted.TLabel", wraplength=600, justify="left").pack(anchor="w")
        self.rules = [dict(r) for r in rules_mod.valid_rules(st["folder_rules"])]
        self._old_rules = [dict(r) for r in self.rules]
        self.rlb = theme.listbox(t, height=8)
        self.rlb.pack(fill="both", expand=True, pady=6)
        rb = ttk.Frame(t, style="Panel.TFrame")
        rb.pack(fill="x")
        ttk.Label(rb, text=_("Muster/Ordner:"), style="Panel.TLabel").pack(side="left")
        self.pattern = tk.StringVar()
        ttk.Entry(rb, textvariable=self.pattern, width=28).pack(side="left", padx=4)
        ttk.Button(rb, text=_("Ordner …"), command=self._pick_rule_dir).pack(side="left")
        rb2 = ttk.Frame(t, style="Panel.TFrame")
        rb2.pack(fill="x", pady=4)
        ttk.Button(rb2, text="✔ " + _("immer behalten"), command=lambda: self._add_rule("keep")).pack(side="left")
        ttk.Button(rb2, text="➜ " + _("immer archivieren"), command=lambda: self._add_rule("archive")).pack(
            side="left", padx=4)
        ttk.Button(rb2, text=_("Entfernen"), command=self._del_rule).pack(side="left")
        ttk.Label(t, text=_("Beispiele: „WhatsApp“, „Downloads“, „Fotos/Best“ oder ein kompletter Ordnerpfad."),
                  style="PanelMuted.TLabel").pack(anchor="w")
        self._fill_rules()

        # ------------------------------------------------ Bewertungen
        t = ttk.Frame(nb, style="Panel.TFrame", padding=12)
        nb.add(t, text=_("Bewertungen"))
        self.use_ratings = tk.BooleanVar(value=st["use_ratings"])
        ttk.Checkbutton(t, text=_("Bewertete Bilder bevorzugt behalten, abgelehnte bevorzugt archivieren"),
                        variable=self.use_ratings).pack(anchor="w")
        ttk.Label(t, text=_("Gelesen werden Sterne, Farbmarkierungen und Flaggen aus XMP-Begleitdateien "
                            "(Lightroom, darktable, Capture One, digiKam) und aus in die Bilder eingebettetem XMP. "
                            "Optional zusätzlich aus einem Lightroom-Classic-Katalog (nur lesend)."),
                  style="PanelMuted.TLabel", wraplength=600, justify="left").pack(anchor="w", pady=(4, 8))
        row = ttk.Frame(t, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text=_("Lightroom-Katalog (.lrcat):"), style="Panel.TLabel").pack(side="left")
        self.lrcat = tk.StringVar(value=st["lrcat_path"])
        ttk.Entry(row, textvariable=self.lrcat).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row, text="…", width=3, command=self._pick_lrcat).pack(side="left")
        ttk.Label(t, text=_("Reihenfolge beim Original: Ordnerregel „behalten“ → Bewertung → gewählte Regel "
                            "(Master, älteste …)."), style="PanelMuted.TLabel", wraplength=600,
                  justify="left").pack(anchor="w", pady=(8, 0))

        # ------------------------------------------------ Archiv & Suche
        t = ttk.Frame(nb, style="Panel.TFrame", padding=12)
        nb.add(t, text=_("Archiv & Suche"))
        row = ttk.Frame(t, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text=_("Archiv-Einträge zur Löschfreigabe vorschlagen nach (Tagen):"),
                  style="Panel.TLabel").pack(side="left")
        self.retention = tk.StringVar(value=str(st["retention_days"]))
        ttk.Spinbox(row, from_=1, to=3650, width=6, textvariable=self.retention).pack(side="left", padx=6)
        self.trash = tk.BooleanVar(value=st["use_recycle_bin"] and HAVE_TRASH)
        ttk.Checkbutton(t, text=_("Endgültig löschen = in den Papierkorb") + ("" if HAVE_TRASH else
                                                                              " " + _("(nicht verfügbar)")),
                        variable=self.trash).pack(anchor="w", pady=(8, 0))
        self.hidden = tk.BooleanVar(value=st["include_hidden"])
        ttk.Checkbutton(t, text=_("Versteckte Dateien/Ordner einbeziehen"), variable=self.hidden).pack(anchor="w")
        row = ttk.Frame(t, style="Panel.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text=_("Mindestgröße (KB):"), style="Panel.TLabel").pack(side="left")
        self.min_kb = tk.StringVar(value=str(st["min_size_kb"]))
        ttk.Spinbox(row, from_=0, to=1_000_000, width=8, textvariable=self.min_kb).pack(side="left", padx=6)

        # ------------------------------------------------ Werkzeuge
        t = ttk.Frame(nb, style="Panel.TFrame", padding=12)
        nb.add(t, text=_("Werkzeuge"))
        self.use_et = tk.BooleanVar(value=st["use_exiftool"])
        ttk.Checkbutton(t, text=_("ExifTool verwenden, wenn vorhanden (vollständige Hersteller-Metadaten)"),
                        variable=self.use_et).pack(anchor="w")
        self.et_path = tk.StringVar(value=st["exiftool_path"])
        self.ff_path = tk.StringVar(value=st["ffmpeg_path"])
        for label, var, name in (("ExifTool:", self.et_path, "exiftool"),
                                 (_("ffmpeg (Video-Vorschau):"), self.ff_path, "ffmpeg")):
            row = ttk.Frame(t, style="Panel.TFrame")
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, style="Panel.TLabel", width=24).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="…", width=3, command=lambda v=var: self._pick_exe(v)).pack(side="left", padx=4)
            found = tools.find(name)
            ttk.Label(t, text=("✔ " + _("gefunden:") + " " + found) if found else "✖ " + _("nicht gefunden – optional"),
                      style="PanelGreen.TLabel" if found else "PanelYellow.TLabel").pack(anchor="w")
            if found:
                info = ttk.Label(t, text=_("Version und Prüfsumme werden ermittelt …"), style="PanelMuted.TLabel")
                info.pack(anchor="w")
                self._tool_labels[name] = info
        ttk.Label(t, text=_("Ohne Pfadangabe wird neben der EXE und im Unterordner „tools“ gesucht (unter Windows aus "
                            "Sicherheitsgründen nicht im Systempfad). Die SHA-256-Prüfsumme lässt sich mit der Angabe "
                            "auf exiftool.org bzw. der ffmpeg-Downloadseite vergleichen."),
                  style="PanelMuted.TLabel", wraplength=600, justify="left").pack(anchor="w", pady=(8, 0))
        for name in list(self._tool_labels):
            app.run_bg(tools.tool_info, (name,), lambda i, n=name: self._show_tool(n, i), lambda e: None)

        # ------------------------------------------------ Wartung & Datenschutz
        t = ttk.Frame(nb, style="Panel.TFrame", padding=12)
        nb.add(t, text=_("Wartung"))
        for label, hint, cmd in (
                (_("Cache bereinigen"), _("entfernt Einträge gelöschter Dateien (automatisch monatlich)"),
                 app.prune_cache),
                (_("Cache leeren"), _("löscht alle Prüfsummen – die nächste Suche dauert länger"), app.clear_cache),
                (_("Alle Cloud-Anmeldungen entfernen"), _("gespeicherte Tokens und pCloud-Client-Secret löschen"),
                 lambda: app.cloud_tab.forget_all() if app.cloud_tab else None),
                (_("Datenordner öffnen"), _("Einstellungen, Cache, Protokoll"),
                 lambda: open_in_file_manager(app.data_dir))):
            row = ttk.Frame(t, style="Panel.TFrame")
            row.pack(fill="x", pady=4)
            ttk.Button(row, text=label, command=cmd, width=32).pack(side="left")
            ttk.Label(row, text=hint, style="PanelMuted.TLabel").pack(side="left", padx=10)

        # ------------------------------------------------ Leistung
        t = ttk.Frame(nb, style="Panel.TFrame", padding=12)
        nb.add(t, text=_("Leistung"))
        row = ttk.Frame(t, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text=_("Parallele Lesevorgänge:"), style="Panel.TLabel").pack(side="left")
        self.workers = tk.StringVar(value=str(st["workers"]))
        ttk.Spinbox(row, from_=1, to=16, width=5, textvariable=self.workers).pack(side="left", padx=6)
        ttk.Label(t, text=_("SSD/Cloud/NAS: 4–8 · einzelne Magnetplatte (USB-HDD): 1–2"),
                  style="PanelMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(t, style="Panel.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=_("Gruppen pro Seite in der Liste:"), style="Panel.TLabel").pack(side="left")
        self.page = tk.StringVar(value=str(st["page_size"]))
        ttk.Spinbox(row, from_=50, to=5000, increment=50, width=6, textvariable=self.page).pack(side="left", padx=6)

        bar = ttk.Frame(w, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text=_("Übernehmen"), style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Button(bar, text=_("Abbrechen"), command=w.destroy).pack(side="right", padx=6)
        w.bind("<Escape>", lambda e: w.destroy())
        style_titlebar(w)
        w.deiconify()
        w.grab_set()

    # ----------------------------------------------------------------
    def _fill_rules(self):
        self.rlb.delete(0, "end")
        for r in self.rules:
            label = "✔ " + _("behalten") if r["action"] == "keep" else "➜ " + _("archivieren")
            self.rlb.insert("end", f"{label}   {r['pattern']}")

    def _pick_rule_dir(self):
        d = filedialog.askdirectory(parent=self.win, title=_("Ordner für Regel wählen"))
        if d:
            self.pattern.set(os.path.abspath(d))

    def _add_rule(self, action):
        p = self.pattern.get().strip()
        if not p:
            return
        self.rules = [r for r in self.rules if r["pattern"].lower() != p.lower()]
        self.rules.append({"pattern": p, "action": action})
        self.pattern.set("")
        self._fill_rules()

    def _del_rule(self):
        for i in reversed(self.rlb.curselection()):
            del self.rules[i]
        self._fill_rules()

    def _pick_exe(self, var):
        f = filedialog.askopenfilename(parent=self.win, title=_("Programm wählen"))
        if f:
            var.set(os.path.abspath(f))

    def _pick_lrcat(self):
        f = filedialog.askopenfilename(parent=self.win, title=_("Lightroom-Katalog wählen"),
                                       filetypes=[("Lightroom", "*.lrcat"), ("*", "*")])
        if f:
            self.lrcat.set(os.path.abspath(f))

    def _test_speech(self):
        was = self.app.speaker.enabled
        self.app.speaker.enabled = True
        self.app.speaker.say(_("Sprachausgabe von BildZwilling ist bereit."))
        self.app.speaker.enabled = was

    @staticmethod
    def _int(v, lo, hi, default):
        try:
            return max(lo, min(hi, int(float(str(v).replace(",", ".")))))
        except ValueError:
            return default

    def save(self):
        st = self.app.settings
        old_lang = st["language"]
        st["language"] = self.lang.get()
        st["theme"] = self.theme.get()
        st["large_font"] = bool(self.large.get())
        st["speech"] = bool(self.speech.get())
        st["folder_rules"] = rules_mod.valid_rules(self.rules)
        st["use_ratings"] = bool(self.use_ratings.get())
        st["lrcat_path"] = self.lrcat.get().strip()
        st["retention_days"] = self._int(self.retention.get(), 1, 3650, 30)
        st["use_recycle_bin"] = bool(self.trash.get())
        st["include_hidden"] = bool(self.hidden.get())
        st["min_size_kb"] = self._int(self.min_kb.get(), 0, 1_000_000, 1)
        st["use_exiftool"] = bool(self.use_et.get())
        st["exiftool_path"] = self.et_path.get().strip()
        st["ffmpeg_path"] = self.ff_path.get().strip()
        st["workers"] = self._int(self.workers.get(), 1, 16, 4)
        st["page_size"] = self._int(self.page.get(), 50, 5000, 300)
        st.save()
        self.app.use_ratings.set(st["use_ratings"])
        self.win.destroy()
        self.app.apply_settings()
        if st["language"] != old_lang:
            dialogs.showinfo(APP_NAME, "Die Sprache wird beim nächsten Programmstart übernommen.\n\n"
                                       "The language will change the next time you start the program.",
                             parent=self.app.root)
        if (self.app.groups and st["folder_rules"] != self._old_rules
                and dialogs.askyesno(APP_NAME, _("Ordnerregeln geändert.\n\nJetzt auf die aktuelle Ergebnisliste "
                                                 "anwenden? (Ihre manuellen Markierungen werden dabei ersetzt.)"),
                                     parent=self.app.root)):
            self.app.reapply_rule()
