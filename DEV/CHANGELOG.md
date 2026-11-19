# Changelog

## 2.2 – 18.11.2026
- A1/A2 Neues Info-Fenster (zweispaltig, ohne Farbrand, Systeminfo kopieren, Drittanbieter); alle Meldungen ohne Farbrand
- A3/A4 GNU GPL v3 oder später: LICENSE, SPDX-Kopf in allen Quelldateien, THIRD_PARTY_LICENSES.txt (Build), Lizenzfenster, CLI --license/--version
- A5 Haftungsausschluss (Info, Lizenzfenster, README, Quick-Guide, Doku) und einmalige Bestätigung beim ersten Start
- A6 Copyright aus einer Quelle (Name einmal, „Idee, Konzept & Prompt“ zugeordnet)
- B1 Nur eine Instanz (Dateisperre; CLI-Verschieben gesperrt, solange das Programm läuft)
- B2 Externe Werkzeuge unter Windows nicht aus dem PATH; Version + SHA-256 in den Einstellungen
- B3 „Alle Cloud-Anmeldungen entfernen“ · B4 Protokoll ohne E-Mail/Tokens · B5 SHA256SUMS.txt · B6 CSP im HTML-Bericht
- C1 Einstellungen mit Sicherung (.bak) und Wiederherstellung · C2 kein Ruhezustand während Suche/Archivierung
- C3 Vorschau-Grenze für riesige Bilder · C4 Test lange Windows-Pfade · C5 unvollständige Archivierungen erkennen/zurückholen
- C6 Fehlerdialog mit „Details kopieren“ · C7 Cache monatlich bereinigen, Temp-Reste löschen, ⚙ → Wartung
- D1 Pyright (Windows/macOS/Linux) im Build und in der CI, Testabdeckung in der CI
- Fix (von der Typprüfung gefunden): Seestar-Fehlerzähler überschrieb eine Methode (T19); Cloud-Vergleich nach Abmelden (T20)
- R13 Quellcode öffentlich auf https://github.com/dm5cq/BildZwilling – Link im Info-Fenster, Lizenztext, Systeminfo, CLI --license
- Releases: Versions-Tag (v2.2) erzeugt automatisch ein GitHub-Release mit Windows-Paket (Programm, Kommandozeile, Lizenzen, Quick-Guides, SHA256SUMS) und PDFs
- Tests: 61 (vorher 42)

## 2.1 – 17.11.2026
- pCloud mit Zwei-Faktor-Anmeldung: Browser-Anmeldung (OAuth 2.0, eigene pCloud-App) empfohlen; alternativ E-Mail/Passwort + Sicherheitscode (tfa_login, „Diesem Gerät vertrauen“)
- Seitenvorschau wird ohne Auswahl geleert (Duplikate, Seestar)
- Großansicht per Klick auf die Vorschau (100 %-Zoom, verschieben), SCHLIESSEN/Esc
- Platzprüfung vor dem Archivieren (GUI, Seestar, CLI)
- Fix: Cloud-Rückgängig ließ die Oberfläche bei Netzwerkfehler „beschäftigt“ (T17); Abmelden-Fehler im Hintergrund (T18)
- Doku: Bedienung BildZwilling.exe und BildZwilling-cli.exe, Gesamt-Prompt (DEV/PROMPT_GESAMT.md + Anhang), Code-Review 2.1 mit R1–R11, Testvorschläge Q1–Q10, V24–V30
- GitHub-Actions-Vorlage .github/workflows/tests.yml (Windows/macOS/Linux)

## 2.0 – 17.11.2026
- V12 Seestar-Assistent (Zuordnung Subs↔Stack, Ausschuss über Sterne/FWHM/Form/Hintergrund, Archivieren inkl. JPG)
- V13 Cloud direkt: pCloud (EU/US) und OneDrive per API, Server-Prüfsummen, Cloud-Archiv, Journal, Rückgängig
- V14 Rückgängig: Sitzungen im Journal, „↶ Rückgängig“ / Strg+Z, CLI archive --undo-last --yes
- V15 Bewertungen aus XMP (Begleitdatei/eingebettet) und Lightroom-Katalog
- V16 Ähnliche Bilder auch gedreht/gespiegelt (8 Hashes)
- V17 Englische Oberfläche, englischer Quick-Guide, CLI --lang en
- Copyright: Name nur noch einmal („… · Idee, Konzept & Prompt · Umsetzung: Claude“)
- Fix 1.5: Windows-Build brach im Test ab (Dateiname „<script>.jpg“ unter Windows unzulässig)
- Fix Windows: Seestar-Begleitdateien (.jpg/_thn.jpg) wurden doppelt gezählt (Groß/Klein-Schreibung) – Build-Test schlug fehl
- Code-Review 2.0: S12–S15, D12–D15, T12–T16, F13–F19

## 1.5 – 17.11.2026
- V1 Ähnliche Bilder (dHash, BK-Baum, Regler 0–16, nie automatisch archiviert)
- V2 RAW+JPEG- bzw. FIT+JPG-Paare zusammenhalten (Paar-Planer)
- V3 Dunkel/Hell/Hoher Kontrast, große Schrift, Sprachausgabe
- V4 Seiten, Filter (Text, Art, Typ), Sortierung
- V5 Ordnerregeln (immer behalten / immer archivieren)
- V6 Archiv-Aufbewahrung mit „Fällige auswählen“
- V7 ExifTool-Anbindung (optional)
- V8 Videos (Byte-Vergleich, ffmpeg-Vorschau)
- V9 Kommandozeile BildZwilling-cli.exe
- V10 HTML-Bericht mit Vorschaubildern
- Neu: Smart-Teleskope (ZWO Seestar S50/S30 u. a.) – FITS-Leser mit Entbayerung, Auto-Stretch, Header-Anzeige
- Neu: graue Titelleiste (Windows 10/11) und eigene Dialoge im App-Stil mit App-Icon; Löschfragen mit „Nein“ vorausgewählt
- Code-Review 1.5: S7–S11, D6–D11, T9–T11, F7–F12 (siehe Technische Beschreibung)

## 1.0 – 17.11.2026
- Erste Version: Byte-identische Suche, optional Bildinhalt (Pixel/RAW-Sensordaten)
- Mehrere Quellordner mit Master-Priorität; Regeln für das Original
- Vergleichsfenster mit synchronem Zoom, EXIF-Gegenüberstellung, Byte-/Pixel-Prüfung
- Archiv mit Journal, Wiederherstellen, endgültiges Löschen (Papierkorb) nach Freigabe
- XMP-Begleitdateien, Cloud-Platzhalter-Schutz, Prüfsummen-Cache, CSV-Berichte
- Code-Review (Sicherheit/Stabilität/Funktion) mit Korrekturen, siehe Technische Beschreibung
