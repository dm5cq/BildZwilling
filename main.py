# SPDX-License-Identifier: GPL-3.0-or-later
"""Startpunkt von BildZwilling (Windows / macOS / Linux).

© 2026 Stefan J. Kaiser DM5CQ / OE8KKS · Lizenz: GNU GPL v3 oder später (siehe LICENSE)
"""

import os
import sys
import traceback


def _dpi_aware():
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # pyright: ignore[reportAttributeAccessIssue]
        except Exception:  # noqa: BLE001
            pass


def _crash(exc_type, exc, tb):
    """Unerwarteter Fehler: crash.log schreiben, Meldung im App-Stil mit „Details kopieren“ (2.2, C6)."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    details = text
    try:
        from bildzwilling.core.logutil import anonymize_paths, redact
        from bildzwilling.core.settings import data_dir
        from bildzwilling.core.sysinfo import system_info

        details = anonymize_paths(redact(system_info() + "\n\n" + text))
        with open(os.path.join(data_dir(), "crash.log"), "a", encoding="utf-8") as f:
            f.write(redact(text) + "\n")
    except Exception:  # noqa: BLE001
        pass
    try:
        from bildzwilling.gui import dialogs
        from bildzwilling.i18n import _

        if dialogs._CFG.get("root") is not None:  # noqa: SLF001
            dialogs.showerror("BildZwilling", _("Unerwarteter Fehler:\n\n{e}\n\nDie Details stehen in crash.log im "
                                                "Datenordner. Mit „Details kopieren“ können Sie sie z. B. in eine "
                                                "Fehlermeldung einfügen.").format(e=exc), details=details)
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        from tkinter import messagebox

        messagebox.showerror("BildZwilling – Fehler", f"Unerwarteter Fehler:\n\n{exc}\n\nDetails in crash.log")
    except Exception:  # noqa: BLE001
        print(text, file=sys.stderr)


def main():
    _dpi_aware()
    sys.excepthook = _crash
    from bildzwilling.gui.app import App

    app = App()
    app.root.report_callback_exception = _crash
    app.run()


if __name__ == "__main__":
    main()
