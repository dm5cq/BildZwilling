# SPDX-License-Identifier: GPL-3.0-or-later
"""BildZwilling – Kommandozeilenmodus (für Server, NAS, Aufgabenplanung).

Beispiele:
  BildZwilling-cli scan D:\\Fotos P:\\Bilder --csv bericht.csv --html bericht.html
  BildZwilling-cli scan D:\\Fotos --similar 6 --html bericht.html
  BildZwilling-cli scan D:\\Fotos --archive D:\\Archiv --move --yes
  BildZwilling-cli archive D:\\Archiv --older-than 30
  BildZwilling-cli archive D:\\Archiv --undo-last --yes
  BildZwilling-cli --lang en scan D:\\Photos      (englische Ausgabe)

Rückgabewerte: 0 = keine Duplikate, 1 = Duplikate gefunden, 2 = Fehler, 3 = abgebrochen
Ähnliche Bilder werden nur berichtet, nie verschoben.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import threading

from . import APP_NAME, COPYRIGHT, LICENSE_SPDX, VERSION
from .core import htmlreport, report, tools
from .core.instance import InstanceLock
from .core.power import keep_awake
from .core.archive import ArchiveError, ArchiveManager
from .core.fsutil import human_size
from .core.hashcache import NullCache, open_cache
from .core.plan import plan_archive
from .core.rules import valid_rules
from .core.scanner import ScanCancelled, ScanOptions, Scanner, validate_options
from .core.settings import data_dir
from .i18n import _ as tr


def _print(*a):
    try:
        print(*a, flush=True)
    except UnicodeEncodeError:  # alte Windows-Konsole
        print(*(str(x).encode("ascii", "replace").decode() for x in a), flush=True)


def _rules(items):
    out = []
    for r in items or []:
        act, _, pat = r.partition(":")
        out.append({"action": act.strip().lower(), "pattern": pat.strip()})
    vr = valid_rules(out)
    if len(vr) != len(out):
        raise SystemExit("Ungültige --rule. Format: keep:MUSTER oder archive:MUSTER")
    return vr


def cmd_scan(a) -> int:
    opts = ScanOptions(
        roots=[os.path.abspath(r) for r in a.roots], archive_dir=os.path.abspath(a.archive) if a.archive else "",
        mode="pixels" if a.pixels else "bytes", images_only=not a.all_files, include_hidden=a.hidden,
        include_placeholders=a.online, min_size=int(a.min_kb * 1024), keep_rule=a.keep_rule,
        workers=max(1, min(16, a.workers)), include_videos=a.videos, similar=a.similar is not None,
        similar_threshold=a.similar if a.similar is not None else 6, folder_rules=_rules(a.rule),
        rotations=not a.no_rotations, use_ratings=not a.no_ratings, lrcat=a.lrcat or "",
    )
    problems = validate_options(opts)
    if problems:
        for p in problems:
            _print(tr('FEHLER:'), p)
        return 2
    if a.move and not (opts.archive_dir and a.yes):
        _print(tr('FEHLER: --move benötigt --archive ORDNER und --yes'))
        return 2
    cache = NullCache() if a.no_cache else open_cache(os.path.join(data_dir(), "hashcache.sqlite"))
    cancel = threading.Event()
    last = [""]

    def progress(phase, done, total):
        if not a.quiet and phase != last[0]:
            last[0] = phase
            _print(f"… {phase}")

    def log(level, msg):
        if level in ("warn", "error") and not a.quiet:
            _print(f"[{level.upper()}] {msg}")

    try:
        with keep_awake():
            res = Scanner(opts, cache, progress, log, cancel).run()
    except ScanCancelled:
        return 3
    except KeyboardInterrupt:
        cancel.set()
        return 3
    finally:
        cache.close()
    st = res.stats
    _print(tr('{0} Dateien · {1} identische Gruppen · {2} Duplikate · {3} freizugeben · {4} Gruppen ähnlicher Bilder').format(st['files'], st['groups'], st['duplicates'], human_size(st['savable']), st.get('similar_groups', 0)))
    if a.csv:
        report.export_groups_csv(res.groups, a.csv)
        _print(tr('CSV:'), a.csv)
    if a.html:
        htmlreport.export_html(res.groups, a.html, thumbs=not a.no_thumbs, workers=opts.workers)
        _print(tr('HTML:'), a.html)
    if a.move:
        am = ArchiveManager(opts.archive_dir, move_sidecars=not a.no_sidecars)
        plan = plan_archive([g for g in res.groups if g.kind != "similar"], keep_pairs=not a.no_pairs,
                            include_similar=False)
        need, free = am.space_check([(it.dup.path, it.dup.size) for it in plan if not it.skip])
        if free >= 0 and need > 0 and need * 1.05 > free:
            _print(tr("FEHLER: zu wenig Speicherplatz im Archiv (benötigt {0}, frei {1})").format(
                human_size(need), human_size(free)))
            return 2
        lock = InstanceLock(data_dir())
        if not lock.acquire():
            _print(tr("FEHLER: BildZwilling läuft bereits (Programm oder Kommandozeile). Verschieben abgebrochen."))
            return 2
        moved = skipped = failed = 0
        session = am.new_session()
        state = "error"
        try:
            with keep_awake():
                am.begin_session(session, sum(1 for it in plan if not it.skip), "cli")
                for it in plan:
                    if it.skip:
                        skipped += 1
                        _print(tr('übersprungen: {0} – {1}').format(it.dup.path, it.skip))
                        continue
                    try:
                        ok, why = am.archive(it.dup, it.keep, it.kind, companions=it.companions, session=session)
                    except (OSError, ArchiveError) as e:
                        failed += 1
                        _print(tr('FEHLER: {0} – {1}').format(it.dup.path, e))
                        continue
                    if ok:
                        moved += 1
                    else:
                        skipped += 1
                        _print(tr('nicht verschoben: {0} – {1}').format(it.dup.path, why))
                state = "done"
        except KeyboardInterrupt:
            state = "cancelled"
            raise
        finally:
            try:
                am.end_session(session, moved, state)
            except OSError:
                pass
            lock.release()
        _print(tr('Archiviert: {0} · übersprungen: {1} · Fehler: {2}').format(moved, skipped, failed))
        if failed:
            return 2
    return 1 if st["groups"] else 0


def cmd_archive(a) -> int:
    am = ArchiveManager(os.path.abspath(a.archive))
    for inc in am.incomplete_sessions():
        _print(tr("WARNUNG: Archivierung {0} ({1}) wurde nicht abgeschlossen – {2} von {3} Dateien verschoben. "
                  "Rückgängig mit --undo-last --yes.").format(inc["session"], inc["time"], inc["moved"], inc["total"]))
    if a.undo_last:
        sid, items = am.last_session()
        if not sid:
            _print(tr('Keine rückgängig zu machende Archivierung gefunden.'))
            return 0
        _print(tr('Letzte Archivierung {0}: {1} Dateien').format(sid, len(items)))
        if not a.yes:
            _print(tr('Zum Wiederherstellen zusätzlich --yes angeben.'))
            return 0
        lock = InstanceLock(data_dir())
        if not lock.acquire():
            _print(tr("FEHLER: BildZwilling läuft bereits (Programm oder Kommandozeile). Verschieben abgebrochen."))
            return 2
        try:
            n, errors = am.undo_session(sid)
            for inc in am.incomplete_sessions():
                if inc["session"] == sid:
                    am.end_session(sid, 0, "undone")
        finally:
            lock.release()
        for e in errors:
            _print(tr('FEHLER:'), e)
        _print(tr('{0} Dateien wiederhergestellt.').format(n))
        return 2 if errors else 0
    entries, bad = am.entries()
    now = _dt.datetime.now()
    due = []
    for e in entries:
        try:
            age = (now - _dt.datetime.fromisoformat(e.get("time", ""))).days
        except ValueError:
            age = 0
        if a.older_than is None or age >= a.older_than:
            due.append((age, e))
    for age, e in sorted(due, key=lambda x: -x[0]):
        ok = "✔" if am.keep_exists(e) else "✖ Original fehlt"
        _print(tr('{0:>4} Tage  {1:>9}  {2}  [{3}]').format(age, human_size(int(e.get('size', 0) or 0)), e['dst'], ok))
    total = sum(int(e.get("size", 0) or 0) for _, e in due)
    _print(f"{len(due)} von {len(entries)} Einträgen · {human_size(total)}"
           + (f" · {bad} defekte Journalzeilen" if bad else ""))
    if a.csv:
        report.export_archive_csv([e for _, e in due], a.csv)
        _print(tr('CSV:'), a.csv)
    return 0


def build_parser() -> argparse.ArgumentParser:
    from .legal import disclaimer_short

    p = argparse.ArgumentParser(prog="BildZwilling-cli", description=f"{APP_NAME} {VERSION} – {COPYRIGHT}",
                                epilog=tr("Sprache der Ausgabe: --lang de | --lang en (vor dem Befehl). "
                                          "Rückgabewerte: 0 keine Duplikate, 1 Duplikate gefunden, 2 Fehler, "
                                          "3 abgebrochen.") + "  " + disclaimer_short())
    p.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION} ({LICENSE_SPDX}) – {COPYRIGHT}")
    p.add_argument("--license", action="store_true", help=tr("Lizenz- und Haftungshinweis anzeigen"))
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="Ordner nach Duplikaten durchsuchen")
    s.add_argument("roots", nargs="+", help="Bildordner (der erste ist der Master)")
    s.add_argument("--archive", help="Archivordner")
    s.add_argument("--pixels", action="store_true", help="zusätzlich gleichen Bildinhalt erkennen")
    s.add_argument("--similar", type=int, metavar="ABSTAND", help="ähnliche Bilder (0–16, typ. 6) berichten")
    s.add_argument("--videos", action="store_true", help="Videos einbeziehen")
    s.add_argument("--all-files", action="store_true", help="alle Dateitypen vergleichen")
    s.add_argument("--hidden", action="store_true", help="versteckte Dateien einbeziehen")
    s.add_argument("--online", action="store_true", help="Nur-Online-Cloud-Dateien herunterladen und prüfen")
    s.add_argument("--min-kb", type=float, default=1, help="Mindestgröße in KB (Standard 1)")
    s.add_argument("--keep-rule", default="first_root", choices=["first_root", "oldest", "newest", "shortest_path"])
    s.add_argument("--rule", action="append", metavar="keep|archive:MUSTER", help="Ordnerregel (mehrfach)")
    s.add_argument("--csv", help="CSV-Bericht schreiben")
    s.add_argument("--html", help="HTML-Bericht mit Vorschaubildern schreiben")
    s.add_argument("--no-thumbs", action="store_true", help="HTML ohne Vorschaubilder")
    s.add_argument("--move", action="store_true", help="identische Duplikate ins Archiv verschieben")
    s.add_argument("--yes", action="store_true", help="Verschieben bestätigen (erforderlich mit --move)")
    s.add_argument("--no-pairs", action="store_true", help="RAW+JPEG-Paare nicht zusammenhalten")
    s.add_argument("--no-sidecars", action="store_true", help="XMP-Begleitdateien nicht mitverschieben")
    s.add_argument("--no-cache", action="store_true", help="Prüfsummen-Cache nicht verwenden")
    s.add_argument("--no-rotations", action="store_true", help="ähnliche Bilder nicht gedreht/gespiegelt suchen")
    s.add_argument("--no-ratings", action="store_true", help="Bewertungen (XMP/Lightroom) ignorieren")
    s.add_argument("--lrcat", help="Lightroom-Katalog (.lrcat) für Bewertungen")
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--exiftool", help="Pfad zu exiftool")
    s.add_argument("--ffmpeg", help="Pfad zu ffmpeg")
    s.add_argument("-q", "--quiet", action="store_true")
    s.set_defaults(func=cmd_scan)
    r = sub.add_parser("archive", help="Archivinhalt auflisten (Aufbewahrung)")
    r.add_argument("archive", help="Archivordner")
    r.add_argument("--older-than", type=int, metavar="TAGE", help="nur Einträge älter als TAGE")
    r.add_argument("--csv", help="Liste als CSV schreiben")
    r.add_argument("--undo-last", action="store_true", help="letzte Archivierung rückgängig machen")
    r.add_argument("--yes", action="store_true", help="Rückgängig bestätigen")
    r.set_defaults(func=cmd_archive)
    return p


def main(argv=None) -> int:
    from .core.settings import Settings
    from .i18n import set_language

    argv = list(sys.argv[1:] if argv is None else argv)
    lang = None
    if "--lang" in argv:
        i = argv.index("--lang")
        lang = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    try:
        set_language(lang or Settings()["language"])
    except Exception:  # noqa: BLE001
        set_language(lang or "de")
    parser = build_parser()
    a = parser.parse_args(argv)
    if getattr(a, "license", False):
        from .legal import disclaimer_full, license_notice

        _print(f"{APP_NAME} {VERSION} – {COPYRIGHT}\n\n{license_notice()}\n\n{disclaimer_full()}")
        return 0
    if not getattr(a, "cmd", None):
        parser.print_help()
        return 2
    tools.configure(exiftool=getattr(a, "exiftool", "") or "", ffmpeg=getattr(a, "ffmpeg", "") or "")
    try:
        return a.func(a)
    except KeyboardInterrupt:
        return 3
    except (OSError, ArchiveError) as e:
        _print(tr('FEHLER:'), e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
