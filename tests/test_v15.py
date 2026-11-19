# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests der Funktionen aus Version 1.5."""

import os
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

from bildzwilling import cli  # noqa: E402
from bildzwilling.core import archive as arc  # noqa: E402
from bildzwilling.core import exifinfo, fits, htmlreport, imaging, rules, tools  # noqa: E402
from bildzwilling.core.hashcache import NullCache  # noqa: E402
from bildzwilling.core.plan import plan_archive  # noqa: E402
from bildzwilling.core.scanner import DuplicateGroup, FileEntry, ScanOptions, Scanner, apply_keep_rule  # noqa: E402


def photo(path, seed, size=(640, 480)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (12, 16, 3), dtype=np.uint8)
    im = Image.fromarray(base).resize(size, Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(2))
    im.save(path, quality=92)
    return im


def write_fits(path, data, header=None):
    """Minimaler FITS-Schreiber (16 Bit, BZERO 32768) für Tests."""
    cards = ["SIMPLE  =                    T", "BITPIX  =                   16",
             f"NAXIS   = {data.ndim:>20}"]
    for i, n in enumerate(reversed(data.shape), 1):
        cards.append(f"NAXIS{i}  = {n:>20}")
    cards += ["BZERO   =                32768", "BSCALE  =                    1"]
    for k, v in (header or {}).items():
        cards.append(f"{k:<8}= '{v}'" if isinstance(v, str) else f"{k:<8}= {v:>20}")
    cards.append("END")
    hdr = "".join(c.ljust(80) for c in cards).encode("ascii")
    hdr += b" " * (-len(hdr) % 2880)
    raw = (data.astype(np.int32) - 32768).astype(">i2").tobytes()
    raw += b"\0" * (-len(raw) % 2880)
    with open(path, "wb") as f:
        f.write(hdr + raw)


def fe(path, root, ri=0, action="archive"):
    st = os.stat(path)
    f = FileEntry(path, st.st_size, st.st_mtime_ns, root, ri)
    f.action = action
    return f


class V15Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "Fotos")
        self.arch = os.path.join(self.tmp, "Archiv")
        os.makedirs(self.root)

    def tearDown(self):
        tools.configure(exiftool="", ffmpeg="", use_exiftool=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------- V5 Ordnerregeln
    def test_folder_rules(self):
        r = [{"pattern": "WhatsApp", "action": "archive"}, {"pattern": "Fotos/Best", "action": "keep"}]
        self.assertEqual(rules.decide("C:\\x\\WhatsApp Images\\a.jpg", r), "archive")
        self.assertEqual(rules.decide("/home/u/Fotos/Best/a.jpg", r), "keep")
        self.assertIsNone(rules.decide("/home/u/Fotos/a.jpg", r))
        a = os.path.join(self.root, "WhatsApp", "a.jpg")
        b = os.path.join(self.root, "Best", "b.jpg")
        c = os.path.join(self.root, "c.jpg")
        for p in (a, b, c):
            photo(p, 1)
        g = DuplicateGroup(1, "bytes", [fe(a, self.root), fe(c, self.root), fe(b, self.root)])
        apply_keep_rule(g, "oldest", [{"pattern": "WhatsApp", "action": "archive"},
                                      {"pattern": os.path.join(self.root, "Best"), "action": "keep"}])
        self.assertEqual(g.files[0].path, b)
        acts = {os.path.basename(f.path): f.action for f in g.files}
        self.assertEqual(acts, {"b.jpg": "keep", "c.jpg": "archive", "a.jpg": "archive"})
        # alles in Archiv-Ordnern -> trotzdem eine Datei behalten
        g2 = DuplicateGroup(2, "bytes", [fe(a, self.root), fe(a, self.root)])
        apply_keep_rule(g2, "oldest", [{"pattern": "WhatsApp", "action": "archive"}])
        self.assertEqual(len(g2.keepers), 1)

    # ------------------------------------------------------------- V1 ähnliche Bilder
    def test_similar(self):
        im = photo(os.path.join(self.root, "orig.jpg"), 7, (1600, 1200))
        im.resize((800, 600)).save(os.path.join(self.root, "klein.jpg"), quality=70)    # WhatsApp-artig
        os.makedirs(os.path.join(self.root, "sub"))
        im.save(os.path.join(self.root, "sub", "q50.jpg"), quality=50)
        shutil.copy2(os.path.join(self.root, "orig.jpg"), os.path.join(self.root, "kopie.jpg"))  # identisch
        photo(os.path.join(self.root, "anders.jpg"), 99, (1600, 1200))
        Image.new("RGB", (1600, 1200), (0, 0, 0)).save(os.path.join(self.root, "schwarz1.jpg"))
        Image.new("RGB", (1600, 1200), (2, 2, 2)).save(os.path.join(self.root, "schwarz2.jpg"))
        o = ScanOptions([self.root], min_size=0, similar=True, similar_threshold=8)
        res = Scanner(o, NullCache()).run()
        exact = [g for g in res.groups if g.kind == "bytes"]
        sim = [g for g in res.groups if g.kind == "similar"]
        self.assertEqual(len(exact), 1)
        self.assertEqual(len(sim), 1, [[os.path.basename(f.path) for f in g.files] for g in sim])
        names = [os.path.basename(f.path) for f in sim[0].files]
        self.assertEqual(len(names), 3)                      # Original-Vertreter, klein, q50
        self.assertIn("klein.jpg", names)
        self.assertNotIn("anders.jpg", names)
        self.assertEqual(sim[0].files[0].dims, (1600, 1200))  # beste Qualität zuerst
        self.assertTrue(all(f.action == "keep" for f in sim[0].files))  # nie automatisch archivieren
        self.assertEqual(res.stats["similar_groups"], 1)

    # ------------------------------------------------------------- V2 RAW+JPEG-Paare
    def _pair_setup(self):
        a = os.path.join(self.root, "A")
        b = os.path.join(self.root, "B")
        os.makedirs(a)
        os.makedirs(b)
        for d in (a, b):
            with open(os.path.join(d, "IMG_1.CR3"), "wb") as f:
                f.write(b"RAWDATA" * 500)
        return a, b

    def test_pairs(self):
        a, b = self._pair_setup()
        with open(os.path.join(a, "IMG_1.JPG"), "wb") as f:
            f.write(b"JPEG-A" * 300)
        # c) Original (B) hat kein JPEG -> Duplikat in A (mit Partner) wird übersprungen
        g = DuplicateGroup(1, "bytes", [fe(os.path.join(b, "IMG_1.CR3"), self.root, action="keep"),
                                        fe(os.path.join(a, "IMG_1.CR3"), self.root)])
        it = plan_archive([g])[0]
        self.assertIn("Paar", it.skip)
        self.assertFalse(plan_archive([g], keep_pairs=False)[0].skip)
        # b) Original hat ebenfalls JPEG -> Partner wandert mit
        with open(os.path.join(b, "IMG_1.JPG"), "wb") as f:
            f.write(b"JPEG-B" * 300)
        it = plan_archive([g])[0]
        self.assertEqual(it.skip, "")
        self.assertEqual([os.path.basename(c) for c in it.companions], ["IMG_1.JPG"])
        with open(os.path.join(a, "IMG_1.xmp"), "w") as f:
            f.write("<x/>")
        for x in g.files:
            x.digest = "d"
        am = arc.ArchiveManager(self.arch)
        ok, why = am.archive(it.dup, it.keep, it.kind, companions=it.companions)
        self.assertTrue(ok, why)
        self.assertEqual(os.listdir(a), [])                  # ganzes Paar + XMP im Archiv
        rec = am.entries()[0][0]
        self.assertEqual(len(rec["sidecars"]), 2)
        am.restore(rec)
        self.assertEqual(sorted(os.listdir(a)), ["IMG_1.CR3", "IMG_1.JPG", "IMG_1.xmp"])
        # a) Partner ist selbst Duplikat -> beide normal
        with open(os.path.join(a, "IMG_1.JPG"), "wb") as f:
            f.write(b"JPEG-B" * 300)
        g2 = DuplicateGroup(2, "bytes", [fe(os.path.join(b, "IMG_1.JPG"), self.root, action="keep"),
                                         fe(os.path.join(a, "IMG_1.JPG"), self.root)])
        items = plan_archive([g, g2])
        self.assertTrue(all(i.skip == "" and not i.companions for i in items))

    def test_similar_archive_verify(self):
        p1, p2 = os.path.join(self.root, "a.jpg"), os.path.join(self.root, "b.jpg")
        photo(p1, 1)
        photo(p2, 2)
        am = arc.ArchiveManager(self.arch)
        ok, _ = am.archive(fe(p2, self.root), fe(p1, self.root), "bytes")
        self.assertFalse(ok)                                 # nicht identisch -> abgelehnt
        ok, why = am.archive(fe(p2, self.root), fe(p1, self.root), "similar")
        self.assertTrue(ok, why)

    # ------------------------------------------------------------- Seestar / FITS
    def test_fits_seestar(self):
        rng = np.random.default_rng(3)
        sub = (rng.random((108, 192)) * 3000 + 1000).astype(np.uint16)
        sub[50:60, 90:100] = 60000  # „Stern“
        p1 = os.path.join(self.root, "Light_M42_10.0s_IRCUT_20261117-220000.fit")
        p2 = os.path.join(self.root, "kopie", "anders_benannt.fit")
        os.makedirs(os.path.dirname(p2))
        write_fits(p1, sub, {"BAYERPAT": "GRBG", "INSTRUME": "Seestar S50", "EXPTIME": 10.0, "OBJECT": "M 42"})
        write_fits(p2, sub, {"BAYERPAT": "GRBG", "INSTRUME": "Seestar S50", "EXPTIME": 10.0, "OBJECT": "M42 neu"})
        self.assertEqual(imaging.image_size(p1), (192, 108))
        im, info = imaging.load_preview(p1, 1000)
        self.assertEqual((im.size, im.mode), ((96, 54), "RGB"))
        self.assertIn("Bayer GRBG", info)
        rows = dict(exifinfo.read_exif(p1))
        self.assertEqual(rows["FITS INSTRUME"], "Seestar S50")
        self.assertEqual(rows["FITS OBJECT"], "M 42")
        self.assertEqual(fits.pixel_digest(p1), fits.pixel_digest(p2))   # Header egal
        stacked = os.path.join(self.root, "Stacked_30_M 42_10.0s_IRCUT.fit")
        write_fits(stacked, np.stack([sub, sub // 2, sub // 3]), {"BAYERPAT": "GRBG", "STACKCNT": 30})
        im, info = imaging.load_preview(stacked, 1000)
        self.assertEqual(im.size, (192, 108))
        self.assertIn("gestackt", info)
        o = ScanOptions([self.root], min_size=0, mode="pixels")
        res = Scanner(o, NullCache()).run()
        kinds = [(g.kind, len(g.files)) for g in res.groups]
        self.assertEqual(kinds, [("pixels", 2)])
        # FIT + JPG (Seestar) = Paar
        from bildzwilling.core.plan import PairFinder
        Image.new("RGB", (10, 10)).save(p1[:-4] + ".jpg")
        self.assertTrue(PairFinder().partner(p1).endswith(".jpg"))

    def test_fits_corrupt(self):
        p = os.path.join(self.root, "kaputt.fit")
        with open(p, "wb") as f:
            f.write(b"SIMPLE  =                    T" + b"x" * 100)
        self.assertIsNone(fits.image_size(p))
        self.assertIsNone(fits.pixel_digest(p))
        with self.assertRaises(imaging.ImageLoadError):
            imaging.load_preview(p)

    # ------------------------------------------------------------- V8 Videos
    def test_videos(self):
        for n in ("clip.mp4", "kopie.MP4", "VID_360.insv", "VID_360b.insv"):
            with open(os.path.join(self.root, n), "wb") as f:
                f.write(b"\0\0\0\x18ftypmp42" + (b"A" if "360" not in n else b"B") * 5000)
        o = ScanOptions([self.root], min_size=0)
        self.assertEqual(Scanner(o, NullCache()).run().groups, [])          # ohne Option keine Videos
        o.include_videos = True
        res = Scanner(o, NullCache()).run()
        self.assertEqual(sorted(len(g.files) for g in res.groups), [2, 2])
        tools.configure(ffmpeg=os.path.join(self.tmp, "gibtsnicht"))
        if tools.find("ffmpeg") is None:
            with self.assertRaises(imaging.ImageLoadError):
                imaging.load_preview(os.path.join(self.root, "clip.mp4"))

    @unittest.skipUnless(tools.find("ffmpeg"), "ffmpeg nicht vorhanden")
    def test_video_preview_ffmpeg(self):
        import subprocess
        v = os.path.join(self.root, "test clip.mp4")
        subprocess.run([tools.find("ffmpeg"), "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc=size=320x240:rate=10", "-t", "2", "-pix_fmt", "yuv420p", v], check=True)
        im, info = imaging.load_preview(v, 200)
        self.assertEqual(im.size, (200, 150))
        self.assertIn("ffmpeg", info)

    # ------------------------------------------------------------- V7 ExifTool
    @unittest.skipIf(os.name == "nt", "Attrappe als Shell-Skript")
    def test_exiftool_fake(self):
        exe = os.path.join(self.tmp, "exiftool")
        with open(exe, "w") as f:
            f.write("#!/bin/sh\nread taste\necho '[{\"SourceFile\":\"x\",\"IFD0:Make\":\"FUJIFILM\","
                    "\"ExifIFD:ISO\":400,\"ExifTool:ExifToolVersion\":13}]'\n")
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
        tools.configure(exiftool=exe, use_exiftool=True)
        p = os.path.join(self.root, "a.jpg")
        photo(p, 1)
        d = dict(exifinfo.read_exif(p))
        self.assertEqual(d["IFD0:Make"], "FUJIFILM")
        self.assertEqual(d["ExifIFD:ISO"], "400")
        self.assertNotIn("ExifTool:ExifToolVersion", d)
        tools.configure(use_exiftool=False)
        self.assertNotIn("IFD0:Make", dict(exifinfo.read_exif(p)))

    # ------------------------------------------------------------- V10 HTML / V9 CLI
    def test_html_and_cli(self):
        # Windows erlaubt < > nicht in Dateinamen -> dort mit & und ' prüfen (müssen ebenfalls maskiert werden)
        evil = "Tom & Jerry's.jpg" if os.name == "nt" else "Tom & Jerry's <script>.jpg"
        p = os.path.join(self.root, evil)
        photo(p, 5)
        shutil.copy2(p, os.path.join(self.root, "kopie.jpg"))
        out = os.path.join(self.tmp, "b.html")
        csv = os.path.join(self.tmp, "b.csv")
        rc = cli.main(["scan", self.root, "--min-kb", "0", "--html", out, "--csv", csv, "-q", "--no-cache"])
        self.assertEqual(rc, 1)
        with open(out, encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn("data:image/jpeg;base64,", html)
        self.assertIn("Tom &amp; Jerry&#x27;s", html)
        self.assertNotIn("Jerry's", html)
        if os.name != "nt":
            self.assertIn("&lt;script&gt;.jpg", html)
            self.assertNotIn("<script>.jpg", html)
        rc = cli.main(["scan", self.root, "--min-kb", "0", "--move", "--no-cache", "-q"])
        self.assertEqual(rc, 2)                              # ohne --archive/--yes verweigert
        rc = cli.main(["scan", self.root, "--min-kb", "0", "--archive", self.arch, "--move", "--yes",
                       "--no-cache", "-q"])
        self.assertEqual(rc, 1)
        self.assertEqual(len(os.listdir(self.root)), 1)
        self.assertEqual(cli.main(["scan", self.root, "--min-kb", "0", "--no-cache", "-q"]), 0)
        self.assertEqual(cli.main(["archive", self.arch, "--older-than", "0"]), 0)
        self.assertEqual(htmlreport.export_html([], out, thumbs=False), 0)


if __name__ == "__main__":
    unittest.main()
