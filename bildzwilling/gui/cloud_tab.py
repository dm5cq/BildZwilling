# SPDX-License-Identifier: GPL-3.0-or-later
"""Tab „Cloud direkt“: pCloud/OneDrive über die Server-Prüfsummen prüfen – ohne Download."""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import tempfile
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from .. import APP_NAME
from ..core import cloud
from ..core.fsutil import human_size, num
from ..core.rules import valid_rules
from ..core.secret import AVAILABLE as CAN_REMEMBER
from ..core.secret import TokenStore
from ..i18n import _
from . import dialogs, theme
from .winstyle import style_titlebar


class CloudTab:
    def __init__(self, app, nb):
        self.app = app
        self.client = None
        self.account = ""
        self.groups = []
        self._thumb_dir = tempfile.mkdtemp(prefix="bz_cloud_")
        self.tokens = TokenStore(os.path.join(app.data_dir, "cloud_tokens.dat"))
        st = app.settings
        f = self.frame = ttk.Frame(nb, padding=8)
        nb.add(f, text=_("Cloud direkt"))

        r1 = ttk.Frame(f)
        r1.pack(fill="x", pady=(0, 4))
        ttk.Label(r1, text=_("Anbieter:")).pack(side="left")
        self.provider = ttk.Combobox(r1, state="readonly", width=16, values=list(cloud.PROVIDERS.values()))
        self.provider.set(cloud.PROVIDERS.get(st["cloud_provider"], cloud.PROVIDERS["pcloud_eu"]))
        self.provider.pack(side="left", padx=4)
        self.provider.bind("<<ComboboxSelected>>", lambda e: self._switch_provider())
        self.login_btn = ttk.Button(r1, text=_("Anmelden …"), command=self.login)
        self.login_btn.pack(side="left", padx=4)
        ttk.Button(r1, text=_("Abmelden"), command=self.logout).pack(side="left")
        ttk.Button(r1, text=_("Alle Anmeldungen entfernen"), command=self.forget_all).pack(side="left", padx=(6, 0))
        self.remember = tk.BooleanVar(value=st["cloud_remember"] and CAN_REMEMBER)
        cb = ttk.Checkbutton(r1, text=_("Anmeldung merken (verschlüsselt)"), variable=self.remember,
                             style="Bg.TCheckbutton")
        cb.pack(side="left", padx=10)
        if not CAN_REMEMBER:
            cb.state(["disabled"])
        self.acc_label = ttk.Label(r1, text=_("nicht angemeldet"), style="Yellow.TLabel")
        self.acc_label.pack(side="left", padx=10)

        r2 = ttk.Frame(f)
        r2.pack(fill="x", pady=(0, 4))
        ttk.Label(r2, text=_("Cloud-Ordner:")).pack(side="left")
        self.root_var = tk.StringVar(value=st["cloud_root"])
        ttk.Entry(r2, textvariable=self.root_var, width=28).pack(side="left", padx=4)
        ttk.Label(r2, text=_("Cloud-Archiv:")).pack(side="left", padx=(10, 0))
        self.arch_var = tk.StringVar(value=st["cloud_archive"])
        ttk.Entry(r2, textvariable=self.arch_var, width=26).pack(side="left", padx=4)
        ttk.Label(r2, text=_("OneDrive Client-ID:")).pack(side="left", padx=(10, 0))
        self.client_id = tk.StringVar(value=st["onedrive_client_id"])
        ttk.Entry(r2, textvariable=self.client_id, width=38).pack(side="left", padx=4)
        self.scan_btn = ttk.Button(r2, text="▶ " + _("Cloud prüfen"), style="Accent.TButton", command=self.scan)
        self.scan_btn.pack(side="right")

        ttk.Label(f, text=_("Es wird nichts heruntergeladen: Duplikate werden über die Prüfsummen des Servers erkannt "
                            "(pCloud: SHA-256/SHA-1, OneDrive: quickXorHash). Verschoben wird innerhalb der Cloud in "
                            "den Archivordner – rückgängig jederzeit."), style="Muted.TLabel", wraplength=1000,
                  justify="left").pack(anchor="w", pady=(0, 6))

        tb = ttk.Frame(f)
        tb.pack(fill="x", pady=(0, 6))
        ttk.Button(tb, text=_("Vergleichen (Vorschaubilder)"), command=self.compare).pack(side="left")
        ttk.Button(tb, text="★ " + _("Als Original"), command=self.set_original).pack(side="left", padx=4)
        ttk.Button(tb, text=_("Behalten ⇄ Archiv"), command=self.toggle).pack(side="left")
        ttk.Button(tb, text="CSV", command=self.export_csv).pack(side="left", padx=4)
        self.arch_btn = ttk.Button(tb, text="➜ " + _("In Cloud-Archiv verschieben"), style="Accent.TButton",
                                   command=self.archive)
        self.arch_btn.pack(side="right")
        self.undo_btn = ttk.Button(tb, text="↶ " + _("Letzte Cloud-Archivierung rückgängig"), command=self.undo)
        self.undo_btn.pack(side="right", padx=6)

        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True)
        cols = ("status", "folder", "size", "dims", "date")
        self.tree = ttk.Treeview(tf, columns=cols, selectmode="extended")
        self.tree.heading("#0", text=_("Gruppe / Datei"))
        self.tree.column("#0", width=300)
        for c, t, w, a in (("status", _("Aktion"), 120, "w"), ("folder", _("Cloud-Ordner"), 330, "w"),
                           ("size", _("Größe"), 85, "e"), ("dims", _("Prüfsumme"), 140, "w"),
                           ("date", _("Geändert"), 125, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "folder"))  # pyright: ignore[reportArgumentType]
        vs = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.bind("<space>", lambda e: (self.toggle(), "break")[1])
        self.tree.bind("<Double-1>", lambda e: self.compare())
        self.summary = ttk.Label(f, text="", style="Muted.TLabel")
        self.summary.pack(anchor="w", pady=(6, 0))
        self.app.root.after(300, self._auto_login)

    # ------------------------------------------------------------------ Grundlagen
    def provider_key(self) -> str:
        label = self.provider.get()
        return next((k for k, v in cloud.PROVIDERS.items() if v == label), "pcloud_eu")

    def recolor(self):
        pass

    def set_busy(self, busy):
        for b in (self.scan_btn, self.arch_btn, self.undo_btn, self.login_btn):
            b.state(["disabled"] if busy else ["!disabled"])

    def collect_settings(self):
        st = self.app.settings
        st["cloud_provider"] = self.provider_key()
        st["cloud_root"] = self.root_var.get().strip() or "/"
        st["cloud_archive"] = self.arch_var.get().strip() or "/BildZwilling_Archiv"
        st["onedrive_client_id"] = self.client_id.get().strip()
        st["cloud_remember"] = bool(self.remember.get())

    def cleanup(self):
        shutil.rmtree(self._thumb_dir, ignore_errors=True)

    def _set_account(self, acc: str):
        self.account = acc
        if acc:
            self.acc_label.configure(text=_("angemeldet: {a}").format(a=acc), style="Green.TLabel")
        else:
            self.acc_label.configure(text=_("nicht angemeldet"), style="Yellow.TLabel")

    # ------------------------------------------------------------------ Anmeldung
    def _auto_login(self):
        key = self.provider_key()
        tok = self.tokens.get(key) if CAN_REMEMBER and self.app.settings["cloud_remember"] else ""
        if not tok:
            return
        c = cloud.make_client(key, self.client_id.get())
        c.set_token(tok)

        def check():
            return c.account()

        def ok(acc):
            self.client = c
            self._set_account(acc)

        self.app.run_bg(check, (), ok, lambda e: self.app.log("warn", _("Gespeicherte Cloud-Anmeldung ungültig: {e}")
                                                                .format(e=e)))

    def login(self):
        key = self.provider_key()
        self.collect_settings()
        self.app.settings.save()
        if key == "onedrive":
            self._login_onedrive()
        else:
            self._login_pcloud(key)

    def _dialog(self, title):
        w = tk.Toplevel(self.app.root)
        w.withdraw()
        w.title(title)
        w.configure(bg=theme.BG)
        w.transient(self.app.root)
        w.resizable(False, False)
        fr = ttk.Frame(w, padding=16)
        fr.pack(fill="both", expand=True)
        return w, fr

    def _login_pcloud(self, key):
        """pCloud-Anmeldung: A) im Browser (OAuth, auch mit 2FA) oder B) E-Mail/Passwort + ggf. 2FA-Code."""
        w, fr = self._dialog(_("pCloud-Anmeldung"))
        st = self.app.settings
        ttk.Label(fr, text=cloud.PROVIDERS[key], style="Orange.TLabel").pack(anchor="w")
        nb = ttk.Notebook(fr)
        nb.pack(fill="both", expand=True, pady=(6, 0))
        msg = ttk.Label(fr, text="", style="Red.TLabel", wraplength=520, justify="left")
        msg.pack(anchor="w", pady=(8, 0))
        c = cloud.PCloud(key)

        def success(token_str, acc):
            self.client = c
            self._set_account(acc)
            if self.remember.get() and CAN_REMEMBER:
                self.tokens.set(key, token_str)
            w.destroy()

        def fail(e):
            if w.winfo_exists():
                msg.configure(text=str(e), style="Red.TLabel")

        # ---------------------------------------------- A) Browser / OAuth
        a = ttk.Frame(nb, padding=10)
        nb.add(a, text=_("Im Browser (empfohlen, auch mit 2FA)"))
        ttk.Label(a, text=_("Sie melden sich auf der pCloud-Seite an – inklusive Zwei-Faktor-Code. BildZwilling sieht "
                            "Ihr Passwort nie. Einmalig nötig: eine eigene pCloud-App (kostenlos) unter "
                            "docs.pcloud.com → „My applications“ anlegen und Client-ID/Secret hier eintragen."),
                  style="Muted.TLabel", wraplength=520, justify="left").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(a, text=_("Client-ID:")).grid(row=1, column=0, sticky="w", pady=(8, 2))
        cid = tk.StringVar(value=st["pcloud_client_id"])
        ttk.Entry(a, textvariable=cid, width=36).grid(row=1, column=1, sticky="w", pady=(8, 2))
        ttk.Label(a, text=_("Client-Secret:")).grid(row=2, column=0, sticky="w", pady=2)
        sec = tk.StringVar(value=self.tokens.get("pcloud_app_secret") if CAN_REMEMBER else "")
        ttk.Entry(a, textvariable=sec, width=36, show="•").grid(row=2, column=1, sticky="w", pady=2)

        def open_page():
            if not cid.get().strip():
                fail(_("Bitte zuerst die Client-ID eintragen."))
                return
            webbrowser.open(cloud.PCloud.oauth_url(cid.get()))
            msg.configure(text=_("Im Browser anmelden (ggf. 2FA-Code eingeben), „Zulassen“ wählen und den angezeigten "
                                 "Code unten einfügen."), style="Blue.TLabel")

        ttk.Button(a, text="1. " + _("Anmeldeseite öffnen"), command=open_page).grid(row=3, column=0, columnspan=2,
                                                                                       sticky="w", pady=(10, 4))
        ttk.Label(a, text="2. " + _("Angezeigten Code einfügen:")).grid(row=4, column=0, sticky="w")
        code = tk.StringVar()
        ttk.Entry(a, textvariable=code, width=36).grid(row=4, column=1, sticky="w")

        def go_oauth(_e=None):
            if not (cid.get().strip() and sec.get().strip() and code.get().strip()):
                fail(_("Bitte Client-ID, Client-Secret und Code eintragen."))
                return
            st["pcloud_client_id"] = cid.get().strip()
            st.save()
            if self.remember.get() and CAN_REMEMBER:
                self.tokens.set("pcloud_app_secret", sec.get().strip())
            msg.configure(text=_("Anmeldung läuft …"), style="Blue.TLabel")

            def work():
                t = c.oauth_finish(cid.get(), sec.get(), code.get())
                return t, c.account()

            self.app.run_bg(work, (), lambda r: success(*r), fail)

        ttk.Button(a, text="3. " + _("Anmelden"), style="Accent.TButton", command=go_oauth).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # ---------------------------------------------- B) E-Mail / Passwort / 2FA
        b = ttk.Frame(nb, padding=10)
        nb.add(b, text=_("E-Mail und Passwort"))
        ttk.Label(b, text=_("E-Mail:")).grid(row=0, column=0, sticky="w", pady=4)
        user = tk.StringVar()
        e1 = ttk.Entry(b, textvariable=user, width=34)
        e1.grid(row=0, column=1, pady=4, sticky="w")
        ttk.Label(b, text=_("Passwort:")).grid(row=1, column=0, sticky="w", pady=4)
        pw = tk.StringVar()
        ttk.Entry(b, textvariable=pw, width=34, show="•").grid(row=1, column=1, pady=4, sticky="w")
        tfa_lbl = ttk.Label(b, text=_("Sicherheitscode (2FA):"))
        tfa_code = tk.StringVar()
        tfa_entry = ttk.Entry(b, textvariable=tfa_code, width=16)
        trust = tk.BooleanVar(value=True)
        trust_cb = ttk.Checkbutton(b, text=_("Diesem Gerät 30 Tage vertrauen"), variable=trust, style="Bg.TCheckbutton")
        ttk.Label(b, text=_("Das Passwort wird nur per HTTPS an pCloud gesendet und nie gespeichert. Bei aktivierter "
                            "Zwei-Faktor-Anmeldung erscheint nach dem ersten Schritt ein Feld für den Sicherheitscode "
                            "(App, SMS oder Wiederherstellungscode)."),
                  style="Muted.TLabel", wraplength=520, justify="left").grid(row=5, column=0, columnspan=2,
                                                                             sticky="w", pady=(8, 0))
        state = {"tfa": ""}

        def show_tfa(e):
            state["tfa"] = e.tfa_token
            tfa_lbl.grid(row=2, column=0, sticky="w", pady=4)
            tfa_entry.grid(row=2, column=1, sticky="w", pady=4)
            trust_cb.grid(row=3, column=1, sticky="w")
            tfa_entry.focus_set()
            msg.configure(text=_("Zwei-Faktor-Anmeldung: Bitte den Sicherheitscode eingeben."), style="Blue.TLabel")

        def go_pw(_e=None):
            if state["tfa"]:
                cd = tfa_code.get().strip()
                if not cd:
                    return
                msg.configure(text=_("Anmeldung läuft …"), style="Blue.TLabel")

                def fail2(e):
                    fail(str(e) + "\n" + _("Tipp: Falls die Code-Abfrage hier nicht klappt, die Anmeldung im Browser "
                                            "verwenden (Reiter links)."))

                self.app.run_bg(lambda: (c.login_2fa(state["tfa"], cd, bool(trust.get())), user.get().strip()),
                                (), lambda r: success(*r), fail2)
                return
            u, p = user.get().strip(), pw.get()
            if not u or not p:
                return
            pw.set("")
            msg.configure(text=_("Anmeldung läuft …"), style="Blue.TLabel")

            def failed(e):
                if isinstance(e, cloud.TwoFactorRequired) and e.tfa_token:
                    show_tfa(e)
                elif isinstance(e, cloud.TwoFactorRequired):
                    fail(_("pCloud verlangt die Zwei-Faktor-Anmeldung. Bitte die Anmeldung im Browser verwenden "
                           "(Reiter links)."))
                else:
                    fail(e)

            self.app.run_bg(lambda: (c.login(u, p), u), (), lambda r: success(*r), failed)

        ttk.Button(b, text=_("Anmelden"), style="Accent.TButton", command=go_pw).grid(row=4, column=1, sticky="w",
                                                                                      pady=(10, 0))
        bar = ttk.Frame(fr)
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text=_("Abbrechen"), command=w.destroy).pack(side="right")

        def on_return(_e=None):
            if nb.index("current") == 0:
                go_oauth()
            else:
                go_pw()

        w.bind("<Return>", on_return)
        w.bind("<Escape>", lambda e: w.destroy())
        if st["pcloud_client_id"]:
            nb.select(0)
        style_titlebar(w)
        w.deiconify()
        self._login_widgets = dict(win=w, cid=cid, sec=sec, code=code, user=user, pw=pw, tfa=tfa_code,
                                   go_oauth=go_oauth, go_pw=go_pw, nb=nb, msg=msg)

    def _login_onedrive(self):
        cid = self.client_id.get().strip()
        if not cid:
            dialogs.showinfo(APP_NAME, _("Für OneDrive wird eine eigene, kostenlose App-Registrierung benötigt:\n\n"
                                         "1. portal.azure.com → „App-Registrierungen“ → „Neue Registrierung“\n"
                                         "2. Kontotyp: „Konten in beliebigen Organisationen und persönliche "
                                         "Microsoft-Konten“\n"
                                         "3. „Authentifizierung“ → „Öffentliche Clientflows zulassen“ = Ja\n"
                                         "4. „API-Berechtigungen“: Microsoft Graph → Files.ReadWrite, User.Read\n"
                                         "5. Die „Anwendungs-ID (Client)“ hier eintragen.\n\n"
                                         "Details: Technische Beschreibung, Kapitel „Cloud direkt“."), parent=self.app.root)
            return
        c = cloud.OneDrive(cid)
        w, fr = self._dialog(_("OneDrive-Anmeldung"))
        info = ttk.Label(fr, text=_("Code wird angefordert …"), style="Blue.TLabel", justify="left")
        info.pack(anchor="w")
        code_lbl = ttk.Label(fr, text="", style="Title.TLabel")
        code_lbl.pack(anchor="w", pady=8)
        bar = ttk.Frame(fr)
        bar.pack(fill="x", pady=(8, 0))
        cancel = threading.Event()
        url = {"u": "https://microsoft.com/devicelogin"}
        ttk.Button(bar, text=_("Anmeldeseite öffnen"), style="Accent.TButton",
                   command=lambda: webbrowser.open(url["u"])).pack(side="left")
        ttk.Button(bar, text=_("Code kopieren"), command=lambda: (self.app.root.clipboard_clear(),
                                                                   self.app.root.clipboard_append(code_lbl.cget("text")))
                   ).pack(side="left", padx=6)
        ttk.Button(bar, text=_("Abbrechen"), command=lambda: (cancel.set(), w.destroy())).pack(side="right")
        style_titlebar(w)
        w.deiconify()

        def on_code(code, uri, message):
            def show():
                if uri:
                    url["u"] = uri
                info.configure(text=_("1. Anmeldeseite öffnen: {u}\n2. Diesen Code eingeben und mit Ihrem "
                                      "Microsoft-Konto bestätigen:").format(u=url["u"]), style="TLabel")
                code_lbl.configure(text=code)
            self.app.ui(show)

        def done(refresh):
            if not w.winfo_exists():
                return
            self.client = c
            if self.remember.get() and CAN_REMEMBER:
                self.tokens.set("onedrive", refresh)
            self.app.run_bg(c.account, (), lambda acc: self._set_account(acc or "OneDrive"),
                            lambda e: self._set_account("OneDrive"))
            w.destroy()

        def fail(e):
            if w.winfo_exists():
                info.configure(text=str(e), style="Red.TLabel")

        self.app.run_bg(lambda: c.device_login(on_code, cancel), (), done, fail)

    def _switch_provider(self):
        """Anbieter gewechselt: Sitzung beenden, gespeicherte Anmeldungen bleiben erhalten."""
        self.client = None
        self._set_account("")
        self.groups = []
        self.render()
        self._auto_login()

    def logout(self, silent=False):
        if self.client is not None:
            try:
                if getattr(self.client, "kind", "") == "pcloud":
                    c = self.client

                    def bg_logout():
                        try:
                            c.logout()  # Token beim Server ungültig machen; Fehler (offline) sind unkritisch
                        except Exception:  # noqa: BLE001
                            pass

                    threading.Thread(target=bg_logout, daemon=True).start()
                else:
                    self.client.logout()
            except Exception:  # noqa: BLE001
                pass
        self.client = None
        self.tokens.clear(self.provider_key())
        self._set_account("")
        self.groups = []
        self.render()
        if not silent:
            self.app.set_status(_("Von der Cloud abgemeldet."), "Green")

    def forget_all(self, ask=True):
        """Alle gespeicherten Anmeldungen (alle Anbieter, pCloud-Client-Secret) löschen und abmelden (2.2, B3)."""
        if ask and not dialogs.askyesno(APP_NAME, _("Alle gespeicherten Cloud-Anmeldungen (pCloud, OneDrive) und das "
                                                    "pCloud-Client-Secret von diesem Rechner entfernen und abmelden?"),
                                        parent=self.app.root):
            return 0
        self.logout(silent=True)
        n = self.tokens.clear_all()
        self.app.settings["cloud_remember"] = False
        self.remember.set(False)
        self.app.set_status(_("Alle Cloud-Anmeldungen entfernt ({n} gespeicherte Einträge).").format(n=n), "Green")
        self.app.log("info", _("Alle gespeicherten Cloud-Anmeldungen entfernt."))
        return n

    # ------------------------------------------------------------------ Suche
    def scan(self):
        app = self.app
        if app.busy:
            return
        if self.client is None:
            app.set_status(_("Bitte zuerst bei der Cloud anmelden."), "Yellow")
            return
        self.collect_settings()
        app._collect_settings()
        st = app.settings
        app.cancel_ev.clear()
        app._set_busy(True)
        app.log("blue", _("Cloud-Prüfung gestartet: {p} {r}").format(p=self.provider.get(), r=st["cloud_root"]))

        def worker():
            try:
                res = cloud.scan(self.client, st["cloud_root"], st["images_only"], st["include_videos"],
                                 st["min_size_kb"] * 1024, st["keep_rule"], valid_rules(st["folder_rules"]),
                                 int(st["workers"]), lambda p, d, t: app.ui(app._progress, p, d, t), app.log,
                                 app.cancel_ev)
                app.ui(self._done, res)
            except Exception as e:  # noqa: BLE001
                app.ui(self._failed, e)

        threading.Thread(target=worker, daemon=True).start()

    def _failed(self, e):
        self.app._set_busy(False)
        self.app.set_status(_("Cloud-Prüfung fehlgeschlagen: {e}").format(e=e), "Red")
        self.app.log("error", str(e))

    def _done(self, groups):
        self.app._set_busy(False)
        self.groups = groups
        self.render()
        dup = sum(len(g.files) - 1 for g in groups)
        self.app.set_status(_("Cloud: {g} Gruppen · {d} Duplikate · {sz} freizugeben (ohne Download geprüft).").format(
            g=len(groups), d=dup, sz=human_size(sum(g.savable for g in groups))), "Green")

    # ------------------------------------------------------------------ Liste
    def render(self):
        self.tree.delete(*self.tree.get_children())
        for gi, g in enumerate(self.groups):
            self.tree.insert("", "end", iid=f"g{gi}", open=True, tags=("group",),
                             text=_("Gruppe {n}  ·  {c} Dateien  ·  {k}").format(n=gi + 1, c=len(g.files),
                                                                                 k=_("Server-Prüfsumme gleich")),
                             values=("", "", human_size(g.savable), "", ""))
            for fi, f in enumerate(g.files):
                self.tree.insert(f"g{gi}", "end", iid=f"f{gi}_{fi}", text=f.cloud.name, tags=(f.action,),
                                 values=self._vals(f))
        self._summary()

    def _vals(self, f):
        st = "✔ " + _("BEHALTEN") if f.action == "keep" else "➜ " + _("Archiv")
        date = _dt.datetime.fromtimestamp(f.cloud.mtime).strftime("%d.%m.%Y %H:%M") if f.cloud.mtime else ""
        folder = f.path.rsplit("/", 1)[0] or "/"
        return (st, folder, human_size(f.size), (f.digest or "")[:16], date)

    def _refresh(self):
        for gi, g in enumerate(self.groups):
            self.tree.item(f"g{gi}", values=("", "", human_size(g.savable), "", ""))
            for fi, f in enumerate(g.files):
                self.tree.item(f"f{gi}_{fi}", tags=(f.action,), values=self._vals(f))
        self._summary()

    def _summary(self):
        n = sum(len(g.to_archive) for g in self.groups)
        self.summary.configure(text=_("{g} Gruppen · {n} Dateien zum Verschieben markiert · {sz}").format(
            g=num(len(self.groups)), n=num(n), sz=human_size(sum(g.savable for g in self.groups))))

    def _sel(self):
        out = []
        for iid in self.tree.selection():
            if iid.startswith("f"):
                gi, fi = map(int, iid[1:].split("_"))
                out.append((gi, fi))
        return out

    def toggle(self):
        for gi, fi in self._sel():
            g = self.groups[gi]
            f = g.files[fi]
            if f.action == "keep":
                if len(g.keepers) <= 1:
                    self.app.set_status(_("In der identischen Gruppe muss mindestens eine Datei behalten werden."),
                                        "Yellow")
                    continue
                f.action = "archive"
            else:
                f.action = "keep"
        self._refresh()

    def set_original(self):
        sel = self._sel()
        if not sel:
            return
        gi, fi = sel[0]
        for i, f in enumerate(self.groups[gi].files):
            f.action = "keep" if i == fi else "archive"
        self._refresh()

    def compare(self):
        sel = self._sel()
        if not sel or self.client is None:
            return
        gi, fi = sel[0]
        g = self.groups[gi]
        other = next((i for i in range(len(g.files)) if i != fi), 0)
        a, b = g.files[fi], g.files[other]
        app = self.app

        def fetch():
            paths = []
            for f in (a, b):
                p = os.path.join(self._thumb_dir, f"{f.cloud.id}.jpg")
                if not os.path.exists(p):
                    client = self.client
                    if client is None:
                        raise cloud.CloudError(_("Nicht angemeldet."))
                    with open(p, "wb") as fh:
                        fh.write(client.thumbnail(f.cloud.id))
                paths.append(p)
            return paths

        def show(paths):
            from .compare import CompareWindow
            if app.compare_win is None:
                app.compare_win = CompareWindow(app)
            app.compare_win.show_paths(paths[0], paths[1], _("Cloud: {p}").format(p=a.path),
                                       _("Cloud: {p}").format(p=b.path))

        app.set_status(_("Vorschaubilder werden geladen …"), "Blue")
        app.run_bg(fetch, (), show, lambda e: app.set_status(_("Keine Vorschau: {e}").format(e=e), "Yellow"))

    def export_csv(self):
        if not self.groups:
            return
        from tkinter import filedialog

        from ..core import report
        p = filedialog.asksaveasfilename(parent=self.app.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile="BildZwilling_Cloud.csv")
        if p:
            report.export_groups_csv(self.groups, p)
            self.app.log("ok", _("CSV-Bericht gespeichert ({n} Zeilen): {p}").format(
                n=sum(len(g.files) for g in self.groups), p=p))

    # ------------------------------------------------------------------ Archiv & Rückgängig
    def _archive_obj(self):
        self.collect_settings()
        return cloud.CloudArchive(self.client, self.app.settings["cloud_archive"],
                                  os.path.join(self.app.data_dir, "cloud_journal.jsonl"),
                                  self.provider_key(), self.account)

    def archive(self):
        app = self.app
        todo = [(g, f, g.keepers[0]) for g in self.groups if g.keepers for f in g.to_archive]
        if app.busy or not todo or self.client is None:
            if not todo:
                app.set_status(_("Keine Dateien zum Verschieben markiert."), "Yellow")
            return
        ca = self._archive_obj()
        if not dialogs.askyesno(APP_NAME, _("{n} Dateien ({sz}) innerhalb der Cloud in den Ordner\n{a}\nverschieben?\n\n"
                                            "Vor jedem Verschieben werden Größe und Server-Prüfsumme von Duplikat und "
                                            "Original erneut abgefragt. Nichts wird gelöscht; „↶ Rückgängig“ holt "
                                            "alles zurück.").format(n=len(todo), sz=human_size(sum(f.size for _g, f, _k
                                                                                                    in todo)),
                                                                    a=ca.root), parent=app.root):
            return
        app.cancel_ev.clear()
        app._set_busy(True)
        session = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")

        def worker():
            moved, skipped, failed = set(), 0, 0
            try:
                for i, (g, f, keep) in enumerate(todo):
                    if app.cancel_ev.is_set():
                        break
                    app.ui(app._progress, "Cloud: verschieben", i, len(todo))
                    try:
                        ok, why = ca.archive(f, keep, session)
                    except cloud.CloudError as e:
                        failed += 1
                        app.log("error", _("Fehler: {p} – {e}").format(p=f.path, e=e))
                        continue
                    if ok:
                        moved.add(id(f))
                        app.log("ok", _("In Cloud-Archiv verschoben: {p}").format(p=f.path))
                    else:
                        skipped += 1
                        app.log("warn", _("Übersprungen: {p} – {w}").format(p=f.path, w=_(why)))
            finally:
                app.ui(self._archived, moved, skipped, failed)

        threading.Thread(target=worker, daemon=True).start()

    def _archived(self, moved, skipped, failed):
        self.app._set_busy(False)
        for g in self.groups:
            g.files = [f for f in g.files if id(f) not in moved]
        self.groups = [g for g in self.groups if len(g.files) > 1]
        self.render()
        msg = _("{n} Dateien in das Cloud-Archiv verschoben").format(n=len(moved))
        if skipped:
            msg += " · " + _("{n} übersprungen").format(n=skipped)
        if failed:
            msg += " · " + _("{n} Fehler").format(n=failed)
        self.app.set_status(msg, "Red" if failed else ("Yellow" if skipped else "Green"))

    def undo(self):
        app = self.app
        if app.busy or self.client is None:
            if self.client is None:
                app.set_status(_("Bitte zuerst bei der Cloud anmelden."), "Yellow")
            return
        ca = self._archive_obj()
        sid, items = ca.last_session()
        if not sid:
            app.set_status(_("Keine Cloud-Archivierung zum Rückgängigmachen gefunden."), "Yellow")
            return
        if not dialogs.askyesno(APP_NAME, _("Letzte Cloud-Archivierung ({n} Dateien) rückgängig machen?").format(
                n=len(items)), parent=app.root):
            return
        app._set_busy(True)

        def worker():
            n, errors, fatal = 0, [], None
            try:
                n, errors = ca.undo_session(sid)
            except Exception as e:  # noqa: BLE001 – z. B. Netzwerk weg: Oberfläche darf nicht „beschäftigt“ bleiben
                fatal = e
            finally:
                for e in errors:
                    app.log("error", e)
                if fatal is not None:
                    app.log("error", str(fatal))
                app.ui(lambda: (app._set_busy(False), app.set_status(
                    _("{n} Dateien in der Cloud wiederhergestellt – bitte erneut prüfen.").format(n=n)
                    + (" " + _("Fehler: {e}").format(e=fatal) if fatal else ""),
                    "Red" if fatal else ("Yellow" if errors else "Green"))))

        threading.Thread(target=worker, daemon=True).start()
