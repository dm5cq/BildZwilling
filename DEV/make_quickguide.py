# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt den einseitigen Quick-Guide als PDF (Deutsch und Englisch).

Aufruf: python DEV/make_quickguide.py   ->  docs/BildZwilling_QuickGuide.pdf, docs/BildZwilling_QuickGuide_EN.pdf
"""

import os

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
for n, f in (("DV", "DejaVuSans.ttf"), ("DVB", "DejaVuSans-Bold.ttf"), ("DVI", "DejaVuSans-Oblique.ttf"),
             ("DVBI", "DejaVuSans-BoldOblique.ttf")):
    pdfmetrics.registerFont(TTFont(n, os.path.join(FONT_DIR, f)))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DVB", italic="DVI", boldItalic="DVBI")

VERSION = "2.2"
DATE = {"de": "18.11.2026", "en": "18 Nov 2026"}
BG, PANEL, FIELD = HexColor("#2b2b2b"), HexColor("#333333"), HexColor("#3c3c3c")
ORANGE, GREEN, RED = HexColor("#ff8c00"), HexColor("#4caf50"), HexColor("#e53935")
YELLOW, BLUE, MUTED, DARK = HexColor("#fdd835"), HexColor("#42a5f5"), HexColor("#b0b0b0"), HexColor("#222222")
W, H = A4
M = 36
body = ParagraphStyle("b", fontName="DV", fontSize=8.0, leading=10.3, textColor=DARK)

TXT = {
    "de": dict(
        sub="Quick-Guide · Doppelte & ähnliche Fotos finden, prüfen und sicher archivieren",
        caption="schematische Darstellung des Hauptfensters",
        slogan="Doppelte Fotos finden · prüfen · archivieren",
        s1="1 · Bildordner", s2="2 · Archivordner", s3="3 · Suche", start="▶  Suche starten",
        opts=["◉ Byte-identisch", "○ + gleicher Bildinhalt", "☑ Ähnliche  ━━●━━  6", "☑ gedreht/gespiegelt",
              "☑ Paare  ☑ Bewertungen ★"],
        tabs=["Duplikate", "Seestar", "Cloud", "Archiv (12)", "Protokoll"],
        filt="Filter …   Alle Arten ▾  Alle Typen ▾  Ersparnis ↓ ▾",
        rows=[("Gruppe 1 · 3 Dateien · byte-identisch", "g", ""), ("   IMG_4711.RAF", "k", "✔ BEHALTEN ★★★★"),
              ("   Kopie von IMG_4711.RAF", "a", "➜ Archiv · Paar"), ("   Light_M42_10.0s.fit", "a", "➜ Archiv"),
              ("Gruppe 2 · ähnlich · gedreht/gespiegelt", "s", ""), ("   DJI_0042.DNG  5280×3956", "k", "✔ BEHALTEN"),
              ("   IMG-WA0012.jpg  1600×1200", "k", "✔ BEHALTEN")],
        arch="➜ Markierte ins Archiv", undo="↶ Rückgängig", preview="Vorschau",
        done="Fertig · 42 Gruppen · 3,8 GB freizugeben",
        steps_title="In 7 Schritten",
        steps=[
            ("Bildordner hinzufügen", "„+ Ordner“ – lokal, HDD, NAS, pCloud, OneDrive, Nextcloud/ownCloud. Der "
             "<b>erste Ordner ist der Master</b>: dort liegende Dateien bleiben bevorzugt."),
            ("Archivordner wählen", "Eigener Ordner für Duplikate – am besten auf demselben Laufwerk (blitzschnell)."),
            ("Suchart wählen", "<b>Byte-identisch</b> (auch mit anderem Namen) · <b>+ gleicher Bildinhalt</b> "
             "(andere Metadaten) · <b>Ähnliche Bilder</b> inkl. gedrehter/gespiegelter Kopien, Regler "
             "<i>streng ↔ locker</i>. Bewertete Bilder (★, Farbe, Flagge) bleiben bevorzugt."),
            ("Suche starten (F5)", "Fortschritt unten in Blau, Abbruch jederzeit; der Cache macht Folgesuchen schnell."),
            ("Prüfen", "Filter/Typ/Sortierung, ◀ ▶ blättert. Doppelklick = <b>Vergleich</b> (Z = 100 %, EXIF, "
             "Byte-/Pixelprüfung). <b>Klick auf die Vorschau</b> = Großansicht (SCHLIESSEN/Esc). <b>★ Als Original</b> · "
             "<b>Leertaste</b> = Behalten ⇄ Archiv."),
            ("Ins Archiv verschieben", "„➜ Markierte ins Archiv“ – vorher erneut verglichen, Paare und XMP bleiben "
             "zusammen. <b>Nichts wird gelöscht.</b> <b>↶ Rückgängig (Strg+Z)</b> holt alles zurück."),
            ("Sichten & freigeben", "Tab <b>Archiv</b>: vergleichen, wiederherstellen oder „Endgültig löschen …“ "
             "(Papierkorb). <b>Gelb</b> = Aufbewahrungsfrist abgelaufen → „Fällige auswählen“."),
        ],
        legend_title="Farben",
        legend=[("Grün", "behalten · erfolgreich"), ("Orange", "wird archiviert · Aktion"),
                ("Gelb", "Warnung · Unterschied · fällig"), ("Rot", "Fehler · Original fehlt"),
                ("Blau", "läuft · ähnliche Bilder")],
        tips_title="Gut zu wissen",
        tips=("• <b>Seestar-Assistent:</b> ordnet Subs ihrem Stack zu und erkennt Ausschuss (Wolken, Unschärfe, "
              "Nachführfehler) über Sternanzahl, FWHM und Sternform.<br/>"
              "• <b>Cloud direkt:</b> pCloud/OneDrive über die Server-Prüfsummen prüfen – <b>ohne Download</b>; "
              "Verschieben innerhalb der Cloud, rückgängig möglich; pCloud auch mit <b>Zwei-Faktor</b> (Browser-Anmeldung).<br/>"
              "• <b>RAW:</b> Fujifilm, Nikon, Canon, Panasonic, OM System, Leica, Hasselblad, DJI, Insta360 u. a.<br/>"
              "• <b>⚙ Einstellungen:</b> Sprache Deutsch/English, Ordnerregeln, Lightroom-Katalog, Hell/Dunkel/"
              "Kontrast, große Schrift, Sprachausgabe.<br/>"
              "• <b>Optional:</b> exiftool.exe / ffmpeg.exe im Ordner <i>tools</i>.<br/>"
              "• <b>Berichte:</b> CSV, HTML mit Vorschaubildern · <b>BildZwilling-cli.exe</b> für NAS/Aufgabenplanung.<br/>"
              "• <b>Freie Software (GNU GPL v3)</b> – Nutzung auf eigene Verantwortung, ohne Gewährleistung. "
              "Vorher eine Datensicherung anlegen."),
        copy="© 2026 Stefan J. Kaiser DM5CQ / OE8KKS (Idee, Konzept & Prompt) · Umsetzung: Claude (Anthropic) · "
             "Lizenz: GNU GPL v3 · Stand {d} · Version {v}",
        file="BildZwilling_QuickGuide.pdf",
    ),
    "en": dict(
        sub="Quick guide · Find, check and safely archive duplicate & similar photos",
        caption="schematic view of the main window",
        slogan="Find · check · archive duplicate photos",
        s1="1 · Image folders", s2="2 · Archive folder", s3="3 · Search", start="▶  Start search",
        opts=["◉ Byte-identical", "○ + same image content", "☑ Similar  ━━●━━  6", "☑ rotated/mirrored",
              "☑ Pairs  ☑ Ratings ★"],
        tabs=["Duplicates", "Seestar", "Cloud", "Archive (12)", "Log"],
        filt="Filter …   All kinds ▾  All types ▾  Savings ↓ ▾",
        rows=[("Group 1 · 3 files · byte-identical", "g", ""), ("   IMG_4711.RAF", "k", "✔ KEEP ★★★★"),
              ("   Copy of IMG_4711.RAF", "a", "➜ Archive · pair"), ("   Light_M42_10.0s.fit", "a", "➜ Archive"),
              ("Group 2 · similar · rotated/mirrored", "s", ""), ("   DJI_0042.DNG  5280×3956", "k", "✔ KEEP"),
              ("   IMG-WA0012.jpg  1600×1200", "k", "✔ KEEP")],
        arch="➜ Archive selected", undo="↶ Undo", preview="Preview",
        done="Done · 42 groups · 3.8 GB to free",
        steps_title="In 7 steps",
        steps=[
            ("Add image folders", "“+ Folder” – local, HDD, NAS, pCloud, OneDrive, Nextcloud/ownCloud. The "
             "<b>first folder is the master</b>: files there are preferably kept."),
            ("Choose an archive folder", "A separate folder for duplicates – ideally on the same drive (instant)."),
            ("Choose the search type", "<b>Byte-identical</b> (even with a different name) · <b>+ same image "
             "content</b> (different metadata) · <b>Similar images</b> incl. rotated/mirrored copies, slider "
             "<i>strict ↔ loose</i>. Rated images (★, color, flag) are preferably kept."),
            ("Start search (F5)", "Progress in blue at the bottom, cancel any time; the cache makes repeat searches fast."),
            ("Check", "Filter/type/sort, ◀ ▶ pages. Double-click = <b>compare</b> (Z = 100 %, EXIF, byte/pixel check). "
             "<b>Click the preview</b> = large view (CLOSE/Esc). <b>★ As original</b> · <b>Space</b> = keep ⇄ archive."),
            ("Move to archive", "“➜ Archive selected” – compared again beforehand, pairs and XMP stay together. "
             "<b>Nothing is deleted.</b> <b>↶ Undo (Ctrl+Z)</b> brings everything back."),
            ("Review & release", "<b>Archive</b> tab: compare, restore or “Delete permanently …” (recycle bin). "
             "<b>Yellow</b> = retention period expired → “Select due”."),
        ],
        legend_title="Colors",
        legend=[("Green", "keep · success"), ("Orange", "to be archived · action"),
                ("Yellow", "warning · difference · due"), ("Red", "error · original missing"),
                ("Blue", "running · similar images")],
        tips_title="Good to know",
        tips=("• <b>Seestar assistant:</b> assigns subs to their stack and detects rejects (clouds, blur, tracking "
              "errors) using star count, FWHM and star shape.<br/>"
              "• <b>Cloud direct:</b> checks pCloud/OneDrive via server checksums – <b>without downloading</b>; "
              "moves within the cloud, undo possible; pCloud also with <b>two-factor</b> (browser sign-in).<br/>"
              "• <b>RAW:</b> Fujifilm, Nikon, Canon, Panasonic, OM System, Leica, Hasselblad, DJI, Insta360 and more.<br/>"
              "• <b>⚙ Settings:</b> language Deutsch/English, folder rules, Lightroom catalog, light/dark/contrast, "
              "large font, speech output.<br/>"
              "• <b>Optional:</b> exiftool.exe / ffmpeg.exe in the <i>tools</i> folder.<br/>"
              "• <b>Reports:</b> CSV, HTML with thumbnails · <b>BildZwilling-cli.exe</b> for NAS/task scheduler.<br/>"
              "• <b>Free software (GNU GPL v3)</b> – use at your own risk, without warranty. Make a backup first."),
        copy="© 2026 Stefan J. Kaiser DM5CQ / OE8KKS (idea, concept & prompt) · Implementation: Claude (Anthropic) · "
             "License: GNU GPL v3 · {d} · Version {v}",
        file="BildZwilling_QuickGuide_EN.pdf",
    ),
}


def para(c, text, x, y_top, w, style=body):
    p = Paragraph(text, style)
    _, h = p.wrap(w, 1000)
    p.drawOn(c, x, y_top - h)
    return y_top - h


def badge(c, x, y, n):
    c.setFillColor(ORANGE)
    c.circle(x, y, 7.5, stroke=0, fill=1)
    c.setFillColor(HexColor("#000000"))
    c.setFont("DVB", 8.5)
    c.drawCentredString(x, y - 3, str(n))


def mockup(c, x, y, w, h, t):
    c.setFillColor(BG)
    c.roundRect(x, y, w, h, 6, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.setFont("DVB", 11)
    c.drawString(x + 10, y + h - 20, "BildZwilling")
    c.setFillColor(MUTED)
    c.setFont("DV", 6.5)
    c.drawString(x + 86, y + h - 19, t["slogan"])
    sw = 122
    sx, sy, sh = x + 8, y + 30, h - 60
    c.setFillColor(PANEL)
    c.rect(sx, sy, sw, sh, stroke=0, fill=1)

    def lbl(s, yy, col=ORANGE, f="DVB", sz=6.8):
        c.setFillColor(col)
        c.setFont(f, sz)
        c.drawString(sx + 6, yy, s)

    top = sy + sh
    lbl(t["s1"], top - 12)
    c.setFillColor(FIELD)
    c.rect(sx + 6, top - 52, sw - 12, 34, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("DV", 5.6)
    for i, s in enumerate(["D:\\Fotos", "P:\\pCloud\\Bilder", "\\\\NAS\\Bilder"]):
        c.drawString(sx + 9, top - 26 - i * 9, s)
    lbl(t["s2"], top - 66)
    c.setFillColor(FIELD)
    c.rect(sx + 6, top - 82, sw - 12, 11, stroke=0, fill=1)
    c.setFillColor(white)
    c.drawString(sx + 9, top - 79, "D:\\Fotos_Archiv")
    lbl(t["s3"], top - 96)
    c.setFont("DV", 5.6)
    for i, s in enumerate(t["opts"]):
        c.setFillColor(white)
        c.drawString(sx + 8, top - 107 - i * 8.5, s)
    c.setFillColor(ORANGE)
    c.roundRect(sx + 6, sy + 8, sw - 12, 15, 2, stroke=0, fill=1)
    c.setFillColor(HexColor("#000000"))
    c.setFont("DVB", 7)
    c.drawCentredString(sx + sw / 2, sy + 12.5, t["start"])

    mx = sx + sw + 8
    mw = x + w - 8 - mx
    c.setFont("DVB", 6.2)
    tx = mx
    for i, s in enumerate(t["tabs"]):
        tw = c.stringWidth(s, "DVB", 6.2) + 12
        c.setFillColor(BG if i == 0 else PANEL)
        c.rect(tx, top - 12, tw, 13, stroke=0, fill=1)
        c.setFillColor(ORANGE if i == 0 else MUTED)
        c.drawString(tx + 6, top - 8, s)
        if i == 3:
            arch_tab_x = tx + tw / 2
        if i == 1:
            seestar_x = tx + tw / 2
        if i == 2:
            cloud_x = tx + tw / 2
        tx += tw + 2
    c.setFillColor(ORANGE)
    c.roundRect(mx + mw - 86, top - 30, 86, 13, 2, stroke=0, fill=1)
    c.setFillColor(HexColor("#000000"))
    c.setFont("DVB", 6)
    c.drawCentredString(mx + mw - 43, top - 26, t["arch"])
    c.setFillColor(FIELD)
    c.roundRect(mx + mw - 136, top - 30, 46, 13, 2, stroke=0, fill=1)
    c.setFillColor(white)
    c.drawCentredString(mx + mw - 113, top - 26, t["undo"])
    c.setFillColor(FIELD)
    c.rect(mx, top - 34, 160, 11, stroke=0, fill=1)
    c.setFillColor(MUTED)
    c.setFont("DV", 5.6)
    c.drawString(mx + 3, top - 31, t["filt"])
    c.setFillColor(FIELD)
    c.rect(mx, sy + 8, mw - 72, sh - 46, stroke=0, fill=1)
    ry = top - 46
    col = {"g": ORANGE, "s": BLUE, "k": GREEN, "a": white}
    for s, kind, st in t["rows"]:
        c.setFillColor(col[kind])
        c.setFont("DVB" if kind in "gs" else "DV", 5.8)
        c.drawString(mx + 4, ry, s)
        if st:
            c.setFillColor(GREEN if kind == "k" else ORANGE)
            c.drawString(mx + mw - 144, ry, st)
        ry -= 10
    px = mx + mw - 66
    c.setFillColor(PANEL)
    c.rect(px, sy + 8, 66, sh - 46, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.setFont("DVB", 6)
    c.drawString(px + 4, top - 46, t["preview"])
    c.setFillColor(HexColor("#555555"))
    c.rect(px + 6, top - 100, 54, 44, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.circle(px + 46, top - 68, 5, stroke=0, fill=1)
    p = c.beginPath()
    p.moveTo(px + 8, top - 98)
    p.lineTo(px + 26, top - 74)
    p.lineTo(px + 40, top - 90)
    p.lineTo(px + 58, top - 98)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(x + 8, y + 12, 90, 5, stroke=0, fill=1)
    c.setFillColor(GREEN)
    c.setFont("DVB", 6)
    c.drawString(x + 104, y + 12, t["done"])

    badge(c, sx + sw - 4, top - 10, 1)
    badge(c, sx + sw - 4, top - 64, 2)
    badge(c, sx + sw - 4, top - 94, 3)
    badge(c, sx + sw - 4, sy + 26, 4)
    badge(c, mx + mw - 150, top - 44, 5)
    badge(c, mx + mw - 92, top - 36, 6)
    badge(c, arch_tab_x, top + 5, 7)
    return seestar_x, cloud_x, top


def build(lang):
    t = TXT[lang]
    out = os.path.join(ROOT, "docs", t["file"])
    c = canvas.Canvas(out, pagesize=A4)
    c.setTitle(f"BildZwilling {VERSION} – Quick Guide")
    c.setAuthor("Stefan J. Kaiser DM5CQ / OE8KKS")
    c.setFillColor(BG)
    c.rect(0, H - 78, W, 78, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(0, H - 81, W, 3, stroke=0, fill=1)
    c.drawImage(os.path.join(ROOT, "assets", "icon.png"), M, H - 68, 52, 52, mask="auto")
    c.setFont("DVB", 22)
    c.drawString(M + 64, H - 40, f"BildZwilling {VERSION}")
    c.setFillColor(white)
    c.setFont("DV", 10.5)
    c.drawString(M + 64, H - 58, t["sub"])

    mock_h = 225
    mockup(c, M, H - 100 - mock_h, W - 2 * M, mock_h, t)
    c.setFillColor(MUTED)
    c.setFont("DV", 6.5)
    c.drawRightString(W - M, H - 108 - mock_h, t["caption"])

    col_w = (W - 2 * M - 16) / 2
    y_top = H - 122 - mock_h
    c.setFillColor(ORANGE)
    c.setFont("DVB", 12)
    c.drawString(M, y_top, t["steps_title"])
    y_l = y_r = y_top - 8
    for i, (title, txt) in enumerate(t["steps"], 1):
        left = i <= 4
        x = M if left else M + col_w + 16
        y = y_l if left else y_r
        badge(c, x + 7.5, y - 8, i)
        c.setFillColor(DARK)
        c.setFont("DVB", 9.3)
        c.drawString(x + 20, y - 11.5, title)
        y = para(c, txt, x + 20, y - 15, col_w - 20) - 6
        if left:
            y_l = y
        else:
            y_r = y

    y = min(y_l, y_r) - 2
    box_h = 150
    c.setFillColor(HexColor("#f4f4f4"))
    c.roundRect(M, y - box_h, W - 2 * M, box_h, 6, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(M, y - box_h, 4, box_h, stroke=0, fill=1)
    c.setFont("DVB", 10)
    c.drawString(M + 14, y - 16, t["legend_title"])
    ly = y - 32
    for colr, (name, txt) in zip((GREEN, ORANGE, YELLOW, RED, BLUE), t["legend"]):
        c.setFillColor(colr)
        c.roundRect(M + 14, ly - 2, 22, 9, 2, stroke=0, fill=1)
        c.setFillColor(DARK)
        c.setFont("DVB", 8)
        c.drawString(M + 42, ly, name)
        c.setFont("DV", 7.6)
        c.drawString(M + 84, ly, txt)
        ly -= 15
    tx = M + 232
    c.setFillColor(ORANGE)
    c.setFont("DVB", 10)
    c.drawString(tx, y - 16, t["tips_title"])
    para(c, t["tips"], tx, y - 24, W - M - tx - 12, ParagraphStyle("t", parent=body, fontSize=7.3, leading=9.3))

    c.setFillColor(BG)
    c.rect(0, 0, W, 26, stroke=0, fill=1)
    c.setFillColor(MUTED)
    c.setFont("DV", 7)
    c.drawCentredString(W / 2, 10, t["copy"].format(d=DATE[lang], v=VERSION))
    c.showPage()
    c.save()
    print(out)


if __name__ == "__main__":
    for lng in ("de", "en"):
        build(lng)
