# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt docs/BildZwilling_Technische_Beschreibung.pdf.  Aufruf: python DEV/make_techdoc.py"""

import os
import sys

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FD = "/usr/share/fonts/truetype/dejavu"
for n, f in (("DV", "DejaVuSans.ttf"), ("DVB", "DejaVuSans-Bold.ttf"), ("DVI", "DejaVuSans-Oblique.ttf"),
             ("DVBI", "DejaVuSans-BoldOblique.ttf"), ("DVM", "DejaVuSansMono.ttf")):
    pdfmetrics.registerFont(TTFont(n, os.path.join(FD, f)))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DVB", italic="DVI", boldItalic="DVBI")

BG, ORANGE, GREEN, RED = HexColor("#2b2b2b"), HexColor("#ff8c00"), HexColor("#4caf50"), HexColor("#e53935")
YELLOW, BLUE, MUTED, DARK, LIGHT = (HexColor("#f2c200"), HexColor("#42a5f5"), HexColor("#8a8a8a"),
                                    HexColor("#222222"), HexColor("#f4f4f4"))

S = {
    "h1": ParagraphStyle("h1", fontName="DVB", fontSize=15, leading=19, textColor=ORANGE, spaceBefore=10,
                         spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="DVB", fontSize=11, leading=14, textColor=DARK, spaceBefore=8,
                         spaceAfter=3),
    "p": ParagraphStyle("p", fontName="DV", fontSize=9, leading=12.6, textColor=DARK, spaceAfter=5),
    "li": ParagraphStyle("li", fontName="DV", fontSize=9, leading=12.4, textColor=DARK, leftIndent=12,
                         bulletIndent=2, spaceAfter=2),
    "td": ParagraphStyle("td", fontName="DV", fontSize=7.8, leading=10, textColor=DARK),
    "th": ParagraphStyle("th", fontName="DVB", fontSize=7.8, leading=10, textColor=white),
    "prompt": ParagraphStyle("prompt", fontName="DV", fontSize=8.4, leading=11.6, textColor=DARK,
                             backColor=LIGHT, borderPadding=6, leftIndent=6, rightIndent=6, spaceBefore=2,
                             spaceAfter=8),
    "code": ParagraphStyle("code", fontName="DVM", fontSize=7.8, leading=10, textColor=DARK, backColor=LIGHT,
                           borderPadding=5, leftIndent=5, rightIndent=5, spaceBefore=3, spaceAfter=8),
}


_H = [0]


sys.path.insert(0, ROOT)
from bildzwilling import COPYRIGHT, VERSION  # noqa: E402


def H1(title):
    _H[0] += 1
    return P(f"{_H[0]} · {title}", "h1")


def P(t, s="p"):
    return Paragraph(t, S[s])


def bullets(items):
    return [Paragraph(t, S["li"], bulletText="•") for t in items]


def table(rows, widths, head=True, zebra=True):
    data = [[Paragraph(str(c), S["th"] if (head and i == 0) else S["td"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#dddddd"))]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), BG))
    if zebra:
        for i in range(1 if head else 0, len(rows)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(st))
    return t


def status(s):  # noqa: D401
    col = {"behoben": "#2e7d32", "umgesetzt": "#2e7d32", "vorbereitet": "#1565c0", "teilweise": "#b26a00", "offen": "#c62828", "Hinweis": "#1565c0",
           "akzeptiert": "#b28704"}.get(s, "#222222")
    return f'<font color="{col}"><b>{s}</b></font>'


def on_page(c, doc):
    w, h = A4
    c.saveState()
    c.setFillColor(BG)
    c.rect(0, h - 22 * mm, w, 22 * mm, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(0, h - 22 * mm - 2, w, 2, stroke=0, fill=1)
    c.drawImage(os.path.join(ROOT, "assets", "icon.png"), 15 * mm, h - 19 * mm, 15 * mm, 15 * mm, mask="auto")
    c.setFont("DVB", 14)
    c.drawString(34 * mm, h - 12 * mm, f"BildZwilling {VERSION}")
    c.setFillColor(white)
    c.setFont("DV", 9)
    c.drawString(34 * mm, h - 17.5 * mm, "Technische Beschreibung · Bedienung · Code-Review · Verbesserungsvorschläge")
    c.setFillColor(MUTED)
    c.setFont("DV", 7)
    size = 7.0
    while c.stringWidth(COPYRIGHT, "DV", size) > w - 30 * mm - 18 * mm and size > 5:
        size -= 0.25
    c.setFont("DV", size)
    c.drawString(15 * mm, 10 * mm, COPYRIGHT)
    c.setFont("DV", 7)
    c.drawRightString(w - 15 * mm, 10 * mm, f"Seite {doc.page}")
    c.restoreState()


def prompt_paragraphs() -> list[str]:
    """Teil A aus DEV/PROMPT_GESAMT.md lesen (eine Quelle für Prompt-Datei und PDF)."""
    import re

    with open(os.path.join(ROOT, "DEV", "PROMPT_GESAMT.md"), encoding="utf-8") as f:
        text = f.read()
    part = text[text.index("## Teil A"):text.index("## Teil B")]
    lines = [ln[2:] if ln.startswith("> ") else ("" if ln.strip() == ">" else ln) for ln in part.splitlines()[2:]]
    body = "\n".join(lines).strip().strip("-").strip()
    out = []
    for para in (p.strip().replace("\n", " ") for p in body.split("\n\n") if p.strip()):
        para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        para = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", para)
        para = re.sub(r"`(.+?)`", r"<font name='DVM'>\1</font>", para)
        out.append(para)
    return out


def build():
    out = os.path.join(ROOT, "docs", "BildZwilling_Technische_Beschreibung.pdf")
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=30 * mm,
                            bottomMargin=18 * mm, title=f"BildZwilling {VERSION} – Technische Beschreibung",
                            author="Stefan J. Kaiser DM5CQ / OE8KKS")
    W = A4[0] - 36 * mm
    s = []
    ok = status("umgesetzt")

    # 1 ------------------------------------------------------------------
    s.append(H1("Überblick"))
    s.append(P("BildZwilling findet Fotos, die <b>vollständig identisch</b> sind – unabhängig von Dateiname, Ordner "
               "oder Laufwerk – und verschiebt die Duplikate in einen Archivordner. Endgültig gelöscht wird erst "
               "nach Sichtung und ausdrücklicher Freigabe. Zusätzlich erkennt es dasselbe Bild mit anderen Metadaten "
               "und – als eigene, nie automatisch archivierte Kategorie – <b>ähnliche Bilder</b>."))
    s.append(table([
        ["Eigenschaft", "Umsetzung"],
        ["Plattform", "Windows 10/11 (portable EXE + Kommandozeilen-EXE), macOS 12+ (App), Linux aus dem Quellcode"],
        ["Sprache / GUI", "Python 3.11–3.13, Tkinter/ttk"],
        ["Quellen", "Lokal, USB/externe HDD, NAS (UNC), pCloud Drive, OneDrive, Nextcloud, ownCloud, Seestar-Speicher"],
        ["Erkennung", "Byte-identisch (BLAKE2b-256 + direkter Byte-Vergleich) · gleicher Bildinhalt (Pixel / RAW- "
                      "bzw. FITS-Sensordaten) · ähnlich (dHash, Regler 0–16)"],
        ["Formate", "Alle Dateien vergleichbar; Vorschau/Metadaten für Standardformate, RAW aller großen Hersteller, "
                    "FITS von Smart-Teleskopen (ZWO Seestar u. a.) und Videos (mit ffmpeg)"],
        ["Sicherheit", "Nie automatisch löschen, Prüfung vor jeder Aktion, Journal, Wiederherstellen, Papierkorb"],
        ["Bedienung", "Dunkel / Hell / Hoher Kontrast, große Schrift, Sprachausgabe, Tastatursteuerung"],
        ["Berichte", "CSV (Excel), HTML mit Vorschaubildern, Kommandozeile für NAS/Aufgabenplanung"],
        ["Neu in 2.2", "Neues Info-Fenster · GNU GPL v3 und Haftungsausschluss · nur eine Instanz · "
                       "Sicherung der Einstellungen · unvollständige Archivierungen erkennen · kein Ruhezustand "
                       "während langer Vorgänge · Typprüfung im Build"],
        ["Neu in 2.1", "pCloud mit Zwei-Faktor-Anmeldung · leere Vorschau ohne Auswahl · Großansicht per Klick · "
                       "Platzprüfung · Bedienungsanleitung beider EXE · Gesamt-Prompt"],
        ["Neu in 2.0", "Seestar-Assistent · Cloud direkt (pCloud/OneDrive ohne Download) · Rückgängig (Strg+Z) · "
                       "Bewertungen aus XMP/Lightroom · gedrehte/gespiegelte Kopien · englische Oberfläche"],
    ], [34 * mm, W - 34 * mm]))

    # NEU 2.2 -----------------------------------------------------------
    s.append(H1("Neu in Version 2.2"))
    s.append(P("Umgesetzt wurden alle freigegebenen Vorschläge A1–A6 (Info, Lizenz, Haftung), B1–B6 (Sicherheit), "
               "C1–C7 (Stabilität) und D1–D3 (Qualität, Dokumentation)."))
    s.append(table([
        ["Nr", "Funktion", "Umsetzung", "Status"],
        ["A1", "Neues Info-Fenster", "Eigenes Fenster ohne Farbrand, breiter, mit Abstand: Kopf (Icon, Name, Version, "
                                     "Kurzbeschreibung), zweispaltige Übersicht (Idee, Konzept &amp; Prompt · "
                                     "Umsetzung · Lizenz · Komponenten · Datenordner), kurzer Haftungsausschluss, "
                                     "Knöpfe „Systeminfo kopieren“, „Drittanbieter“, „OK“.", ok],
        ["A2", "Meldungen ohne Farbrand", "Die Art (Info/Warnung/Fehler/Frage) zeigt nur noch das farbige Symbol.", ok],
        ["A3", "GNU GPL v3 oder später", "LICENSE (voller Text), Lizenzkopf in jeder Quelldatei (per Test geprüft), "
                                         "Lizenztext im Programm, CLI --license.", ok],
        ["A4", "Drittanbieter-Lizenzen", "THIRD_PARTY_LICENSES.txt wird beim Build aus den installierten Paketen "
                                         "erzeugt (Übersicht + Volltexte) und in EXE und Portable-Ordner gelegt.", ok],
        ["A5", "Haftungsausschluss", "Kurz im Info-Fenster, ausführlich im Lizenzfenster, in README, Quick-Guide, "
                                     "dieser Beschreibung und einmalig beim ersten Start mit „Gelesen und "
                                     "verstanden“ (gilt je Hauptversion).", ok],
        ["A6", "Copyright aus einer Quelle", "Fenster, Berichte, PDFs, CLI --version und EXE-Eigenschaften lesen "
                                             "dieselbe Zeile; der Name steht genau einmal.", ok],
        ["B1", "Nur eine Instanz", "Dateisperre im Datenordner (verschwindet auch nach Absturz); CLI verschiebt nur, "
                                   "wenn kein Programm läuft.", ok],
        ["B2", "Externe Werkzeuge", "Windows: nur eingestellter Pfad oder Programmordner/„tools“ (kein PATH); "
                                   "Einstellungen zeigen Version und SHA-256.", ok],
        ["B3", "Alle Anmeldungen entfernen", "Knopf im Tab Cloud und unter ⚙ → Wartung.", ok],
        ["B4", "Datensparsames Protokoll", "E-Mail-Adressen, Tokens, Passwörter und Codes werden im Log geschwärzt; "
                                           "Rotation 3 × 1 MB; Systeminfo ohne Benutzernamen.", ok],
        ["B5", "Prüfsummen", "Build erzeugt SHA256SUMS.txt; Code-Signatur bleibt V11.", ok],
        ["B6", "HTML-Bericht", "Content-Security-Policy: nur das eigene Skript (SHA-256), keine Netzzugriffe.", ok],
        ["C1", "Einstellungen sicher speichern", "Atomar mit fsync; vorige Fassung als .bak; beschädigte Datei → "
                                                 "Sicherung bzw. Standardwerte, Hinweis im Protokoll.", ok],
        ["C2", "Kein Ruhezustand", "Während Suche und Archivierung (Programm, Seestar, CLI) bleibt der Rechner wach.",
         ok],
        ["C3", "Sehr große Bilder", "Vorschau-Grenze 600 MP mit klarer Meldung; Speichermangel abgefangen.", ok],
        ["C4", "Lange Windows-Pfade", "\\\\?\\-Präfix für alle Dateizugriffe; Test unter Windows.", ok],
        ["C5", "Unvollständige Archivierung", "Sitzungsanfang/-ende im Journal; beim Start Hinweis mit Angebot "
                                              "zum Zurückholen; CLI meldet sie bei „archive“.", ok],
        ["C6", "Fehler melden", "Fehlerdialog mit „Details kopieren“ (Systeminfo + Ablauf, anonymisiert); "
                                "„Systeminfo kopieren“ im Info-Fenster.", ok],
        ["C7", "Aufräumen", "Cache monatlich bereinigen (nur erreichbare Ordner), Knopf unter ⚙ → Wartung; alte "
                            "Temp-Ordner beim Start löschen.", ok],
        ["R13", "Quellcode öffentlich", "github.com/dm5cq/BildZwilling – Link im Info-Fenster, im Lizenztext, in der "
                                        "Systeminfo und bei CLI --license.", ok],
        ["–", "Releases", "Eine neue Versionsnummer auf main (oder ein Versions-Tag) baut automatisch das Windows-Paket (Programm, "
                          "Kommandozeile, Lizenzen, Quick-Guides, SHA256SUMS) und veröffentlicht es mit den PDFs "
                          "als GitHub-Release.", ok],
        ["D1", "Typprüfung im Build", "Pyright fest in build-exe.bat/build-mac.sh und CI (Windows, macOS, Linux); "
                                      "Testabdeckung in der CI.", ok],
    ], [10 * mm, 40 * mm, W - 73 * mm, 23 * mm]))

    s.append(H1("Lizenz und Haftung"))
    s.append(P("BildZwilling ist freie Software unter der <b>GNU General Public License Version 3 oder später</b> "
               "(SPDX: GPL-3.0-or-later). Jeder darf das Programm nutzen, weitergeben und verändern – "
               "Weitergaben müssen wieder unter der GPL stehen und den Quellcode verfügbar machen."))
    s += bullets([
        "<b>Quellcode:</b> öffentlich unter <b>https://github.com/dm5cq/BildZwilling</b> (auch im Info-Fenster "
        "und im Lizenztext genannt).",
        "<b>Weitergabe der EXE:</b> LICENSE.txt, THIRD_PARTY_LICENSES.txt und SHA256SUMS.txt beilegen (im "
        "Release-Paket bereits enthalten) und auf den Quellcode-Link hinweisen.",
        "<b>Eingebundene Komponenten</b> (Python, Tcl/Tk, Pillow, pillow-heif/libheif, rawpy/LibRaw, NumPy, "
        "ExifRead, Send2Trash, PyInstaller-Startprogramm) stehen unter GPL-verträglichen Lizenzen (PSF, MIT, BSD, "
        "LGPL). ExifTool und FFmpeg werden nicht mitgeliefert.",
        "<b>Haftungsausschluss:</b> Nutzung auf eigene Verantwortung und ohne Gewährleistung. Vor dem Aufräumen eine "
        "Datensicherung anlegen; archivierte Dateien vor dem endgültigen Löschen prüfen. Soweit gesetzlich zulässig "
        "keine Haftung für Datenverlust oder sonstige Schäden (GPL v3, Abschnitte 15 und 16); zwingende gesetzliche "
        "Haftung bleibt unberührt.",
        "Hinweis: Die Texte folgen den üblichen GPL-Vorgaben und sind keine Rechtsberatung; für eine kommerzielle "
        "Weitergabe rechtlich prüfen lassen.",
    ])

    # NEU 2.1 -----------------------------------------------------------
    s.append(H1("Neu in Version 2.1"))
    s.append(table([
        ["Funktion", "Umsetzung", "Status"],
        ["pCloud mit Zwei-Faktor-Anmeldung", "Empfohlen: Anmeldung im Browser (OAuth 2.0, offiziell dokumentiert) – "
                                             "der 2FA-Code wird auf der pCloud-Seite eingegeben, BildZwilling sieht "
                                             "kein Passwort. Alternativ E-Mail/Passwort: verlangt pCloud einen Code, "
                                             "erscheint ein Feld für den Sicherheitscode (App/SMS/Wiederherstellungs"
                                             "code), optional „Diesem Gerät 30 Tage vertrauen“.", ok],
        ["Vorschau ohne Auswahl leer", "Ist keine Datei ausgewählt (oder nur eine Gruppe), wird die Seitenvorschau "
                                       "geleert – im Tab Duplikate und im Seestar-Assistenten.", ok],
        ["Großansicht", "Klick auf das Vorschaubild öffnet es groß (bis 4096 px, 100-%-Zoom, verschieben); "
                        "„SCHLIESSEN“ oder Esc schließt die Großansicht wieder.", ok],
        ["Platzprüfung", "Vor dem Archivieren auf ein anderes Laufwerk wird der freie Speicher geprüft (Programm, "
                         "Seestar-Assistent und Kommandozeile).", ok],
        ["Dokumentation", "Bedienung von BildZwilling.exe und BildZwilling-cli.exe, extrahierter Gesamt-Prompt "
                          "(Anhang und DEV/PROMPT_GESAMT.md), Verbesserungsvorschläge aus Review und Tests.", ok],
        ["Automatische Tests", "Vorlage für GitHub Actions (.github/workflows/tests.yml): Tests auf Windows, macOS "
                               "und Linux bei jedem Push, Windows-EXE als Download.", status("vorbereitet")],
    ], [42 * mm, W - 65 * mm, 23 * mm]))

    # BEDIENUNG -----------------------------------------------------------
    s.append(H1("Bedienung: Welche EXE wofür?"))
    s.append(P("Der Build erzeugt im Ordner <i>Portable</i> zwei Programme. Beide nutzen dieselbe geprüfte Suchlogik, "
               "dieselben Einstellungen (<i>BildZwilling_Daten</i>) und denselben Prüfsummen-Cache."))
    s.append(table([
        ["", "BildZwilling.exe", "BildZwilling-cli.exe"],
        ["Art", "Programm mit Oberfläche (Fenster)", "Kommandozeile (Eingabeaufforderung/PowerShell)"],
        ["Start", "Doppelklick", "in cmd/PowerShell aufrufen oder per Aufgabenplanung"],
        ["Ideal für", "Sichten, Vergleichen, Entscheiden, Seestar-Assistent, Cloud direkt, Archiv freigeben",
         "regelmäßige Berichte, NAS/Server, große Ordner über Nacht, Automatisierung"],
        ["Verschieben", "markierte Dateien nach Bestätigung (auch ähnliche, manuell)",
         "nur identische Duplikate, nur mit --move --yes; ähnliche nie"],
        ["Löschen", "nur im Tab Archiv nach Bestätigung", "nie (nur Auflisten, Rückgängig)"],
        ["Sprache", "⚙ → Darstellung (Deutsch/English)", "--lang de | --lang en"],
    ], [24 * mm, (W - 24 * mm) / 2, (W - 24 * mm) / 2]))

    s.append(H1("Bedienung: BildZwilling.exe"))
    s.append(P("Erster Start", "h2"))
    s += bullets([
        "<b>BildZwilling.exe</b> per Doppelklick starten (keine Installation). Beim ersten Start legt das Programm "
        "neben der EXE den Ordner <i>BildZwilling_Daten</i> an (Einstellungen, Cache, Protokoll). Windows "
        "SmartScreen kann bei unsignierten Programmen warnen: „Weitere Informationen“ → „Trotzdem ausführen“.",
        "Optional <i>exiftool.exe</i> und <i>ffmpeg.exe</i> in den Unterordner <i>tools</i> legen (vollständige "
        "Metadaten, Video-Vorschau).",
        "Beim ersten Start erscheint der Haftungshinweis: „Gelesen und verstanden“ ankreuzen → „Zustimmen und "
        "starten“. Das Programm läuft immer nur einmal; ein zweiter Start meldet das bereits geöffnete Fenster.",
    ])
    s.append(P("Hauptfenster", "h2"))
    s.append(table([
        ["Bereich", "Bedienung"],
        ["Seitenleiste 1 · Bildordner", "„+ Ordner“ fügt Quellen hinzu (lokal, HDD, NAS, Sync-Ordner). „▲ Master“ "
                                        "setzt den gewählten Ordner an die erste Stelle – dort bleiben Originale "
                                        "bevorzugt. „Entfernen“ nimmt Ordner aus der Liste (löscht nichts)."],
        ["Seitenleiste 2 · Archivordner", "„Wählen …“ legt fest, wohin Duplikate verschoben werden; „Öffnen“ zeigt "
                                          "ihn im Explorer. Gleiches Laufwerk wie die Bilder = blitzschnell."],
        ["Seitenleiste 3 · Suche", "Byte-identisch oder + gleicher Bildinhalt; „Ähnliche Bilder“ mit Regler "
                                   "streng↔locker (wirkt nach der Suche sofort) und „auch gedrehte/gespiegelte "
                                   "Kopien“; Optionen für Bilder/Videos, Cloud-Platzhalter, XMP, Paare, Bewertungen; "
                                   "Regel für das Original. „▶ Suche starten (F5)“, „■ Abbrechen“."],
        ["Tab Duplikate", "Gruppenliste (orange = identisch, blau = ähnlich). Filterzeile: Text, Art, Dateityp, "
                          "Sortierung, ◀ ▶ Seiten. Knöpfe: Vergleichen, ★ Als Original, Behalten ⇄ Archiv "
                          "(Leertaste), Regel neu anwenden, CSV, HTML-Bericht, ↶ Rückgängig (Strg+Z), "
                          "➜ Markierte ins Archiv."],
        ["Seitenvorschau", "Zeigt die gewählte Datei; ohne Auswahl leer. <b>Klick auf das Bild</b> öffnet die "
                           "Großansicht; dort Doppelklick/Z = 100 %, Ziehen = verschieben, <b>SCHLIESSEN</b> oder "
                           "Esc = zurück."],
        ["Vergleichsfenster", "Doppelklick/Enter auf eine Datei: beide Bilder nebeneinander, synchroner Zoom, EXIF-"
                              "Tabelle (gelb = Unterschied, „nur Unterschiede“), Byte-/Pixel-Vergleich, „★ Als "
                              "Original behalten“, Bild↑/↓ = nächste Gruppe."],
        ["Tab Seestar-Assistent", "Ordner „MyWorks“ (oder Kopie) wählen, Strenge wählen, „▶ Analysieren“. Liste: "
                                  "Stacks mit Subs, Werte Sterne/FWHM/Form/Hintergrund, rot = Ausschuss mit Grund. "
                                  "Leertaste/„Ausschuss ⇄ Behalten“, „Alle Subs dieses Stacks markieren“, CSV, "
                                  "„➜ Markierte ins Archiv“. Vorschau mit Großansicht wie oben."],
        ["Tab Cloud direkt", "Anbieter wählen, „Anmelden …“ (pCloud: im Browser oder E-Mail/Passwort + 2FA-Code; "
                             "OneDrive: Gerätecode), Cloud-Ordner und Cloud-Archiv eintragen, „▶ Cloud prüfen“. "
                             "Vergleichen lädt nur Vorschaubilder; „➜ In Cloud-Archiv verschieben“, „↶ Letzte "
                             "Cloud-Archivierung rückgängig“."],
        ["Tab Archiv", "Alle archivierten Dateien mit Alter. Mit Original vergleichen, Wiederherstellen, ↶ Letzte "
                       "Archivierung rückgängig, Fällige auswählen (gelb = Aufbewahrungsfrist abgelaufen), "
                       "„Endgültig löschen …“ (Papierkorb; nur wenn das Original noch existiert)."],
        ["Tab Protokoll", "Alle Meldungen farbig; zusätzlich in <i>BildZwilling_Daten/BildZwilling.log</i>."],
        ["⚙ Einstellungen", "Sprache, Farbschema, große Schrift, Sprachausgabe · Ordnerregeln · Bewertungen und "
                            "Lightroom-Katalog · Aufbewahrungsfrist, Papierkorb, versteckte Dateien, Mindestgröße · "
                            "ExifTool/ffmpeg mit Version und SHA-256 · parallele Lesevorgänge, Gruppen pro Seite · "
                            "<b>Wartung</b>: Cache bereinigen/leeren, alle Cloud-Anmeldungen entfernen, Datenordner."],
        ["Info", "Version, Urheber, Lizenz (Lizenztext), Komponenten, Datenordner, Haftungsausschluss; "
                 "„Systeminfo kopieren“ für Fehlermeldungen, „Drittanbieter“ für die Lizenzen der Komponenten."],
    ], [38 * mm, W - 38 * mm]))
    s.append(P("Typischer Ablauf", "h2"))
    s += bullets([
        "Ordner hinzufügen → Archivordner wählen → F5 → Liste nach Ersparnis prüfen → Stichproben im Vergleich "
        "ansehen → „➜ Markierte ins Archiv“ → einige Tage mit den Fotos arbeiten → Tab Archiv → „Fällige auswählen“ "
        "→ „Endgültig löschen …“.",
        "Fehlgriff? <b>Strg+Z</b> bzw. „↶ Rückgängig“ holt die letzte Archivierung vollständig zurück.",
        "Tastatur: Enter = Vergleich · Leertaste = Behalten ⇄ Archiv · F5 = Suche · Strg+F = Filter · Strg+Z = "
        "Rückgängig · Bild↑/↓ = Seite · Esc = Fenster schließen.",
    ])

    s.append(H1("Bedienung: BildZwilling-cli.exe"))
    s.append(P("Die Kommandozeilenversion läuft ohne Fenster – ideal für Berichte über Nacht, ein NAS oder die "
               "Windows-Aufgabenplanung. Aufruf in der Eingabeaufforderung (cmd) oder PowerShell im Ordner "
               "<i>Portable</i>; Hilfe mit <font name='DVM'>BildZwilling-cli.exe --help</font> bzw. "
               "<font name='DVM'>BildZwilling-cli.exe scan --help</font>."))
    s.append(P("Befehl „scan“ – Ordner durchsuchen", "h2"))
    s.append(P("BildZwilling-cli.exe scan ORDNER [ORDNER …] [Optionen]   (der erste Ordner ist der Master)", "code"))
    s.append(table([
        ["Option", "Wirkung"],
        ["--csv DATEI / --html DATEI", "Bericht als CSV (Excel) bzw. HTML mit Vorschaubildern; --no-thumbs = ohne Bilder"],
        ["--pixels", "zusätzlich gleichen Bildinhalt (andere Metadaten) erkennen"],
        ["--similar N", "ähnliche Bilder bis Abstand N (0–16, typisch 6) berichten; --no-rotations = ohne gedrehte"],
        ["--videos · --all-files", "Videos einbeziehen · alle Dateitypen vergleichen"],
        ["--hidden · --online", "versteckte Dateien · Nur-Online-Cloud-Dateien herunterladen und prüfen"],
        ["--min-kb N", "Mindestgröße in KB (Standard 1)"],
        ["--keep-rule R", "Original: first_root (Master) · oldest · newest · shortest_path"],
        ["--rule keep:MUSTER / --rule archive:MUSTER", "Ordnerregel, mehrfach möglich (z. B. --rule archive:WhatsApp)"],
        ["--no-ratings · --lrcat DATEI", "Bewertungen ignorieren · Lightroom-Katalog für Bewertungen"],
        ["--archive ORDNER --move --yes", "identische Duplikate ins Archiv verschieben (nur mit allen drei Angaben; "
                                          "vorher Platzprüfung; ähnliche nie)"],
        ["--no-pairs · --no-sidecars", "Paare nicht zusammenhalten · XMP nicht mitverschieben"],
        ["--no-cache · --workers N", "ohne Prüfsummen-Cache · parallele Lesevorgänge (Standard 4)"],
        ["--exiftool PFAD · --ffmpeg PFAD", "Werkzeuge für HTML-Vorschauen/Metadaten"],
        ["-q / --quiet", "nur Ergebnis ausgeben (für Aufgabenplanung)"],
    ], [58 * mm, W - 58 * mm]))
    s.append(P("Befehl „archive“ – Archiv verwalten", "h2"))
    s.append(table([
        ["Aufruf", "Wirkung"],
        ["archive ORDNER", "alle archivierten Dateien mit Alter, Größe und „Original vorhanden“ auflisten"],
        ["archive ORDNER --older-than 30 [--csv DATEI]", "nur Einträge älter als 30 Tage (Aufbewahrung)"],
        ["archive ORDNER --undo-last --yes", "letzte Archivierung komplett zurückholen (ohne --yes nur Anzeige)"],
    ], [72 * mm, W - 72 * mm]))
    s.append(P("Weitere Aufrufe: <font name='DVM'>--version</font> (Version, Copyright, Lizenz) und "
               "<font name='DVM'>--license</font> (Lizenz- und Haftungshinweis). Verschieben und Rückgängig sind "
               "gesperrt, solange BildZwilling.exe läuft (Rückgabewert 2)."))
    s.append(P("Allgemein: <font name='DVM'>--lang de|en</font> vor dem Befehl stellt die Ausgabesprache ein. "
               "Rückgabewerte: <b>0</b> keine Duplikate · <b>1</b> Duplikate gefunden · <b>2</b> Fehler · "
               "<b>3</b> abgebrochen (für Skripte und Aufgabenplanung)."))
    s.append(P("Beispiele", "h2"))
    s.append(P("REM Bericht über zwei Quellen (Master = D:\\Fotos)<br/>"
               "BildZwilling-cli.exe scan D:\\Fotos P:\\Bilder --csv bericht.csv --html bericht.html<br/>"
               "REM ähnliche Bilder und Videos mitberichten<br/>"
               "BildZwilling-cli.exe scan D:\\Fotos --similar 6 --videos --html bericht.html<br/>"
               "REM WhatsApp-Kopien automatisch archivieren<br/>"
               "BildZwilling-cli.exe scan D:\\Fotos --rule archive:WhatsApp --archive D:\\Archiv --move --yes<br/>"
               "REM Bewertungen aus Lightroom, englische Ausgabe<br/>"
               "BildZwilling-cli.exe --lang en scan D:\\Fotos --lrcat D:\\LR\\Katalog.lrcat --html report.html<br/>"
               "REM Aufbewahrung prüfen / Rückgängig<br/>"
               "BildZwilling-cli.exe archive D:\\Archiv --older-than 30 --csv faellig.csv<br/>"
               "BildZwilling-cli.exe archive D:\\Archiv --undo-last --yes", "code"))
    s.append(P("Wöchentlicher Bericht über die Windows-Aufgabenplanung:", "p"))
    s.append(P("schtasks /Create /TN \"BildZwilling Bericht\" /SC WEEKLY /D SUN /ST 03:00 /TR "
               "\"C:\\Tools\\BildZwilling-cli.exe scan D:\\Fotos --html D:\\Berichte\\duplikate.html -q\"", "code"))
    s.append(P("Auswertung im Skript (cmd): <font name='DVM'>if %ERRORLEVEL%==1 echo Duplikate gefunden</font>. "
               "Ausgaben mit Umlauten: in PowerShell ggf. <font name='DVM'>chcp 65001</font>."))

    # NEU 2.0 -----------------------------------------------------------
    s.append(H1("Neu in Version 2.0"))
    s.append(table([
        ["Nr", "Funktion", "Umsetzung", "Status"],
        ["V12", "Seestar-Assistent", "Einzelbilder (Subs) werden ihrem Stack zugeordnet (Objekt, Belichtung, Filter, "
                                     "Aufnahmesitzung). Ausschuss wird über Sternanzahl, Sterngröße (FWHM), Sternform "
                                     "(Elongation) und Himmelshelligkeit erkannt – relativ zum Median der Sitzung. "
                                     "Archivieren inkl. .jpg/_thn.jpg, rückgängig möglich (Kapitel „Seestar-Assistent“)", ok],
        ["V13", "Cloud direkt", "pCloud (Europa/USA) und OneDrive über die offiziellen Schnittstellen: Duplikate über "
                                "Server-Prüfsummen, ohne Download; Verschieben innerhalb der Cloud in einen "
                                "Archivordner; Journal und Rückgängig (Kapitel „Cloud direkt“)", ok],
        ["V14", "Rückgängig", "Jede Archivierung ist eine Sitzung im Journal; „↶ Rückgängig“ (Strg+Z) holt die "
                              "letzte komplett zurück – auch Seestar- und Cloud-Archivierungen; CLI: "
                              "archive --undo-last --yes", ok],
        ["V15", "Bewertungen", "Sterne, Farbmarkierung und Flagge aus XMP-Begleitdateien, eingebettetem XMP und "
                               "optional dem Lightroom-Classic-Katalog (nur lesend). Bewertete bevorzugt behalten, "
                               "abgelehnte bevorzugt archivieren; Anzeige ★ in der Liste", ok],
        ["V16", "Gedrehte/gespiegelte Kopien", "8 Ähnlichkeits-Hashes je Bild (0°, 90°, 180°, 270°, gespiegelt, "
                                               "transponiert); Seitenverhältnis-Prüfung berücksichtigt die Drehung; "
                                               "Gruppen mit Hinweis „gedreht/gespiegelt“", ok],
        ["V17", "Englische Oberfläche", "Alle Texte über ein Wörterbuch (490 Einträge, automatisch auf Vollständigkeit "
                                        "und Platzhalter geprüft); Umschalten unter ⚙ → Darstellung; Quick-Guide "
                                        "auch auf Englisch; CLI: --lang en", ok],
        ["neu", "Copyright", "Name nur noch einmal: „© 2026 Stefan J. Kaiser DM5CQ / OE8KKS · Idee, Konzept & "
                             "Prompt · Umsetzung: Claude (Anthropic)“", ok],
    ], [10 * mm, 30 * mm, W - 63 * mm, 23 * mm]))

    # 2 ------------------------------------------------------------------
    s.append(H1("Funktionen aus Version 1.5"))
    s.append(table([
        ["Nr", "Funktion", "Umsetzung", "Status"],
        ["V1", "Ähnliche Bilder", "dHash 64 Bit (EXIF-Ausrichtung berücksichtigt), BK-Baum-Suche, Regler „streng ↔ "
                                  "locker“ gruppiert ohne neue Suche um; je identischer Gruppe nur das Original als "
                                  "Vertreter; Kontrast- und Seitenverhältnis-Prüfung gegen Fehltreffer; bestes Bild "
                                  "(höchste Auflösung) zuerst; <b>nie vorab zum Archivieren markiert</b>", ok],
        ["V2", "RAW+JPEG-Paare", "Paare (RAW/FITS ↔ JPG/HEIF, gleicher Name, gleicher Ordner) werden nie getrennt: "
                                 "Partner wandert mit, wenn auch das Original ein Paar ist, sonst wird das Duplikat "
                                 "mit Begründung übersprungen", ok],
        ["V3", "Barrierefreiheit", "Farbschemata Dunkel/Hell/Hoher Kontrast, große Schrift, Sprachausgabe (Windows "
                                   "System.Speech, macOS „say“) für Status, Auswahl und Prüfergebnisse", ok],
        ["V4", "Große Bibliotheken", "Seitenweise Liste (Gruppen pro Seite einstellbar), Filter nach Text, Art, "
                                     "Dateityp; Sortierung nach Ersparnis, Größe, Anzahl, Name, Ordner", ok],
        ["V5", "Ordnerregeln", "„immer behalten“ / „immer archivieren“ per Ordnerpfad oder Textmuster "
                               "(z. B. „WhatsApp“, „Fotos/Best“); „behalten“ gewinnt; eine Datei bleibt immer", ok],
        ["V6", "Archiv-Aufbewahrung", "Einträge älter als X Tage gelb markiert, „Fällige auswählen“, Hinweis beim "
                                      "Start; gelöscht wird weiterhin nur nach Bestätigung", ok],
        ["V7", "ExifTool", "Automatisch erkannt (neben EXE, Ordner tools, PATH) oder Pfad in den Einstellungen; "
                           "alle Metadaten inkl. MakerNotes und Video", ok],
        ["V8", "Videos", "MP4, MOV, M4V, AVI, MKV, MTS, 3GP, WEBM, Insta360 INSV/LRV, GoPro 360; Byte-Vergleich; "
                         "Vorschaubild über ffmpeg (optional)", ok],
        ["V9", "Kommandozeile", "BildZwilling-cli.exe: scan / archive, Berichte, Verschieben nur mit --yes; "
                                "ähnliche Bilder werden nie verschoben", ok],
        ["V10", "HTML-Bericht", "Eine Datei mit eingebetteten Vorschaubildern, Suche und Filter – ohne Internet, "
                                "auf Tablet/zweitem Rechner nutzbar", ok],
        ["neu", "Fenster im App-Stil", "Titelleiste grau mit weißer Schrift (Windows 11 exakt im App-Grau, "
                                       "Windows 10 dunkler Modus); alle Meldungen, Fragen und der Info-Dialog als "
                                       "eigene graue Fenster mit App-Icon; bei Löschfragen ist „Nein“ vorausgewählt", ok],
        ["neu", "Smart-Teleskope", "FITS von ZWO Seestar S50/S30 (Einzelbilder & Stacks) und anderen FITS-"
                                   "Teleskopen: Vorschau mit Entbayerung + Auto-Stretch, Header als Metadaten, "
                                   "Datenprüfsumme unabhängig vom Header, FIT+JPG als Paar", ok],
    ], [10 * mm, 30 * mm, W - 63 * mm, 23 * mm]))

    # 3 ------------------------------------------------------------------
    s.append(H1("Bauen &amp; Starten"))
    s.append(P("<b>Windows:</b> Python 3.12 (64 Bit) von python.org installieren (Optionen „py launcher“ und „Add to "
               "PATH“), dann <b>build-exe.bat</b> doppelklicken. Das Skript legt <i>.venv</i> an, installiert die Pakete, "
               "führt alle Tests und die Typprüfung (Pyright) aus – bei Fehlern Abbruch –, erstellt die Lizenzliste und "
               "erzeugt in <i>Portable</i>:"))
    s += bullets(["<b>BildZwilling.exe</b> – die Anwendung (portabel, eine Datei)",
                  "<b>BildZwilling-cli.exe</b> – Kommandozeilenversion (Kapitel 5)",
                  "<b>tools\\</b> – Ablage für optionales <i>exiftool.exe</i> und <i>ffmpeg.exe</i> (mit LIESMICH)",
                  "den Quick-Guide als PDF, <b>LICENSE.txt</b>, <b>THIRD_PARTY_LICENSES.txt</b> und "
                  "<b>SHA256SUMS.txt</b> (Prüfsummen der EXE-Dateien)"])
    s.append(P("<b>Fertiges Paket ohne eigenen Build:</b> unter <i>github.com/dm5cq/BildZwilling/releases</i> "
               "das ZIP „BildZwilling-&lt;Version&gt;-Windows“ herunterladen, entpacken, starten. Die Prüfsummen "
               "stehen in SHA256SUMS.txt. Neue Releases entstehen automatisch: Sobald auf <i>main</i> eine neue "
               "Versionsnummer (VERSION in bildzwilling/__init__.py) liegt und alle Tests bestehen, wird das Release "
               "„v&lt;Version&gt;“ mit Paket und PDFs erstellt (alternativ per Versions-Tag)."))
    s.append(P("<b>macOS:</b> <font name='DVM'>./build-mac.sh</font> auf dem Mac → <i>Portable/BildZwilling.app</i> "
               "und <i>BildZwilling-cli</i>. <b>Ohne Build:</b> <font name='DVM'>python main.py</font> bzw. "
               "<font name='DVM'>python cli.py</font>."))
    s.append(table([
        ["Paket / Werkzeug", "Zweck", "ohne"],
        ["Pillow ≥ 11.3", "Standardformate, Vorschau, Pixel- und Ähnlichkeitsprüfung", "erforderlich"],
        ["numpy", "FITS (Seestar), RAW-Sensordaten", "FITS nur Byte-Vergleich"],
        ["rawpy (LibRaw)", "RAW-Vorschau und -Sensordaten", "eingebettetes JPEG"],
        ["pillow-heif", "HEIC/HEIF", "HEIC nur Byte-Vergleich"],
        ["ExifRead", "EXIF inkl. RAW", "Pillow-EXIF"],
        ["Send2Trash", "Löschen in den Papierkorb", "direktes Löschen (doppelte Bestätigung)"],
        ["ExifTool (extern, optional)", "alle Metadaten, MakerNotes, Video", "eingebauter Leser"],
        ["ffmpeg (extern, optional)", "Video-Vorschaubild", "Hinweis statt Vorschau"],
    ], [42 * mm, 74 * mm, W - 116 * mm]))

    # 4 ------------------------------------------------------------------
    s.append(H1("Architektur"))
    s.append(P("Logik (<i>bildzwilling.core</i>) und Oberfläche (<i>bildzwilling.gui</i>) sind strikt getrennt; die "
               "Kommandozeile nutzt dieselbe getestete Engine. Plattformspezifisches ist in <i>fsutil.py</i> und "
               "<i>tools.py</i> gekapselt."))
    s.append(table([
        ["Modul", "Aufgabe"],
        ["core/scanner.py", "Einlesen, Gruppierung, Prüfsummen (parallel), Union-Find, Original-Regeln, Ähnlichkeits-Stufe"],
        ["core/similar.py", "dHash, BK-Baum, Gruppenbildung ähnlicher Bilder"],
        ["core/plan.py", "Archivierungsplan: Original je Datei, RAW+JPEG/FIT+JPG-Paare"],
        ["core/rules.py", "Ordnerregeln"],
        ["core/archive.py", "Prüfen, Verschieben (atomar bzw. Kopieren+Prüfen), Journal, Wiederherstellen, Löschen"],
        ["core/fits.py", "FITS-Leser (Header, Daten, Entbayerung, Auto-Stretch, Datenprüfsumme)"],
        ["core/imaging.py · exifinfo.py", "Vorschau (Pillow/rawpy/FITS/ffmpeg), Pixelprüfsumme, Metadaten"],
        ["core/tools.py", "ExifTool und ffmpeg finden und sicher aufrufen"],
        ["core/htmlreport.py · report.py", "HTML-Bericht mit Vorschaubildern, CSV"],
        ["core/hashcache.py · settings.py · fsutil.py", "Cache (SQLite), portable Einstellungen, Pfad-Hilfen"],
        ["cli.py", "Kommandozeile"],
        ["gui/app.py · compare.py", "Hauptfenster (Filter, Seiten, Regler, Archiv) und Vergleichsfenster"],
        ["gui/settings_dialog.py · theme.py · speech.py", "Einstellungen, Farbschemata, Sprachausgabe"],
        ["gui/dialogs.py · winstyle.py", "Eigene Meldungsfenster mit App-Icon, graue Titelleiste (Windows)"],
    ], [58 * mm, W - 58 * mm]))

    # 5 ------------------------------------------------------------------
    s.append(H1("So wird ein Duplikat erkannt"))
    s.append(table([
        ["Nr", "Verfahren", "Wirkung"],
        ["1", "Rekursives Einlesen ohne Symlinks/Junctions, Schleifenschutz; System-, Papierkorb-, NAS-Thumbnail- und "
              "Archivordner ausgelassen; Nur-Online-Dateien standardmäßig übersprungen", "keine Doppelzählung"],
        ["2", "Gruppierung nach exakter Dateigröße", "> 95 % fallen weg"],
        ["3", "BLAKE2b über Größe + erste/letzte 64 KB", "128 KB je Kandidat"],
        ["4", "Vollständige BLAKE2b-256-Prüfsumme (Cache)", "„völlig identisch“"],
        ["5", "<i>Bildinhalt:</i> gleiche Maße → Prüfsumme über Pixel bzw. RAW-/FITS-Daten", "andere Metadaten"],
        ["6", "<i>Ähnlich:</i> dHash je Bild (Cache), BK-Baum-Suche bis Abstand N, Seitenverhältnis ±4 %",
         "verkleinert/neu komprimiert"],
        ["7", "Vor dem Verschieben: Größe/Zeitstempel prüfen und <b>Byte für Byte</b> (bzw. Pixel) mit dem Original "
              "vergleichen; ähnliche nur nach Ihrer Markierung", "absolute Sicherheit"],
    ], [10 * mm, W - 58 * mm, 48 * mm]))
    s.append(P("Gemessen: 1.800 Dateien in 0,2 s (Byte), 0,8 s (Pixel). Mit Ähnlichkeit: 1.650 Bilder in 1,2 s, "
               "Wiederholung mit Cache 0,3 s; Regler-Neugruppierung 0,01–0,5 s; bei Abstand 6 exakt die 150 "
               "eingebauten verkleinerten Kopien gefunden. Auf Cloud/NAS bestimmt die Leserate die Dauer."))

    # 6 ------------------------------------------------------------------
    s.append(H1("Sicherheitskonzept Archiv"))
    s += bullets([
        "<b>Nie direkt löschen.</b> Verschieben in <i>Archiv/&lt;Quellordner&gt;_&lt;Kennung&gt;/…</i>, Namenskonflikte "
        "→ „(1)“. Gleiches Laufwerk: atomares Umbenennen; sonst Kopie → Prüfung → erst dann Quelle entfernen.",
        "<b>Journal</b> (append-only) im Archiv; Wiederherstellen überschreibt nie; Journal-Pfade außerhalb des "
        "Archivs werden abgelehnt.",
        "<b>Endgültig löschen</b> nur aus dem Archiv, nur bestätigt und nur, wenn das Original noch existiert. "
        "Die Aufbewahrungsfrist schlägt nur vor – sie löscht nie selbst.",
        "<b>Ähnliche Bilder</b> sind nie vorab markiert, werden blau dargestellt, im Bestätigungsdialog gesondert "
        "gewarnt und von der Kommandozeile nie verschoben.",
        "<b>Paare</b> (RAW/FITS + JPG/HEIF) und <b>Begleitdateien</b> (XMP, PP3, DOP) bleiben zusammen und sind mit "
        "der Hauptdatei wiederherstellbar.",
        "<b>Ordnerregeln</b> können nie alle Dateien einer Gruppe archivieren.",
    ])

    # 7 ------------------------------------------------------------------
    s.append(H1("Formate"))
    s.append(P("Kameras (RAW)", "h2"))
    s.append(table([
        ["Hersteller", "Endungen", "Hinweis"],
        ["Fujifilm", ".RAF", "EXIF über eingebettetes JPEG"],
        ["Nikon", ".NEF, .NRW", ""],
        ["Canon", ".CR3, .CR2, .CRW", "CR3-EXIF über CMT-Boxen"],
        ["Panasonic / Lumix", ".RW2, .RAW", ""],
        ["OM System / Olympus", ".ORF, .ORI", ""],
        ["Leica", ".DNG, .RWL", ""],
        ["Hasselblad", ".3FR, .FFF", "bis 600 MP"],
        ["DJI", ".DNG", "Drohnen, Osmo"],
        ["Insta360", ".DNG, .INSP", ".INSP = JPEG-basiert"],
        ["weitere", ".ARW/.SRF/.SR2, .PEF, .SRW, .X3F, .IIQ, .MOS, .MEF, .DCR, .KDC, .MRW, .ERF", ""],
    ], [36 * mm, 76 * mm, W - 112 * mm]))
    s.append(P("Smart-Teleskope", "h2"))
    s.append(table([
        ["Gerät / Datei", "Inhalt", "Verhalten in BildZwilling"],
        ["ZWO Seestar S50/S30 – Einzelbilder (Ordner „… -sub“, .fit)", "16 Bit, Bayer-Mosaik, BAYERPAT im Header",
         "Superpixel-Entbayerung + Auto-Stretch; Header (OBJECT, EXPTIME, GAIN, CCD-TEMP …) als Metadaten"],
        ["ZWO Seestar – Stack (Stacked_….fit)", "16 Bit RGB (3 Ebenen), bereits entbayert",
         "RGB-Vorschau mit Auto-Stretch; BAYERPAT wird ignoriert"],
        ["Seestar – .jpg / _thn.jpg", "Vorschau/Thumbnail zur FIT", "normales Bild; FIT+JPG gilt als Paar"],
        ["Andere FITS-Teleskope (z. B. DWARF)", "FITS 8/16/32 Bit, float, 1 oder 3 Ebenen", "wie oben"],
        ["Komprimiertes FITS (.fz), PixInsight .xisf", "–", "nur Byte-Vergleich"],
    ], [52 * mm, 44 * mm, W - 96 * mm]))
    s.append(P("Die Datenprüfsumme eines FITS umfasst nur Geometrie und Bilddaten. Dasselbe Einzelbild wird daher "
               "auch erkannt, wenn ein Programm den Header geändert hat (Modus „gleicher Bildinhalt“). Hinweis: "
               "Laut Anwenderberichten passt bei der Seestar S30 das BAYERPAT im Header nicht zum Sensor – dann sind "
               "nur die Farben der <i>Vorschau</i> von Einzelbildern vertauscht; die Duplikatprüfung ist davon "
               "nicht betroffen."))
    s.append(P("<b>Videos</b> (Option „Videos einbeziehen“): .MP4, .MOV, .M4V, .AVI, .MKV, .MTS/.M2TS, .3GP, .WMV, "
               ".WEBM, Insta360 .INSV/.LRV, GoPro .360 – Byte-Vergleich, Vorschau mit ffmpeg, Metadaten mit ExifTool."))

    # 8 ------------------------------------------------------------------
    s.append(H1("Cloud- und Netzlaufwerke"))
    s.append(table([
        ["Quelle", "Hinweise"],
        ["pCloud Drive", "Virtuelles Laufwerk; Lesen = Streaming. Archiv auf P: → schnelles Umbenennen."],
        ["OneDrive / Nextcloud / ownCloud", "„Nur online“-Dateien werden erkannt und standardmäßig ausgelassen. "
                                            "Verschieben im Sync-Ordner synchronisiert der Client."],
        ["NAS / Netzlaufwerk", "UNC-Pfade; Synology @eaDir/#recycle ausgelassen. Ideal für die Kommandozeile."],
        ["Seestar (USB-Speicher)", "Am besten zuerst auf den PC kopieren und dort prüfen."],
        ["Externe HDD", "„Parallele Lesevorgänge“ in den Einstellungen auf 1–2 stellen."],
    ], [48 * mm, W - 48 * mm]))

    # Seestar-Assistent -----------------------------------------------
    s.append(H1("Seestar-Assistent"))
    s.append(P("Die Seestar legt je Objekt zwei Ordner an: <i>&lt;Objekt&gt;</i> mit den gestackten Bildern "
               "(<i>Stacked_…fit</i> + .jpg) und <i>&lt;Objekt&gt;_sub</i> bzw. <i>-sub</i> mit den Einzelbildern "
               "(<i>Light_&lt;Objekt&gt;_&lt;Belichtung&gt;s_&lt;Filter&gt;_&lt;Datum-Zeit&gt;.fit</i> + .jpg + _thn.jpg). "
               "Der Assistent liest Namen und FITS-Kopfzeilen (OBJECT, EXPTIME, FILTER, DATE-OBS, STACKCNT)."))
    s.append(table([
        ["Schritt", "Verfahren"],
        ["Zuordnung", "Subs gleicher Aufnahme (Objekt, Belichtung, Filter) werden in Sitzungen geteilt (Lücke > 30 min). "
                      "Jede Sitzung gehört zum zeitlich passenden Stack; Abweichungen zur Anzahl im Header sind sichtbar. "
                      "Subs ohne Stack erscheinen unter „ohne passenden Stack“."],
        ["Sterne", "Lokale Maxima über Hintergrund + 5 σ auf dem 2×2-gebinnten Bild; Hotpixel (ohne Nachbarn) werden "
                   "ignoriert."],
        ["FWHM / Form", "Für bis zu 40 helle, nicht gesättigte Sterne: zweite Momente in voller Auflösung → "
                        "FWHM (Schärfe) und Achsenverhältnis (1,0 = rund)."],
        ["Hintergrund", "Median des Bildes (Wolken, Dämmerung, Mond, Streulicht)."],
        ["Bewertung", "Relativ zum Median der Sitzung (ab 5 Subs). Strenge „normal“: Sterne &lt; 50 %, FWHM &gt; 1,5×, "
                      "Form &gt; 1,3× (mind. 1,25), Hintergrund &gt; Median + 3,5 σ. „locker“/„streng“ verschieben die "
                      "Grenzen. Begründung je Sub in der Liste."],
        ["Speicher sparen", "Ausschuss archivieren (inkl. .jpg und _thn.jpg) oder alle Subs eines fertigen Stacks "
                            "markieren. Alles bleibt im Archiv bis zur Freigabe; Rückgängig möglich."],
    ], [32 * mm, W - 32 * mm]))
    s.append(P("Gemessen an simulierten Seestar-Einzelbildern (1080×1920, Bayer GRBG): runde Sterne Form 1,02, "
               "Nachführfehler 2,8, Unschärfe FWHM 7,3 statt 3,0 px; 0,03 s je Bild. Wolken, Nachführfehler und "
               "Unschärfe wurden im Test korrekt erkannt, gute Subs nicht verworfen. <b>Hinweis:</b> Die Grenzwerte "
               "sind Erfahrungswerte – bitte die Vorschläge stichprobenartig in der Vorschau prüfen."))

    # Cloud direkt ------------------------------------------------------
    s.append(H1("Cloud direkt (pCloud, OneDrive)"))
    s.append(P("Statt über den Sync-Ordner (der bei „nur online“-Dateien alles herunterladen müsste) fragt BildZwilling "
               "die Prüfsummen direkt beim Anbieter ab. Es werden nur Dateilisten und Prüfsummen übertragen – bei "
               "Bedarf kleine Vorschaubilder."))
    s.append(table([
        ["", "pCloud", "OneDrive"],
        ["Anmeldung", "a) im Browser per OAuth 2.0 (empfohlen, funktioniert mit 2FA; eigene pCloud-App nötig) · "
                      "b) E-Mail + Passwort per HTTPS, bei 2FA anschließend Sicherheitscode; gespeichert wird nur "
                      "das Token", "Gerätecode-Anmeldung im Browser; eigene App-Registrierung (Client-ID) nötig"],
        ["Vorauswahl", "Größe + 64-Bit-Inhalts-Hash aus der Ordnerliste", "Größe + quickXorHash aus der Ordnerliste"],
        ["Bestätigung", "SHA-256 (Europa) bzw. SHA-1 (USA) per checksumfile", "quickXorHash (laut Microsoft der einzige "
                        "für privat und geschäftlich garantierte Hash)"],
        ["Verschieben", "renamefile in den Archivordner; Zielname wird vorher geprüft (nie überschreiben)",
         "PATCH parentReference; bei Namenskonflikt „Datei (1)“"],
        ["Vor jedem Verschieben", "Duplikat und Original neu abfragen (existiert, Größe, Hash); pCloud zusätzlich SHA",
         "Duplikat und Original neu abfragen (existiert, Größe, Hash)"],
    ], [30 * mm, (W - 30 * mm) / 2, (W - 30 * mm) / 2]))
    s.append(P("pCloud mit Zwei-Faktor-Anmeldung", "h2"))
    s += bullets([
        "<b>Empfohlen – Anmeldung im Browser (OAuth 2.0):</b> einmalig unter docs.pcloud.com → „My applications“ "
        "eine eigene App anlegen (kostenlos) und Client-ID sowie Client-Secret im Anmeldedialog eintragen. "
        "„1. Anmeldeseite öffnen“ → bei pCloud anmelden, 2FA-Code eingeben, „Zulassen“ → den angezeigten Code "
        "in BildZwilling einfügen → „3. Anmelden“. Der Server (Europa/USA) wird automatisch ermittelt. "
        "BildZwilling sieht weder Passwort noch 2FA-Code. Das Token gilt, bis die App bei pCloud entfernt wird.",
        "<b>Alternativ – E-Mail und Passwort:</b> Ist 2FA aktiv, meldet pCloud nach dem ersten Schritt einen Code-"
        "Bedarf; BildZwilling zeigt dann ein Feld für den Sicherheitscode (Authenticator-App, SMS oder "
        "Wiederherstellungscode) und optional „Diesem Gerät 30 Tage vertrauen“. Hinweis: Dieser zweite Schritt "
        "ist in der öffentlichen pCloud-Dokumentation nicht beschrieben; sollte pCloud ihn ändern, bleibt die "
        "Browser-Anmeldung als offizieller Weg.",
        "Client-Secret und Token werden nur mit „Anmeldung merken“ und nur unter Windows verschlüsselt (DPAPI) "
        "gespeichert. Gespeicherte Tokens werden ausschließlich an api.pcloud.com bzw. eapi.pcloud.com gesendet.",
    ])
    s.append(P("OneDrive: App-Registrierung (einmalig, kostenlos)", "h2"))
    s += bullets([
        "portal.azure.com → „App-Registrierungen“ → „Neue Registrierung“, Kontotyp „Konten in beliebigen "
        "Organisationen und persönliche Microsoft-Konten“.",
        "„Authentifizierung“ → „Öffentliche Clientflows zulassen“ = Ja. „API-Berechtigungen“: Microsoft Graph "
        "(delegiert) Files.ReadWrite, User.Read, offline_access.",
        "„Anwendungs-ID (Client)“ im Tab „Cloud direkt“ eintragen → „Anmelden …“ → Code im Browser eingeben.",
    ])
    s.append(P("Sicherheit", "h2"))
    s += bullets([
        "Nur HTTPS (unverschlüsselte Adressen werden abgelehnt); bei Weiterleitungen auf andere Server (z. B. CDN "
        "für Vorschaubilder) werden Anmeldedaten entfernt.",
        "Passwörter werden nie gespeichert. Das Token nur auf Wunsch („Anmeldung merken“) und nur unter Windows, "
        "verschlüsselt mit DPAPI (nur derselbe Windows-Benutzer kann es lesen).",
        "Cloud-Journal lokal (<i>cloud_journal.jsonl</i>); Rückgängig verschiebt zurück in den Ursprungsordner.",
        "Endgültiges Löschen erfolgt bewusst über den Papierkorb des Anbieters (Weboberfläche) – BildZwilling löscht "
        "in der Cloud nichts.",
        "Hinweis OneDrive: quickXorHash ist keine kryptografische Prüfsumme. Zusammen mit identischer Größe ist ein "
        "Fehltreffer extrem unwahrscheinlich; da nur verschoben (nicht gelöscht) wird, bleibt er jederzeit korrigierbar.",
    ])

    # 10 -----------------------------------------------------------------
    s.append(H1("Dateien der Anwendung"))
    s.append(table([
        ["Datei", "Ort", "Inhalt"],
        ["settings.json (+ .bak)", "BildZwilling_Daten (neben EXE)*", "Ordner, Optionen, Regeln, Darstellung; "
                                                                       "vorige Fassung als Sicherung"],
        ["BildZwilling.lock", "BildZwilling_Daten", "Sperre „nur eine Instanz“ (vom System gehalten)"],
        ["cloud_tokens.dat", "BildZwilling_Daten", "nur mit „Anmeldung merken“, DPAPI-verschlüsselt"],
        ["hashcache.sqlite", "BildZwilling_Daten", "Prüfsummen, Bildmaße, Ähnlichkeits-Hashes"],
        ["BildZwilling.log / crash.log", "BildZwilling_Daten", "Protokoll (3 × 1 MB) / Absturzdetails"],
        ["_BildZwilling_Journal.jsonl", "Archivordner", "Alle Archiv-Aktionen inkl. Sitzungsanfang/-ende"],
        ["LICENSE, THIRD_PARTY_LICENSES.txt", "Projekt, EXE, Portable", "Lizenztexte (GPL v3, Komponenten)"],
    ], [46 * mm, 50 * mm, W - 96 * mm]))
    s.append(P("* Schreibgeschützter EXE-Ordner → %APPDATA%\\BildZwilling bzw. ~/Library/Application Support/BildZwilling.",
               "td"))

    # 11 -----------------------------------------------------------------
    s.append(PageBreak())
    s.append(H1("Code-Review 2.2: Sicherheit, Stabilität, Funktion"))
    s.append(P("Alle neuen und geänderten Teile wurden durchgesehen und getestet. Neu ist die Typprüfung über das "
               "ganze Projekt für Windows, macOS und Linux – sie hat zwei echte Fehler gefunden (T19, T20)."))
    s.append(table([
        ["Nr", "Bereich", "Befund / Risiko", "Maßnahme", "Status"],
        ["S19", "Sicherheit", "Gleichzeitig laufende Instanzen könnten Journal/Cache stören", "Dateisperre (B1); "
                                                                                             "CLI-Verschieben gesperrt",
         status("behoben")],
        ["S20", "Sicherheit", "Windows: exiftool.exe/ffmpeg.exe aus dem PATH könnte untergeschoben sein",
         "nur eingestellter Pfad/Programmordner; SHA-256 sichtbar (B2)", status("behoben")],
        ["S21", "Datenschutz", "E-Mail-Adresse der Cloud-Anmeldung stand im Protokoll", "Schwärzung im Log (B4)",
         status("behoben")],
        ["S22", "Sicherheit", "HTML-Bericht ohne Inhaltsrichtlinie", "CSP mit Skript-Prüfsumme (B6)",
         status("behoben")],
        ["S23", "Sicherheit", "Keine Prüfsummen für die Weitergabe", "SHA256SUMS.txt; Signatur weiter offen (V11)",
         status("teilweise")],
        ["D17", "Datenverlust", "Absturz/Stromausfall während Archivierung blieb unbemerkt", "Sitzungsstatus, Hinweis "
                                                                                             "+ Zurückholen (C5)",
         status("behoben")],
        ["D18", "Datenverlust", "Beschädigte settings.json → alle Einstellungen weg", "Sicherung .bak + "
                                                                                     "Wiederherstellung (C1)",
         status("behoben")],
        ["T19", "Stabilität", "Seestar: Fehlerzähler überschrieb die Methode „_failed“ – nach einer Archivierung "
                              "hätte die nächste fehlgeschlagene Analyse einen Absturz ausgelöst (von der "
                              "Typprüfung gefunden)", "eigener Zähler; Test", status("behoben")],
        ["T20", "Stabilität", "Cloud-Vergleich: nach Abmelden während des Ladens Zugriff auf fehlende Anmeldung "
                              "(von der Typprüfung gefunden)", "Prüfung mit klarer Meldung", status("behoben")],
        ["T21", "Stabilität", "Ruhezustand unterbricht lange Suchen auf Netzlaufwerken", "keep_awake (C2)",
         status("behoben")],
        ["T22", "Stabilität", "Riesige Bilder → Speicherüberlauf in der Vorschau", "Grenze + Meldung (C3)",
         status("behoben")],
        ["F24", "Funktion", "Info-Fenster unübersichtlich, Text gequetscht, blauer Rand", "neues Fenster (A1/A2)",
         status("behoben")],
        ["F25", "Funktion", "Lizenz und Haftung fehlten", "GPL v3, Haftungsausschluss (A3–A5)", status("umgesetzt")],
        ["F26", "Funktion", "Fehlermeldungen schwer weiterzugeben", "„Details kopieren“, „Systeminfo kopieren“ (C6)",
         status("umgesetzt")],
    ], [11 * mm, 24 * mm, 56 * mm, W - 112 * mm, 21 * mm]))
    s.append(P("Stand der Vorschläge aus dem Review 2.1", "h2"))
    s.append(P("Umgesetzt: R1 (Cache bereinigen), R3 (unvollständige Sitzungen), R5 (Typprüfung im Build), "
               "R8 (Temp aufräumen), R9 (Details kopieren), Q1 (CI inkl. Typprüfung), Q7 (Abdeckung wird in der CI "
               "gemessen; Zielwert 85 % noch festzulegen). Offen: R2 Journal verdichten, R4 app.py aufteilen, "
               "R6 Vorschau-Cache, R7 Sprachausgabe-Prozess, R10 OneDrive-Delta, R11/V11 Code-Signatur; "
               "Q2–Q6, Q8–Q10."))
    s.append(P("Neue Vorschläge aus dem Review 2.2", "h2"))
    s.append(table([
        ["Nr", "Vorschlag", "Warum", "Aufwand"],
        ["R12", "Code-Signatur (Zertifikat, z. B. über SignPath für Open Source kostenlos)", "Vertrauen, keine "
                                                                                             "SmartScreen-Warnung",
         "mittel"],
        ["R13", "Quellcode öffentlich (GitHub) und Link im Info-Fenster – umgesetzt", "erfüllt GPL-Quellcodepflicht",
         "erledigt"],
        ["R14", "Update-Hinweis (nur auf Wunsch, HTTPS, signierte Versionsdatei)", "Sicherheitsupdates erreichen "
                                                                                    "Nutzer", "mittel"],
        ["R15", "Archiv-Journal mit Prüfsumme je Zeile", "erkennt Manipulation/Bitfehler", "gering"],
    ], [10 * mm, 78 * mm, W - 110 * mm, 22 * mm]))

    s.append(H1("Code-Review 2.1: Sicherheit, Stabilität, Funktion"))
    s.append(P("Alle in 2.1 neuen und geänderten Teile wurden durchgesehen, statisch geprüft (Pyright), mit neuen "
               "Tests abgesichert und im Ablauftest der Oberfläche durchlaufen. Dabei wurden zwei bestehende Fehler "
               "gefunden (T17, T18)."))
    s.append(table([
        ["Nr", "Bereich", "Befund / Risiko", "Maßnahme", "Status"],
        ["S16", "Sicherheit", "2FA-Anmeldung: Passwort/Code könnten gespeichert oder protokolliert werden",
         "Passwortfeld wird nach dem Absenden geleert, nie gespeichert oder protokolliert; OAuth-Weg ohne Passwort",
         status("behoben")],
        ["S17", "Sicherheit", "Manipulierte Token-Datei könnte das Token an einen fremden Server lenken",
         "Gespeicherter Server wird nur akzeptiert, wenn er api.pcloud.com/eapi.pcloud.com ist", status("behoben")],
        ["S18", "Sicherheit", "Client-Secret der pCloud-App im Klartext", "Nur mit „merken“, DPAPI-verschlüsselt; "
                              "sonst nur im Speicher", status("behoben")],
        ["D16", "Datenverlust", "Archivieren auf ein volles Laufwerk bricht mitten im Kopieren ab",
         "Platzprüfung vorab (GUI, Seestar, CLI) mit 5 % Reserve. Test.", status("behoben")],
        ["T17", "Stabilität", "„Letzte Cloud-Archivierung rückgängig“: bei Netzwerkfehler blieb die Oberfläche "
                              "dauerhaft „beschäftigt“", "Fehler abgefangen, Status rot, Bedienung wieder frei",
         status("behoben")],
        ["T18", "Stabilität", "Abmelden von pCloud im Hintergrund: unbehandelter Fehler ohne Konsole",
         "abgefangen (Abmelden ist auch offline unkritisch)", status("behoben")],
        ["F20", "Funktion", "Vorschau blieb ohne Auswahl stehen", "Vorschau wird geleert (Duplikate, Seestar, "
                            "nach Neuaufbau der Liste)", status("behoben")],
        ["F21", "Funktion", "Bild nur klein ansehbar", "Großansicht per Klick, SCHLIESSEN/Esc", status("umgesetzt")],
        ["F22", "Funktion", "2FA-Code mit Leerzeichen („123 456“)", "wird bereinigt. Test.", status("behoben")],
        ["F23", "Funktion", "pCloud-2FA per Passwort nutzt einen öffentlich nicht dokumentierten Schritt",
         "Browser-Anmeldung (offiziell) als empfohlener Weg; Hinweis im Dialog", status("Hinweis")],
    ], [11 * mm, 24 * mm, 52 * mm, W - 108 * mm, 21 * mm]))
    s.append(P("Verbesserungsvorschläge aus dem Review (sollten umgesetzt werden)", "h2"))
    s.append(table([
        ["Nr", "Vorschlag", "Warum", "Aufwand", "Priorität"],
        ["R1", "Prüfsummen-Cache bereinigen (Einträge gelöschter Dateien, VACUUM) – Knopf + automatisch monatlich",
         "Cache wächst sonst unbegrenzt", "gering", "hoch"],
        ["R2", "Journal verdichten (erledigte Einträge in Jahresdatei auslagern)", "schneller Start bei großen "
                                                                                    "Archiven", "gering", "mittel"],
        ["R3", "Abgebrochene Archivierung als „unvollständige Sitzung“ kennzeichnen", "klare Anzeige nach Abbruch",
         "gering", "mittel"],
        ["R4", "app.py (≈ 1.400 Zeilen) in Module je Tab aufteilen", "Wartbarkeit, weniger Fehler", "mittel", "mittel"],
        ["R5", "Typprüfung (Pyright) und Linter fest in Build und CI aufnehmen", "findet Fehler wie T12/T13 "
                                                                                  "automatisch", "gering", "hoch"],
        ["R6", "Vorschau-Cache (verkleinerte Bilder) auf der Platte", "schnelleres Blättern, v. a. RAW/Cloud",
         "mittel", "mittel"],
        ["R7", "Sprachausgabe als dauerhafter Prozess statt PowerShell-Start je Meldung", "ca. 1 s weniger "
                                                                                           "Verzögerung", "gering",
         "niedrig"],
        ["R8", "Beim Start alte Cloud-Vorschau-Ordner (bz_cloud_*) im Temp aufräumen", "nach Absturz kein Rest",
         "gering", "mittel"],
        ["R9", "Fehlerdialog mit „Details kopieren“ (Protokollauszug, Version, System)", "schnellere Fehlersuche",
         "gering", "mittel"],
        ["R10", "OneDrive: Delta-Abfrage für Folgeprüfungen", "Cloud-Folgeprüfung in Sekunden", "mittel",
         "niedrig"],
        ["R11", "Code-Signatur der EXE (V11)", "keine SmartScreen-Warnung, Vertrauen", "Kosten", "hoch"],
    ], [10 * mm, 66 * mm, W - 128 * mm, 18 * mm, 24 * mm]))

    s.append(H1("Code-Review 2.0: Sicherheit, Stabilität, Funktion"))
    s.append(P("Der neue und geänderte Code wurde erneut systematisch geprüft (Durchsicht, statische Analyse mit "
               "Pyright, gezielte Tests, Ablauftest der Oberfläche in Deutsch und Englisch). Befunde aus 1.0 und 1.5 "
               "bleiben behoben und durch Tests abgesichert."))
    s.append(table([
        ["Nr", "Bereich", "Befund / Risiko", "Maßnahme", "Status"],
        ["S12", "Sicherheit", "Cloud: unverschlüsselte Verbindung oder Weitergabe des Tokens bei Weiterleitung an "
                              "fremde Server", "Nur HTTPS; Authorization-Kopf bei Host-Wechsel entfernt. Tests.",
         status("behoben")],
        ["S13", "Sicherheit", "Speicherung von Cloud-Anmeldedaten", "Kein Passwort; Token nur auf Wunsch, DPAPI-"
                              "verschlüsselt; Fehler beim Speichern brechen die Anmeldung nicht ab", status("behoben")],
        ["S14", "Sicherheit", "Cloud-Pfade mit „..“", "Pfadnormalisierung, „..“ wird abgelehnt", status("behoben")],
        ["S15", "Sicherheit", "Lightroom-Katalog könnte durch BildZwilling verändert werden", "Nur lesend geöffnet "
                              "(mode=ro, immutable); Windows-taugliche Datei-URI", status("behoben")],
        ["D12", "Datenverlust", "pCloud-Verschieben könnte eine gleichnamige Datei im Archiv überschreiben",
         "Zielordner vorher gelesen, freier Name gewählt. Test.", status("behoben")],
        ["D13", "Datenverlust", "Cloud-Datei nach der Suche geändert/gelöscht", "Erneute Abfrage von Größe, Hash, "
                                "Existenz vor jedem Verschieben. Test.", status("behoben")],
        ["D14", "Datenverlust", "Rückgängig überschreibt neu angelegte Datei am Ursprungsort", "Lokal und in der "
                                "Cloud: freier Name „(1)“. Test.", status("behoben")],
        ["D15", "Datenverlust", "Seestar-Ausschuss ohne „Original“ wäre im Archiv nie löschbar bzw. würde ohne "
                                "Prüfung gelöscht", "Eigene Art „seestar“: gelöscht wird nur nach Bestätigung, "
                                "Kennzeichnung im Archiv", status("behoben")],
        ["T12", "Stabilität", "Lokale Variable „tr“ überdeckte die Übersetzungsfunktion (Seestar ohne numpy)",
         "Umbenannt; Prüfung auf überdeckte Namen in allen Modulen", status("behoben")],
        ["T13", "Stabilität", "„Alle Subs dieses Stacks markieren“ – nicht hashbare Objekte in einer Menge",
         "Auswahl über Objekt-IDs. Ablauftest.", status("behoben")],
        ["T14", "Stabilität", "Anbieterwechsel löschte gespeicherte Anmeldung des neuen Anbieters", "Wechsel beendet "
                              "nur die Sitzung", status("behoben")],
        ["T15", "Stabilität", "Cloud-API: Drosselung (HTTP 429) und Serverfehler", "Automatische Wiederholung mit "
                              "Wartezeit (Retry-After), Zeitlimits", status("behoben")],
        ["T16", "Stabilität", "Tests auf Rechnern mit Firmen-Proxy", "Lokale Testserver ohne Proxy angesprochen. "
                              "Test mit ungültigem Proxy.", status("behoben")],
        ["F13", "Funktion", "1.5-Build unter Windows: Test legte Datei „&lt;script&gt;.jpg“ an (unter Windows "
                            "unzulässig)", "Test plattformgerecht (&amp; und ' unter Windows)", status("behoben")],
        ["F14", "Funktion", "Elongation auf gebinntem Bild verfälscht (runde Sterne 2,05)", "Messung in voller "
                            "Auflösung mit Rauschschwelle → 1,02", status("behoben")],
        ["F15", "Funktion", "Sitzungen in derselben Sekunde nicht eindeutig sortierbar", "Reihenfolge im "
                            "append-only-Journal maßgeblich. Test.", status("behoben")],
        ["F16", "Funktion", "Zahlenformat in englischer Oberfläche", "Dezimal-/Tausendertrennzeichen je Sprache",
         status("behoben")],
        ["F17", "Funktion", "pCloud-Konten mit Zwei-Faktor-Anmeldung", "Anmeldung per Passwort ggf. abgelehnt – "
                            "Hinweis im Dialog; OAuth-App als Ausbaustufe (V19)", status("Hinweis")],
        ["F19", "Funktion", "Windows: Seestar-Begleitdateien doppelt gezählt (.jpg und .JPG = dieselbe Datei, "
                            "Build-Test schlug fehl)", "Abgleich mit dem Ordnerinhalt unabhängig von Groß/Klein; "
                            "Test bildet Windows-Verhalten nach", status("behoben")],
        ["F18", "Funktion", "Cloud-Schnittstellen nur gegen Nachbildung getestet", "Test mit echtem Konto empfohlen "
                            "(kleiner Testordner)", status("offen")],
    ], [11 * mm, 24 * mm, 52 * mm, W - 108 * mm, 21 * mm]))
    s.append(P("Befunde aus Version 1.5 (weiterhin gültig)", "h2"))
    rv = [
        ["Nr", "Bereich", "Befund / Risiko", "Maßnahme", "Status"],
        ["S7", "Sicherheit", "Windows sucht Programme auch im aktuellen Arbeitsordner – eine untergeschobene "
                             "exiftool.exe/ffmpeg.exe könnte gestartet werden", "Treffer im Arbeitsordner werden "
                             "verworfen (außer es ist der Programmordner)", status("behoben")],
        ["S8", "Sicherheit", "HTML-Bericht: Skript-Einschleusung über präparierte Dateinamen", "Alle Werte "
                             "maskiert; Test mit Datei „&lt;script&gt;.jpg“", status("behoben")],
        ["S9", "Sicherheit", "Aufruf externer Programme", "Keine Shell, Argumentliste, Pfad über UTF-8-"
                             "Argumentdatei (Umlaute, führendes „-“), Zeitlimit, kein Konsolenfenster", status("behoben")],
        ["S10", "Sicherheit", "Präparierte FITS-Dateien (Riesen-Header, falsche Geometrie, abgeschnittene Daten)",
         "Header-Grenze, Geometrieprüfung, Pixelgrenze 400 MP, Längenprüfung. Test.", status("behoben")],
        ["S11", "Sicherheit", "Sprachausgabe: Befehlsinjektion über Dateinamen", "Text nur per Standardeingabe",
         status("behoben")],
        ["D6", "Datenverlust", "Ähnliche (nicht identische) Bilder versehentlich archiviert", "Nie vorab markiert, "
                               "blau, Warnung im Dialog, CLI verschiebt nie", status("behoben")],
        ["D7", "Datenverlust", "RAW+JPEG- bzw. FIT+JPG-Paar wird getrennt", "Paar-Planer mit drei Regeln, "
                               "iterativ stabil; Partner wiederherstellbar. Test.", status("behoben")],
        ["D8", "Datenverlust", "Datei ist Original einer identischen und Mitglied einer ähnlichen Gruppe",
         "Prüfung über alle Gruppen; Verifikation gegen identische Gruppe bevorzugt", status("behoben")],
        ["D9", "Datenverlust", "Regel „archivieren“ trifft alle Dateien einer Gruppe", "Eine Datei bleibt immer; "
                               "„behalten“ gewinnt. Test.", status("behoben")],
        ["D10", "Datenverlust", "Regler-Neugruppierung überschrieb manuelle Markierungen", "Markierungen identischer "
                                "Gruppen werden gesichert und wiederhergestellt", status("behoben")],
        ["T9", "Stabilität", "Fehltreffer/Kettenbildung bei dunklen Nachtaufnahmen", "Kontrastschwelle, "
                             "Seitenverhältnis ±4 %. Test.", status("behoben")],
        ["T10", "Stabilität", "„exiftool(-k).exe“ wartet auf Tastendruck → jeder Aufruf hängt 25 s",
         "Standardeingabe geschlossen. Test mit wartender Attrappe.", status("behoben")],
        ["T11", "Stabilität", "Große Listen / Neugruppierung blockieren Oberfläche", "Seiten, Hintergrund-"
                              "Threads, Token gegen veraltete Ergebnisse", status("behoben")],
        ["F7", "Funktion", "Zahlenformat „103.9 KB“ statt „103,9 KB“ in Statusmeldungen (auch 1.0)",
         "Tausenderpunkt getrennt formatiert", status("behoben")],
        ["F8", "Funktion", "Umlaute in der Windows-Sprachausgabe", "UTF-8-Eingabe für PowerShell", status("behoben")],
        ["F9", "Funktion", "Seestar S30: BAYERPAT evtl. falsch → Vorschaufarben von Subs vertauscht",
         "Nur Vorschau betroffen; Vergleich unberührt", status("Hinweis")],
        ["F10", "Funktion", "Sehr große ähnliche Gruppen bei Regler „locker“ (16)", "Gewollt; Standard 6 empfohlen",
         status("akzeptiert")],
        ["F12", "Funktion", "Weiße Windows-Titelleiste und Standarddialoge passten nicht zum Stil",
         "Titelleiste per DWM gefärbt, eigene Dialoge; Datei-/Ordnerauswahl bleibt der Windows-Dialog "
         "(folgt dem Windows-Dunkelmodus)", status("behoben")],
        ["D11", "Datenverlust", "Enter in einer Löschabfrage bestätigt versehentlich", "„Nein“ vorausgewählt; "
                                "Schließen/Esc = Nein. Test.", status("behoben")],
        ["F11", "Funktion", "PyInstaller-EXE wird gelegentlich vom Virenscanner gemeldet", "Code-Signatur (V11)",
         status("Hinweis")],
    ]
    s.append(table(rv, [11 * mm, 25 * mm, 50 * mm, W - 107 * mm, 21 * mm]))

    s.append(P("Durchgeführte Prüfungen (2.2)", "h2"))
    s += bullets([
        "<b>61 Unit-Tests</b>, alle bestanden (einer nur unter Windows: lange Pfade) – neu u. a.: Lizenzdateien und "
        "Lizenzkopf in jeder Quelldatei, Copyright, CLI --version/--license, Instanzsperre, Werkzeugsuche ohne PATH, "
        "„Alle Anmeldungen entfernen“, Schwärzung im Log, CSP im HTML-Bericht, Sicherung/Wiederherstellung der "
        "Einstellungen, Bildgrößen-Grenze, unvollständige Sitzungen, Cache-Bereinigung, Temp-Aufräumen, "
        "CLI-Verschieben bei laufendem Programm.",
        "<b>Ablauftest der Oberfläche</b>: Haftungshinweis ablehnen → Programm endet · zustimmen → Start · "
        "unvollständige Archivierung wird erkannt und zurückgeholt · zweite Instanz abgewiesen · Info-Fenster, "
        "Systeminfo, Lizenz, Drittanbieter · Fehlerdialog mit Details · Einstellungen/Wartung · Suche und "
        "Archivierung mit Sitzungsstatus · keine E-Mail im Protokoll; dazu die Abläufe aus 2.0/2.1 (de/en).",
        "<b>Typprüfung</b> (Pyright) für Windows, macOS und Linux: 0 Fehler.",
        "<b>Nicht geprüft</b> (keine Bildschirmausgabe in der Testumgebung): die tatsächliche Optik des neuen "
        "Info-Fensters unter Windows – bitte nach dem Build ansehen.",
    ])
    s.append(P("Durchgeführte Prüfungen (2.1)", "h2"))
    s += bullets([
        "<b>42 Unit-Tests</b>, alle bestanden – neu: pCloud-2FA (Code-Abfrage, falscher Code, Code mit "
        "Leerzeichen), OAuth (Code-Tausch, falscher Code, gespeicherte Anmeldung, Bearer-Token), Platzprüfung "
        "(gleiches/anderes Laufwerk, zu wenig Platz), Windows-Groß/Klein-Nachbildung (Seestar-Begleitdateien).",
        "<b>Ablauftest der Oberfläche</b>: Vorschau → Großansicht (Zoom, SCHLIESSEN) → Gruppe gewählt → keine Auswahl "
        "(Vorschau leer) → pCloud-Dialog Passwort + 2FA (falscher und richtiger Code) → Browser-Anmeldung → Cloud "
        "prüfen; dazu der komplette 2.0-Ablauf auf Deutsch und Englisch – ohne Fehler im Protokoll.",
        "<b>Statische Analyse</b> (Pyright): keine Fehler in der Tk-Verwendung.",
    ])
    s.append(P("Verbesserungsvorschläge für die Tests (sollten umgesetzt werden)", "h2"))
    s.append(table([
        ["Nr", "Vorschlag", "Nutzen", "Aufwand"],
        ["Q1", "Tests automatisch auf Windows, macOS und Linux bei jedem Push (GitHub Actions) – Vorlage "
               "<i>.github/workflows/tests.yml</i> liegt bei", "hätte beide Windows-Fehler (1.5, 2.0) vor dem "
                                                                 "Build gefunden", "gering (vorbereitet)"],
        ["Q2", "Echte Oberflächentests unter Windows (z. B. pywinauto) statt Tk-Attrappe", "prüft Optik, Fokus, "
                                                                                        "Tastatur", "mittel"],
        ["Q3", "Beispieldatensatz echter Dateien: RAW je Hersteller (z. B. raw.pixls.us), Seestar-FITS, HEIC, Videos",
         "prüft rawpy/ExifRead/LibRaw mit echten Daten", "gering"],
        ["Q4", "Cloud-Integrationstest mit Testkonto (pCloud EU/US, OneDrive privat/geschäftlich), Zugangsdaten "
               "nur per Umgebungsvariable, manuell ausgelöst", "bestätigt die echten Schnittstellen inkl. 2FA",
         "mittel"],
        ["Q5", "Fuzzing der Leser (FITS, XMP, EXIF-Fallback, Journal) mit Hypothesis", "Robustheit gegen kaputte "
                                                                                     "Dateien", "gering"],
        ["Q6", "Last- und Störungstest: 100.000+ Dateien, Netzwerk trennen, USB-Laufwerk abziehen", "Stabilität im "
                                                                                                 "Ernstfall", "mittel"],
        ["Q7", "Testabdeckung messen (coverage), Ziel ≥ 85 % für den Kern", "Lücken sichtbar machen", "gering"],
        ["Q8", "Windows-Sonderfälle: Pfade > 260 Zeichen, schreibgeschützte Dateien, OneDrive-Platzhalter, "
               "Laufwerkswechsel", "die häufigsten Praxisprobleme", "gering"],
        ["Q9", "Barrierefreiheit real prüfen (NVDA, Windows-Kontrastdesign, 150 % Skalierung)", "Bedienbarkeit für "
                                                                                              "alle", "gering"],
        ["Q10", "Übersetzungstest um Längenprüfung erweitern (abgeschnittene Knöpfe im Englischen)", "saubere "
                                                                                                  "Oberfläche", "gering"],
    ], [10 * mm, 82 * mm, W - 120 * mm, 28 * mm]))

    s.append(P("Durchgeführte Prüfungen (2.0)", "h2"))
    s += bullets([
        "<b>40 Unit-Tests</b>, alle bestanden: Kern 1.0/1.5 sowie 2.0 – Rückgängig-Sitzungen (inkl. CLI), XMP-"
        "Bewertungen (Begleitdatei und eingebettet), Lightroom-Katalog, gedrehte/gespiegelte Kopien, Seestar-"
        "Assistent mit simulierten Subs (Wolken, Nachführfehler, Unschärfe, Zuordnung, Archivieren, Rückgängig), "
        "Cloud gegen einen lokalen pCloud-/Graph-Nachbau (Anmeldung, Seitenumbruch, Kollision, Namenskonflikt, "
        "Änderung nach Suche, Rückgängig, nur HTTPS, Weiterleitung ohne Token), Vollständigkeit der englischen "
        "Übersetzung. Der Build führt sie erneut aus.",
        "<b>Ablauftest der Oberfläche</b> (Tk-Attrappe) auf Deutsch und Englisch: Suche mit Bewertungen und gedrehten "
        "Kopien → Archivieren → Rückgängig → Seestar-Analyse → Stack markieren → Ausschuss archivieren → Rückgängig → "
        "Cloud prüfen → in Cloud-Archiv verschieben → Rückgängig → Einstellungen – ohne Fehler im Protokoll.",
        "<b>Statische Analyse</b> (Pyright): zwei echte Fehler gefunden und behoben (T12, T13).",
    ])
    s.append(P("Grenzen dieser Prüfung", "h2"))
    s.append(P("Nicht verfügbar waren: ein Bildschirm-Tk, echte Konten bei pCloud und Microsoft, echte Seestar-Daten "
               "sowie rawpy, ExifRead, pillow-heif und Send2Trash. Die Cloud-Schnittstellen sind nach den offiziellen "
               "Dokumentationen umgesetzt und gegen eine Nachbildung getestet; die DPAPI-Speicherung ist nur unter "
               "Windows aktiv und hier nicht ausführbar. <b>Empfehlung:</b> Cloud zuerst mit einem kleinen Testordner, "
               "Seestar mit der Kopie eines Objektordners prüfen."))

    # 12 -----------------------------------------------------------------
    s.append(H1("Verbesserungsvorschläge"))
    s.append(P("V1–V10 (Version 1.5) und V12–V17 (Version 2.0) sind umgesetzt; 2.1 ergänzt pCloud mit 2FA, 2.2 Lizenz, Haftung, Sicherheit und Stabilität. Offene Vorschläge (zusätzlich R2–R15 und Q2–Q10 aus den Code-Reviews):"))
    s.append(table([
        ["Nr", "Vorschlag", "Nutzen", "Aufwand"],
        ["V11", "Code-Signatur (Authenticode / Apple Developer ID) und Notarisierung",
         "keine SmartScreen-/Gatekeeper-Warnungen", "Kosten"],
        ["V18", "Seestar direkt: Seestar-Speicher (WLAN/USB) als Quelle, nur neue Objekte übernehmen und auf dem "
                "Gerät aufräumen", "Speicher auf der Seestar frei, ein Klick", "mittel"],
        ["V19", "Weitere Cloud-Anbieter: Nextcloud/ownCloud (WebDAV + Prüfsummen), Google Drive (MD5), Dropbox "
                "(content_hash)", "alle Clouds ohne Download", "mittel"],
        ["V20", "Lightroom-Katalog bereinigen: fehlende/verschobene Dateien nach Archivierung im Katalog markieren",
         "Katalog bleibt konsistent", "mittel"],
        ["V21", "Ähnlichkeit über Bildmerkmale (lokales KI-Modell) für stark bearbeitete Varianten",
         "findet auch zugeschnittene/gefilterte Versionen", "hoch"],
        ["V22", "Weitere Sprachen (z. B. Französisch, Italienisch) – nur Wörterbuch", "Weitergabe", "gering"],
        ["V23", "macOS-Schlüsselbund für Cloud-Anmeldungen", "„Anmeldung merken“ auch auf dem Mac", "gering"],
        ["V24", "pCloud-Anmeldung ohne Code abtippen: lokaler Rückruf (http://localhost) für OAuth",
         "Browser-Anmeldung mit einem Klick", "gering"],
        ["V25", "Großansicht mit Blättern (← →) durch die Gruppe und Vergleich per Taste", "schnelleres Sichten",
         "gering"],
        ["V26", "Ordnerüberwachung: neue Dateien sofort gegen den Bestand prüfen (z. B. Import-Ordner)",
         "Duplikate entstehen gar nicht erst", "mittel"],
        ["V27", "Import-Assistent: Speicherkarte einlesen, bereits vorhandene Bilder überspringen",
         "kein doppeltes Importieren", "mittel"],
        ["V28", "Videos: ähnliche Videos über Schlüsselbilder (ffmpeg)", "auch umkodierte Videos finden", "mittel"],
        ["V29", "Statistik-Seite: Ersparnis über die Zeit, größte Duplikat-Ordner", "Überblick", "gering"],
        ["V30", "Seestar: Teilstapel neu stacken (Siril-Aufruf) nur mit guten Subs", "besseres Ergebnis aus den "
                                                                                    "gleichen Daten", "hoch"],
    ], [11 * mm, 78 * mm, W - 109 * mm, 20 * mm]))

    # 13 -----------------------------------------------------------------
    s.append(H1("macOS-Portierung"))
    s += bullets([
        "Titelleiste und Dialoge: Auf macOS folgt die Titelleiste dem Systemerscheinungsbild; die eigenen Dialoge "
        "sehen überall gleich aus.",
        "Plattformneutraler Code; Daten neben dem .app-Bundle; Finder-Integration; Cmd+Q; iCloud/OneDrive "
        "„dataless“-Dateien werden erkannt.",
        "Sprachausgabe über „say“, Schrift Helvetica Neue; ExifTool/ffmpeg z. B. per Homebrew (auf dem Mac auch im PATH "
        "gesucht). Ruhezustand wird über „caffeinate“ verhindert.",
        "Bauen mit <i>build-mac.sh</i> auf dem Mac; für die Weitergabe Apple-Signatur empfohlen (V11).",
        "„Anmeldung merken“ für die Cloud ist auf dem Mac noch nicht verfügbar (Anmeldung gilt bis Programmende, V23).",
    ])
    s.append(PageBreak())
    s.append(H1("Anhang: Extrahierter Gesamt-Prompt"))
    s.append(P("Mit diesem Prompt lässt sich BildZwilling mit einem KI-Modell fortführen oder neu erzeugen. "
               "Die Originalaufträge aller Versionen im Wortlaut stehen in <i>DEV/PROMPT_GESAMT.md</i>."))
    for para in prompt_paragraphs():
        s.append(P(para, "prompt"))
    s.append(Spacer(1, 8))
    s.append(KeepTogether([P("Copyright", "h2"),
                           P(COPYRIGHT.replace("&", "&amp;"))]))
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    print(out)


if __name__ == "__main__":
    build()
