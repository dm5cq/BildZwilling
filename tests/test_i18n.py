# SPDX-License-Identifier: GPL-3.0-or-later
"""Prüft, dass jeder übersetzbare Text eine englische Übersetzung mit identischen Platzhaltern hat."""

import ast
import glob
import os
import string
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bildzwilling import i18n  # noqa: E402
from bildzwilling.i18n_en import EN  # noqa: E402


def keys_in_code():
    keys = {}
    for p in glob.glob(os.path.join(ROOT, "bildzwilling", "**", "*.py"), recursive=True):
        src = open(p, encoding="utf-8").read()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call):
                f = n.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                if name in ("_", "tr") and n.args and isinstance(n.args[0], ast.Constant) \
                        and isinstance(n.args[0].value, str):
                    keys[n.args[0].value] = os.path.basename(p)
    return keys


def fields(s):
    return sorted((f, spec) for _, f, spec, _ in string.Formatter().parse(s) if f is not None)


class I18nTest(unittest.TestCase):
    def test_all_translated(self):
        missing = {k: f for k, f in keys_in_code().items() if k not in EN}
        self.assertEqual(missing, {}, "Fehlende englische Übersetzungen (in bildzwilling/i18n_en.py ergänzen)")

    def test_placeholders(self):
        bad = [k for k, v in EN.items() if fields(k) != fields(v)]
        self.assertEqual(bad, [])

    def test_switch(self):
        try:
            i18n.set_language("en")
            self.assertEqual(i18n._("Suche starten (F5)"), "Start search (F5)")
            self.assertEqual(i18n._("unbekannter Text"), "unbekannter Text")
        finally:
            i18n.set_language("de")
        self.assertEqual(i18n._("Suche starten (F5)"), "Suche starten (F5)")


if __name__ == "__main__":
    unittest.main()
