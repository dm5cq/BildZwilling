# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests für Version 2.2: Lizenz/Haftung, Sicherheit (B1–B6) und Stabilität (C1–C7)."""

import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bildzwilling import COPYRIGHT, LICENSE_SPDX, VERSION, cli, legal  # noqa: E402
from bildzwilling.core import archive as arc  # noqa: E402
from bildzwilling.core import htmlreport, imaging, maintenance, tools  # noqa: E402
from bildzwilling.core.fsutil import IS_WINDOWS, lp  # noqa: E402
from bildzwilling.core.hashcache import HashCache, NullCache  # noqa: E402
from bildzwilling.core.instance import InstanceLock  # noqa: E402
from bildzwilling.core.logutil import anonymize_paths, redact  # noqa: E402
from bildzwilling.core.power import keep_awake  # noqa: E402
from bildzwilling.core.scanner import ScanOptions, Scanner  # noqa: E402
from bildzwilling.core.secret import TokenStore  # noqa: E402
from bildzwilling.core.settings import Settings  # noqa: E402
from test_v15 import photo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Legal(unittest.TestCase):
    def test_copyright_and_version(self):
        self.assertEqual(VERSION, "2.2")
        self.assertEqual(COPYRIGHT.count("Stefan J. Kaiser"), 1)      # Name genau einmal
        self.assertIn("Idee, Konzept & Prompt", COPYRIGHT)
        self.assertIn("GPL v3", COPYRIGHT)
        self.assertEqual(LICENSE_SPDX, "GPL-3.0-or-later")

    def test_license_files(self):
        lic = legal.read_text_file("LICENSE")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", lic)
        self.assertIn("Version 3, 29 June 2007", lic)
        self.assertIn("15. Disclaimer of Warranty", lic)
        self.assertIn("Pillow", legal.read_text_file("THIRD_PARTY_LICENSES.txt"))

    def test_every_source_has_spdx_header(self):
        missing = []
        for base, _d, files in os.walk(ROOT):
            if any(x in base for x in (".venv", "build", "dist", "__pycache__", "BildZwilling_Daten")):
                continue
            for f in files:
                if f.endswith(".py"):
                    with open(os.path.join(base, f), encoding="utf-8") as fh:
                        if "SPDX-License-Identifier: GPL-3.0-or-later" not in fh.read(400):
                            missing.append(f)
        self.assertEqual(missing, [])

    def test_disclaimer_texts(self):
        self.assertIn("eigene Verantwortung", legal.disclaimer_short())
        self.assertIn("Datensicherung", legal.disclaimer_full())
        self.assertIn("Version 3", legal.license_notice())
        self.assertIn("https://github.com/dm5cq/BildZwilling", legal.license_notice())   # GPL-Quellcode-Hinweis

    def test_cli_version_and_license(self):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
            cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("2.2", buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(["--license"]), 0)
        self.assertIn("GEWÄHRLEISTUNG", buf.getvalue())
        self.assertIn("github.com/dm5cq/BildZwilling", buf.getvalue())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main([]), 2)


class Security(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # B1
    def test_single_instance_lock(self):
        a, b = InstanceLock(self.tmp), InstanceLock(self.tmp)
        self.assertTrue(a.acquire())
        self.assertFalse(b.acquire())          # zweite Instanz wird erkannt
        a.release()
        self.assertTrue(b.acquire())           # nach dem Beenden wieder frei
        b.release()

    # B2
    def test_tools_not_from_path_on_windows(self):
        fake = os.path.join(self.tmp, "exiftool.exe")
        open(fake, "w").close()
        tools.configure(exiftool="", ffmpeg="")
        with mock.patch.object(tools, "IS_WINDOWS", True), mock.patch.object(tools.shutil, "which", return_value=fake), \
                mock.patch.object(tools, "_app_dir", return_value=os.path.join(self.tmp, "app")):
            self.assertIsNone(tools.find("exiftool"))
        tools.configure(exiftool=fake)
        with mock.patch.object(tools, "IS_WINDOWS", True), \
                mock.patch.object(tools, "_app_dir", return_value=os.path.join(self.tmp, "app")):
            self.assertEqual(tools.find("exiftool"), fake)   # ausdrücklich eingestellter Pfad gilt
        tools.configure(exiftool="")
        self.assertEqual(tools.sha256_file(fake), hashlib.sha256(b"").hexdigest())

    # B3
    def test_token_store_clear_all(self):
        p = os.path.join(self.tmp, "cloud_tokens.dat")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"pcloud_eu": "x", "pcloud_app_secret": "y"}, f)
        ts = TokenStore(p)
        self.assertEqual(ts.keys(), ["pcloud_app_secret", "pcloud_eu"])
        self.assertEqual(ts.clear_all(), 2)
        self.assertFalse(os.path.exists(p))
        self.assertEqual(ts.keys(), [])

    # B4
    def test_log_redaction(self):
        s = redact("angemeldet: stefan@example.org auth=ABCDEF123 Bearer abcdefghijkl12 password: geheim code=123456")
        for secret in ("stefan@example.org", "ABCDEF123", "abcdefghijkl12", "geheim", "123456"):
            self.assertNotIn(secret, s)
        self.assertIn("<E-Mail>", s)
        home = os.path.expanduser("~")
        self.assertNotIn(home, anonymize_paths(os.path.join(home, "Bilder", "a.jpg")))

    # B6
    def test_html_report_csp(self):
        root = os.path.join(self.tmp, "b")
        photo(os.path.join(root, "a.jpg"), 1)
        shutil.copy2(os.path.join(root, "a.jpg"), os.path.join(root, "b.jpg"))
        res = Scanner(ScanOptions([root], min_size=0), NullCache()).run()
        out = os.path.join(self.tmp, "r.html")
        htmlreport.export_html(res.groups, out, thumbs=True)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r"script-src 'sha256-([^']+)'", html)
        self.assertIsNotNone(m)
        assert m is not None
        self.assertIn("default-src 'none'", html)
        script = re.search(r"<script>(.*)</script>", html, re.S).group(1)  # type: ignore[union-attr]
        self.assertEqual(m.group(1), base64.b64encode(hashlib.sha256(script.encode()).digest()).decode())
        self.assertNotIn("http://", script + "".join(re.findall(r"src='([^']*)'", html)))


class Stability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "bilder")
        self.arch = os.path.join(self.tmp, "archiv")
        os.makedirs(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # C1
    def test_settings_backup_and_recovery(self):
        p = os.path.join(self.tmp, "settings.json")
        s = Settings(p)
        s["retention_days"] = 11
        s.save()
        s["retention_days"] = 22
        s.save()                                             # .bak enthält die vorige Fassung (11)
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"retention_days": 33, kaputt')         # Absturz mitten im Schreiben o. Ä.
        s2 = Settings(p)
        self.assertEqual(s2.recovered, "backup")
        self.assertEqual(s2["retention_days"], 11)
        self.assertTrue(os.path.exists(p + ".defekt"))
        os.remove(p + ".bak")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{{{")
        s3 = Settings(p)
        self.assertEqual(s3.recovered, "defaults")
        self.assertEqual(s3["retention_days"], 30)

    # C2
    def test_keep_awake_is_safe(self):
        with keep_awake():
            pass

    # C3
    def test_preview_size_limit(self):
        p = os.path.join(self.root, "gross.jpg")
        photo(p, 3)
        with mock.patch.object(imaging, "MAX_PREVIEW_PIXELS", 1000):
            with self.assertRaises(imaging.ImageLoadError) as cm:
                imaging.load_preview(p)
        self.assertIn("MP", str(cm.exception))
        im, _ = imaging.load_preview(p, 200)
        self.assertLessEqual(max(im.size), 200)

    # C4
    @unittest.skipUnless(IS_WINDOWS, "nur Windows")
    def test_long_paths_windows(self):
        deep = os.path.join(self.root, *(["sehr_langer_ordnername_" * 2] * 7))
        self.assertGreater(len(deep), 260)
        os.makedirs(lp(deep))
        a = os.path.join(deep, "a.jpg")
        photo(lp(a), 1)
        shutil.copy2(lp(a), lp(os.path.join(deep, "b.jpg")))
        res = Scanner(ScanOptions([self.root], min_size=0), NullCache()).run()
        self.assertEqual(len(res.groups), 1)
        am = arc.ArchiveManager(self.arch)
        g = res.groups[0]
        self.assertTrue(am.archive(g.to_archive[0], g.keepers[0], g.kind)[0])

    # C5
    def test_incomplete_session_detected(self):
        for i in range(3):
            photo(os.path.join(self.root, f"a{i}.jpg"), i)
            shutil.copy2(os.path.join(self.root, f"a{i}.jpg"), os.path.join(self.root, f"kopie{i}.jpg"))
        res = Scanner(ScanOptions([self.root], min_size=0, keep_rule="shortest_path"), NullCache()).run()
        am = arc.ArchiveManager(self.arch)
        ok_sid, crash_sid = "s-ok", "s-crash"
        am.begin_session(ok_sid, 1)
        g0 = res.groups[0]
        am.archive(g0.to_archive[0], g0.keepers[0], g0.kind, session=ok_sid)
        am.end_session(ok_sid, 1)
        am.begin_session(crash_sid, 2)                       # 2 geplant, nur 1 verschoben, kein Ende
        g1 = res.groups[1]
        am.archive(g1.to_archive[0], g1.keepers[0], g1.kind, session=crash_sid)
        inc = am.incomplete_sessions()
        self.assertEqual([(i["session"], i["moved"], i["total"]) for i in inc], [(crash_sid, 1, 2)])
        self.assertEqual(len(am.entries()[0]), 2)            # alte Journalleser ignorieren die neuen Zeilen
        n, errors = am.undo_session(crash_sid)
        am.end_session(crash_sid, 0, "undone")
        self.assertEqual((n, errors), (1, []))
        self.assertEqual(am.incomplete_sessions(), [])

    # C6
    def test_system_info_has_no_personal_data(self):
        from bildzwilling.core.sysinfo import system_info

        home = os.path.expanduser("~")
        info = system_info(os.path.join(home, "BildZwilling_Daten"), {"Pillow": True})
        self.assertIn("BildZwilling 2.2", info)
        self.assertNotIn(home, info)

    # C7
    def test_cache_prune(self):
        db = HashCache(os.path.join(self.tmp, "c.sqlite"))
        alive = os.path.join(self.root, "lebt.jpg")
        open(alive, "w").close()
        gone = os.path.join(self.root, "weg.jpg")
        offline = os.path.join(self.tmp, "nicht_verbunden", "x.jpg")   # Laufwerk/Cloud gerade nicht da
        for p in (alive, gone, offline):
            db.put(p, "b2", 1, 1, "d")
        db.commit()
        self.assertEqual(db.prune(), 1)
        self.assertEqual(db.get(alive, "b2", 1, 1), "d")
        self.assertIsNone(db.get(gone, "b2", 1, 1))
        self.assertEqual(db.get(offline, "b2", 1, 1), "d")
        db.close()

    def test_temp_cleanup(self):
        base = os.path.join(self.tmp, "temp")
        old, new, foreign = (os.path.join(base, n) for n in ("bz_cloud_alt", "bz_cloud_neu", "anderes_programm"))
        for d in (old, new, foreign):
            os.makedirs(d)
        t = time.time() - 3 * 86400
        os.utime(old, (t, t))
        os.utime(foreign, (t, t))
        self.assertEqual(maintenance.cleanup_temp(base=base), 1)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new) and os.path.exists(foreign))
        self.assertTrue(maintenance.prune_due(""))
        self.assertFalse(maintenance.prune_due(maintenance.today()))

    def test_cli_move_blocked_by_running_instance(self):
        photo(os.path.join(self.root, "a.jpg"), 1)
        shutil.copy2(os.path.join(self.root, "a.jpg"), os.path.join(self.root, "b.jpg"))
        lock = InstanceLock(self.tmp)
        self.assertTrue(lock.acquire())
        try:
            with mock.patch.object(cli, "data_dir", return_value=self.tmp), redirect_stdout(io.StringIO()):
                rc = cli.main(["scan", self.root, "--archive", self.arch, "--move", "--yes", "--min-kb", "0",
                               "--no-cache", "-q"])
            self.assertEqual(rc, 2)
            self.assertEqual(len(os.listdir(self.root)), 2)   # nichts verschoben
        finally:
            lock.release()
        with mock.patch.object(cli, "data_dir", return_value=self.tmp), redirect_stdout(io.StringIO()):
            rc = cli.main(["scan", self.root, "--archive", self.arch, "--move", "--yes", "--min-kb", "0",
                           "--no-cache", "-q"])
        self.assertEqual(rc, 1)
        self.assertEqual(len(os.listdir(self.root)), 1)
        self.assertEqual(arc.ArchiveManager(self.arch).incomplete_sessions(), [])


if __name__ == "__main__":
    unittest.main()
