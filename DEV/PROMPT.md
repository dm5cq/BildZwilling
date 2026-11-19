# Ursprünglicher Prompt (17.11.2026)

> Ich brauche eine portable.exe die folgende Funktion behinhaltet. Ich habe ein Bildverzeichnis, dies kann
> lokal oder auf entfernten Systemen lietgen. pcloud, onedrive nextcloud, owncloud externe hdds. Die
> Anwendung soll nach doppelten also föllig identischen Bildern suchen und die dupletten in ein Archiv
> verzeichnis - verschieben. Also löschen erst nach sichtung und freigabe. In der App muss es die
> möglichkeit geben sich beide bilder anzusehen um zu prüfen ob es wirklich das gleiche bild ist. Es
> könnte sein dass der dateinamen anders lautet aber der Inhalt des bildes eine Kopie ist. Es sollen auch
> die EXIF informationen angezeigt werden können. Es sollen alle Bildformate untersützt werden. Auch RAW
> Dateien der KAmerahersteller, Fujifilm, Nikon, Canon, Panasonic, OMSystem, LEICA, HASELBLAD, DJI,
> Insta360 Die Oberfläche soll in meinem bekannten Stiel aussehen, Dunkelgrau, mit weisser schrift und
> Orangen Akzenten, für Status auch grün, rot, gelb und blau, Copyright hinweis wie gehabt. Idee und
> Konzept sowie Prompt Stefan J. Kaiser usw. Ich brauche auf alle Fälle einen Code review auf punkto
> Sicherheit stabilität, Funktion. Es soll eine kurze einseitige Quick-Guide als PDF erstellt werden.
> Export als fertiges Projekt - ggf. lokal zum erstellen mit einer Built.exe.bat - Wenn Du selbst noch
> verbesserungsvorschläge für die Funktionalität hast ggf. Vorschlag - bitte unten auch in der Technischen
> Beschreibung als PDF ergänzen Setze es um. Die Anwendung soll später auch auf MacOS lauffähig sein also
> so bauen das man es später hier auch portieren kann.

## Auftrag Version 1.5 (17.11.2026)

> Setze diese Punkte um in Version 1.5 – [alle in 1.0 umgesetzten Zusatzfunktionen beibehalten] sowie V1–V10:
> Ähnliche Bilder, RAW+JPEG-Paare, Barrierefreiheit (Sprachausgabe, Hoher Kontrast, Hell), virtuelle Liste/Filter/
> Sortierung, Ordnerregeln, Archiv-Aufbewahrung, ExifTool, Videos, Kommandozeilenmodus, HTML-Bericht.
>
> Nachtrag: Es muss noch mit hinein, dass Smartteleskope wie Seestar und deren RAW-Formate auch unterstützt werden.
>
> Nachtrag: Oben die Menüzeile soll auch in Grau sein, nicht in Weiß – der INFO-Hinweis auch in Grau mit weißer
> Schrift und mit dem ICON der Anwendung.

## Auftrag Version 2.0 (17.11.2026)

> bitte in V2.0 umsetzen - entferne Stefan J. Kaiser nach Idee und Konzept - das ist ja doppelt und macht keinen
> Sinn.. setzte weiter diese themen um V12 Seestar-Assistent … V13 Direkte Cloud-Anbindung (pCloud-/OneDrive-API) …
> V14 „Letzte Archivierung rückgängig“ … V15 Bewertungen/Farbmarkierungen aus XMP bzw. Lightroom … V16 Ähnlichkeit
> auch für gedrehte/gespiegelte Kopien … V17 Englische Oberfläche
>
> Nachtrag: Fehler im 1.5-Build (test_html_and_cli: Dateiname „<script>.jpg“ unter Windows ungültig) beheben.

## Auftrag Version 2.1 (17.11.2026)

> die Pcloud anmeldung muss auch mit 2FA funktionieren! Die Bildervorschau bleibt wenn keine Auswahl mehr
> getroffen wurde immer noch stehen. da soll dann nichts mehr angezeigt werden. Wenn auf das Bild geklickt wird
> soll das Vorschaufenster bzw. das Bild groß dargestellt werden - mit Button SCHLIESSEN wird es wieder klein.
> In der Beschreibung dukumentiere auch die Nutzung der zwei Versionen vom BildZwilling.exe und die von
> BildZwilling-cli.exe extrahiere auch den Prompt und mach im Review und im Test noch mal Verbesserungsvorschläge
> die man umsetzten sollte.

Zusammengefasster Gesamt-Prompt: siehe `PROMPT_GESAMT.md`.

## Hinweis für die Weiterarbeit mit einem KI-Modell

Diesen Ordner `DEV` zusammen mit dem kompletten Projekt übergeben und auf `STAND.md` verweisen.
Versionsnummern zweistellig (1.0, 1.1 …), Major-Änderungen 2.0.
Stil: Dunkelgrau #2b2b2b, weiße Schrift, Akzent Orange #ff8c00, Status Grün/Rot/Gelb/Blau,
Copyright (ab 2.0): „© 2026 Stefan J. Kaiser DM5CQ / OE8KKS · Idee, Konzept & Prompt · Umsetzung: Claude (Anthropic) · Stand <Datum>“ – Name nur einmal.


## Version 2.2 (18.11.2026)
Auftrag: Info-Fenster übersichtlich und professionell (kein blauer Rand, kürzerer Text, nicht gequetscht),
„Idee & Konzept Stefan J. Kaiser“, Hinweis auf GNU GPL v3, Haftungsausschluss; zuerst Vorschläge zu
Verbesserungen aus Code-Review (Sicherheit, Stabilität) – Freigabe: „alles“ (A1–A6, B1–B6, C1–C7, D1–D3).
Vollständiger Gesamt-Prompt: DEV/PROMPT_GESAMT.md.
