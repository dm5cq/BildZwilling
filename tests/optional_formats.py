# SPDX-License-Identifier: GPL-3.0-or-later
"""Optionale Format-Tests (benötigen ExifRead). Nicht build-blockierend."""

import os
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from bildzwilling.core import exifinfo  # noqa: E402


class OptionalFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @unittest.skipUnless(exifinfo.HAVE_EXIFREAD, "ExifRead nicht installiert")
    def test_exif_cr3_and_raf_fallback(self):
        ex1 = Image.Exif()
        ex1[0x010F] = "Canon"
        ex1[0x0110] = "EOS R5"
        ex2 = Image.Exif()
        ex2[0x8827] = 400
        def box(name, payload):
            return struct.pack(">I", len(payload) + 8) + name + payload
        cr3 = os.path.join(self.tmp, "x.cr3")
        with open(cr3, "wb") as f:
            f.write(box(b"ftyp", b"crx \x00\x00\x00\x01") + b"\x00" * 40 +
                    box(b"CMT1", ex1.tobytes()[6:]) + box(b"CMT2", ex2.tobytes()[6:]))
        d = dict(exifinfo.read_exif(cr3))
        self.assertIn("Canon", d.get("Image Make", ""))
        self.assertIn("400", d.get("EXIF ISOSpeedRatings", ""))
        # RAF-ähnlich: Kopf + eingebettetes JPEG mit EXIF
        jp = os.path.join(self.tmp, "e.jpg")
        ex1[0x010F] = "FUJIFILM"
        ex1[0x8769] = {0x8827: 200}
        Image.new("RGB", (32, 32)).save(jp, exif=ex1.tobytes())
        raf = os.path.join(self.tmp, "x.raf")
        with open(raf, "wb") as f, open(jp, "rb") as j:
            f.write(b"FUJIFILMCCD-RAW 0201FF383501" + b"\x00" * 100 + j.read())
        d = dict(exifinfo.read_exif(raf))
        self.assertIn("FUJIFILM", d.get("Image Make", ""))



if __name__ == "__main__":
    unittest.main()
