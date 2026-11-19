# SPDX-License-Identifier: GPL-3.0-or-later
"""Tab „Seestar-Assistent“: Subs ↔ Stack, Ausschuss-Erkennung, Archivieren."""

from __future__ import annotations

from typing import Any

import csv
import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from PIL import ImageTk

from .. import APP_NAME
from ..core import imaging, seestar
from ..core.archive import ArchiveError
from ..core.fsutil import human_size
from ..core.power import keep_awake
from ..i18n import _
from . import dialogs, theme


def STRICT():
    return {_("locker"): "locker", _("normal"): "normal", _("streng"): "streng"}


class SeestarTab:
    def __init__(self, app, nb):
        self.app = app
        self.stacks = []
        self.orphans = []
        self.frames = []
        self.items: dict[str, seestar.Frame] = {}
        self._tok = 0
        self._photo = None
        f = self.frame = ttk.Frame(nb, padding=8)
        nb.add(f, text=_("Seestar-Assistent"))

        top = ttk.Frame(f)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text=_("Seestar-Ordner:")).pack(side="left")
        self.dir_var = tk.StringVar(value=app.settings["seestar_dir"])
        ttk.Entry(top, textvariable=self.dir_var, width=48).pack(side="left", padx=4)
        ttk.Button(top, text=_("Wählen …"), command=self.pick).pack(side="left")
        ttk.Label(top, text="  " + _("Strenge:")).pack(side="left")
        self.strict = ttk.Combobox(top, state="readonly", width=9, values=list(STRICT()))
        self.strict.current(1)
        self.strict.pack(side="left", padx=4)
        self.strict.bind("<<ComboboxSelected>>", lambda e: self.reevaluate())
        self.run_btn = ttk.Button(top, text="▶ " + _("Analysieren"), style="Accent.TButton", command=self.run)
        self.run_btn.pack(side="left", padx=8)
        ttk.Label(top, text=_("Ordner „MyWorks“ der Seestar (oder eine Kopie davon) wählen."),
                  style="Muted.TLabel").pack(side="left", padx=6)

        tb = ttk.Frame(f)
        tb.pack(fill="x", pady=(0, 6))
        ttk.Button(tb, text=_("Ausschuss ⇄ Behalten"), command=self.toggle).pack(side="left")
        ttk.Button(tb, text=_("Alle Subs dieses Stacks markieren"), command=self.mark_stack).pack(side="left", padx=4)
        ttk.Button(tb, text=_("Markierung aufheben"), command=self.unmark).pack(side="left")
        ttk.Button(tb, text="CSV", command=self.export_csv).pack(side="left", padx=4)
        self.archive_btn = ttk.Button(tb, text="➜ " + _("Markierte ins Archiv"), style="Accent.TButton",
                                      command=self.archive)
        self.archive_btn.pack(side="right")

        split = ttk.PanedWindow(f, orient="horizontal")
        split.pack(fill="both", expand=True)
        tf = ttk.Frame(split)
        split.add(tf, weight=3)
        cols = ("time", "stars", "fwhm", "elong", "bg", "verdict")
        self.tree = ttk.Treeview(tf, columns=cols, selectmode="extended")
        self.tree.heading("#0", text=_("Stack / Einzelbild"))
        self.tree.column("#0", width=360)
        for c, t, w, a in (("time", _("Zeit"), 130, "w"), ("stars", _("Sterne"), 60, "e"),
                           ("fwhm", "FWHM", 60, "e"), ("elong", _("Form"), 55, "e"),
                           ("bg", _("Hintergrund"), 90, "e"), ("verdict", _("Bewertung"), 330, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "verdict"))  # pyright: ignore[reportArgumentType]
        vs = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.bind("<space>", lambda e: (self.toggle(), "break")[1])
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.preview())
        pv = ttk.Frame(split, style="Panel.TFrame", padding=8)
        split.add(pv, weight=1)
        ttk.Label(pv, text=_("Vorschau (Auto-Stretch)"), style="Section.TLabel").pack(anchor="w")
        self.pv = tk.Label(pv, bg=theme.PANEL, fg=theme.MUTED, text=_("Datei auswählen"), width=34, height=12,
                           cursor="hand2")
        self.pv.pack(fill="both", expand=True, pady=6)
        self.pv.bind("<Button-1>", lambda e: self.open_large())
        self.pv_path = ""
        self.pv_info = ttk.Label(pv, text=_("Sterne = Anzahl erkannter Sterne · FWHM = Sterngröße in Pixel "
                                            "(kleiner = schärfer) · Form = Achsenverhältnis (1,0 = rund, "
                                            "größer = Nachführfehler/Wind)"),
                                 style="PanelMuted.TLabel", wraplength=300, justify="left")
        self.pv_info.pack(fill="x")
        self.summary = ttk.Label(f, text="", style="Muted.TLabel")
        self.summary.pack(anchor="w", pady=(6, 0))
        self.color_tags()

    # ------------------------------------------------------------------
    def color_tags(self):
        self.tree.tag_configure("stack", foreground=theme.ACCENT, font=(theme.FAMILY, theme.SIZE, "bold"))
        self.tree.tag_configure("orphan", foreground=theme.BLUE, font=(theme.FAMILY, theme.SIZE, "bold"))
        self.tree.tag_configure("ok", foreground=theme.GREEN)
        self.tree.tag_configure("reject", foreground=theme.RED)
        self.tree.tag_configure("marked", foreground=theme.YELLOW)
        self.tree.tag_configure("none", foreground=theme.MUTED)

    def recolor(self):
        self.pv.configure(bg=theme.PANEL, fg=theme.MUTED)

    def set_busy(self, busy):
        for b in (self.run_btn, self.archive_btn):
            b.state(["disabled"] if busy else ["!disabled"])

    def collect_settings(self):
        self.app.settings["seestar_dir"] = self.dir_var.get().strip()

    def pick(self):
        d = filedialog.askdirectory(parent=self.app.root, title=_("Seestar-Ordner wählen"))
        if d:
            self.dir_var.set(os.path.abspath(d))

    # ------------------------------------------------------------------
    def run(self):
        app = self.app
        d = self.dir_var.get().strip()
        if app.busy:
            return
        if not d or not os.path.isdir(d):
            dialogs.showwarning(APP_NAME, _("Bitte einen vorhandenen Seestar-Ordner wählen."), parent=app.root)
            return
        app._collect_settings()
        app.cancel_ev.clear()
        app._set_busy(True)
        strict = STRICT().get(self.strict.get(), "normal")
        app.log("blue", _("Seestar-Analyse gestartet: {d}").format(d=d))

        def worker():
            try:
                res = seestar.run(d, app.cache, strict, int(app.settings["workers"]),
                                  lambda p, n, t: app.ui(app._progress, p, n, t), app.cancel_ev)
                app.ui(self._done, res)
            except Exception as e:  # noqa: BLE001
                app.logger.exception("Seestar")
                app.ui(self._failed, e)

        threading.Thread(target=worker, daemon=True).start()

    def _failed(self, e):
        self.app._set_busy(False)
        self.app.set_status(_("Seestar-Analyse fehlgeschlagen: {e}").format(e=e), "Red")

    def _done(self, res):
        self.app._set_busy(False)
        self.stacks, self.orphans, self.frames = res
        self.render()
        subs = [f for f in self.frames if not f.is_stack]
        rej = [f for f in subs if f.verdict == "reject"]
        self.app.set_status(_("Seestar: {s} Stacks, {n} Einzelbilder, {r} Ausschuss-Kandidaten.").format(
            s=len(self.stacks), n=len(subs), r=len(rej)), "Yellow" if rej else "Green")

    def reevaluate(self):
        if not self.frames:
            return
        seestar.evaluate(seestar.sessions_of([f for f in self.frames if not f.is_stack]),
                         STRICT().get(self.strict.get(), "normal"))
        self.render()

    def _verdict(self, f):
        if f.verdict == "reject":
            txt = "✖ " + "; ".join(_(r) for r in f.reasons)
        elif f.verdict == "ok":
            txt = "✔ " + _("gut")
        else:
            txt = "; ".join(f.reasons) or _("nicht analysiert")
        if f.action == "archive":
            txt = "➜ " + _("Archiv") + " · " + txt
        return txt

    def _row(self, f) -> dict[str, Any]:
        m = f.metrics or {}
        t = f.time.strftime("%d.%m.%Y %H:%M:%S") if f.time else ""
        tag = "marked" if f.action == "archive" else (f.verdict or "none")
        return dict(text=os.path.basename(f.path), tags=(tag,), values=(
            t, m.get("stars", ""), m.get("fwhm", ""), m.get("elong", ""), m.get("bg", ""), self._verdict(f)))

    def render(self):
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        self.clear_preview()
        n = 0
        for si, s in enumerate(self.stacks):
            sid = f"s{si}"
            when = s.time.strftime("%d.%m.%Y %H:%M") if s.time else "?"
            cnt = _(" (Header: {n})").format(n=s.count) if s.count else ""
            self.tree.insert("", "end", iid=sid, open=True, tags=("stack",), text=_(
                "★ Stack {o} · {e:g}s · {f} · {w} · {n} Subs{c}").format(
                o=s.obj, e=s.exposure, f=s.filt, w=when, n=len(s.subs), c=cnt), values=("", "", "", "", "", ""))
            self.items[sid] = s
            for f in sorted(s.subs, key=lambda x: x.time or 0):
                iid = f"f{n}"
                n += 1
                self.items[iid] = f
                self.tree.insert(sid, "end", iid=iid, **self._row(f))
        if self.orphans:
            self.tree.insert("", "end", iid="orph", open=False, tags=("orphan",),
                             text=_("Einzelbilder ohne passenden Stack ({n})").format(n=len(self.orphans)),
                             values=("", "", "", "", "", ""))
            for f in sorted(self.orphans, key=lambda x: (x.obj, x.time or 0)):
                iid = f"f{n}"
                n += 1
                self.items[iid] = f
                self.tree.insert("orph", "end", iid=iid, **self._row(f))
        self._summary()

    def _summary(self):
        subs = [f for f in self.frames if not f.is_stack]
        marked = [f for f in subs if f.action == "archive"]
        rej = [f for f in subs if f.verdict == "reject"]
        size = sum(f.total_size for f in marked)
        self.summary.configure(text=_("{s} Stacks · {n} Einzelbilder · {r} Ausschuss-Kandidaten · {m} markiert "
                                      "({sz} inkl. JPG/Vorschau)").format(s=len(self.stacks), n=len(subs),
                                                                         r=len(rej), m=len(marked), sz=human_size(size)))

    def _selected_subs(self):
        return [self.items[i] for i in self.tree.selection() if i.startswith("f") and i in self.items]

    def toggle(self):
        for f in self._selected_subs():
            f.action = "keep" if f.action == "archive" else "archive"
        self._refresh()

    def unmark(self):
        for f in self.frames:
            f.action = "keep"
        self._refresh()

    def mark_stack(self):
        sel = self.tree.selection()
        found = {}  # id -> Frame (Frames sind nicht hashbar)
        for i in sel:
            fr = self.items.get(i)
            st = fr if i.startswith("s") else (fr.stack if fr is not None else None)
            if st is not None:
                found[id(st)] = st
        stacks = list(found.values())
        if not stacks:
            self.app.set_status(_("Bitte einen Stack auswählen."), "Yellow")
            return
        n = sum(len(s.subs) for s in stacks)
        if not dialogs.askyesno(APP_NAME, _("Alle {n} Einzelbilder der gewählten Stacks zum Archivieren markieren?\n\n"
                                            "Sinnvoll, wenn Sie nur das fertige Stack-Bild behalten und Speicher sparen "
                                            "möchten. Ohne die Subs ist kein späteres Neu-Stacken möglich – sie bleiben "
                                            "aber bis zur Freigabe im Archiv.").format(n=n), parent=self.app.root):
            return
        for s in stacks:
            for f in s.subs:
                f.action = "archive"
        self._refresh()

    def _refresh(self):
        for iid, f in self.items.items():
            if iid.startswith("f"):
                r = self._row(f)
                self.tree.item(iid, text=r["text"], tags=r["tags"], values=r["values"])
        self._summary()

    def clear_preview(self):
        self._tok += 1
        self._photo = None
        self.pv_path = ""
        self.pv.configure(image="", text=_("Datei auswählen"), width=34, height=12)

    def open_large(self):
        if self.pv_path:
            from .viewer import open_viewer
            open_viewer(self.app, self.pv_path)

    def preview(self):
        sel = self._selected_subs()
        if not sel:
            sel = [self.items[i] for i in self.tree.selection() if i.startswith("s") and i in self.items]
        if not sel:
            self.clear_preview()
            return
        f = sel[0]
        self._tok += 1
        tok = self._tok
        self.pv_path = f.path
        self.pv.configure(image="", text=_("Lade …"))

        def done(res):
            if tok == self._tok:
                im = res[0].copy()
                im.thumbnail((360, 360))
                self._photo = ImageTk.PhotoImage(im)
                self.pv.configure(image=self._photo, text="", width=0, height=0)

        def fail(e):
            if tok == self._tok:
                self.pv.configure(image="", text=str(e))

        self.app.run_bg(imaging.load_preview, (f.path, 720), done, fail)

    def export_csv(self):
        if not self.frames:
            return
        p = filedialog.asksaveasfilename(parent=self.app.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile="Seestar_Analyse.csv")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow([_("Datei"), _("Stack"), _("Zeit"), _("Sterne"), "FWHM", _("Form"), _("Hintergrund"),
                            _("Bewertung"), _("Gründe")])
                for f in self.frames:
                    if f.is_stack:
                        continue
                    m = f.metrics or {}
                    w.writerow([f.path, os.path.basename(f.stack.path) if f.stack else "",
                                f.time.isoformat(sep=" ") if f.time else "", m.get("stars", ""),
                                str(m.get("fwhm", "")).replace(".", ","), str(m.get("elong", "")).replace(".", ","),
                                m.get("bg", ""), f.verdict, " | ".join(f.reasons)])
            self.app.log("ok", _("Seestar-Analyse gespeichert: {p}").format(p=p))
        except OSError as e:
            dialogs.showerror(APP_NAME, str(e), parent=self.app.root)

    def archive(self):
        app = self.app
        marked = [f for f in self.frames if not f.is_stack and f.action == "archive"]
        if app.busy or not marked:
            if not marked:
                app.set_status(_("Keine Einzelbilder markiert (Leertaste oder „Ausschuss ⇄ Behalten“)."), "Yellow")
            return
        am = app.manager()
        if am is None:
            return
        root = self.dir_var.get().strip()
        size = sum(f.total_size for f in marked)
        if not app.check_space(am, [(f.path, f.total_size) for f in marked]):
            return
        if not dialogs.askyesno(APP_NAME, _("{n} Seestar-Einzelbilder ({sz}, inkl. .jpg/_thn.jpg) ins Archiv "
                                            "verschieben?\n\nNichts wird gelöscht; „↶ Rückgängig“ holt sie zurück.").format(
                n=len(marked), sz=human_size(size)), parent=app.root):
            return
        app.cancel_ev.clear()
        app._set_busy(True)
        session = am.new_session()

        def worker():
            moved: list = []
            self._n_failed = 0
            state = "error"
            with keep_awake():
                try:
                    am.begin_session(session, len(marked), "seestar")
                    self._archive_loop(am, marked, root, session, moved)
                    state = "cancelled" if app.cancel_ev.is_set() else "done"
                except (OSError, ArchiveError) as e:
                    app.log("error", _("Fehler: {e}").format(e=e))
                finally:
                    failed = self._n_failed
                    try:
                        am.end_session(session, len(moved), state)
                    except OSError:
                        pass
                    app.ui(self._archived, moved, failed)

        threading.Thread(target=worker, daemon=True).start()

    def _archive_loop(self, am, marked, root, session, moved):
        app = self.app
        for i, f in enumerate(marked):
            if app.cancel_ev.is_set():
                break
            app.ui(app._progress, "Archiviere", i, len(marked))
            try:
                am.archive_file(f.path, root, "seestar", "; ".join(f.reasons) or "manuell", f.companions, session)
                moved.append(f)
            except (OSError, ArchiveError) as e:
                self._n_failed += 1
                app.log("error", _("Fehler: {p} – {e}").format(p=f.path, e=e))

    def _archived(self, moved, failed):
        self.app._set_busy(False)
        gone = {id(f) for f in moved}
        self.frames = [f for f in self.frames if id(f) not in gone]
        for s in self.stacks:
            s.subs = [f for f in s.subs if id(f) not in gone]
        self.orphans = [f for f in self.orphans if id(f) not in gone]
        self.render()
        self.app.set_status(_("{n} Seestar-Einzelbilder archiviert.").format(n=len(moved)) +
                            (" " + _("{n} Fehler").format(n=failed) if failed else ""), "Red" if failed else "Green")
        self.app.reload_archive()
