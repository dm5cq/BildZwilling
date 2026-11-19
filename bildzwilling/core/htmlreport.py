# SPDX-License-Identifier: GPL-3.0-or-later
"""HTML-Bericht mit eingebetteten Vorschaubildern – eine einzige Datei, ohne externe Ressourcen,
zum Ansehen auf Tablet oder zweitem Rechner."""

from __future__ import annotations

import base64
import datetime as _dt
import html
import io
import os
from concurrent.futures import ThreadPoolExecutor

from .. import APP_NAME, COPYRIGHT, VERSION
from . import imaging
from .fsutil import human_size
from ..i18n import _ as tr

def KIND():
    return {"bytes": tr("byte-identisch"), "pixels": tr("Bildinhalt identisch"), "similar": tr("ähnlich")}

CSS = """
*{box-sizing:border-box}body{margin:0;background:#2b2b2b;color:#fff;font:14px/1.4 'Segoe UI',Helvetica,Arial,sans-serif}
header{background:#222;border-bottom:3px solid #ff8c00;padding:14px 20px}h1{margin:0;color:#ff8c00;font-size:24px}
.sub{color:#b0b0b0}.bar{position:sticky;top:0;background:#2b2b2b;padding:10px 20px;z-index:2;display:flex;gap:10px;flex-wrap:wrap}
input,select{background:#3c3c3c;color:#fff;border:1px solid #4a4a4a;border-radius:4px;padding:6px 8px}
main{padding:0 20px 20px}.g{background:#333;border-radius:8px;margin:14px 0;padding:12px}
.gh{color:#ff8c00;font-weight:600;margin-bottom:8px}.gh .k{color:#b0b0b0;font-weight:400}
.fs{display:flex;gap:12px;flex-wrap:wrap}.f{background:#3c3c3c;border-radius:6px;padding:8px;width:260px;border:2px solid transparent}
.f.keep{border-color:#4caf50}.f.archive{border-color:#ff8c00}.f img{width:100%;height:170px;object-fit:contain;background:#1e1e1e;border-radius:4px}
.noimg{height:170px;display:flex;align-items:center;justify-content:center;background:#1e1e1e;color:#888;border-radius:4px;text-align:center;padding:6px}
.b{display:inline-block;font-weight:700;font-size:12px;margin:6px 0 2px}.keep .b{color:#4caf50}.archive .b{color:#ff8c00}
.n{word-break:break-all;font-weight:600}.p{word-break:break-all;color:#b0b0b0;font-size:12px}.m{color:#ddd;font-size:12px}
footer{color:#8a8a8a;font-size:12px;padding:16px 20px;border-top:1px solid #444}
"""

JS = """
const q=document.getElementById('q'),k=document.getElementById('k');
function f(){const t=q.value.toLowerCase(),kv=k.value;let n=0;
document.querySelectorAll('.g').forEach(g=>{const ok=(!kv||g.dataset.kind===kv)&&(!t||g.dataset.text.includes(t));
g.style.display=ok?'':'none';if(ok)n++});document.getElementById('cnt').textContent=n+' '+CNT}
q.addEventListener('input',f);k.addEventListener('change',f);f();
"""


def _thumb(path: str, side: int) -> str | None:
    try:
        im, _ = imaging.load_preview(path, side)
        if im.mode != "RGB":
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


def csp_for(script: str) -> str:
    import base64
    import hashlib

    h = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    return ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
            f"script-src 'sha256-{h}'; base-uri 'none'; form-action 'none'")


def export_html(groups, path: str, thumbs: bool = True, max_thumb_files: int = 6000, side: int = 320,
                progress=None, cancel=None, workers: int = 4) -> int:
    """Schreibt den Bericht; liefert die Anzahl Gruppen."""
    e = html.escape
    files = [f for g in groups for f in g.files]
    tmap: dict[int, str | None] = {}
    if thumbs:
        sel = files[:max_thumb_files]
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(_thumb, f.path, side): f for f in sel}
            for n, fut in enumerate(futs, 1):
                if cancel is not None and cancel.is_set():
                    for x in futs:
                        x.cancel()
                    break
                tmap[id(futs[fut])] = fut.result()
                if progress and n % 10 == 0:
                    progress("HTML-Bericht: Vorschaubilder", n, len(sel))

    exact = [g for g in groups if g.kind != "similar"]
    parts = [
        f"<!DOCTYPE html><html lang='{tr('de')}'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{APP_NAME} – {e(tr('Bericht'))}</title><style>{CSS}</style></head><body>",
        f"<header><h1>{APP_NAME} {VERSION} – {e(tr('Bericht'))}</h1><div class='sub'>"
        + e(tr("Erstellt {0} · {1} identische Gruppen · {2} Gruppen ähnlicher Bilder · {3} freizugeben").format(
            f"{_dt.datetime.now():%d.%m.%Y %H:%M}", len(exact), len(groups) - len(exact),
            human_size(sum(g.savable for g in exact)))) + "</div></header>",
        f"<div class='bar'><input id='q' placeholder='{e(tr('Suche nach Name oder Ordner …'))}' size='40'>",
        f"<select id='k'><option value=''>{e(tr('Alle Arten'))}</option>"
        f"<option value='bytes'>{e(tr('byte-identisch'))}</option>",
        f"<option value='pixels'>{e(tr('Bildinhalt identisch'))}</option>"
        f"<option value='similar'>{e(tr('ähnlich'))}</option></select>",
        "<span id='cnt' class='sub'></span></div><main>",
    ]
    for gi, g in enumerate(groups, 1):
        text = " ".join(f.path for f in g.files).lower()
        extra = " · " + tr("Abstand {0}").format(g.distance) if g.kind == "similar" else ""
        parts.append(f"<section class='g' data-kind='{e(g.kind)}' data-text='{e(text)}'>"
                     f"<div class='gh'>{e(tr('Gruppe'))} {gi} <span class='k'>· {len(g.files)} {e(tr('Dateien'))} · "
                     f"{e(KIND().get(g.kind, g.kind))}{extra}</span></div><div class='fs'>")
        for f in g.files:
            b64 = tmap.get(id(f))
            img = (f"<img loading='lazy' alt='' src='data:image/jpeg;base64,{b64}'>" if b64
                   else f"<div class='noimg'>{e(tr('keine Vorschau'))}</div>")
            dims = f" · {f.dims[0]}×{f.dims[1]}" if f.dims else ""
            date = _dt.datetime.fromtimestamp(f.mtime).strftime("%d.%m.%Y %H:%M")
            badge = "✔ " + tr("BEHALTEN") if f.action == "keep" else "➜ " + tr("ARCHIV")
            parts.append(f"<div class='f {e(f.action)}'>{img}<div class='b'>{badge}</div>"
                         f"<div class='n'>{e(os.path.basename(f.path))}</div>"
                         f"<div class='p'>{e(os.path.dirname(f.path))}</div>"
                         f"<div class='m'>{e(human_size(f.size))}{e(dims)} · {date}</div></div>")
        parts.append("</div></section>")
    import json as _json
    script = f"const CNT={_json.dumps(tr('Gruppen'))};{JS}".replace("</", "<\\/")
    parts.append(f"</main><footer>{e(COPYRIGHT)}</footer><script>{script}</script></body></html>")
    # Content-Security-Policy (2.2, B6): nur das eigene, per Prüfsumme freigegebene Skript, eingebettete
    # Bilder (data:) und Stile – keine Netzwerkzugriffe, keine fremden Skripte, keine Formulare.
    parts[1] = parts[1] + "<meta http-equiv='Content-Security-Policy' content=\"" + csp_for(script) + "\">"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(parts))
    os.replace(tmp, path)
    return len(groups)
