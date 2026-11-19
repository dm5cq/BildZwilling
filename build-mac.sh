#!/usr/bin/env bash
# ==========================================================================
#  BildZwilling 2.2 - macOS-App bauen (Apple Silicon oder Intel)
#  © 2026 Stefan J. Kaiser DM5CQ / OE8KKS · Lizenz: GNU GPL v3 oder später
#  Voraussetzung: Python 3.12/3.13 von python.org (enthält Tk)
#  Aufruf:  chmod +x build-mac.sh && ./build-mac.sh
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"

echo "=== 1/4  venv ==="
[ -x .venv/bin/python ] || "$PYTHON" -m venv .venv
PY=.venv/bin/python
"$PY" -c "import tkinter" || { echo "Tkinter fehlt – bitte Python von python.org verwenden."; exit 1; }

echo "=== 2/4  Pakete ==="
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r requirements-build.txt

echo "=== 3/4  Tests ==="
"$PY" -m unittest discover -s tests
"$PY" -m unittest tests/optional_formats.py || echo "[HINWEIS] Optionaler EXIF-Formattest fehlgeschlagen – Build läuft weiter."

echo "=== Typprüfung + Lizenzliste ==="
set +e; "$PY" -m pyright; rc=$?; set -e
if [ $rc -eq 1 ]; then echo "[FEHLER] Typprüfung hat Fehler gefunden"; exit 1; fi
[ $rc -ge 2 ] && echo "[HINWEIS] Typprüfung konnte nicht starten – Build läuft weiter."
"$PY" DEV/make_third_party.py

echo "=== 4/4  App bauen ==="
rm -rf build dist
"$PY" -m PyInstaller --noconfirm --clean --windowed \
  --name BildZwilling \
  --icon assets/icon.icns \
  --osx-bundle-identifier de.kaiser-burghausen.bildzwilling \
  --add-data "assets:assets" \
  --add-data "LICENSE:." \
  --add-data "THIRD_PARTY_LICENSES.txt:." \
  --collect-all rawpy \
  --collect-all pillow_heif \
  --collect-submodules send2trash \
  --hidden-import exifread \
  --hidden-import bildzwilling.i18n_en \
  main.py

echo "=== CLI ==="
"$PY" -m PyInstaller --noconfirm --onefile --console --name BildZwilling-cli --add-data "LICENSE:." \
  --collect-all rawpy --collect-all pillow_heif --collect-submodules send2trash --hidden-import exifread --hidden-import bildzwilling.i18n_en cli.py

# Ad-hoc-Signatur (ohne Apple-Entwicklerkonto). Erster Start: Rechtsklick -> Öffnen.
codesign --force --deep -s - dist/BildZwilling.app || true
mkdir -p Portable/tools && rm -rf Portable/BildZwilling.app && cp -R dist/BildZwilling.app Portable/
cp dist/BildZwilling-cli Portable/ && cp assets/tools_LIESMICH.txt Portable/tools/LIESMICH.txt
cp LICENSE Portable/LICENSE.txt && cp THIRD_PARTY_LICENSES.txt Portable/
(cd Portable && shasum -a 256 BildZwilling-cli BildZwilling.app/Contents/MacOS/BildZwilling > SHA256SUMS.txt)
echo "Fertig: $(pwd)/Portable/BildZwilling.app"
