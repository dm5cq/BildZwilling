@echo off
REM ==========================================================================
REM  BildZwilling 2.2 - portable Windows-EXE bauen
REM  (c) 2026 Stefan J. Kaiser DM5CQ / OE8KKS - Lizenz: GNU GPL v3 oder spaeter
REM  Voraussetzung: Python 3.11 - 3.13 (64 Bit) von python.org, "py"-Launcher
REM ==========================================================================
setlocal
cd /d "%~dp0"
title BildZwilling - Build

where py >nul 2>nul
if errorlevel 1 (
  echo [FEHLER] Python-Launcher "py" nicht gefunden. Bitte Python 3.12 von python.org installieren
  echo          ^(Haken bei "Add python.exe to PATH" und "py launcher"^).
  pause & exit /b 1
)

echo.
echo === 1/7  Virtuelle Umgebung .venv ===
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv || (echo [FEHLER] venv fehlgeschlagen & pause & exit /b 1)
)
set PY=.venv\Scripts\python.exe

echo.
echo === 2/7  Pakete installieren ===
%PY% -m pip install --upgrade pip >nul
%PY% -m pip install -r requirements-build.txt || (echo [FEHLER] pip install fehlgeschlagen & pause & exit /b 1)

echo.
echo === 3/7  Tests ===
%PY% -m unittest discover -s tests || (echo [FEHLER] Tests fehlgeschlagen - Build abgebrochen & pause & exit /b 1)
%PY% -m unittest tests\optional_formats.py || echo [HINWEIS] Optionaler EXIF-Formattest fehlgeschlagen - Build laeuft weiter.

echo.
echo === 4/7  Typpruefung (Pyright) und Lizenzliste ===
%PY% -m pyright
if errorlevel 2 (
  echo [HINWEIS] Typpruefung konnte nicht starten ^(Internet fuer Node.js noetig^) - Build laeuft weiter.
) else if errorlevel 1 (
  echo [FEHLER] Typpruefung hat Fehler gefunden - Build abgebrochen
  pause & exit /b 1
)
%PY% DEV\make_third_party.py || (echo [FEHLER] Lizenzliste konnte nicht erstellt werden & pause & exit /b 1)

echo.
echo === 5/7  EXE erstellen (PyInstaller) ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name BildZwilling ^
  --icon assets\icon.ico ^
  --version-file version_info.txt ^
  --add-data "assets;assets" ^
  --add-data "LICENSE;." ^
  --add-data "THIRD_PARTY_LICENSES.txt;." ^
  --collect-all rawpy ^
  --collect-all pillow_heif ^
  --collect-submodules send2trash ^
  --hidden-import exifread ^
  --hidden-import bildzwilling.i18n_en ^
  main.py || (echo [FEHLER] PyInstaller fehlgeschlagen & pause & exit /b 1)

echo.
echo === 6/7  Kommandozeilen-EXE (BildZwilling-cli.exe) ===
%PY% -m PyInstaller --noconfirm --onefile --console ^
  --name BildZwilling-cli ^
  --icon assets\icon.ico ^
  --version-file version_info.txt ^
  --add-data "LICENSE;." ^
  --collect-all rawpy ^
  --collect-all pillow_heif ^
  --collect-submodules send2trash ^
  --hidden-import exifread ^
  --hidden-import bildzwilling.i18n_en ^
  cli.py || (echo [FEHLER] PyInstaller CLI fehlgeschlagen & pause & exit /b 1)

if not exist Portable mkdir Portable
if not exist Portable\tools mkdir Portable\tools
copy /y dist\BildZwilling.exe Portable\BildZwilling.exe >nul
copy /y dist\BildZwilling-cli.exe Portable\BildZwilling-cli.exe >nul
copy /y assets\tools_LIESMICH.txt Portable\tools\LIESMICH.txt >nul
if exist docs\BildZwilling_QuickGuide.pdf copy /y docs\BildZwilling_QuickGuide.pdf Portable\ >nul
copy /y LICENSE Portable\LICENSE.txt >nul
copy /y THIRD_PARTY_LICENSES.txt Portable\ >nul

echo.
echo === 7/7  Pruefsummen (SHA256SUMS.txt) ===
powershell -NoProfile -Command "Get-FileHash -Algorithm SHA256 Portable\BildZwilling.exe,Portable\BildZwilling-cli.exe | ForEach-Object { $_.Hash.ToLower() + '  ' + (Split-Path $_.Path -Leaf) } | Set-Content -Encoding ascii Portable\SHA256SUMS.txt"
type Portable\SHA256SUMS.txt

echo.
echo ==========================================================
echo  Fertig:  %cd%\Portable\BildZwilling.exe
echo          %cd%\Portable\BildZwilling-cli.exe  (Kommandozeile)
echo  Optional: exiftool.exe und ffmpeg.exe in Portable\tools legen.
echo  Die EXE ist portabel (USB-Stick). Einstellungen, Cache und
echo  Log liegen im Unterordner "BildZwilling_Daten" neben der EXE.
echo  Weitergabe: GPL v3 - LICENSE.txt, THIRD_PARTY_LICENSES.txt und
echo  den Quellcode ^(Projekt-ZIP^) mitgeben. SHA256SUMS.txt beilegen.
echo ==========================================================
pause
