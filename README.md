# BildZwilling 2.2

[![Tests](https://github.com/dm5cq/BildZwilling/actions/workflows/tests.yml/badge.svg)](https://github.com/dm5cq/BildZwilling/actions/workflows/tests.yml)
[![Lizenz: GPL v3](https://img.shields.io/badge/Lizenz-GPL%20v3-blue.svg)](LICENSE)

Findet **doppelte Fotos** – auch mit anderem Dateinamen, in anderen Ordnern oder auf anderen
Laufwerken – und verschiebt die Duplikate **sicher in einen Archivordner**. Gelöscht wird erst
nach Sichtung und ausdrücklicher Freigabe.

*© 2026 Stefan J. Kaiser DM5CQ / OE8KKS (Idee, Konzept & Prompt) · Umsetzung: Claude (Anthropic) · Lizenz: GNU GPL v3 oder später · Version 2.2 · Stand 18.11.2026*

**Dokumentation:** [Quick-Guide](docs/BildZwilling_QuickGuide.pdf) ·
[Quick Guide (English)](docs/BildZwilling_QuickGuide_EN.pdf) ·
[Technische Beschreibung](docs/BildZwilling_Technische_Beschreibung.pdf)

**Download (Windows):** unter [Releases](https://github.com/dm5cq/BildZwilling/releases/latest) das ZIP
`BildZwilling-<Version>-Windows.zip` herunterladen, entpacken und `BildZwilling.exe` starten – keine Installation.
Prüfsummen stehen in `SHA256SUMS.txt`. Oder selbst bauen mit `build-exe.bat` (siehe „Bauen“).

## Funktionen

- Mehrere Bildordner gleichzeitig: lokal, externe HDD/SSD, USB, Netzlaufwerk (UNC/NAS),
  pCloud Drive, OneDrive, Nextcloud, ownCloud
- Zwei Suchmodi
  - **Byte-identisch** – Dateiinhalt 1:1 gleich (BLAKE2b-256 + direkter Byte-Vergleich vor dem Verschieben)
  - **+ gleicher Bildinhalt** – gleiche Pixel bzw. RAW-Sensordaten, auch wenn Metadaten/Container abweichen
- Alle gängigen Bildformate inkl. HEIC/AVIF/WebP/TIFF/PSD und RAW von Fujifilm, Nikon, Canon (CR2/CR3),
  Panasonic, OM System/Olympus, Leica, Hasselblad, DJI, Insta360, Sony, Pentax …
- Vergleichsfenster: beide Bilder nebeneinander, synchroner 100-%-Zoom, EXIF-Gegenüberstellung
  (Unterschiede gelb), Byte- und Pixel-Prüfung per Klick
- Regel für das „Original“ (Master-Ordner, älteste, neueste, kürzester Pfad) – jederzeit pro Gruppe änderbar
- Archiv mit Journal: Wiederherstellen an den Originalort, endgültiges Löschen (Papierkorb) erst nach Freigabe
- XMP-Begleitdateien wandern mit, Nur-Online-Cloud-Dateien werden standardmäßig nicht heruntergeladen
- Prüfsummen-Cache für schnelle Wiederholungssuchen, CSV-Berichte, Protokoll
- Portabel: Einstellungen/Cache/Log im Ordner `BildZwilling_Daten` neben der EXE

### Neu in 2.2
- **Neues Info-Fenster** (übersichtlich, ohne Farbrand), Meldungen ohne Farbrand
- **Freie Software unter GNU GPL v3**, Lizenztexte im Programm, Haftungshinweis beim ersten Start
- **Sicherheit:** nur eine Instanz, Werkzeuge nicht aus dem PATH (Windows), „Alle Cloud-Anmeldungen entfernen“,
  Protokoll ohne E-Mail/Tokens, SHA256SUMS.txt, Content-Security-Policy im HTML-Bericht
- **Stabilität:** Sicherung der Einstellungen, unvollständige Archivierungen erkennen und zurückholen,
  kein Ruhezustand während langer Vorgänge, Grenze für riesige Bilder, Fehlerdialog mit „Details kopieren“,
  Cache-Bereinigung, Typprüfung (Pyright) im Build

### Neu in 2.1
- **pCloud mit Zwei-Faktor-Anmeldung** (Browser/OAuth oder Passwort + Code), **Großansicht** per Klick auf die Vorschau

### Neu in 2.0
- **Seestar-Assistent:** Subs ihrem Stack zuordnen, Ausschuss (Wolken, Unschärfe, Nachführfehler) erkennen
- **Cloud direkt:** pCloud/OneDrive über Server-Prüfsummen prüfen – ohne Download, Verschieben in der Cloud
- **↶ Rückgängig (Strg+Z)** für die letzte Archivierung – lokal, Seestar und Cloud
- **Bewertungen** (★, Farbe, Flagge) aus XMP und Lightroom-Katalog: bewertete bevorzugt behalten
- **Gedrehte/gespiegelte Kopien** bei ähnlichen Bildern
- **Englische Oberfläche** (⚙ → Darstellung), Quick-Guide auch auf Englisch

### Neu in 1.5
- **Ähnliche Bilder** (verkleinerte Kopien, WhatsApp-Versionen, Serien) mit Regler – nie automatisch archiviert
- **RAW+JPEG- und FIT+JPG-Paare** bleiben zusammen
- **Smart-Teleskope:** FITS von ZWO Seestar S50/S30 & Co. (Einzelbilder und Stacks, Auto-Stretch-Vorschau, Header)
- **Videos** (MP4, MOV, Insta360 INSV, DJI …), Vorschau mit optionalem ffmpeg
- **ExifTool** optional für vollständige Metadaten
- **Ordnerregeln** („WhatsApp“ immer archivieren, „Fotos/Best“ immer behalten)
- **Archiv-Aufbewahrung:** fällige Einträge werden zur Löschfreigabe vorgeschlagen
- **Große Bibliotheken:** Seiten, Filter, Sortierung
- **Barrierefreiheit:** Dunkel/Hell/Hoher Kontrast, große Schrift, Sprachausgabe
- **Graue Titelleiste und eigene Dialoge** mit App-Icon statt weißer Windows-Fenster
- **HTML-Bericht** mit Vorschaubildern, **BildZwilling-cli.exe** für NAS/Aufgabenplanung

## Bauen

| System  | Befehl | Ergebnis |
|---------|--------|----------|
| Windows | `build-exe.bat` doppelklicken | `Portable\BildZwilling.exe`, `Portable\BildZwilling-cli.exe` |
| macOS   | `./build-mac.sh` | `Portable/BildZwilling.app` |

Voraussetzung: Python 3.11–3.13 (64 Bit) von python.org. Das Skript legt eine `.venv` an,
installiert die Pakete, führt Tests und Typprüfung aus, erzeugt die Lizenzliste und baut mit PyInstaller.
Im Ordner `Portable` liegen danach auch `LICENSE.txt`, `THIRD_PARTY_LICENSES.txt` und `SHA256SUMS.txt`.

Direkt aus dem Quellcode starten: `python main.py` (bzw. `start-dev.bat`).

## Projektstruktur

```
main.py                     Startpunkt
bildzwilling/core/          Logik ohne Oberfläche (plattformneutral, getestet)
  scanner.py                Suche (Größe -> Anfang/Ende -> BLAKE2b, optional Pixel, ähnlich)
  similar.py, plan.py       Ähnlichkeit (dHash/BK-Baum), Archivplan mit Paaren
  fits.py, seestar.py       FITS (Seestar & Co.), Seestar-Assistent
  cloud.py, secret.py       pCloud/OneDrive-API, verschlüsselte Token (DPAPI)
  ratings.py                Bewertungen aus XMP/Lightroom
  tools.py, htmlreport.py   ExifTool/ffmpeg, HTML-Bericht
bildzwilling/cli.py         Kommandozeile
bildzwilling/i18n*.py       Sprachen (Deutsch, Englisch)
  archive.py                Verschieben, Journal, Wiederherstellen, Löschen
  imaging.py                Vorschau, RAW, Pixel-Prüfsumme
  exifinfo.py               EXIF (ExifRead, Fallback Pillow)
  fsutil.py                 lange Windows-Pfade, Cloud-Platzhalter, Pfadprüfungen
  hashcache.py, settings.py, report.py, formats.py
bildzwilling/gui/           Tkinter-Oberfläche (Dunkelgrau/Orange)
tests/                      Unit-Tests der Kern-Engine
docs/                       Quick-Guide & Technische Beschreibung (PDF)
DEV/                        Prompt, Entwicklungsstand, Changelog
```

## Lizenz

BildZwilling ist freie Software: Sie dürfen es unter den Bedingungen der **GNU General Public License,
Version 3 oder (nach Ihrer Wahl) einer späteren Version** weitergeben und/oder verändern (Datei `LICENSE`).
Wer die EXE weitergibt, legt `LICENSE.txt` und `THIRD_PARTY_LICENSES.txt` bei und macht den Quellcode
verfügbar – ein Hinweis auf **https://github.com/dm5cq/BildZwilling** genügt. Lizenzen der eingebundenen Komponenten: `THIRD_PARTY_LICENSES.txt`.

## Haftungsausschluss

BildZwilling verschiebt Dateien und kann sie nach Ihrer ausdrücklichen Freigabe löschen. Die Nutzung erfolgt
auf eigene Verantwortung und **ohne Gewährleistung**. Legen Sie vor dem Aufräumen eine Datensicherung an und
prüfen Sie archivierte Dateien, bevor Sie sie endgültig löschen. Soweit gesetzlich zulässig, wird keine Haftung
für Datenverlust oder sonstige Schäden übernommen (GPL v3, Abschnitte 15 und 16); zwingende gesetzliche Haftung
bleibt unberührt.
