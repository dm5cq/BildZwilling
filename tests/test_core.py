# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests der Kern-Engine (ohne Oberfläche).  Aufruf:  python -m unittest discover -s tests"""

import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, PngImagePlugin  # noqa: E402

from bildzwilling.core import archive as arc  # noqa: E402
from bildzwilling.core import exifinfo, imaging, report  # noqa: E402
from bildzwilling.core.hashcache import open_cache  # noqa: E402
from bildzwilling.core.scanner import ScanCancelled, ScanOptions, Scanner, validate_options  # noqa: E402


def make_img(path, color, size=(320, 240), fmt=None, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.new("RGB", size, color)
    for x in range(0, size[0], 7):
        im.putpixel((x, x % size[1]), (x % 255, 10, 200))
    im.save(path, fmt, **kw)


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "Bilder")
        self.root2 = os.path.join(self.tmp, "Cloud")
        self.arch = os.path.join(self.tmp, "Archiv")
        make_img(os.path.join(self.root, "2024", "IMG_0001.jpg"), (200, 30, 30), quality=90)
        shutil.copy2(os.path.join(self.root, "2024", "IMG_0001.jpg"),
                     os.path.join(self.root, "Kopie von Urlaub.jpg"))          # anderer Name
        os.makedirs(self.root2)
        shutil.copy2(os.path.join(self.root, "2024", "IMG_0001.jpg"),
                     os.path.join(self.root2, "foto.JPG"))                     # anderer Ordner
        with open(os.path.join(self.root2, "foto.JPG.xmp"), "w") as f:         # Begleitdatei
            f.write("<x/>")
        make_img(os.path.join(self.root, "anders.jpg"), (10, 200, 30), quality=90)
        # gleiche Pixel, andere Metadaten (bytes verschieden)
        m1, m2 = PngImagePlugin.PngInfo(), PngImagePlugin.PngInfo()
        m1.add_text("Comment", "eins")
        m2.add_text("Comment", "zwei – andere Metadaten")
        make_img(os.path.join(self.root, "p1.png"), (1, 2, 3), pnginfo=m1)
        make_img(os.path.join(self.root, "sub", "p2.png"), (1, 2, 3), pnginfo=m2)
        self.cache = open_cache(os.path.join(self.tmp, "cache", "c.sqlite"))

    def tearDown(self):
        self.cache.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def scan(self, mode="bytes", **kw):
        o = ScanOptions(roots=[self.root, self.root2], archive_dir=self.arch, mode=mode, min_size=1, **kw)
        return Scanner(o, self.cache).run()

    def test_bytes_mode(self):
        r = self.scan()
        self.assertEqual(len(r.groups), 1)
        g = r.groups[0]
        self.assertEqual(g.kind, "bytes")
        self.assertEqual(len(g.files), 3)
        self.assertEqual(len(g.keepers), 1)
        # Regel first_root: Original stammt aus dem ersten Quellordner
        self.assertTrue(g.keepers[0].path.startswith(self.root))

    def test_pixel_mode(self):
        r = self.scan("pixels")
        kinds = sorted(g.kind for g in r.groups)
        self.assertEqual(kinds, ["bytes", "pixels"])
        pg = [g for g in r.groups if g.kind == "pixels"][0]
        self.assertEqual({os.path.basename(f.path) for f in pg.files}, {"p1.png", "p2.png"})

    def test_cache_reused(self):
        self.scan()
        with mock.patch("bildzwilling.core.scanner.hash_file", side_effect=AssertionError("kein Cache")):
            r = self.scan()
        self.assertEqual(len(r.groups), 1)

    def test_archive_restore_purge(self):
        r = self.scan()
        g = r.groups[0]
        keep = g.keepers[0]
        am = arc.ArchiveManager(self.arch)
        for d in g.to_archive:
            ok, why = am.archive(d, keep, g.kind)
            self.assertTrue(ok, why)
            self.assertFalse(os.path.exists(d.path))
        self.assertTrue(os.path.exists(keep.path))
        entries, bad = am.entries()
        self.assertEqual((len(entries), bad), (2, 0))
        # Begleitdatei ist mitgewandert
        sc = [e for e in entries if e["sidecars"]]
        self.assertEqual(len(sc), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root2, "foto.JPG.xmp")))
        # Archiv wird bei erneuter Suche nicht gefunden (liegt außerhalb), Rest keine Duplikate
        self.assertEqual(len(self.scan().groups), 0)
        # Wiederherstellen
        target = am.restore(sc[0])
        self.assertTrue(os.path.exists(target))
        self.assertTrue(os.path.exists(os.path.join(self.root2, "foto.JPG.xmp")))
        # Endgültig löschen
        entries, _ = am.entries()
        self.assertEqual(len(entries), 1)
        am.purge(entries[0], use_trash=False)
        self.assertFalse(os.path.exists(entries[0]["dst"]))
        self.assertEqual(am.entries()[0], [])

    def test_cross_device_copy_verify(self):
        r = self.scan()
        g = r.groups[0]
        am = arc.ArchiveManager(self.arch)
        with mock.patch.object(arc, "same_device", return_value=False):
            ok, why = am.archive(g.to_archive[0], g.keepers[0], g.kind)
        self.assertTrue(ok, why)
        self.assertFalse(any(n.endswith(".bz_part") for _, _, fs in os.walk(self.arch) for n in fs))

    def test_changed_file_is_skipped(self):
        r = self.scan()
        g = r.groups[0]
        dup = g.to_archive[0]
        with open(dup.path, "ab") as f:
            f.write(b"x")
        ok, why = arc.ArchiveManager(self.arch).archive(dup, g.keepers[0], g.kind)
        self.assertFalse(ok)
        self.assertIn("verändert", why)
        self.assertTrue(os.path.exists(dup.path))

    def test_journal_outside_archive_rejected(self):
        am = arc.ArchiveManager(self.arch)
        victim = os.path.join(self.root, "anders.jpg")
        with self.assertRaises(arc.ArchiveError):
            am.purge({"id": "x", "dst": victim, "src": victim})
        with self.assertRaises(arc.ArchiveError):
            am.purge({"id": "y", "dst": os.path.join(self.arch, "..", "Bilder", "anders.jpg")})
        self.assertTrue(os.path.exists(victim))

    def test_corrupt_journal_line(self):
        os.makedirs(self.arch)
        with open(os.path.join(self.arch, arc.JOURNAL_NAME), "w") as f:
            f.write("{kaputt\n")
        entries, bad = arc.ArchiveManager(self.arch).entries()
        self.assertEqual((entries, bad), ([], 1))

    def test_archive_inside_root_is_excluded(self):
        inner = os.path.join(self.root, "_Archiv")
        r = self.scan()
        am = arc.ArchiveManager(inner)
        g = r.groups[0]
        for d in g.to_archive:
            am.archive(d, g.keepers[0], g.kind)
        o = ScanOptions(roots=[self.root, self.root2], archive_dir=inner, min_size=1)
        self.assertEqual(Scanner(o, self.cache).run().groups, [])

    def test_validate(self):
        self.assertTrue(validate_options(ScanOptions(roots=[])))
        self.assertTrue(validate_options(ScanOptions(roots=[self.root], archive_dir=self.tmp)))
        self.assertFalse(validate_options(ScanOptions(roots=[self.root], archive_dir=self.arch)))

    def test_cancel(self):
        ev = threading.Event()
        ev.set()
        o = ScanOptions(roots=[self.root], min_size=1)
        with self.assertRaises(ScanCancelled):
            Scanner(o, self.cache, cancel=ev).run()

    def test_preview_exif_csv(self):
        im, info = imaging.load_preview(os.path.join(self.root, "anders.jpg"), 100)
        self.assertLessEqual(max(im.size), 100)
        rows = exifinfo.read_exif(os.path.join(self.root, "anders.jpg"))
        self.assertTrue(any(k.startswith("Datei") for k, _ in rows))
        r = self.scan()
        out = os.path.join(self.tmp, "b.csv")
        self.assertEqual(report.export_groups_csv(r.groups, out), 3)

    def test_preview_16bit(self):
        p = os.path.join(self.tmp, "g16.png")
        Image.new("I;16", (64, 48), 30000).save(p)
        im, _ = imaging.load_preview(p, 50)
        self.assertEqual(im.mode, "RGB")

    def test_raw_embedded_jpeg_fallback(self):
        jp = os.path.join(self.tmp, "v.jpg")
        Image.new("RGB", (400, 300), (9, 99, 199)).save(jp)
        raw = os.path.join(self.tmp, "neu.cr3")
        with open(raw, "wb") as f, open(jp, "rb") as j:
            f.write(b"\x00\x00\x00\x18ftypcrx " + os.urandom(5000) + j.read() + os.urandom(3000))
        im, info = imaging.load_preview(raw, 1000)
        self.assertEqual(im.size, (400, 300))

    def test_restore_never_overwrites(self):
        r = self.scan()
        g = r.groups[0]
        am = arc.ArchiveManager(self.arch)
        d = g.to_archive[0]
        am.archive(d, g.keepers[0], g.kind)
        with open(d.path, "wb") as f:      # neuer Inhalt am alten Ort
            f.write(b"neu")
        rec = am.entries()[0][0]
        target = am.restore(rec)
        self.assertNotEqual(target, d.path)
        with open(d.path, "rb") as f:
            self.assertEqual(f.read(), b"neu")
        with self.assertRaisesRegex(arc.ArchiveError, "Originalpfad"):
            am.restore({"id": "z", "dst": rec["dst"], "src": os.path.join(self.arch, "x.jpg")})

    def test_symlink_loop(self):
        if os.name == "nt":
            self.skipTest("Symlinks unter Windows nur mit Rechten")
        os.symlink(self.root, os.path.join(self.root, "schleife"))
        self.assertEqual(len(self.scan().groups), 1)


if __name__ == "__main__":
    unittest.main()
