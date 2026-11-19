# SPDX-License-Identifier: GPL-3.0-or-later
"""Hauptfenster von BildZwilling 2.0."""

from __future__ import annotations

import datetime as _dt
import logging
import os
import queue
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from tkinter import filedialog, ttk

from PIL import ImageTk

from .. import APP_NAME, COPYRIGHT, VERSION
from ..core import htmlreport, imaging, maintenance, report, tools
from ..core.instance import InstanceLock
from ..core.logutil import RedactFilter
from ..core.power import keep_awake
from ..core.archive import HAVE_TRASH, ArchiveError, ArchiveManager
from ..core.formats import file_type
from ..core.fsutil import IS_MAC, human_size, is_within, num, open_in_file_manager
from ..core.hashcache import open_cache
from ..core.plan import PairFinder, plan_archive
from ..core.rules import valid_rules
from ..core.scanner import (ScanCancelled, ScanOptions, Scanner, apply_keep_rule, similar_groups,
                            validate_options)
from ..core.settings import Settings
from ..i18n import _, set_language
from . import about, dialogs, theme
from .compare import CompareWindow
from .settings_dialog import SettingsDialog
from .speech import Speaker
from .winstyle import style_titlebar


def KEEP_RULES():
    return {
        "first_root": _("Erster Bildordner (Master), dann älteste"),
        "oldest": _("Älteste Datei"),
        "newest": _("Neueste Datei"),
        "shortest_path": _("Kürzester Pfad"),
    }


def KIND_TEXT():
    return {"bytes": _("byte-identisch"), "pixels": _("Bildinhalt identisch"), "similar": _("ähnlich")}


def KIND_FILTER():
    return {_("Alle Arten"): None, _("Byte-identisch"): "bytes", _("Bildinhalt identisch"): "pixels",
            _("Ähnlich"): "similar"}


TYPES = ["RAW", "FITS", "JPEG", "HEIC", "Video", "Andere"]
LEVEL_TAG = {"info": "info", "ok": "ok", "warn": "warn", "error": "error", "blue": "blue"}


def SORTS():
    return [_("Ersparnis ↓"), _("Dateigröße ↓"), _("Anzahl Dateien ↓"), _("Dateiname"), _("Ordner")]


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, rel)


class App:
    def __init__(self):
        self.settings = Settings()
        set_language(self.settings["language"])
        theme.set_palette(self.settings["theme"], self.settings["large_font"])
        self.root = tk.Tk()
        self.root.withdraw()
        theme.apply(self.root)
        self.data_dir = os.path.dirname(self.settings.path)
        self._setup_logging()
        self._configure_tools()
        self.speaker = Speaker()
        self.speaker.enabled = bool(self.settings["speech"])
        self.cache = open_cache(os.path.join(self.data_dir, "hashcache.sqlite"))
        self.q: queue.Queue = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="bz-ui")
        self.groups = []
        self.similar_items = []
        self.view: list[int] = []
        self.page = 0
        self._rendered: set[str] = set()
        self.archive_entries = []
        self.busy = False
        self.closing = False
        self.cancel_ev = threading.Event()
        self.compare_win: CompareWindow | None = None
        self._preview_token = 0
        self._preview_photo = None
        self._preview_after = None
        self._filter_after = None
        self._regroup_after = None
        self._regroup_token = 0
        self.seestar_tab = None
        self.cloud_tab = None

        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.geometry(self.settings.get("geometry", "1400x880"))
        self.root.minsize(1150, 720)
        try:
            self._icon = tk.PhotoImage(file=resource_path(os.path.join("assets", "icon.png")))
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        dialogs.setup(self.root, resource_path(os.path.join("assets", "icon.png")), self.speaker)
        self._startup_checks()
        self._build()
        self._load_settings_into_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if IS_MAC:
            self.root.createcommand("tk::mac::Quit", self.on_close)
        self.root.bind("<F5>", lambda e: self.start_scan())
        self.root.bind("<Control-f>", lambda e: self.filter_entry.focus_set())
        self.root.bind("<Control-z>", lambda e: self.undo_last())
        self.root.after(80, self._poll)
        style_titlebar(self.root)
        self.root.deiconify()
        caps = ", ".join(f"{k}: {_('ja') if v else _('nein')}" for k, v in imaging.capabilities().items())
        self.log("blue", f"{APP_NAME} {VERSION} · {caps}")
        self.log("info", _("Daten/Einstellungen: {p}").format(p=self.data_dir))
        if self.settings.recovered:
            self.log("warn", _("Einstellungen waren beschädigt – {w} wurde verwendet (alte Datei: settings.json.defekt).")
                     .format(w=_("die Sicherung") if self.settings.recovered == "backup" else _("Standardwerte")))
        if self.settings["archive_dir"]:
            self.reload_archive(startup=True)
        self.root.after(1500, self._maintenance)

    # ================================================================== Start & Wartung (2.2)
    def _startup_checks(self):
        """Nur eine Instanz (B1) und Haftungshinweis beim ersten Start (A5)."""
        self.instance = InstanceLock(self.data_dir)
        if not self.instance.acquire():
            dialogs.showwarning(APP_NAME, _("{a} läuft bereits.\n\nZwei gleichzeitig laufende Programme könnten sich "
                                            "beim Archiv und Cache in die Quere kommen. Bitte das bereits geöffnete "
                                            "Fenster verwenden.").format(a=APP_NAME), parent=self.root)
            self._abort_start()
        if self.settings["disclaimer_ok"] != VERSION.split(".")[0]:
            if not about.ask_disclaimer(self.root):
                self._abort_start()
            self.settings["disclaimer_ok"] = VERSION.split(".")[0]
            self.settings.save()

    def _abort_start(self):
        try:
            self.cache.close()
        except Exception:  # noqa: BLE001
            pass
        self.instance.release()
        self.root.destroy()
        raise SystemExit(0)

    def _maintenance(self):
        """Temp-Reste löschen, Cache monatlich bereinigen (C7) – im Hintergrund, ohne die Bedienung zu sperren."""
        due = maintenance.prune_due(self.settings["cache_pruned"])

        def job():
            n_tmp = maintenance.cleanup_temp()
            n_cache = self.cache.prune() if due else -1
            return n_tmp, n_cache

        def done(res):
            n_tmp, n_cache = res
            if n_tmp:
                self.log("info", _("{n} alte temporäre Vorschau-Ordner entfernt.").format(n=n_tmp))
            if n_cache >= 0:
                self.settings["cache_pruned"] = maintenance.today()
                if n_cache:
                    self.log("info", _("Prüfsummen-Cache bereinigt: {n} Einträge gelöschter Dateien entfernt.").format(
                        n=num(n_cache)))

        self.run_bg(job, (), done, lambda e: self.logger.warning("Wartung: %s", e))

    def prune_cache(self):
        if self.busy:
            return
        self.set_status(_("Prüfsummen-Cache wird bereinigt …"), "Blue")

        def done(n):
            self.settings["cache_pruned"] = maintenance.today()
            self.set_status(_("Prüfsummen-Cache bereinigt: {n} Einträge gelöschter Dateien entfernt.").format(
                n=num(n)), "Green")

        self.run_bg(self.cache.prune, (), done, lambda e: self.set_status(_("Fehler: {e}").format(e=e), "Red"))

    # ================================================================== Infrastruktur
    def _setup_logging(self):
        self.logger = logging.getLogger("bildzwilling")
        self.logger.setLevel(logging.INFO)
        try:
            h = RotatingFileHandler(os.path.join(self.data_dir, "BildZwilling.log"),
                                    maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            h.addFilter(RedactFilter())  # 2.2, B4: keine E-Mail-Adressen/Tokens im Protokoll
            self.logger.addHandler(h)
        except OSError:
            pass

    def _configure_tools(self):
        st = self.settings
        tools.configure(exiftool=st["exiftool_path"], ffmpeg=st["ffmpeg_path"], use_exiftool=st["use_exiftool"])

    def ui(self, fn, *args):
        """Funktion im GUI-Thread ausführen (aus beliebigem Thread aufrufbar)."""
        self.q.put((fn, args))

    def log(self, level: str, msg: str):
        self.ui(self._append_log, level, msg)
        lvl = {"warn": logging.WARNING, "error": logging.ERROR}.get(level, logging.INFO)
        self.logger.log(lvl, msg)

    def run_bg(self, fn, args, on_done, on_error):
        def task():
            try:
                res = fn(*args)
            except Exception as e:  # noqa: BLE001
                self.ui(on_error, e)
            else:
                self.ui(on_done, res)

        self.pool.submit(task)

    def _poll(self):
        try:
            for _i in range(400):
                fn, args = self.q.get_nowait()
                try:
                    fn(*args)
                except tk.TclError:
                    pass
                except Exception as e:  # noqa: BLE001
                    self.logger.exception("UI-Fehler")
                    try:
                        self._append_log("error", _("Interner Fehler: {e}").format(e=e))
                    except Exception:  # noqa: BLE001
                        pass
        except queue.Empty:
            pass
        if not self.closing or self.busy:
            self.root.after(60, self._poll)

    # ================================================================== Aufbau
    def _build(self):
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(1, weight=1)

        head = ttk.Frame(r, padding=(16, 12, 16, 6))
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="BildZwilling", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="  " + _("Doppelte Fotos finden · prüfen · archivieren"), style="Sub.TLabel").pack(
            side="left", pady=(8, 0))
        ttk.Button(head, text=_("Info"), command=self.show_info).pack(side="right")
        ttk.Button(head, text="⚙ " + _("Einstellungen"), command=lambda: SettingsDialog(self)).pack(side="right", padx=6)
        ttk.Label(head, text=_("Version {v}").format(v=VERSION), style="Muted.TLabel").pack(side="right", padx=10)

        body = ttk.PanedWindow(r, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=12)
        side = ttk.Frame(body, style="Panel.TFrame", padding=12)
        body.add(side, weight=0)
        main = ttk.Frame(body)
        body.add(main, weight=1)
        self._build_sidebar(side)
        self._build_main(main)

        foot = ttk.Frame(r, padding=(16, 6, 16, 8))
        foot.grid(row=2, column=0, sticky="ew")
        foot.columnconfigure(1, weight=1)
        self.progress = ttk.Progressbar(foot, length=320, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="w")
        self.status = ttk.Label(foot, text=_("Bereit."), style="Green.TLabel")
        self.status.grid(row=0, column=1, sticky="w", padx=12)
        ttk.Label(foot, text=COPYRIGHT, style="Copy.TLabel").grid(row=1, column=0, columnspan=2,
                                                                  sticky="w", pady=(6, 0))

    def _section(self, parent, text):
        ttk.Label(parent, text=text, style="Section.TLabel").pack(anchor="w", pady=(8, 3))

    def _build_sidebar(self, s):
        self._section(s, "1 · " + _("Bildordner"))
        ttk.Label(s, text=_("Lokal, HDD, NAS, pCloud, OneDrive, Nextcloud,\nownCloud, Seestar. Erster Ordner = „Master“."),
                  style="PanelMuted.TLabel", justify="left").pack(anchor="w")
        self.roots_lb = theme.listbox(s, height=5, width=42, selectmode="extended")
        self.roots_lb.pack(fill="x", pady=4)
        rb = ttk.Frame(s, style="Panel.TFrame")
        rb.pack(fill="x")
        ttk.Button(rb, text="+ " + _("Ordner"), command=self.add_root).pack(side="left")
        ttk.Button(rb, text=_("Entfernen"), command=self.remove_root).pack(side="left", padx=4)
        ttk.Button(rb, text="▲ " + _("Master"), command=self.root_up).pack(side="left")

        self._section(s, "2 · " + _("Archivordner"))
        self.archive_var = tk.StringVar()
        ttk.Entry(s, textvariable=self.archive_var, state="readonly").pack(fill="x")
        ab = ttk.Frame(s, style="Panel.TFrame")
        ab.pack(fill="x", pady=4)
        ttk.Button(ab, text=_("Wählen …"), command=self.choose_archive).pack(side="left")
        ttk.Button(ab, text=_("Öffnen"), command=lambda: self._reveal(self.archive_var.get())).pack(side="left", padx=4)

        self._section(s, "3 · " + _("Suche"))
        self.mode_var = tk.StringVar(value="bytes")
        ttk.Radiobutton(s, text=_("Byte-identisch (schnell, 100 % sicher)"), value="bytes",
                        variable=self.mode_var).pack(anchor="w")
        ttk.Radiobutton(s, text=_("+ gleicher Bildinhalt (andere Metadaten)"), value="pixels",
                        variable=self.mode_var).pack(anchor="w")
        self.similar_var = tk.BooleanVar()
        ttk.Checkbutton(s, text=_("Ähnliche Bilder zeigen (nie automatisch archiviert)"),
                        variable=self.similar_var).pack(anchor="w", pady=(4, 0))
        sl = ttk.Frame(s, style="Panel.TFrame")
        sl.pack(fill="x", padx=(20, 0))
        ttk.Label(sl, text=_("streng"), style="PanelMuted.TLabel").pack(side="left")
        self.sim_scale = ttk.Scale(sl, from_=0, to=16, orient="horizontal", length=140, command=self._on_slider)
        self.sim_scale.pack(side="left", padx=4)
        ttk.Label(sl, text=_("locker"), style="PanelMuted.TLabel").pack(side="left")
        self.sim_label = ttk.Label(sl, text="6", style="PanelOrange.TLabel", width=3)
        self.sim_label.pack(side="left", padx=4)
        self.rotations_var = tk.BooleanVar()
        ttk.Checkbutton(s, text=_("auch gedrehte/gespiegelte Kopien"), variable=self.rotations_var).pack(
            anchor="w", padx=(20, 0))

        self.images_only = tk.BooleanVar()
        self.include_videos = tk.BooleanVar()
        self.include_ph = tk.BooleanVar()
        self.move_sidecars = tk.BooleanVar()
        self.keep_pairs = tk.BooleanVar()
        self.use_ratings = tk.BooleanVar()
        for var, txt in (
            (self.images_only, _("Nur Bilddateien (inkl. RAW & FITS)")),
            (self.include_videos, _("Videos einbeziehen (MP4, MOV, INSV …)")),
            (self.include_ph, _("Nur-Online-Dateien (Cloud) laden & prüfen")),
            (self.move_sidecars, _("XMP-Begleitdateien mitverschieben")),
            (self.keep_pairs, _("RAW+JPEG- / FIT+JPG-Paare zusammenhalten")),
            (self.use_ratings, _("Bewertungen (★, Farbe, Flagge) bevorzugt behalten")),
        ):
            ttk.Checkbutton(s, text=txt, variable=var).pack(anchor="w", pady=1)
        ttk.Label(s, text=_("Original behalten nach:"), style="Panel.TLabel").pack(anchor="w", pady=(6, 2))
        self.rule_cb = ttk.Combobox(s, state="readonly", values=list(KEEP_RULES().values()))
        self.rule_cb.pack(fill="x")
        self.rules_info = ttk.Label(s, text="", style="PanelMuted.TLabel")
        self.rules_info.pack(anchor="w", pady=(2, 0))

        bf = ttk.Frame(s, style="Panel.TFrame")
        bf.pack(fill="x", pady=(10, 0))
        self.start_btn = ttk.Button(bf, text="▶  " + _("Suche starten (F5)"), style="Accent.TButton",
                                    command=self.start_scan)
        self.start_btn.pack(fill="x")
        self.cancel_btn = ttk.Button(bf, text="■  " + _("Abbrechen"), command=self.cancel)
        self.cancel_btn.pack(fill="x", pady=(6, 0))
        self.cancel_btn.state(["disabled"])

    def _build_main(self, m):
        self.nb = ttk.Notebook(m)
        self.nb.pack(fill="both", expand=True, padx=(10, 0))

        # ---------------------------------------------------------- Tab Duplikate
        t1 = ttk.Frame(self.nb, padding=8)
        self.nb.add(t1, text=_("Duplikate"))
        tb = ttk.Frame(t1)
        tb.pack(fill="x", pady=(0, 6))
        ttk.Button(tb, text=_("Vergleichen"), command=self.open_compare).pack(side="left")
        ttk.Button(tb, text="★ " + _("Als Original"), command=self.set_original_selected).pack(side="left", padx=4)
        ttk.Button(tb, text=_("Behalten ⇄ Archiv"), command=self.toggle_selected).pack(side="left")
        ttk.Button(tb, text=_("Regel neu anwenden"), command=self.reapply_rule).pack(side="left", padx=4)
        ttk.Button(tb, text="CSV", command=self.export_csv).pack(side="left")
        ttk.Button(tb, text=_("HTML-Bericht"), command=self.export_html).pack(side="left", padx=4)
        self.archive_btn = ttk.Button(tb, text="➜  " + _("Markierte ins Archiv"), style="Accent.TButton",
                                      command=self.archive_marked)
        self.archive_btn.pack(side="right")
        self.undo_btn = ttk.Button(tb, text="↶ " + _("Rückgängig"), command=self.undo_last)
        self.undo_btn.pack(side="right", padx=6)

        fb = ttk.Frame(t1)
        fb.pack(fill="x", pady=(0, 6))
        ttk.Label(fb, text=_("Filter:")).pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(fb, textvariable=self.filter_var, width=24)
        self.filter_entry.pack(side="left", padx=4)
        self.filter_var.trace_add("write", lambda *a: self._schedule_filter())
        self.kind_cb = ttk.Combobox(fb, state="readonly", width=19, values=list(KIND_FILTER()))
        self.kind_cb.current(0)
        self.kind_cb.pack(side="left", padx=4)
        self.type_cb = ttk.Combobox(fb, state="readonly", width=11,
                                    values=[_("Alle Typen")] + [_(t) for t in TYPES])
        self.type_cb.current(0)
        self.type_cb.pack(side="left", padx=4)
        ttk.Label(fb, text=_("Sortierung:")).pack(side="left", padx=(8, 0))
        self.sort_cb = ttk.Combobox(fb, state="readonly", width=16, values=SORTS())
        self.sort_cb.current(0)
        self.sort_cb.pack(side="left", padx=4)
        for cb in (self.kind_cb, self.type_cb, self.sort_cb):
            cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        self.next_btn = ttk.Button(fb, text="▶", width=3, command=lambda: self.goto_page(self.page + 1))
        self.next_btn.pack(side="right")
        self.page_label = ttk.Label(fb, text="", style="Muted.TLabel")
        self.page_label.pack(side="right", padx=6)
        self.prev_btn = ttk.Button(fb, text="◀", width=3, command=lambda: self.goto_page(self.page - 1))
        self.prev_btn.pack(side="right")

        split = ttk.PanedWindow(t1, orient="horizontal")
        split.pack(fill="both", expand=True)
        tf = ttk.Frame(split)
        split.add(tf, weight=3)
        cols = ("status", "folder", "size", "dims", "date")
        self.tree = ttk.Treeview(tf, columns=cols, selectmode="extended")
        self.tree.heading("#0", text=_("Gruppe / Datei"))
        self.tree.column("#0", width=300, stretch=True)
        for c, t, w, a in (("status", _("Aktion"), 160, "w"), ("folder", _("Ordner"), 290, "w"),
                           ("size", _("Größe"), 85, "e"), ("dims", _("Maße"), 95, "e"),
                           ("date", _("Geändert"), 125, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "folder"))  # pyright: ignore[reportArgumentType]
        vs = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.open_compare())
        self.tree.bind("<Return>", lambda e: self.open_compare())
        self.tree.bind("<space>", lambda e: (self.toggle_selected(), "break")[1])
        self.tree.bind("<Prior>", lambda e: (self.goto_page(self.page - 1), "break")[1])
        self.tree.bind("<Next>", lambda e: (self.goto_page(self.page + 1), "break")[1])
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._schedule_preview())

        pv = ttk.Frame(split, style="Panel.TFrame", padding=8)
        split.add(pv, weight=1)
        ttk.Label(pv, text=_("Vorschau"), style="Section.TLabel").pack(anchor="w")
        self.pv_img = tk.Label(pv, bg=theme.PANEL, fg=theme.MUTED, text=_("Datei auswählen"), width=34, height=14,
                               cursor="hand2")
        self.pv_img.pack(fill="both", expand=True, pady=6)
        self.pv_img.bind("<Button-1>", lambda e: self.open_large_preview())
        self.pv_path = ""
        self.pv_info = ttk.Label(pv, text="", style="PanelMuted.TLabel", justify="left", wraplength=300)
        self.pv_info.pack(fill="x")

        self.summary = ttk.Label(t1, text=_("Noch keine Suche durchgeführt."), style="Muted.TLabel")
        self.summary.pack(anchor="w", pady=(6, 0))

        # ---------------------------------------------------------- Seestar & Cloud
        from .cloud_tab import CloudTab
        from .seestar_tab import SeestarTab

        self.seestar_tab = SeestarTab(self, self.nb)
        self.cloud_tab = CloudTab(self, self.nb)

        # ---------------------------------------------------------- Tab Archiv
        t2 = self.archive_frame = ttk.Frame(self.nb, padding=8)
        self.nb.add(t2, text=_("Archiv (Sichtung & Freigabe)"))
        tb2 = ttk.Frame(t2)
        tb2.pack(fill="x", pady=(0, 6))
        ttk.Button(tb2, text=_("Neu laden"), command=self.reload_archive).pack(side="left")
        ttk.Button(tb2, text=_("Mit Original vergleichen"), command=self.compare_archive).pack(side="left", padx=4)
        ttk.Button(tb2, text=_("Alle auswählen"), command=lambda: self.atree.selection_set(
            self.atree.get_children())).pack(side="left")
        self.due_btn = ttk.Button(tb2, text=_("Fällige auswählen"), command=self.select_due)
        self.due_btn.pack(side="left", padx=4)
        ttk.Button(tb2, text="↩ " + _("Wiederherstellen"), command=self.restore_selected).pack(side="left")
        ttk.Button(tb2, text="↶ " + _("Letzte Archivierung rückgängig"), command=self.undo_last).pack(side="left", padx=4)
        ttk.Button(tb2, text="CSV", command=self.export_archive_csv).pack(side="left")
        self.purge_btn = ttk.Button(tb2, text=_("Endgültig löschen …"), style="Danger.TButton",
                                    command=self.purge_selected)
        self.purge_btn.pack(side="right")
        af = ttk.Frame(t2)
        af.pack(fill="both", expand=True)
        acols = ("time", "age", "name", "orig", "size", "keep")
        self.atree = ttk.Treeview(af, columns=acols, show="headings", selectmode="extended")
        for c, t, w, a in (("time", _("Archiviert"), 135, "w"), ("age", _("Tage"), 50, "e"),
                           ("name", _("Datei"), 210, "w"), ("orig", _("Ursprünglicher Ordner"), 360, "w"),
                           ("size", _("Größe"), 85, "e"), ("keep", _("Original vorhanden"), 140, "center")):
            self.atree.heading(c, text=t)
            self.atree.column(c, width=w, anchor=a, stretch=(c == "orig"))  # pyright: ignore[reportArgumentType]
        avs = ttk.Scrollbar(af, orient="vertical", command=self.atree.yview)
        self.atree.configure(yscrollcommand=avs.set)
        self.atree.pack(side="left", fill="both", expand=True)
        avs.pack(side="right", fill="y")
        self.atree.bind("<Double-1>", lambda e: self.compare_archive())
        self.asummary = ttk.Label(t2, text="", style="Muted.TLabel")
        self.asummary.pack(anchor="w", pady=(6, 0))

        # ---------------------------------------------------------- Tab Protokoll
        t3 = ttk.Frame(self.nb, padding=8)
        self.nb.add(t3, text=_("Protokoll"))
        self.logtext = theme.text(t3, height=10, state="disabled")
        lsb = ttk.Scrollbar(t3, orient="vertical", command=self.logtext.yview)
        self.logtext.configure(yscrollcommand=lsb.set)
        self.logtext.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        self._color_tags()

    def _color_tags(self):
        for tree in [self.tree] + ([self.cloud_tab.tree] if self.cloud_tab else []):
            tree.tag_configure("group", foreground=theme.ACCENT, font=(theme.FAMILY, theme.SIZE, "bold"))
            tree.tag_configure("simgroup", foreground=theme.BLUE, font=(theme.FAMILY, theme.SIZE, "bold"))
            tree.tag_configure("keep", foreground=theme.GREEN)
            tree.tag_configure("archive", foreground=theme.TEXT)
        self.atree.tag_configure("ok", foreground=theme.TEXT)
        self.atree.tag_configure("due", foreground=theme.YELLOW)
        self.atree.tag_configure("missing", foreground=theme.RED)
        if self.seestar_tab:
            self.seestar_tab.color_tags()

    def apply_settings(self):
        st = self.settings
        theme.set_palette(st["theme"], st["large_font"])
        theme.apply(self.root)
        theme.recolor_listbox(self.roots_lb)
        theme.recolor_text(self.logtext)
        self.pv_img.configure(bg=theme.PANEL, fg=theme.MUTED)
        if self.seestar_tab:
            self.seestar_tab.recolor()
        if self.cloud_tab:
            self.cloud_tab.recolor()
        self._color_tags()
        self.speaker.enabled = bool(st["speech"])
        self._configure_tools()
        self._update_rules_info()
        if self.compare_win is not None:
            self.compare_win.close()
        style_titlebar(self.root)
        self.root.withdraw()
        self.root.deiconify()
        self.apply_filter()
        self._render_archive()
        self.set_status(_("Einstellungen übernommen."), "Green")

    # ================================================================== Einstellungen
    def _load_settings_into_ui(self):
        st = self.settings
        for r in st["roots"]:
            self.roots_lb.insert("end", r)
        self.archive_var.set(st["archive_dir"])
        self.mode_var.set(st["mode"] if st["mode"] in ("bytes", "pixels") else "bytes")
        self.images_only.set(st["images_only"])
        self.include_videos.set(st["include_videos"])
        self.include_ph.set(st["include_placeholders"])
        self.move_sidecars.set(st["move_sidecars"])
        self.keep_pairs.set(st["keep_pairs"])
        self.use_ratings.set(st["use_ratings"])
        self.similar_var.set(st["similar"])
        self.rotations_var.set(st["rotations"])
        self.sim_scale.set(max(0, min(16, st["similar_threshold"])))
        self.sim_label.configure(text=str(st["similar_threshold"]))
        self.rule_cb.set(KEEP_RULES().get(st["keep_rule"], KEEP_RULES()["first_root"]))
        self._update_rules_info()

    def _update_rules_info(self):
        n = len(valid_rules(self.settings["folder_rules"]))
        lr = " · Lightroom" if self.settings["lrcat_path"] else ""
        self.rules_info.configure(text=(_("{n} Ordnerregel(n) aktiv").format(n=n) if n else
                                        _("Ordnerregeln: ⚙ Einstellungen")) + lr)

    def _rule_key(self) -> str:
        label = self.rule_cb.get()
        return next((k for k, v in KEEP_RULES().items() if v == label), "first_root")

    def _threshold(self) -> int:
        try:
            return int(round(float(self.sim_scale.get())))
        except (TypeError, ValueError):
            return 6

    def _collect_settings(self):
        st = self.settings
        st["roots"] = list(self.roots_lb.get(0, "end"))
        st["archive_dir"] = self.archive_var.get()
        st["mode"] = self.mode_var.get()
        st["images_only"] = bool(self.images_only.get())
        st["include_videos"] = bool(self.include_videos.get())
        st["include_placeholders"] = bool(self.include_ph.get())
        st["move_sidecars"] = bool(self.move_sidecars.get())
        st["keep_pairs"] = bool(self.keep_pairs.get())
        st["use_ratings"] = bool(self.use_ratings.get())
        st["similar"] = bool(self.similar_var.get())
        st["rotations"] = bool(self.rotations_var.get())
        st["similar_threshold"] = self._threshold()
        st["keep_rule"] = self._rule_key()
        if self.seestar_tab:
            self.seestar_tab.collect_settings()
        if self.cloud_tab:
            self.cloud_tab.collect_settings()
        try:
            if self.root.state() == "normal":
                st["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        st.save()

    # ================================================================== Ordner
    def add_root(self):
        d = filedialog.askdirectory(parent=self.root, title=_("Bildordner hinzufügen"), mustexist=True)
        if not d:
            return
        d = os.path.abspath(d)
        for e in self.roots_lb.get(0, "end"):
            if is_within(d, e) or is_within(e, d):
                dialogs.showwarning(APP_NAME, _("Überschneidet sich mit bereits gewähltem Ordner:\n{e}\n\n"
                                                "Bitte nur übergeordneten Ordner verwenden.").format(e=e),
                                    parent=self.root)
                return
        arch = self.archive_var.get()
        if arch and is_within(d, arch):
            dialogs.showerror(APP_NAME, _("Dieser Ordner liegt im Archivordner."), parent=self.root)
            return
        self.roots_lb.insert("end", d)
        self._collect_settings()

    def remove_root(self):
        for i in reversed(self.roots_lb.curselection()):
            self.roots_lb.delete(i)
        self._collect_settings()

    def root_up(self):
        sel = self.roots_lb.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        v = self.roots_lb.get(i)
        self.roots_lb.delete(i)
        self.roots_lb.insert(0, v)
        self.roots_lb.selection_set(0)
        self._collect_settings()

    def choose_archive(self):
        d = filedialog.askdirectory(parent=self.root, title=_("Archivordner wählen (oder neu anlegen)"))
        if not d:
            return
        d = os.path.abspath(d)
        for r in self.roots_lb.get(0, "end"):
            if is_within(r, d):
                dialogs.showerror(APP_NAME, _("Der Bildordner\n{r}\nliegt innerhalb dieses Archivordners.").format(r=r),
                                  parent=self.root)
                return
        if [r for r in self.roots_lb.get(0, "end") if is_within(d, r)]:
            dialogs.showinfo(APP_NAME, _("Der Archivordner liegt innerhalb eines Bildordners.\n"
                                         "Er wird bei der Suche automatisch ausgelassen."), parent=self.root)
        self.archive_var.set(d)
        self._collect_settings()
        self.reload_archive()

    def _reveal(self, path):
        if not path:
            return
        try:
            os.makedirs(path, exist_ok=True)
            open_in_file_manager(path)
        except OSError as e:
            self.log("error", _("Öffnen nicht möglich: {e}").format(e=e))

    # ================================================================== Status/Log
    def _append_log(self, level, msg):
        t = self.logtext
        t.configure(state="normal")
        t.insert("end", _dt.datetime.now().strftime("%H:%M:%S  "), "time")
        t.insert("end", msg + "\n", LEVEL_TAG.get(level, "info"))
        if int(t.index("end-1c").split(".")[0]) > 5000:
            t.delete("1.0", "1000.0")
        t.see("end")
        t.configure(state="disabled")

    def set_status(self, text, color="Green"):
        self.status.configure(text=text, style=f"{color}.TLabel")
        if color != "Blue":
            self.speaker.say(text)

    def _progress(self, phase, done, total):
        phase = _(phase)
        if total <= 0:
            if str(self.progress.cget("mode")) != "indeterminate":
                self.progress.configure(mode="indeterminate")
                self.progress.start(15)
            self.set_status(_("{p} … {n} Dateien").format(p=phase, n=num(done)), "Blue")
        else:
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
            pct = 100.0 * done / total
            self.progress.configure(value=pct)
            self.set_status(f"{phase} … {pct:.0f} %", "Blue")

    def _set_busy(self, busy: bool):
        self.busy = busy
        for b in (self.start_btn, self.archive_btn, self.purge_btn, self.undo_btn):
            b.state(["disabled"] if busy else ["!disabled"])
        for tab in (self.seestar_tab, self.cloud_tab):
            if tab:
                tab.set_busy(busy)
        self.cancel_btn.state(["!disabled"] if busy else ["disabled"])
        if not busy:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)

    def cancel(self):
        if self.busy:
            self.cancel_ev.set()
            self.set_status(_("Wird abgebrochen …"), "Yellow")

    # ================================================================== Suche
    def start_scan(self):
        if self.busy:
            return
        self._collect_settings()
        st = self.settings
        opts = ScanOptions(
            roots=list(st["roots"]), archive_dir=st["archive_dir"], mode=st["mode"],
            images_only=st["images_only"], include_hidden=st["include_hidden"],
            include_placeholders=st["include_placeholders"], min_size=st["min_size_kb"] * 1024,
            keep_rule=st["keep_rule"], workers=max(1, min(16, int(st["workers"]))),
            include_videos=st["include_videos"], similar=st["similar"],
            similar_threshold=st["similar_threshold"], folder_rules=valid_rules(st["folder_rules"]),
            rotations=st["rotations"], use_ratings=st["use_ratings"], lrcat=st["lrcat_path"],
        )
        problems = validate_options(opts)
        if problems:
            dialogs.showerror(APP_NAME, "\n".join(_(p) if "{" not in p else p for p in problems), parent=self.root)
            return
        if not st["archive_dir"]:
            dialogs.showinfo(APP_NAME, _("Hinweis: Es ist noch kein Archivordner gewählt.\n"
                                         "Die Suche läuft trotzdem – zum Verschieben wird er benötigt."),
                             parent=self.root)
        if opts.include_placeholders and not dialogs.askyesno(
                APP_NAME, _("„Nur-Online-Dateien laden“ ist aktiv.\n\nDateien, die nur in der Cloud liegen, werden "
                            "bei Bedarf heruntergeladen. Das kann bei großen Bibliotheken viel Zeit und Speicher "
                            "kosten.\n\nTipp: Der Tab „Cloud direkt“ prüft pCloud/OneDrive ohne Download.\n\n"
                            "Fortfahren?"), parent=self.root):
            return
        if self.compare_win is not None:
            self.compare_win.close()
        self.cancel_ev.clear()
        self._set_busy(True)
        self.groups, self.similar_items = [], []
        self.apply_filter()
        mode = _("Byte + Bildinhalt") if opts.mode == "pixels" else _("Byte-identisch")
        if opts.similar:
            mode += " + " + _("ähnliche (≤ {t})").format(t=opts.similar_threshold)
        self.log("blue", _("Suche gestartet ({m}) in {n} Ordner(n).").format(m=mode, n=len(opts.roots)))

        def worker():
            try:
                sc = Scanner(opts, self.cache, progress=lambda p, d, t: self.ui(self._progress, p, d, t),
                             log=self.log, cancel=self.cancel_ev)
                with keep_awake():
                    res = sc.run()
                self.ui(self._scan_done, res)
            except ScanCancelled:
                self.ui(self._scan_failed, _("Suche abgebrochen."), "Yellow")
            except Exception as e:  # noqa: BLE001
                self.logger.exception("Scan-Fehler")
                self.ui(self._scan_failed, _("Fehler bei der Suche: {e}").format(e=e), "Red")

        threading.Thread(target=worker, daemon=True, name="bz-scan").start()

    def _scan_failed(self, msg, color):
        self._set_busy(False)
        self.set_status(msg, color)
        self.log("warn" if color == "Yellow" else "error", msg)

    def _scan_done(self, res):
        self._set_busy(False)
        self.groups = res.groups
        self.similar_items = res.similar_items
        self.page = 0
        self.apply_filter()
        s = res.stats
        msg = _("Fertig in {sec} s · {f} Dateien · {g} Gruppen · {d} Duplikate · {sz} freizugeben").format(
            sec=f"{s.get('duration', 0):.1f}".replace(".0", ""), f=num(s["files"]), g=num(s["groups"]),
            d=num(s["duplicates"]), sz=human_size(s["savable"]))
        if s.get("similar_groups"):
            msg += " · " + _("{n} Gruppen ähnlicher Bilder").format(n=s["similar_groups"])
        if res.errors:
            msg += " · " + _("{n} Warnungen (Protokoll)").format(n=len(res.errors))
        self.log("ok", msg)
        if not self.groups:
            self.set_status(_("Keine Duplikate gefunden."), "Green")
        else:
            self.set_status(msg, "Yellow" if res.errors else "Green")

    # ---------------------------------------------------------------- Ähnlichkeits-Regler
    def _on_slider(self, _value=None):
        t = self._threshold()
        self.sim_label.configure(text=str(t))
        if self.similar_items and not self.busy:
            if self._regroup_after:
                self.root.after_cancel(self._regroup_after)
            self._regroup_after = self.root.after(350, self._regroup)

    def _regroup(self):
        self._regroup_after = None
        t = self._threshold()
        rot = bool(self.rotations_var.get())
        exact = [g for g in self.groups if g.kind != "similar"]
        saved = {id(f): f.action for g in exact for f in g.files}
        items = list(self.similar_items)
        self._regroup_token += 1
        tok = self._regroup_token
        self.set_status(_("Ähnliche Bilder werden neu gruppiert (Abstand ≤ {t}) …").format(t=t), "Blue")

        def done(sim):
            if tok != self._regroup_token or self.busy:
                return
            for g in exact:
                for f in g.files:
                    f.action = saved.get(id(f), f.action)
            self.groups = exact + sim
            self.apply_filter()
            self.set_status(_("{n} Gruppen ähnlicher Bilder bei Abstand ≤ {t}.").format(n=len(sim), t=t), "Green")

        self.run_bg(lambda: similar_groups(items, t, len(exact) + 1, rotations=rot), (), done,
                    lambda e: self.set_status(_("Fehler: {e}").format(e=e), "Red"))

    # ================================================================== Ergebnisliste, Filter, Seiten
    def _schedule_filter(self):
        if self._filter_after:
            self.root.after_cancel(self._filter_after)
        self._filter_after = self.root.after(250, self.apply_filter)

    def apply_filter(self):
        self._filter_after = None
        text = self.filter_var.get().strip().lower()
        kind = KIND_FILTER().get(self.kind_cb.get())
        tlabel = self.type_cb.get()
        ftype = next((t for t in TYPES if _(t) == tlabel), None)
        view = []
        for gi, g in enumerate(self.groups):
            if kind and g.kind != kind:
                continue
            if ftype and not any(file_type(f.path) == ftype for f in g.files):
                continue
            if text and not any(text in f.path.lower() for f in g.files):
                continue
            view.append(gi)
        sort = self.sort_cb.get()
        G = self.groups
        s = SORTS()
        if sort == s[1]:
            view.sort(key=lambda i: -max(f.size for f in G[i].files))
        elif sort == s[2]:
            view.sort(key=lambda i: -len(G[i].files))
        elif sort == s[3]:
            view.sort(key=lambda i: os.path.basename(G[i].files[0].path).lower())
        elif sort == s[4]:
            view.sort(key=lambda i: os.path.dirname(G[i].files[0].path).lower())
        else:
            view.sort(key=lambda i: (G[i].kind == "similar", -G[i].savable, -max(f.size for f in G[i].files)))
        self.view = view
        self.goto_page(min(self.page, self._pages() - 1))

    def _pages(self) -> int:
        size = max(50, int(self.settings["page_size"]))
        return max(1, (len(self.view) + size - 1) // size)

    def goto_page(self, p: int):
        pages = self._pages()
        self.page = max(0, min(p, pages - 1))
        self.prev_btn.state(["!disabled"] if self.page > 0 else ["disabled"])
        self.next_btn.state(["!disabled"] if self.page < pages - 1 else ["disabled"])
        self.page_label.configure(text=_("Seite {p} / {n} · {g} Gruppen").format(
            p=self.page + 1, n=pages, g=num(len(self.view))))
        self._render_page()

    def file_values(self, f, pairs: PairFinder | None = None):
        date = _dt.datetime.fromtimestamp(f.mtime).strftime("%d.%m.%Y %H:%M") if f.mtime_ns else ""
        status = "✔ " + _("BEHALTEN") if f.action == "keep" else "➜ " + _("Archiv")
        if getattr(f, "rating", None) is not None and not f.rating.empty:
            status += "  " + f.rating.text()
        if f.placeholder:
            status += " ☁"
        if pairs is not None and pairs.partner(f.path):
            status += " · " + _("Paar")
        dims = f"{f.dims[0]}×{f.dims[1]}" if f.dims else ""
        return (status, os.path.dirname(f.path) if not hasattr(f, "cloud") else f.path.rsplit("/", 1)[0] or "/",
                human_size(f.size), dims, date)

    def group_text(self, g, gi):
        kind = str(KIND_TEXT().get(g.kind, g.kind))
        if g.kind == "similar":
            kind += " " + _("(Abstand {d})").format(d=g.distance)
            if g.transformed:
                kind += " · " + _("gedreht/gespiegelt")
        return _("Gruppe {n}  ·  {c} Dateien  ·  {k}").format(n=gi + 1, c=len(g.files), k=kind)

    def _render_page(self):
        self.tree.delete(*self.tree.get_children())
        self.clear_preview()
        self._rendered = set()
        size = max(50, int(self.settings["page_size"]))
        pairs = PairFinder() if self.keep_pairs.get() else None
        for gi in self.view[self.page * size:(self.page + 1) * size]:
            g = self.groups[gi]
            gid = f"g{gi}"
            self.tree.insert("", "end", iid=gid, text=self.group_text(g, gi), open=True,
                             tags=("simgroup" if g.kind == "similar" else "group",),
                             values=("", "", human_size(g.savable), "", ""))
            self._rendered.add(gid)
            for fi, f in enumerate(g.files):
                self.tree.insert(gid, "end", iid=f"f{gi}_{fi}", text=os.path.basename(f.path),
                                 values=self.file_values(f, pairs), tags=(f.action,))
        self._update_summary()
        if self.compare_win is not None:
            self.compare_win.refresh()

    def _refresh_group(self, gi):
        if f"g{gi}" not in self._rendered:
            return
        g = self.groups[gi]
        pairs = PairFinder() if self.keep_pairs.get() else None
        self.tree.item(f"g{gi}", values=("", "", human_size(g.savable), "", ""))
        for fi, f in enumerate(g.files):
            self.tree.item(f"f{gi}_{fi}", values=self.file_values(f, pairs), tags=(f.action,))

    def _refresh_all_visible(self):
        for gid in list(self._rendered):
            self._refresh_group(int(gid[1:]))
        self._update_summary()
        if self.compare_win is not None:
            self.compare_win.refresh()

    def _update_summary(self):
        if not self.groups:
            self.summary.configure(text=_("Keine Duplikat-Gruppen."))
            return
        marked = {id(f): f for g in self.groups for f in g.to_archive}
        size = sum(f.size for f in marked.values())
        n_sim = sum(1 for g in self.groups if g.kind == "similar")
        n_sim_marked = len({id(f) for g in self.groups if g.kind == "similar" for f in g.to_archive})
        txt = _("{e} identische Gruppen · {s} ähnliche · {m} Dateien zum Archivieren markiert · {sz}").format(
            e=num(len(self.groups) - n_sim), s=num(n_sim), m=num(len(marked)), sz=human_size(size))
        if n_sim_marked:
            txt += " · " + _("davon {n} ähnliche (manuell)").format(n=n_sim_marked)
        self.summary.configure(text=txt)

    def _selected_files(self):
        out = []
        for iid in self.tree.selection():
            if iid.startswith("f"):
                gi, fi = map(int, iid[1:].split("_"))
                out.append((gi, fi))
        return out

    def _selected_group(self):
        sel = self.tree.selection()
        if not sel:
            return None, None
        iid = sel[0]
        if iid.startswith("g"):
            return int(iid[1:]), None
        gi, fi = map(int, iid[1:].split("_"))
        return gi, fi

    def _groups_of(self, f):
        return [g for g in self.groups if any(x is f for x in g.files)]

    def _can_archive(self, f) -> str:
        for g in self._groups_of(f):
            if not [k for k in g.keepers if k is not f]:
                return (_("In der ähnlichen Gruppe muss mindestens eine Datei behalten werden.") if g.kind == "similar"
                        else _("In der identischen Gruppe muss mindestens eine Datei behalten werden."))
        return ""

    def toggle_selected(self):
        if self.busy:
            return
        for gi, fi in self._selected_files():
            f = self.groups[gi].files[fi]
            if f.action == "keep":
                why = self._can_archive(f)
                if why:
                    self.set_status(why, "Yellow")
                    continue
                f.action = "archive"
            else:
                f.action = "keep"
        self._refresh_all_visible()

    def set_original(self, gi, fi):
        if self.busy:
            self.set_status(_("Bitte warten, bis der laufende Vorgang beendet ist."), "Yellow")
            return
        g = self.groups[gi]
        target = g.files[fi]
        target.action = "keep"
        for f in g.files:
            if f is not target and self._can_archive(f) == "":
                f.action = "archive"
        self._refresh_all_visible()

    def set_original_selected(self):
        sel = self._selected_files()
        if not sel:
            self.set_status(_("Bitte eine Datei (nicht die Gruppe) auswählen."), "Yellow")
            return
        self.set_original(*sel[0])

    def reapply_rule(self):
        if self.busy:
            return
        self._collect_settings()
        fr = valid_rules(self.settings["folder_rules"])
        for g in self.groups:
            if g.kind != "similar":
                apply_keep_rule(g, self.settings["keep_rule"], fr)
        for g in self.groups:
            if g.kind == "similar":
                for f in g.files:
                    if not any(x is f for eg in self.groups if eg.kind != "similar" for x in eg.files):
                        f.action = "keep"
        self.apply_filter()

    def open_compare(self):
        gi, fi = self._selected_group()
        if gi is None:
            if not self.view:
                return
            gi, fi = self.view[0], None
        li = fi if fi is not None else 0
        ri = 1 if li == 0 else 0
        if self.compare_win is None:
            self.compare_win = CompareWindow(self)
        self.compare_win.show_group(gi, li, ri)

    def _schedule_preview(self):
        if self._preview_after:
            self.root.after_cancel(self._preview_after)
        self._preview_after = self.root.after(150, self._load_side_preview)

    def clear_preview(self):
        """Keine Datei ausgewählt -> Vorschau leeren."""
        self._preview_token += 1
        self._preview_photo = None
        self.pv_path = ""
        self.pv_img.configure(image="", text=_("Datei auswählen"), width=34, height=14)
        self.pv_info.configure(text="")

    def open_large_preview(self):
        """Klick auf die Vorschau: Bild groß anzeigen (SCHLIESSEN macht es wieder klein)."""
        if self.pv_path:
            from .viewer import open_viewer
            open_viewer(self, self.pv_path)

    def _load_side_preview(self):
        self._preview_after = None
        sel = self._selected_files()
        if not sel:
            self.clear_preview()
            return
        gi, fi = sel[0]
        f = self.groups[gi].files[fi]
        self._preview_token += 1
        tok = self._preview_token
        self.pv_path = f.path
        self.pv_img.configure(image="", text=_("Lade …"))
        dims = f" · {f.dims[0]}×{f.dims[1]}" if f.dims else ""
        rating = f"\n{f.rating.text()}" if getattr(f, "rating", None) is not None and not f.rating.empty else ""
        self.pv_info.configure(text=f"{os.path.basename(f.path)}\n{human_size(f.size)}{dims} · "
                                    f"{_(file_type(f.path))}{rating}\n{(f.digest or f.pdigest or '')[:16]}")
        self.speaker.say(f"{os.path.basename(f.path)}, {_('behalten') if f.action == 'keep' else _('Archiv')}")

        def done(res):
            if tok != self._preview_token:
                return
            im = res[0].copy()
            im.thumbnail((360, 360))
            self._preview_photo = ImageTk.PhotoImage(im)
            self.pv_img.configure(image=self._preview_photo, text="", width=0, height=0)
            self.pv_info.configure(text=self.pv_info.cget("text") + "\n" + _("Klick auf das Bild = Großansicht"))

        def fail(err):
            if tok == self._preview_token:
                self.pv_img.configure(image="", text=str(err), wraplength=280)

        self.run_bg(imaging.load_preview, (f.path, 720), done, fail)

    # ================================================================== Berichte
    def export_csv(self):
        if not self.groups:
            return
        p = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile=f"BildZwilling_{_dt.date.today():%Y-%m-%d}.csv")
        if p:
            try:
                n = report.export_groups_csv(self.groups, p)
                self.log("ok", _("CSV-Bericht gespeichert ({n} Zeilen): {p}").format(n=n, p=p))
            except OSError as e:
                dialogs.showerror(APP_NAME, str(e), parent=self.root)

    def export_html(self):
        if not self.groups or self.busy:
            return
        p = filedialog.asksaveasfilename(parent=self.root, defaultextension=".html", filetypes=[("HTML", "*.html")],
                                         initialfile=f"BildZwilling_{_dt.date.today():%Y-%m-%d}.html")
        if not p:
            return
        groups = [self.groups[i] for i in self.view] or list(self.groups)
        self.cancel_ev.clear()
        self._set_busy(True)

        def worker():
            try:
                n = htmlreport.export_html(groups, p, progress=lambda a, d, t: self.ui(self._progress, a, d, t),
                                           cancel=self.cancel_ev, workers=int(self.settings["workers"]))
                self.ui(self._html_done, _("HTML-Bericht mit {n} Gruppen gespeichert: {p}").format(n=n, p=p), "Green")
            except Exception as e:  # noqa: BLE001
                self.ui(self._html_done, _("HTML-Bericht fehlgeschlagen: {e}").format(e=e), "Red")

        threading.Thread(target=worker, daemon=True).start()

    def _html_done(self, msg, color):
        self._set_busy(False)
        self.set_status(msg, color)
        self.log("ok" if color == "Green" else "error", msg)

    # ================================================================== Archivieren
    def manager(self, warn: bool = True):
        d = self.archive_var.get()
        if not d:
            if warn:
                dialogs.showwarning(APP_NAME, _("Bitte zuerst einen Archivordner wählen."), parent=self.root)
            return None
        return ArchiveManager(d, move_sidecars=bool(self.move_sidecars.get()), log=self.log)

    def check_space(self, am, paths_sizes) -> bool:
        """Vor dem Archivieren auf ein anderes Laufwerk: genug freier Platz? (+5 % Reserve)"""
        need, free = am.space_check(paths_sizes)
        if free >= 0 and need > 0 and need * 1.05 > free:
            dialogs.showerror(APP_NAME, _("Zu wenig Speicherplatz im Archivordner.\n\nBenötigt (anderes Laufwerk): "
                                          "{n}\nFrei: {f}\n\nBitte Platz schaffen oder einen Archivordner auf dem "
                                          "Laufwerk der Bilder wählen (dann wird nur umbenannt).").format(
                n=human_size(need), f=human_size(free)), parent=self.root)
            return False
        return True

    def archive_marked(self):
        if self.busy or not self.groups:
            return
        self._collect_settings()
        am = self.manager()
        if am is None:
            return
        for r in self.settings["roots"]:
            if is_within(r, am.dir):
                dialogs.showerror(APP_NAME, _("Ein Bildordner liegt im Archivordner."), parent=self.root)
                return
        plan = plan_archive(self.groups, keep_pairs=bool(self.keep_pairs.get()))
        todo = [it for it in plan if not it.skip]
        skipped = [it for it in plan if it.skip]
        if not todo:
            for it in skipped:
                self.log("warn", _("Übersprungen: {p} – {w}").format(p=it.dup.path, w=_(it.skip)))
            self.set_status(_("Keine Dateien zum Archivieren (Paare/Regeln, siehe Protokoll).") if skipped
                            else _("Keine Dateien zum Archivieren markiert."), "Yellow")
            return
        size = sum(it.dup.size for it in todo)
        if not self.check_space(am, [(it.dup.path, it.dup.size) for it in todo]):
            return
        n_sim = sum(1 for it in todo if it.kind == "similar")
        n_comp = sum(len(it.companions) for it in todo)
        msg = _("{n} Dateien ({sz}) werden in den Archivordner verschoben:\n\n{d}\n\nIdentische Duplikate werden "
                "vorher nochmals direkt mit ihrem Original verglichen. Nichts wird gelöscht.").format(
            n=num(len(todo)), sz=human_size(size), d=am.dir)
        if n_sim:
            msg += "\n\n⚠ " + _("Darunter {n} ÄHNLICHE (nicht identische) Bilder, die Sie manuell markiert haben.").format(n=n_sim)
        if n_comp:
            msg += "\n\n" + _("{n} Paarpartner (RAW/JPEG bzw. FIT/JPG) wandern mit.").format(n=n_comp)
        if skipped:
            msg += "\n\n" + _("{n} Datei(en) werden übersprungen (z. B. würde ein Paar getrennt) – siehe Protokoll.").format(
                n=len(skipped))
        msg += "\n\n" + _("Rückgängig jederzeit mit „↶ Rückgängig“ (Strg+Z).")
        if not dialogs.askyesno(APP_NAME, msg + "\n\n" + _("Fortfahren?"), parent=self.root):
            return
        for it in skipped:
            self.log("warn", _("Übersprungen: {p} – {w}").format(p=it.dup.path, w=_(it.skip)))
        self.cancel_ev.clear()
        self._set_busy(True)
        session = am.new_session()
        self.log("blue", _("Archivierung von {n} Dateien gestartet (Sitzung {s}) …").format(n=len(todo), s=session))

        def worker():
            moved, n_skip, failed = set(), len(skipped), 0
            state = "error"
            awake = keep_awake()
            awake.__enter__()
            try:
                am.begin_session(session, len(todo), "gui")
                for i, it in enumerate(todo):
                    if self.cancel_ev.is_set():
                        self.log("warn", _("Archivierung abgebrochen."))
                        break
                    self.ui(self._progress, "Archiviere", i, len(todo))
                    try:
                        ok, why = am.archive(it.dup, it.keep, it.kind, self.cancel_ev, companions=it.companions,
                                             session=session)
                    except (OSError, ArchiveError) as e:
                        failed += 1
                        self.log("error", _("Fehler: {p} – {e}").format(p=it.dup.path, e=e))
                        continue
                    if ok:
                        moved.add(id(it.dup))
                        extra = f" (+ {', '.join(os.path.basename(c) for c in it.companions)})" if it.companions else ""
                        self.log("ok", _("Archiviert: {p}").format(p=it.dup.path) + extra)
                    else:
                        n_skip += 1
                        self.log("warn", _("Übersprungen: {p} – {w}").format(p=it.dup.path, w=_(why)))
                state = "cancelled" if self.cancel_ev.is_set() else "done"
            finally:
                try:
                    am.end_session(session, len(moved), state)
                except OSError:
                    pass
                try:
                    awake.__exit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
                self.ui(self._archive_done, moved, n_skip, failed,
                        [p for it in todo if id(it.dup) in moved for p in it.companions])

        threading.Thread(target=worker, daemon=True, name="bz-archive").start()

    def _archive_done(self, moved, skipped, failed, companions):
        self._set_busy(False)
        gone = {os.path.normcase(os.path.abspath(c)) for c in companions}
        for g in self.groups:
            g.files = [f for f in g.files
                       if id(f) not in moved and os.path.normcase(os.path.abspath(f.path)) not in gone]
        self.groups = [g for g in self.groups if len(g.files) > 1]
        self.similar_items = [f for f in self.similar_items
                              if id(f) not in moved and os.path.normcase(os.path.abspath(f.path)) not in gone]
        self.apply_filter()
        color = "Red" if failed else ("Yellow" if skipped else "Green")
        msg = _("{n} Dateien archiviert").format(n=len(moved))
        if skipped:
            msg += " · " + _("{n} übersprungen").format(n=skipped)
        if failed:
            msg += " · " + _("{n} Fehler").format(n=failed)
        self.set_status(msg + " – " + _("Sichtung im Tab „Archiv“."), color)
        self.log("ok" if not failed else "warn", msg)
        self.reload_archive()

    # ================================================================== Rückgängig (V14)
    def undo_last(self):
        if self.busy:
            return
        am = self.manager()
        if am is None:
            return
        sid, items = am.last_session()
        if not sid:
            self.set_status(_("Keine Archivierung zum Rückgängigmachen gefunden."), "Yellow")
            return
        when = max(str(e.get("time", "")) for e in items).replace("T", " ")
        size = sum(int(e.get("size", 0) or 0) for e in items)
        if not dialogs.askyesno(APP_NAME, _("Letzte Archivierung vom {t} rückgängig machen?\n\n{n} Dateien ({sz}) "
                                            "werden an ihren ursprünglichen Ort zurückverschoben (vorhandene Dateien "
                                            "werden nie überschrieben).").format(t=when, n=len(items),
                                                                                  sz=human_size(size)),
                                parent=self.root):
            return
        self.cancel_ev.clear()
        self._set_busy(True)

        def worker():
            try:
                n, errors = am.undo_session(sid, self.cancel_ev)
                for inc in am.incomplete_sessions():
                    if inc["session"] == sid:
                        am.end_session(sid, 0, "undone")
                for e in errors:
                    self.log("error", _("Nicht wiederhergestellt: {e}").format(e=e))
                self.ui(self._after_archive_op, _("{n} Dateien wiederhergestellt – bitte erneut suchen (F5).").format(n=n),
                        "Yellow" if errors else "Green")
            except Exception as e:  # noqa: BLE001
                self.ui(self._after_archive_op, _("Fehler: {e}").format(e=e), "Red")

        threading.Thread(target=worker, daemon=True).start()

    # ================================================================== Archiv-Tab
    def reload_archive(self, startup: bool = False):
        d = self.archive_var.get()
        if not d:
            return
        am = ArchiveManager(d, log=self.log)

        def load():
            entries, bad = am.entries()
            for e in entries:
                e["_keep_ok"] = am.keep_exists(e)
            return entries, bad, am.incomplete_sessions()

        def done(res):
            entries, bad, incomplete = res
            if startup and incomplete and not self.busy:
                self.root.after(300, self._offer_incomplete, am, incomplete)
            self.archive_entries = sorted(entries, key=lambda e: e.get("time", ""), reverse=True)
            self._render_archive()
            if bad:
                self.log("warn", _("Journal: {n} beschädigte Zeile(n) ignoriert.").format(n=bad))
            due = self._due()
            if startup and due:
                self.log("warn", _("Archiv: {n} Einträge sind älter als {d} Tage und können nach Sichtung endgültig "
                                   "gelöscht werden (Tab „Archiv“ → „Fällige auswählen“).").format(
                    n=len(due), d=self.settings["retention_days"]))

        self.run_bg(load, (), done, lambda e: self.log("error", _("Archiv nicht lesbar: {e}").format(e=e)))

    def _offer_incomplete(self, am, incomplete):
        """Unvollständige Archivierung (Absturz, Stromausfall, Laufwerk weg) melden – C5."""
        for inc in incomplete:
            when = str(inc.get("time", "")).replace("T", " ")
            self.log("warn", _("Archivierung vom {t} wurde nicht abgeschlossen ({m} von {n} Dateien verschoben).").format(
                t=when, m=inc["moved"], n=inc["total"]))
            if inc["moved"] and dialogs.askyesno(
                    APP_NAME, _("Die Archivierung vom {t} wurde nicht abgeschlossen – vermutlich wurde das Programm "
                                "beendet, der Rechner ausgeschaltet oder ein Laufwerk getrennt.\n\n{m} von {n} Dateien "
                                "wurden bereits verschoben.\n\nJa = diese Dateien zurückholen\nNein = so lassen (später "
                                "mit „↶ Rückgängig“ möglich)").format(t=when, m=inc["moved"], n=inc["total"]),
                    parent=self.root):
                sid = inc["session"]

                def job(sid=sid):
                    n, errors = am.undo_session(sid)
                    am.end_session(sid, 0, "undone")
                    return n, errors

                def done(res):
                    n, errors = res
                    for e in errors:
                        self.log("error", _("Nicht wiederhergestellt: {e}").format(e=e))
                    self._after_archive_op(_("{n} Dateien wiederhergestellt – bitte erneut suchen (F5).").format(n=n),
                                           "Yellow" if errors else "Green")

                self._set_busy(True)
                self.run_bg(job, (), done, lambda e: self._after_archive_op(_("Fehler: {e}").format(e=e), "Red"))
                return
            try:
                am.end_session(inc["session"], inc["moved"], "acknowledged")
            except OSError:
                pass

    @staticmethod
    def _age(e) -> int:
        try:
            return max(0, (_dt.datetime.now() - _dt.datetime.fromisoformat(str(e.get("time", "")))).days)
        except ValueError:
            return 0

    def _due(self):
        days = int(self.settings["retention_days"])
        return [i for i, e in enumerate(self.archive_entries) if self._age(e) >= days]

    def _render_archive(self):
        self.atree.delete(*self.atree.get_children())
        total = missing = 0
        due = set(self._due())
        for i, e in enumerate(self.archive_entries):
            ok = e.get("_keep_ok", False)
            missing += 0 if ok else 1
            size = int(e.get("size", 0) or 0)
            total += size
            tag = "missing" if not ok else ("due" if i in due else "ok")
            keep_txt = ("– " + _("Seestar-Ausschuss") if e.get("kind") == "seestar" else
                        ("✔" if ok else "✖ " + _("fehlt")))
            self.atree.insert("", "end", iid=f"a{i}", tags=(tag,), values=(
                str(e.get("time", "")).replace("T", " "), self._age(e), os.path.basename(e["src"]),
                os.path.dirname(e["src"]), human_size(size), keep_txt))
        days = self.settings["retention_days"]
        txt = _("{n} Dateien im Archiv · {sz}").format(n=len(self.archive_entries), sz=human_size(total))
        if due:
            txt += " · " + _("{n} älter als {d} Tage (gelb) – zur Löschfreigabe vorgeschlagen").format(n=len(due), d=days)
        if missing:
            txt += " · " + _("{n} ohne vorhandenes Original (rot, werden nicht gelöscht)").format(n=missing)
        self.asummary.configure(text=txt)
        self.due_btn.configure(text=_("Fällige auswählen (> {d} Tage)").format(d=days))
        self.nb.tab(self.archive_frame, text=_("Archiv ({n})").format(n=len(self.archive_entries)))

    def select_due(self):
        due = [f"a{i}" for i in self._due() if self.archive_entries[i].get("_keep_ok")]
        self.atree.selection_set(due)
        self.set_status(_("{n} fällige Archiv-Einträge ausgewählt.").format(n=len(due)) if due else
                        _("Keine fälligen Einträge."), "Green")

    def _selected_archive(self):
        return [self.archive_entries[int(i[1:])] for i in self.atree.selection()]

    def compare_archive(self):
        sel = self._selected_archive()
        if not sel:
            return
        e = sel[0]
        if self.compare_win is None:
            self.compare_win = CompareWindow(self)
        self.compare_win.show_paths(e["dst"], e.get("keep", ""), _("Archiv (Duplikat)"), _("Behaltenes Original"))

    def restore_selected(self):
        sel = self._selected_archive()
        if not sel or self.busy:
            return
        if not dialogs.askyesno(APP_NAME, _("{n} Datei(en) an den ursprünglichen Ort zurückverschieben?").format(
                n=len(sel)), parent=self.root):
            return
        am = self.manager()
        if am is None:
            return
        self._set_busy(True)

        def worker():
            n = 0
            try:
                for e in sel:
                    try:
                        target = am.restore(e)
                        n += 1
                        self.log("ok", _("Wiederhergestellt: {p}").format(p=target))
                    except (OSError, ArchiveError) as ex:
                        self.log("error", _("Nicht wiederhergestellt: {e}").format(e=f"{e['dst']} – {ex}"))
            finally:
                self.ui(self._after_archive_op, _("{n} Datei(en) wiederhergestellt.").format(n=n), "Green")

        threading.Thread(target=worker, daemon=True).start()

    def purge_selected(self):
        sel = self._selected_archive()
        if not sel or self.busy:
            if not sel:
                self.set_status(_("Bitte Dateien im Archiv auswählen (oder „Fällige auswählen“)."), "Yellow")
            return
        safe = [e for e in sel if e.get("_keep_ok")]
        blocked = len(sel) - len(safe)
        if not safe:
            dialogs.showwarning(APP_NAME, _("Bei keiner der gewählten Dateien existiert das behaltene Original noch. "
                                            "Zur Sicherheit wird nichts gelöscht.\nTipp: Datei wiederherstellen."),
                                parent=self.root)
            return
        trash = bool(self.settings["use_recycle_bin"]) and HAVE_TRASH
        size = sum(int(e.get("size", 0) or 0) for e in safe)
        how = _("in den Papierkorb verschieben") if trash else _("UNWIDERRUFLICH LÖSCHEN")
        msg = _("{n} archivierte Datei(en) ({sz}) {how}?").format(n=len(safe), sz=human_size(size), how=how)
        if blocked:
            msg += "\n\n" + _("{n} Datei(en) werden ausgelassen, weil ihr Original nicht mehr existiert.").format(n=blocked)
        if not dialogs.askyesno(APP_NAME, msg, icon="warning", parent=self.root):
            return
        if not trash and not dialogs.askyesno(APP_NAME, _("Wirklich endgültig löschen? Dies kann nicht rückgängig "
                                                          "gemacht werden."), icon="warning", parent=self.root):
            return
        am = self.manager()
        if am is None:
            return
        self._set_busy(True)

        def worker():
            n = 0
            try:
                for e in safe:
                    try:
                        how_done = am.purge(e, use_trash=trash)
                        n += 1
                        self.log("ok", _("Entfernt ({h}): {p}").format(h=_(how_done), p=e["dst"]))
                    except (OSError, ArchiveError) as ex:
                        self.log("error", _("Nicht entfernt: {p} – {e}").format(p=e["dst"], e=ex))
            finally:
                self.ui(self._after_archive_op, _("{n} Datei(en) endgültig entfernt.").format(n=n), "Green")

        threading.Thread(target=worker, daemon=True).start()

    def _after_archive_op(self, msg, color="Green"):
        self._set_busy(False)
        self.set_status(msg, color)
        self.reload_archive()

    def export_archive_csv(self):
        if not self.archive_entries:
            return
        p = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile=f"BildZwilling_Archiv_{_dt.date.today():%Y-%m-%d}.csv")
        if p:
            try:
                report.export_archive_csv(self.archive_entries, p)
                self.log("ok", _("Archivliste gespeichert: {p}").format(p=p))
            except OSError as e:
                dialogs.showerror(APP_NAME, str(e), parent=self.root)

    # ================================================================== Sonstiges
    def clear_cache(self):
        if self.busy:
            return
        if dialogs.askyesno(APP_NAME, _("Prüfsummen-Cache leeren? Die nächste Suche dauert dann länger."),
                            parent=self.root):
            self.cache.clear()
            self.log("info", _("Cache geleert."))

    def show_info(self):
        about.show_about(self)

    def on_close(self):
        if self.busy and not self.closing:
            if not dialogs.askyesno(APP_NAME, _("Es läuft noch ein Vorgang. Abbrechen und beenden?"), parent=self.root):
                return
        self.closing = True
        self.cancel_ev.set()
        try:
            self._collect_settings()
        except Exception:  # noqa: BLE001
            pass
        self._finish_close(0)

    def _finish_close(self, tries):
        if self.busy and tries < 50:
            self.root.after(100, self._finish_close, tries + 1)
            return
        if self.cloud_tab:
            self.cloud_tab.cleanup()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.cache.close()
        self.instance.release()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
