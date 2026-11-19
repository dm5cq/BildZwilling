# SPDX-License-Identifier: GPL-3.0-or-later
"""Einfache Sprachausgabe ohne Zusatzpakete (Barrierefreiheit).

Windows: System.Speech über PowerShell (Text per Standardeingabe – keine Befehlsinjektion)
macOS:   „say“ (Text per Standardeingabe)
Linux:   spd-say oder espeak, falls vorhanden
Es wird immer nur die neueste Meldung gesprochen; ältere, noch wartende werden verworfen.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading

_PS = ("[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
       "Add-Type -AssemblyName System.Speech; "
       "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
       "try { $v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'de*' } | "
       "Select-Object -First 1; if ($v) { $s.SelectVoice($v.VoiceInfo.Name) } } catch {}; "
       "$s.Speak([Console]::In.ReadToEnd())")


def _command():
    if sys.platform.startswith("win"):
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS]
    if sys.platform == "darwin":
        return ["say"]
    for c in (["spd-say", "-e", "-l", "de"], ["espeak", "-v", "de", "--stdin"]):
        if shutil.which(c[0]):
            return c
    return None


class Speaker:
    def __init__(self):
        self.enabled = False
        self._cmd = _command()
        self._pending: str | None = None
        self._cv = threading.Condition()
        self._thread = None

    @property
    def available(self) -> bool:
        return self._cmd is not None

    def say(self, text: str) -> None:
        if not self.enabled or not self._cmd or not text:
            return
        with self._cv:
            self._pending = text[:600]
            self._cv.notify()
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="bz-speech")
            self._thread.start()

    def _loop(self):
        while True:
            with self._cv:
                while self._pending is None:
                    self._cv.wait()
                text, self._pending = self._pending, None
            try:
                kw: dict = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
                if not self._cmd:
                    continue
                subprocess.run(self._cmd, input=text.encode("utf-8"), timeout=60,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, **kw)
            except (OSError, subprocess.SubprocessError):
                pass
