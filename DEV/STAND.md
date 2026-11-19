# BildZwilling – Entwicklungsstand 2.2 (18.11.2026)

## Status
- 61 Unit-Tests grün (`python -m unittest discover -s tests`; 1 nur unter Windows), plus optionaler ExifRead-Test
- Typprüfung: `python -m pyright` → 0 Fehler (auch mit `--pythonplatform Windows` und `Darwin`)
- Oberfläche per Ablauftest (Tk-Attrappe) durchlaufen: smoke20 (de/en), smoke21, smoke22
- **Noch nicht real geprüft:** Optik des neuen Info-Fensters unter Windows, echte Cloud-Konten (inkl. 2FA),
  echte Seestar-Daten, DPAPI, Sperre/Ruhezustand unter Windows (Code + Tests vorhanden)

## Neu in 2.2 (Module)
- `legal.py` Lizenz-/Haftungstexte · `gui/about.py` Info-Fenster, Textanzeige, Haftungshinweis beim Start
- `core/instance.py` Einzelinstanz · `core/power.py` Ruhezustand verhindern · `core/logutil.py` Schwärzung
- `core/sysinfo.py` Systeminfo · `core/maintenance.py` Temp/Cache-Wartung
- `archive.py`: `begin_session`/`end_session`/`incomplete_sessions` · `settings.py`: .bak + Wiederherstellung
- `LICENSE`, `THIRD_PARTY_LICENSES.txt` (DEV/make_third_party.py), `pyrightconfig.json`

## Regeln
- Neue Quelldateien beginnen mit `# SPDX-License-Identifier: GPL-3.0-or-later` (Test prüft das)
- Neue Texte mit `_("…")`/`tr("…")` + Englisch in `bildzwilling/i18n_en.py`
- Copyright nur über `bildzwilling.COPYRIGHT`

## Nächste Schritte (Technische Beschreibung: Code-Review 2.2 und Verbesserungsvorschläge)
R12 Code-Signatur (z. B. SignPath) · R13 Quellcode auf GitHub + Link im Info-Fenster · R14 Update-Hinweis ·
R15 Journal-Prüfsummen · R4 app.py aufteilen · Q2 echte Oberflächentests · Q3 echte Beispieldateien · V18–V30
