# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests der Funktionen aus Version 2.0 (V14 Rückgängig, V15 Bewertungen, V16 gedrehte Kopien)."""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageOps  # noqa: E402

from bildzwilling import COPYRIGHT, cli  # noqa: E402
from bildzwilling.core import archive as arc  # noqa: E402
from bildzwilling.core import ratings  # noqa: E402
from bildzwilling.core.hashcache import NullCache  # noqa: E402
from bildzwilling.core.scanner import ScanOptions, Scanner  # noqa: E402
from test_v15 import photo  # noqa: E402


class V20Core(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "Fotos")
        self.arch = os.path.join(self.tmp, "Archiv")
        os.makedirs(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_copyright_name_once(self):
        self.assertEqual(COPYRIGHT.count("Stefan J. Kaiser"), 1)
        self.assertIn("Idee, Konzept & Prompt", COPYRIGHT)

    # ------------------------------------------------------------- V14
    def test_undo_last_session(self):
        for i in range(3):
            photo(os.path.join(self.root, f"a{i}.jpg"), i)
            shutil.copy2(os.path.join(self.root, f"a{i}.jpg"), os.path.join(self.root, f"kopie{i}.jpg"))
        o = ScanOptions([self.root], min_size=0, keep_rule="shortest_path")
        res = Scanner(o, NullCache()).run()
        am = arc.ArchiveManager(self.arch)
        s1, s2 = "s1-alt", "s2-neu"
        for n, g in enumerate(res.groups):
            for d in g.to_archive:
                self.assertTrue(am.archive(d, g.keepers[0], g.kind, session=s1 if n == 0 else s2)[0])
        sid, items = am.last_session()
        self.assertEqual((sid, len(items)), (s2, 2))
        n, err = am.undo_session(sid)
        self.assertEqual((n, err), (2, []))
        self.assertEqual(am.last_session()[0], s1)
        self.assertEqual(len(os.listdir(self.root)), 5)
        self.assertEqual(cli.main(["archive", self.arch, "--undo-last", "--yes"]), 0)
        self.assertEqual(len(os.listdir(self.root)), 6)
        self.assertEqual(am.last_session(), ("", []))

    def test_space_check(self):
        p = os.path.join(self.root, "a.jpg")
        photo(p, 1)
        am = arc.ArchiveManager(os.path.join(self.arch, "neu", "unter"))   # existiert noch nicht
        need, free = am.space_check([(p, 10 ** 15)])
        self.assertEqual(need, 0)                       # gleiches Laufwerk -> nur Umbenennen
        self.assertGreater(free, 0)
        with mock.patch.object(arc, "same_device", return_value=False):
            need, free = am.space_check([(p, 10 ** 15)])
        self.assertEqual(need, 10 ** 15)
        self.assertLess(free, need)

    # ------------------------------------------------------------- V15
    def test_xmp_ratings_keep_preference(self):
        a = os.path.join(self.root, "a", "IMG_1.jpg")
        b = os.path.join(self.root, "b", "IMG_1.jpg")
        c = os.path.join(self.root, "c", "IMG_1.jpg")
        photo(a, 1)
        for p in (b, c):
            os.makedirs(os.path.dirname(p))
            shutil.copy2(a, p)
        with open(os.path.join(self.root, "b", "IMG_1.xmp"), "w") as f:
            f.write('<x:xmpmeta><rdf:Description xmp:Rating="4" xmp:Label="Red"/></x:xmpmeta>')
        with open(os.path.join(self.root, "a", "IMG_1.jpg.xmp"), "w") as f:
            f.write('<x:xmpmeta><rdf:Description><xmp:Rating>-1</xmp:Rating></rdf:Description></x:xmpmeta>')
        r = ratings.read_xmp(b)
        self.assertEqual((r.stars, r.label, r.text()), (4, "Red", "★★★★ Red"))
        self.assertTrue(ratings.read_xmp(a).rejected)
        g = Scanner(ScanOptions([self.root], min_size=0, keep_rule="oldest"), NullCache()).run().groups[0]
        self.assertEqual(g.files[0].path, b)            # 4 Sterne -> Original
        self.assertEqual(g.files[-1].path, a)           # abgelehnt -> zuletzt
        g = Scanner(ScanOptions([self.root], min_size=0, use_ratings=False), NullCache()).run().groups[0]
        self.assertIsNone(g.files[0].rating)

    def test_embedded_xmp(self):
        p = os.path.join(self.root, "e.jpg")
        xmp = (b'<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
               b'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="5"/></rdf:RDF></x:xmpmeta>')
        Image.new("RGB", (20, 20)).save(p, xmp=xmp)
        self.assertEqual(ratings.read_xmp(p).stars, 5)

    def test_lightroom_catalog(self):
        cat = os.path.join(self.tmp, "Katalog.lrcat")
        con = sqlite3.connect(cat)
        con.executescript("""
            CREATE TABLE AgLibraryRootFolder (id_local INTEGER, absolutePath TEXT);
            CREATE TABLE AgLibraryFolder (id_local INTEGER, pathFromRoot TEXT, rootFolder INTEGER);
            CREATE TABLE AgLibraryFile (id_local INTEGER, baseName TEXT, extension TEXT, folder INTEGER);
            CREATE TABLE Adobe_images (id_local INTEGER, rootFile INTEGER, rating REAL, colorLabels TEXT, pick REAL);
        """)
        root = self.root.replace("\\", "/") + "/"
        con.execute("INSERT INTO AgLibraryRootFolder VALUES (1, ?)", (root,))
        con.execute("INSERT INTO AgLibraryFolder VALUES (2, 'Urlaub/', 1)")
        con.execute("INSERT INTO AgLibraryFile VALUES (3, 'DSC_1', 'NEF', 2)")
        con.execute("INSERT INTO Adobe_images VALUES (4, 3, 3, 'Grün', 1)")
        con.commit()
        con.close()
        lr = ratings.open_catalog(cat)
        r = lr.get(os.path.join(self.root, "Urlaub", "DSC_1.NEF"))
        self.assertEqual((r.stars, r.label, r.pick), (3, "Grün", 1))
        self.assertIsNone(ratings.open_catalog(os.path.join(self.tmp, "fehlt.lrcat")))

    # ------------------------------------------------------------- V16
    def test_rotated_and_mirrored(self):
        im = photo(os.path.join(self.root, "orig.jpg"), 11, (1600, 1000))
        im.transpose(Image.Transpose.ROTATE_90).save(os.path.join(self.root, "gedreht.jpg"), quality=85)
        ImageOps.mirror(im).resize((800, 500)).save(os.path.join(self.root, "gespiegelt.jpg"), quality=85)
        photo(os.path.join(self.root, "anders.jpg"), 12, (1600, 1000))
        o = ScanOptions([self.root], min_size=0, similar=True, similar_threshold=6)
        sim = [g for g in Scanner(o, NullCache()).run().groups if g.kind == "similar"]
        self.assertEqual(len(sim), 1)
        self.assertEqual({os.path.basename(f.path) for f in sim[0].files}, {"orig.jpg", "gedreht.jpg", "gespiegelt.jpg"})
        self.assertTrue(sim[0].transformed)
        o.rotations = False
        sim = [g for g in Scanner(o, NullCache()).run().groups if g.kind == "similar"]
        self.assertEqual(sim, [])


def star_field(rng, n_stars=80, sigma=(1.3, 1.3), bg=1000.0, noise=15.0, h=200, w=320, dim=1.0):
    import numpy as np
    img = rng.normal(bg, noise, (h, w))
    yy, xx = np.mgrid[0:h, 0:w]
    pos = np.random.default_rng(42).uniform([12, 12], [h - 12, w - 12], (n_stars, 2))  # gleiche Sterne
    amps = np.random.default_rng(43).uniform(800, 8000, n_stars) * dim
    for (y, x), a in zip(pos, amps):
        img += a * np.exp(-(((xx - x) / sigma[0]) ** 2 + ((yy - y) / sigma[1]) ** 2) / 2)
    return np.clip(img, 0, 65535).astype("uint16")


class SeestarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_assistant(self):
        import numpy as np
        from bildzwilling.core import seestar
        from test_v15 import write_fits
        rng = np.random.default_rng(1)
        obj = os.path.join(self.tmp, "MyWorks", "M 42")
        sub = os.path.join(self.tmp, "MyWorks", "M 42_sub")
        os.makedirs(obj)
        os.makedirs(sub)
        kinds = ["ok"] * 8 + ["wolken", "nachfuehrung", "unscharf"]
        for i, k in enumerate(kinds):
            t = f"20261117-22{i:02d}00"
            if k == "wolken":
                d = star_field(rng, bg=1900, dim=0.12)
            elif k == "nachfuehrung":
                d = star_field(rng, sigma=(4.0, 1.2))
            elif k == "unscharf":
                d = star_field(rng, sigma=(3.2, 3.2))
            else:
                d = star_field(rng)
            p = os.path.join(sub, f"Light_M 42_10.0s_IRCUT_{t}.fit")
            write_fits(p, d, {"BAYERPAT": "GRBG", "INSTRUME": "Seestar S50", "EXPTIME": 10.0})
            Image.new("RGB", (8, 8)).save(p[:-4] + ".jpg")
            Image.new("RGB", (4, 4)).save(p[:-4] + "_thn.jpg")
        # anderer Abend (andere Sitzung) ohne Stack
        write_fits(os.path.join(sub, "Light_M 42_10.0s_IRCUT_20261120-210000.fit"), star_field(rng),
                   {"BAYERPAT": "GRBG"})
        st = np.stack([star_field(rng)] * 3)
        write_fits(os.path.join(obj, "Stacked_11_M 42_10.0s_IRCUT_20261117-221100.fit"), st, {"STACKCNT": 11})
        stacks, orphans, frames = seestar.run(os.path.join(self.tmp, "MyWorks"))
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0].count, 11)
        self.assertEqual(len(stacks[0].subs), 11)
        self.assertEqual(len(orphans), 1)
        verdict = {os.path.splitext(f.path)[0][-6:]: (f.verdict, f.reasons, f.metrics) for f in stacks[0].subs}
        bad = {k: v for k, v in verdict.items() if v[0] == "reject"}
        self.assertEqual(sorted(bad), ["220800", "220900", "221000"], verdict)
        self.assertIn("Wolken", " ".join(bad["220800"][1]))
        self.assertIn("Nachführ", " ".join(bad["220900"][1]))
        self.assertIn("unscharf", " ".join(bad["221000"][1]))
        self.assertEqual(len(stacks[0].subs[0].companions), 2)
        # Windows/macOS: Dateisystem unterscheidet nicht nach Groß/Klein -> trotzdem jede Datei nur einmal
        real_isfile = os.path.isfile
        with mock.patch("os.path.isfile", lambda q: real_isfile(q) or real_isfile(q.replace(".JPG", ".jpg"))):
            fr = seestar.read_frame(stacks[0].subs[0].path)
        self.assertEqual(sorted(os.path.basename(c)[-8:] for c in fr.companions), ["0000.jpg", "_thn.jpg"])
        # Ausschuss archivieren (mit JPG/_thn.jpg) und rückgängig machen
        am = arc.ArchiveManager(os.path.join(self.tmp, "Archiv"))
        sid = am.new_session()
        for f in stacks[0].subs:
            if f.verdict == "reject":
                am.archive_file(f.path, os.path.join(self.tmp, "MyWorks"), "seestar", "; ".join(f.reasons),
                                f.companions, sid)
        self.assertEqual(len(os.listdir(sub)), 8 * 3 + 1)
        entries, _ = am.entries()
        self.assertTrue(all(am.keep_exists(e) for e in entries))
        self.assertEqual(am.undo_session(sid)[0], 3)
        self.assertEqual(len(os.listdir(sub)), 11 * 3 + 1)


if __name__ == "__main__":
    unittest.main()
