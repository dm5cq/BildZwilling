# SPDX-License-Identifier: GPL-3.0-or-later
"""Startpunkt für den Kommandozeilenmodus (BildZwilling-cli.exe)."""
import sys

from bildzwilling.cli import main

if __name__ == "__main__":
    sys.exit(main())
