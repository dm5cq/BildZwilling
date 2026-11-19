# SPDX-License-Identifier: GPL-3.0-or-later
"""Archiv: Duplikate sicher verschieben, wiederherstellen und erst nach Freigabe löschen.

Sicherheitsprinzipien
- Es wird nie gelöscht, nur ins Archiv verschoben. Endgültiges Löschen ist ein eigener,
  bestätigter Schritt (wahlweise in den Papierkorb).
- Vor jedem Verschieben wird das Duplikat erneut direkt mit dem behaltenen Original
  verglichen (Byte für Byte bzw. Pixel). Hat sich eine Datei seit der Suche geändert,
  wird sie übersprungen.
- Laufwerksübergreifend: kopieren -> Kopie prüfen -> erst dann Quelle entfernen.
- Jede Aktion wird in einem Journal (JSON-Lines) im Archivordner protokolliert;
  daraus kann jederzeit wiederhergestellt werden.
- Wiederherstellen/Löschen akzeptiert nur Pfade innerhalb des Archivordners.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import threading
import uuid

from . import imaging
from .formats import SIDECAR_EXT
from .fsutil import is_within, lp, safe_name, same_device, unique_path
from .scanner import FileEntry
from ..i18n import _ as tr

JOURNAL_NAME = "_BildZwilling_Journal.jsonl"
CHUNK = 1024 * 1024

try:
    from send2trash import send2trash  # type: ignore

    HAVE_TRASH = True
except Exception:  # noqa: BLE001
    HAVE_TRASH = False


class ArchiveError(Exception):
    pass


def files_identical(a: str, b: str, cancel=None) -> bool:
    """Direkter Byte-Vergleich (kein Hash) – bricht beim ersten Unterschied ab."""
    if os.path.getsize(lp(a)) != os.path.getsize(lp(b)):
        return False
    with open(lp(a), "rb") as fa, open(lp(b), "rb") as fb:
        while True:
            if cancel is not None and cancel.is_set():
                raise ArchiveError(tr('abgebrochen'))
            x, y = fa.read(CHUNK), fb.read(CHUNK)
            if x != y:
                return False
            if not x:
                return True


def root_label(root: str) -> str:
    root = os.path.abspath(root)
    name = os.path.basename(root.rstrip("\\/")) or root.replace(":", "").strip("\\/") or "Root"
    tag = hashlib.blake2b(os.path.normcase(root).encode("utf-8", "surrogatepass"), digest_size=3).hexdigest()
    return f"{safe_name(name)}_{tag}"


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


class Journal:
    def __init__(self, archive_dir: str):
        self.path = os.path.join(archive_dir, JOURNAL_NAME)
        self._lock = threading.Lock()

    def append(self, rec: dict) -> None:
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(lp(self.path), "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

    def records(self):
        """Alle lesbaren Journalzeilen (für Sitzungsstatus)."""
        try:
            with open(lp(self.path), encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(rec, dict):
                        yield rec
        except FileNotFoundError:
            return

    def active(self) -> tuple[list[dict], int]:
        """Aktive (archivierte, nicht wiederhergestellte/gelöschte) Einträge + Anzahl defekter Zeilen."""
        moves: dict[str, dict] = {}
        bad = 0
        try:
            with open(lp(self.path), encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        op = rec.get("op")
                        rid = str(rec.get("id", ""))
                        if op == "move" and rid and isinstance(rec.get("dst"), str) and isinstance(rec.get("src"), str):
                            moves[rid] = rec
                        elif op in ("restore", "delete"):
                            moves.pop(rid, None)
                    except (ValueError, AttributeError):
                        bad += 1
        except FileNotFoundError:
            pass
        return list(moves.values()), bad


class ArchiveManager:
    def __init__(self, archive_dir: str, move_sidecars: bool = True, log=None):
        if not archive_dir:
            raise ArchiveError(tr('Kein Archivordner gewählt.'))
        self.dir = os.path.abspath(archive_dir)
        self.move_sidecars = move_sidecars
        self.journal = Journal(self.dir)
        self.log = log or (lambda level, msg: None)

    # ------------------------------------------------------------------ Grundoperation
    def _inside(self, path: str) -> bool:
        return is_within(path, self.dir) and os.path.normcase(os.path.abspath(path)) != os.path.normcase(self.dir)

    def _move(self, src: str, dst: str) -> None:
        os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
        if os.path.lexists(lp(dst)):
            raise ArchiveError(tr('Ziel existiert bereits: {0}').format(dst))
        if same_device(src, os.path.dirname(dst)):
            os.rename(lp(src), lp(dst))
            return
        tmp = dst + ".bz_part"
        try:
            shutil.copy2(lp(src), lp(tmp))
            if not files_identical(src, tmp):
                raise ArchiveError(tr('Kopie weicht vom Original ab – Vorgang abgebrochen.'))
            os.replace(lp(tmp), lp(dst))
        except BaseException:
            try:
                if os.path.exists(lp(tmp)):
                    os.remove(lp(tmp))
            except OSError:
                pass
            raise
        try:
            os.remove(lp(src))
        except OSError as e:
            # Quelle nicht entfernbar (schreibgeschützt/Cloud) -> Kopie zurücknehmen
            try:
                os.remove(lp(dst))
            except OSError:
                pass
            raise ArchiveError(tr('Quelldatei konnte nicht entfernt werden: {0}').format(e)) from e

    def _sidecars(self, src: str, also_moving=()) -> list[str]:
        """Begleitdateien (XMP …), die eindeutig zu dieser Datei gehören.

        also_moving: Dateinamen (klein), die gemeinsam verschoben werden (RAW+JPEG-Paar).
        """
        moving = {n.lower() for n in also_moving}
        if not self.move_sidecars:
            return []
        folder, name = os.path.split(src)
        stem = os.path.splitext(name)[0]
        try:
            names = os.listdir(lp(folder))
        except OSError:
            return []
        lower = {n.lower(): n for n in names}
        out = []
        for ext in {e.lower() for e in SIDECAR_EXT}:
            n = lower.get((name + ext).lower())  # bild.cr3.xmp
            if n:
                out.append(os.path.join(folder, n))
        # bild.xmp nur, wenn keine andere Datei mit gleichem Stamm existiert (z. B. RAW+JPEG)
        others = [n for n in names
                  if os.path.splitext(n)[0].lower() == stem.lower()
                  and n.lower() != name.lower() and n.lower() not in moving
                  and os.path.splitext(n)[1].lower() not in {e.lower() for e in SIDECAR_EXT}]
        if not others:
            for ext in {e.lower() for e in SIDECAR_EXT}:
                n = lower.get((stem + ext).lower())
                if n:
                    out.append(os.path.join(folder, n))
        return out

    # ------------------------------------------------------------------ Prüfen
    def verify(self, dup: FileEntry, keep: FileEntry, cancel=None, similar: bool = False) -> tuple[bool, str]:
        try:
            st = os.stat(lp(dup.path))
        except OSError:
            return False, tr('Duplikat existiert nicht mehr')
        if st.st_size != dup.size or st.st_mtime_ns != dup.mtime_ns:
            return False, tr('Duplikat wurde seit der Suche verändert')
        if not os.path.isfile(lp(keep.path)):
            return False, tr('Behaltene Datei existiert nicht mehr')
        if os.path.normcase(os.path.abspath(dup.path)) == os.path.normcase(os.path.abspath(keep.path)):
            return False, tr('Duplikat und Original sind dieselbe Datei')
        try:
            if os.path.samefile(lp(dup.path), lp(keep.path)):
                return False, tr('Hardlink auf dieselbe Datei – nichts zu sparen')
        except OSError:
            pass
        if similar:
            return True, tr('ähnliches Bild – vom Benutzer bestätigt')
        if dup.digest and keep.digest and dup.digest == keep.digest:
            if files_identical(dup.path, keep.path, cancel):
                return True, tr('byte-identisch bestätigt')
            return False, tr('nicht mehr byte-identisch')
        pa = imaging.pixel_digest(dup.path, cancel)
        pb = imaging.pixel_digest(keep.path, cancel)
        if pa and pa == pb:
            return True, tr('Bildinhalt identisch bestätigt')
        return False, tr('Bildinhalt nicht (mehr) identisch')

    # ------------------------------------------------------------------ Archivieren
    def target_for(self, f: FileEntry) -> str:
        rel = os.path.relpath(os.path.abspath(f.path), os.path.abspath(f.root)) if f.root else ""
        if not rel or rel.startswith("..") or os.path.isabs(rel):
            rel = os.path.basename(f.path)
        return os.path.join(self.dir, root_label(f.root or os.path.dirname(f.path)), rel)

    def archive(self, dup: FileEntry, keep: FileEntry, kind: str, cancel=None,
                companions=(), session: str = "") -> tuple[bool, str]:
        if self._inside(dup.path):
            return False, tr('liegt bereits im Archiv')
        ok, why = self.verify(dup, keep, cancel, similar=(kind == "similar"))
        if not ok:
            return False, why
        companions = [c for c in companions if os.path.isfile(lp(c)) and not self._inside(c)]
        comp_names = [os.path.basename(c) for c in companions]
        sidecars = self._sidecars(dup.path, comp_names)
        dst = unique_path(self.target_for(dup))
        self._move(dup.path, dst)
        moved_sc = []
        # Paarpartner (RAW <-> JPEG) mit gleichem Namensstamm wie das archivierte Duplikat
        for comp in companions:
            cdst = unique_path(os.path.join(os.path.dirname(dst),
                                            os.path.splitext(os.path.basename(dst))[0] + os.path.splitext(comp)[1]))
            try:
                c_sc = self._sidecars(comp, [os.path.basename(dup.path)])
                self._move(comp, cdst)
                moved_sc.append([comp, cdst])
                for sc in c_sc:
                    if any(os.path.normcase(sc) == os.path.normcase(x) for x in sidecars):
                        continue
                    sdst = unique_path(os.path.join(os.path.dirname(cdst),
                                                    os.path.basename(cdst) + sc[len(comp):]
                                                    if sc.lower().startswith(comp.lower())
                                                    else os.path.basename(sc)))
                    self._move(sc, sdst)
                    moved_sc.append([sc, sdst])
            except (OSError, ArchiveError) as e:
                self.log("warn", tr('Paarpartner nicht verschoben: {0} ({1})').format(comp, e))
        for sc in sidecars:
            sname = os.path.basename(sc)
            dname = os.path.basename(dst)
            if sname.lower().startswith(os.path.basename(dup.path).lower()):
                new = dname + sname[len(os.path.basename(dup.path)):]
            else:
                new = os.path.splitext(dname)[0] + os.path.splitext(sname)[1]
            sdst = unique_path(os.path.join(os.path.dirname(dst), new))
            try:
                self._move(sc, sdst)
                moved_sc.append([sc, sdst])
            except (OSError, ArchiveError) as e:
                self.log("warn", tr('Begleitdatei nicht verschoben: {0} ({1})').format(sc, e))
        self.journal.append({
            "v": 1, "op": "move", "id": uuid.uuid4().hex, "time": _now(),
            "src": dup.path, "dst": dst, "keep": keep.path, "size": dup.size,
            "digest": dup.digest or dup.pdigest or "", "kind": kind, "sidecars": moved_sc,
            "session": session,
        })
        return True, why

    # ------------------------------------------------------------------ Archiv verwalten
    def entries(self) -> tuple[list[dict], int]:
        return self.journal.active()

    def restore(self, rec: dict) -> str:
        dst = rec.get("dst", "")
        if not self._inside(dst):
            raise ArchiveError(tr('Journal-Eintrag zeigt außerhalb des Archivs – abgelehnt.'))
        src = rec.get("src", "")
        if not src or self._inside(src) or not os.path.isabs(src):
            raise ArchiveError(tr('Ungültiger Originalpfad im Journal – abgelehnt.'))
        if not os.path.isfile(lp(dst)):
            raise ArchiveError(tr('Archivdatei fehlt.'))
        target = unique_path(src)  # nie überschreiben
        self._move(dst, target)
        for pair in rec.get("sidecars", []) or []:
            try:
                s_orig, s_arch = pair
                if self._inside(s_arch) and os.path.exists(lp(s_arch)):
                    self._move(s_arch, unique_path(s_orig))
            except (OSError, ArchiveError, ValueError, TypeError) as e:
                self.log("warn", tr('Begleitdatei nicht wiederhergestellt: {0} ({1})').format(pair, e))
        self.journal.append({"v": 1, "op": "restore", "id": rec["id"], "time": _now(), "to": target})
        self._cleanup_dirs(os.path.dirname(dst))
        return target

    def archive_file(self, path: str, root: str, kind: str, reason: str = "", companions=(),
                     session: str = "") -> str:
        """Einzelne Datei ohne Original archivieren (z. B. Seestar-Ausschuss). Liefert Archivpfad."""
        if self._inside(path):
            raise ArchiveError(tr('liegt bereits im Archiv'))
        st = os.stat(lp(path))
        f = FileEntry(path, st.st_size, st.st_mtime_ns, root, 0)
        dst = unique_path(self.target_for(f))
        self._move(path, dst)
        moved = []
        for c in companions:
            if not os.path.isfile(lp(c)) or self._inside(c):
                continue
            stem = os.path.splitext(os.path.basename(path))[0]
            cname = os.path.basename(c)
            suffix = cname[len(stem):] if cname.lower().startswith(stem.lower()) else "_" + cname
            cdst = unique_path(os.path.join(os.path.dirname(dst), os.path.splitext(os.path.basename(dst))[0] + suffix))
            try:
                self._move(c, cdst)
                moved.append([c, cdst])
            except (OSError, ArchiveError) as e:
                self.log("warn", tr('Begleitdatei nicht verschoben: {0} ({1})').format(c, e))
        self.journal.append({
            "v": 1, "op": "move", "id": uuid.uuid4().hex, "time": _now(), "src": path, "dst": dst,
            "keep": "", "size": st.st_size, "digest": "", "kind": kind, "reason": reason,
            "sidecars": moved, "session": session,
        })
        return dst

    def space_check(self, paths_sizes) -> tuple[int, int]:
        """(benötigt, frei) in Bytes für Dateien, die auf ein ANDERES Laufwerk kopiert werden müssen.

        Auf demselben Laufwerk wird nur umbenannt (kein Platzbedarf). frei = -1, wenn unbekannt.
        """
        probe = self.dir
        while probe and not os.path.isdir(lp(probe)):
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        need = 0
        for p, size in paths_sizes:
            if not same_device(p, probe):
                need += int(size)
        try:
            free = shutil.disk_usage(lp(probe)).free
        except OSError:
            free = -1
        return need, free

    # ------------------------------------------------------------------ Sitzungen (Rückgängig)
    @staticmethod
    def new_session() -> str:
        return _dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]

    def last_session(self) -> tuple[str, list[dict]]:
        """Jüngste Archivierungssitzung mit noch aktiven (nicht wiederhergestellten/gelöschten) Einträgen."""
        entries, _ = self.entries()
        sessions: dict[str, list[dict]] = {}
        for e in entries:
            sid = e.get("session") or ""
            if sid:
                sessions.setdefault(sid, []).append(e)
        if not sessions:
            return "", []
        # Journal ist append-only: die zuletzt geschriebene Sitzung ist die jüngste
        order = {id(e): i for i, e in enumerate(entries)}
        sid = max(sessions, key=lambda k: max(order[id(e)] for e in sessions[k]))
        return sid, sessions[sid]

    # Sitzungsstatus (2.2, C5): Start/Ende im Journal. Fehlt das Ende (Absturz, Stromausfall, Laufwerk
    # abgezogen), gilt die Sitzung als unvollständig und wird beim nächsten Start gemeldet.
    def begin_session(self, session: str, total: int, source: str = "") -> None:
        self.journal.append({"v": 1, "op": "session", "state": "start", "session": session, "total": int(total),
                             "source": source, "time": _now()})

    def end_session(self, session: str, moved: int, state: str = "done") -> None:
        self.journal.append({"v": 1, "op": "session", "state": state, "session": session, "moved": int(moved),
                             "time": _now()})

    def incomplete_sessions(self) -> list[dict]:
        """[{session, total, time, moved}] – gestartet, aber nie beendet."""
        open_s: dict[str, dict] = {}
        moved: dict[str, int] = {}
        for rec in self.journal.records():
            op, sid = rec.get("op"), str(rec.get("session") or "")
            if not sid:
                continue
            if op == "session":
                if rec.get("state") == "start":
                    open_s[sid] = {"session": sid, "total": rec.get("total", 0), "time": rec.get("time", "")}
                else:
                    open_s.pop(sid, None)
            elif op == "move":
                moved[sid] = moved.get(sid, 0) + 1
        out = []
        for sid, info in open_s.items():
            info["moved"] = moved.get(sid, 0)
            out.append(info)
        return out

    def undo_session(self, session: str, cancel=None) -> tuple[int, list[str]]:
        """Alle aktiven Einträge einer Sitzung wiederherstellen. (Anzahl, Fehlermeldungen)."""
        entries, _ = self.entries()
        n, errors = 0, []
        for e in entries:
            if e.get("session") != session:
                continue
            if cancel is not None and cancel.is_set():
                break
            try:
                self.restore(e)
                n += 1
            except (OSError, ArchiveError) as ex:
                errors.append(f"{e.get('dst')}: {ex}")
        return n, errors

    def keep_exists(self, rec: dict) -> bool:
        if rec.get("kind") == "seestar":
            return True  # Ausschuss-Einzelbild: kein Original nötig
        k = rec.get("keep")
        return bool(k) and os.path.isfile(lp(k))

    def purge(self, rec: dict, use_trash: bool = True) -> str:
        """Archivierte Datei endgültig entfernen (Papierkorb, falls verfügbar)."""
        dst = rec.get("dst", "")
        if not self._inside(dst):
            raise ArchiveError(tr('Journal-Eintrag zeigt außerhalb des Archivs – abgelehnt.'))
        paths = [dst]
        for pair in rec.get("sidecars", []) or []:
            try:
                if self._inside(pair[1]):
                    paths.append(pair[1])
            except (IndexError, TypeError):
                pass
        how = "Papierkorb" if (use_trash and HAVE_TRASH) else "gelöscht"
        for p in paths:
            if not os.path.lexists(lp(p)):
                continue
            if use_trash and HAVE_TRASH:
                try:
                    send2trash(p)
                    continue
                except Exception as e:  # noqa: BLE001 – z. B. Netzlaufwerk ohne Papierkorb
                    self.log("warn", tr('Papierkorb nicht möglich, lösche direkt: {0} ({1})').format(p, e))
                    how = "gelöscht"
            os.remove(lp(p))
        self.journal.append({"v": 1, "op": "delete", "id": rec["id"], "time": _now(), "how": how})
        self._cleanup_dirs(os.path.dirname(dst))
        return how

    def _cleanup_dirs(self, d: str) -> None:
        """Leere Unterordner im Archiv entfernen (nie den Archivordner selbst)."""
        while self._inside(d):
            try:
                os.rmdir(lp(d))
            except OSError:
                break
            d = os.path.dirname(d)
