# BildZwilling – extrahierter Gesamt-Prompt (Stand Version 2.2, 18.11.2026)

© 2026 Stefan J. Kaiser DM5CQ / OE8KKS (Idee, Konzept & Prompt) · Umsetzung: Claude (Anthropic) · Lizenz: GNU GPL v3 oder später

Dieses Dokument fasst alle Aufträge zu BildZwilling in **einem** Prompt zusammen. Damit lässt sich das Projekt
mit einem KI-Modell fortführen oder vollständig neu erzeugen. Teil A ist der bereinigte Gesamt-Prompt,
Teil B enthält die Originalaufträge im Wortlaut (Teil C: Hinweise zur Weiterarbeit).

---

## Teil A – Gesamt-Prompt (zum Kopieren)

> **Rolle & Ziel**
> Du bist Softwareentwickler für Desktop-Anwendungen. Erstelle „BildZwilling“, eine portable Windows-Anwendung
> (BildZwilling.exe, eine Datei, ohne Installation) plus Kommandozeilenversion (BildZwilling-cli.exe), die
> doppelte Fotos findet und Duplikate sicher in einen Archivordner verschiebt. Gelöscht wird erst nach Sichtung
> und ausdrücklicher Freigabe. Die Anwendung muss später auf macOS lauffähig sein (plattformneutral bauen:
> Python 3.11–3.13, Tkinter/ttk, Logik strikt von der Oberfläche getrennt).
>
> **Quellen**
> Lokale Ordner, externe HDDs/USB, Netzlaufwerke/NAS (UNC), Sync-Ordner von pCloud, OneDrive, Nextcloud, ownCloud,
> sowie direkt pCloud und OneDrive über deren Web-Schnittstellen (Duplikate über Server-Prüfsummen, ohne Download).
> Mehrere Ordner gleichzeitig; der erste Ordner ist der „Master“ (dort liegende Dateien werden bevorzugt behalten).
> „Nur online“-Dateien von Cloud-Clients standardmäßig nicht herunterladen.
>
> **Erkennung**
> 1. Völlig identisch (Byte für Byte), unabhängig vom Dateinamen: Größe → Anfang/Ende → BLAKE2b-256 →
>    direkter Byte-Vergleich unmittelbar vor dem Verschieben.
> 2. Optional gleicher Bildinhalt bei anderen Metadaten (Pixel-Prüfsumme; RAW/FITS: Sensordaten).
> 3. Optional ähnliche Bilder (dHash, Regler streng↔locker, auch gedreht/gespiegelt) – eigene Kategorie,
>    **nie automatisch** zum Archivieren markiert.
> Prüfsummen-Cache (SQLite) für schnelle Folgesuchen.
>
> **Formate**
> Alle Bildformate (JPEG, PNG, TIFF, WebP, HEIC/HEIF, AVIF, PSD …), RAW von Fujifilm, Nikon, Canon (inkl. CR3),
> Panasonic, OM System, Leica, Hasselblad, DJI, Insta360 (+ Sony, Pentax u. a.), FITS von Smart-Teleskopen
> (ZWO Seestar S50/S30: Einzelbilder mit Bayer-Muster und gestackte RGB-Bilder; Vorschau mit Entbayerung und
> Auto-Stretch), Videos (MP4, MOV, INSV …, optional). Unbekannte Formate mindestens per Byte-Vergleich.
>
> **Sichtung**
> Liste mit Gruppen (Seiten, Filter nach Text/Art/Dateityp, Sortierung), Seitenvorschau (leer, wenn nichts
> ausgewählt ist; Klick auf das Bild = Großansicht mit Knopf SCHLIESSEN), Vergleichsfenster mit beiden Bildern
> nebeneinander (synchroner 100-%-Zoom), EXIF-Gegenüberstellung (Unterschiede gelb), Byte- und Pixelprüfung per
> Klick. Original wählbar; Regeln: Master, älteste, neueste, kürzester Pfad; Ordnerregeln („immer behalten“ /
> „immer archivieren“); Bewertungen (Sterne, Farbe, Flagge aus XMP und Lightroom-Katalog) bevorzugt behalten.
> RAW+JPEG- und FIT+JPG-Paare sowie XMP-Begleitdateien bleiben zusammen.
>
> **Archiv**
> Verschieben (gleiches Laufwerk: umbenennen; sonst kopieren → prüfen → Quelle entfernen), Platzprüfung,
> Journal je Aktion, Wiederherstellen (nie überschreiben), „Letzte Archivierung rückgängig“ (Strg+Z),
> Aufbewahrungsfrist mit Vorschlag zur Löschfreigabe, endgültiges Löschen nur bestätigt, nur wenn das Original
> noch existiert, bevorzugt in den Papierkorb.
>
> **Seestar-Assistent**
> Einzelbilder ihrem Stack zuordnen (Objekt, Belichtung, Filter, Sitzung), Ausschuss erkennen (Sternanzahl,
> FWHM, Sternform/Nachführfehler, Himmelshelligkeit/Wolken) relativ zur Sitzung, mit Begründung; Archivieren
> inkl. .jpg/_thn.jpg, rückgängig möglich.
>
> **Cloud direkt**
> pCloud (Europa/USA): Anmeldung **auch mit Zwei-Faktor** – empfohlen im Browser (OAuth 2.0, eigene pCloud-App),
> alternativ E-Mail/Passwort mit Abfrage des Sicherheitscodes. OneDrive: Gerätecode-Anmeldung (eigene
> App-Registrierung). Nur HTTPS, Passwörter nie speichern, Token nur auf Wunsch verschlüsselt (Windows DPAPI),
> vor jedem Verschieben Prüfsumme/Größe erneut prüfen, nie überschreiben, Cloud-Journal und Rückgängig.
>
> **Oberfläche & Stil**
> Dunkelgrau (#2b2b2b), weiße Schrift, orange Akzente (#ff8c00), Status Grün/Rot/Gelb/Blau. Titelleiste
> grau (Windows 10/11), alle Meldungen als eigene graue Fenster mit weißer Schrift und App-Icon, **ohne
> farbigen Rand** (die Art zeigt nur das farbige Symbol). Info-Fenster professionell und übersichtlich: Kopf mit
> Icon, Name, Version/Datum und Kurzbeschreibung; darunter zweispaltig „Idee, Konzept & Prompt: Stefan J. Kaiser
> DM5CQ / OE8KKS“, „Umsetzung: Claude (Anthropic)“, Lizenz (mit „Lizenztext anzeigen“), Komponenten, Datenordner
> (gekürzt, „Öffnen“); kurzer Haftungsausschluss; Knöpfe „Systeminfo kopieren“, „Drittanbieter“, „OK“.
> Zusätzlich Hell und Hoher Kontrast, große Schrift, Sprachausgabe. Sprachen Deutsch und Englisch.
> Copyright aus **einer** Quelle in App, Berichten, PDFs, CLI und EXE-Eigenschaften: „© 2026 Stefan J. Kaiser
> DM5CQ / OE8KKS (Idee, Konzept & Prompt) · Umsetzung: Claude (Anthropic) · Lizenz: GNU GPL v3 · Stand <Datum>“
> (Name nur einmal).
>
> **Lizenz & Haftung**
> Freie Software unter **GNU GPL v3 oder später** (SPDX `GPL-3.0-or-later`): Datei LICENSE (voller Text),
> Lizenzkopf in jeder Quelldatei, THIRD_PARTY_LICENSES.txt (wird beim Build aus den Paketen erzeugt), beides
> in der EXE und im Portable-Ordner, Lizenztext im Programm anzeigbar, CLI `--license`/`--version`.
> Haftungsausschluss (GPL Abschnitte 15/16, Datensicherung empfehlen) im Info-Fenster, in README, Quick-Guide,
> Technischer Beschreibung und als einmalige Bestätigung beim ersten Start („Gelesen und verstanden“).
>
> **Sicherheit & Stabilität**
> Nur eine Instanz gleichzeitig (Dateisperre), externe Werkzeuge unter Windows nur aus eingestelltem Pfad oder
> Programmordner (Version + SHA-256 anzeigen), „Alle Cloud-Anmeldungen entfernen“, Protokoll ohne E-Mail/
> Tokens (Logrotation), SHA256SUMS.txt beim Build, Content-Security-Policy im HTML-Bericht. Einstellungen
> atomar speichern mit Sicherung (.bak) und Wiederherstellung, kein Ruhezustand während Suche/Archivierung,
> Bildgrößen-Grenze mit klarer Meldung, lange Windows-Pfade, unvollständige Archivierungen beim Start melden
> und zurückholen, Fehlerdialog mit „Details kopieren“, Cache monatlich bereinigen, Temp-Reste löschen.
>
> **Kommandozeile**
> BildZwilling-cli.exe mit `scan` (Berichte CSV/HTML, optional Verschieben nur mit `--move --yes`, ähnliche nie)
> und `archive` (Aufbewahrung, `--undo-last --yes`), Rückgabewerte 0/1/2/3, `--lang de|en`.
>
> **Lieferumfang**
> Komplettes Projekt als ZIP, lokal baubar mit `build-exe.bat` (venv, Pakete, Tests, PyInstaller →
> Portable\BildZwilling.exe + BildZwilling-cli.exe), `build-mac.sh` für macOS. Einseitiger Quick-Guide als PDF
> (Deutsch und Englisch). Technische Beschreibung als PDF mit Bedienung beider EXE, Architektur, Sicherheits-
> konzept, **Code-Review (Sicherheit, Stabilität, Funktion)** mit Maßnahmen, durchgeführten Tests,
> Verbesserungsvorschlägen aus Review und Tests, sowie diesem Prompt. Ordner DEV mit Prompt, Entwicklungsstand
> und Changelog. Versionsnummern zweistellig (2.2), große Änderungen = neue Hauptversion. Vor der Umsetzung
> größerer Schritte zuerst Vorschläge machen und auf Freigabe warten.
>
> **Qualität**
> Automatische Tests für jede Funktion; Tests müssen unter **Windows**, macOS und Linux laufen (Dateinamen-
> Sonderzeichen, Groß/Klein-Schreibung, Pfadlängen beachten). Nach jeder Änderung Review und Tests wiederholen,
> Befunde dokumentieren. Typprüfung (Pyright) für Windows, macOS und Linux fest im Build. Nichts darf ohne
> Prüfung und Bestätigung gelöscht oder überschrieben werden.

---

## Teil B – Originalaufträge (Wortlaut)

### Version 1.0
> Ich brauche eine portable.exe die folgende Funktion behinhaltet. Ich habe ein Bildverzeichnis, dies kann lokal
> oder auf entfernten Systemen lietgen. pcloud, onedrive nextcloud, owncloud externe hdds. Die Anwendung soll nach
> doppelten also föllig identischen Bildern suchen und die dupletten in ein Archiv verzeichnis - verschieben. Also
> löschen erst nach sichtung und freigabe. In der App muss es die möglichkeit geben sich beide bilder anzusehen um
> zu prüfen ob es wirklich das gleiche bild ist. Es könnte sein dass der dateinamen anders lautet aber der Inhalt
> des bildes eine Kopie ist. Es sollen auch die EXIF informationen angezeigt werden können. Es sollen alle
> Bildformate untersützt werden. Auch RAW Dateien der KAmerahersteller, Fujifilm, Nikon, Canon, Panasonic,
> OMSystem, LEICA, HASELBLAD, DJI, Insta360 Die Oberfläche soll in meinem bekannten Stiel aussehen, Dunkelgrau,
> mit weisser schrift und Orangen Akzenten, für Status auch grün, rot, gelb und blau, Copyright hinweis wie
> gehabt. Idee und Konzept sowie Prompt Stefan J. Kaiser usw. Ich brauche auf alle Fälle einen Code review auf
> punkto Sicherheit stabilität, Funktion. Es soll eine kurze einseitige Quick-Guide als PDF erstellt werden.
> Export als fertiges Projekt - ggf. lokal zum erstellen mit einer Built.exe.bat - Wenn Du selbst noch
> verbesserungsvorschläge für die Funktionalität hast ggf. Vorschlag - bitte unten auch in der Technischen
> Beschreibung als PDF ergänzen Setze es um. Die Anwendung soll später auch auf MacOS lauffähig sein also so
> bauen das man es später hier auch portieren kann.

### Version 1.5
> Setze diese Punkte um in Version 1.5 – [alle in 1.0 umgesetzten Zusatzfunktionen] sowie V1 Ähnliche Bilder,
> V2 RAW+JPEG-Paare, V3 Barrierefreiheit wie SyncWerk 2.0 (Sprachausgabe, Hoher-Kontrast-Modus, Hell-Modus),
> V4 Virtuelle Liste, Filter und Sortierung, V5 Ordnerregeln, V6 Archiv-Aufbewahrung, V7 ExifTool-Anbindung,
> V8 Videos, V9 Kommandozeilenmodus, V10 HTML-Bericht mit Vorschaubildern.
>
> Nachtrag: es muss noch mit hinein das Smartteleskope wie Seestar und dessen RAW Formate auch untersützt werden....
>
> Nachtrag: oben die Menüzeile soll auch in Grau sien nicht in weiss - der INFO Hinweis auch in Grau mit
> Weisserschrift und mit dem ICON der Anwendung.

### Version 2.0
> bitte in V2.0 umsetzen - entferne Stefan J. Kaiser nach Idee und Konzept - das ist ja doppelt und macht keinen
> Sinn.. setzte weiter diese themen um V12 Seestar-Assistent: Subs ihrem Stack zuordnen, Ausschuss-Subs (Wolken,
> Nachführfehler) über Sternanzahl/Schärfe erkennen · V13 Direkte Cloud-Anbindung (pCloud-/OneDrive-API):
> Prüfsummen vom Server statt Download · V14 „Letzte Archivierung rückgängig“ mit einem Klick (Sitzungen im
> Journal) · V15 Bewertungen/Farbmarkierungen aus XMP bzw. Lightroom berücksichtigen · V16 Ähnlichkeit auch für
> gedrehte/gespiegelte Kopien (zusätzliche Hashes) · V17 Englische Oberfläche
>
> Fehlermeldungen aus dem Build: 1.5 `test_html_and_cli` (Dateiname „<script>.jpg“ unter Windows ungültig),
> 2.0 `test_assistant` (Begleitdateien unter Windows doppelt gezählt) – beheben.

### Version 2.1
> die Pcloud anmeldung muss auch mit 2FA funktionieren! Die Bildervorschau bleibt wenn keine Auswahl mehr
> getroffen wurde immer noch stehen. da soll dann nichts mehr angezeigt werden. Wenn auf das Bild geklickt wird
> soll das Vorschaufenster bzw. das Bild groß dargestellt werden - mit Button SCHLIESSEN wird es wieder klein.
> In der Beschreibung dukumentiere auch die Nutzung der zwei Versionen vom BildZwilling.exe und die von
> BildZwilling-cli.exe extrahiere auch den Prompt und mach im Review und im Test noch mal Verbesserungsvorschläge
> die man umsetzten sollte.

### Version 2.2
> diese Anordnung unter Info ist nicht übersichtlich - der blaue Rand muss weg! ändere den Text kürze den Text
> hier - das ist unübersichtlich mach es professioneller zudem ist unter der Text gequetscht. Idee & Konzept
> Stefan J. Kaiser Hinweis auf GNU3 lizenz usw was da hinen muss auch ein Haftungsausschluß beim verwneden der
> App! Welche Verbesserungen und im Codereview sihst du auch in punkto sicherheit udn stabilität etc. befor du
> es umsetzt bitte zuerst Vorschleäge ich gebe dann den nächsten Entwicklungsschritt frei.

Freigabe nach den Vorschlägen A1–A6, B1–B6, C1–C7, D1–D3:
> alles

(Offene Entscheidungen nach Empfehlung: GPL-3.0-or-later, Haftungshinweis beim ersten Start bestätigen,
Farbrand in allen Meldungen entfernt.)

---

## Teil C – Hinweise zur Weiterarbeit

- Projekt-ZIP komplett übergeben und auf `DEV/STAND.md`, `DEV/CHANGELOG.md` und dieses Dokument verweisen.
- Neue Texte im Code mit `_("…")` (GUI) bzw. `tr("…")` (Kern) schreiben und in `bildzwilling/i18n_en.py`
  übersetzen – `tests/test_i18n.py` meldet fehlende Einträge.
- Vor jeder Auslieferung: `python -m unittest discover -s tests` (alle grün), idealerweise automatisch auf
  Windows/macOS/Linux über `.github/workflows/tests.yml`.
- Typprüfung: `python -m pyright` (Konfiguration `pyrightconfig.json`) muss 0 Fehler melden.
- Lizenz: neue Quelldateien beginnen mit `# SPDX-License-Identifier: GPL-3.0-or-later` (Test prüft das).
- Offene Vorschläge: Technische Beschreibung, Kapitel „Verbesserungsvorschläge“ (V11, V18–V30, R/Q-Listen).
