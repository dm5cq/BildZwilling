# SPDX-License-Identifier: GPL-3.0-or-later
"""Direkte Cloud-Anbindung: pCloud und OneDrive über die offiziellen Web-Schnittstellen.

Duplikate werden anhand der Prüfsummen erkannt, die der Server liefert – es wird NICHTS heruntergeladen
(außer kleinen Vorschaubildern auf Wunsch). Verschoben wird innerhalb der Cloud in einen Archivordner;
jede Aktion steht in einem lokalen Journal und lässt sich rückgängig machen.

pCloud:   Ordnerliste liefert Größe + 64-Bit-Inhalts-Hash; Bestätigung über checksumfile
          (Europa: SHA-256, USA: SHA-1). Anmeldung mit E-Mail/Passwort (getauth) über HTTPS.
OneDrive: Microsoft Graph, Anmeldung per Gerätecode (eigene App-Registrierung mit Client-ID nötig).
          Prüfsumme: quickXorHash (laut Microsoft der einzige für privat und geschäftlich garantierte Hash).
"""

from __future__ import annotations

from typing import Any

import datetime as _dt
import email.utils
import json
import os
import posixpath
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .formats import is_image, is_video
from .scanner import DuplicateGroup, FileEntry, apply_keep_rule
from ..i18n import _ as tr

PCLOUD_HOSTS = {"pcloud_eu": "https://eapi.pcloud.com", "pcloud_us": "https://api.pcloud.com"}
GRAPH = "https://graph.microsoft.com/v1.0"
MS_LOGIN = "https://login.microsoftonline.com/common/oauth2/v2.0"
PROVIDERS = {"pcloud_eu": "pCloud (Europa)", "pcloud_us": "pCloud (USA)", "onedrive": "OneDrive"}
_LOCAL_TEST_HOSTS = {"127.0.0.1", "localhost"}


class CloudError(Exception):
    pass


class TwoFactorRequired(CloudError):
    """pCloud verlangt einen Zwei-Faktor-Code (Konto mit 2FA)."""

    def __init__(self, msg: str, tfa_token: str = "", via_sms: bool = False):
        super().__init__(msg)
        self.tfa_token = tfa_token
        self.via_sms = via_sms


PCLOUD_AUTHORIZE = "https://my.pcloud.com/oauth2/authorize"


# --------------------------------------------------------------------------- HTTP

class _NoAuthLeakRedirect(urllib.request.HTTPRedirectHandler):
    """Bei Weiterleitung auf einen anderen Host (z. B. CDN für Vorschaubilder) Anmeldedaten entfernen."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            for h in ("Authorization", "authorization"):
                new.headers.pop(h, None)
                new.unredirected_hdrs.pop(h, None)
        return new


class Http:
    def __init__(self, timeout: float = 30):
        self.timeout = timeout
        self.opener = urllib.request.build_opener(_NoAuthLeakRedirect())
        # lokale Testserver nie über einen System-Proxy ansprechen
        self.local_opener = urllib.request.build_opener(_NoAuthLeakRedirect(), urllib.request.ProxyHandler({}))

    @staticmethod
    def _check_url(url: str):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in _LOCAL_TEST_HOSTS):
            raise CloudError(tr('Nur verschlüsselte Verbindungen (HTTPS) sind erlaubt.'))

    def request(self, method: str, url: str, data=None, headers=None, raw: bool = False, retries: int = 4):
        self._check_url(url)
        body = None
        hdrs = {"User-Agent": "BildZwilling/2.0"}
        hdrs.update(headers or {})
        if isinstance(data, dict):
            if hdrs.get("Content-Type") == "application/json":
                body = json.dumps(data).encode("utf-8")
            else:
                body = urllib.parse.urlencode(data).encode("utf-8")
                hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
        delay = 1.0
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            try:
                op = self.local_opener if urllib.parse.urlsplit(url).hostname in _LOCAL_TEST_HOSTS else self.opener
                with op.open(req, timeout=self.timeout) as r:
                    content = r.read()
                    return content if raw else (json.loads(content.decode("utf-8")) if content else {})
            except urllib.error.HTTPError as e:
                payload = e.read()
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    ra = e.headers.get("Retry-After")
                    time.sleep(min(30.0, float(ra)) if ra and ra.isdigit() else delay)
                    delay *= 2
                    continue
                try:
                    j = json.loads(payload.decode("utf-8"))
                except ValueError:
                    j = {}
                err = j.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("code")
                else:
                    msg = j.get("error_description") or err or payload[:200].decode("utf-8", "replace")
                e2 = CloudError(tr('HTTP {0}: {1}').format(e.code, msg))
                e2.status = e.code  # type: ignore[attr-defined]
                e2.payload = j  # type: ignore[attr-defined]
                raise e2 from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise CloudError(tr('Verbindung fehlgeschlagen: {0}').format(getattr(e, 'reason', e))) from None
        raise CloudError(tr('Zu viele Wiederholungen'))


# --------------------------------------------------------------------------- Datenmodell

class CloudItem:
    __slots__ = ("id", "name", "path", "parent_id", "size", "mtime", "qhash", "strong")

    def __init__(self, id, name, path, parent_id, size, mtime, qhash, strong=None):
        self.id, self.name, self.path, self.parent_id = str(id), name, path, str(parent_id)
        self.size, self.mtime, self.qhash, self.strong = int(size), float(mtime), str(qhash or ""), strong


def _parse_rfc1123(s: str) -> float:
    try:
        return email.utils.parsedate_to_datetime(s).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _parse_iso(s: str) -> float:
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _norm_path(p: str) -> str:
    p = "/" + (p or "").replace("\\", "/").strip("/")
    p = posixpath.normpath(p)
    if ".." in p.split("/"):
        raise CloudError(tr('Ungültiger Cloud-Pfad'))
    return p if p != "//" else "/"


# --------------------------------------------------------------------------- pCloud

class PCloud:
    kind = "pcloud"

    def __init__(self, region: str = "pcloud_eu", base: str | None = None, http: Http | None = None):
        self.base = base or PCLOUD_HOSTS.get(region, PCLOUD_HOSTS["pcloud_eu"])
        self.region = region
        self.http = http or Http()
        self.token = ""
        self.bearer = False        # True = OAuth-Token (Authorization: Bearer)
        self._hosts = [self.base] if base else [PCLOUD_HOSTS.get(region, PCLOUD_HOSTS["pcloud_eu"])] + [
            h for k, h in PCLOUD_HOSTS.items() if k != region]

    @property
    def strong_algo(self) -> str:
        return "sha1" if self.region == "pcloud_us" else "sha256"

    def _call(self, method: str, params: dict, post: bool = False, raw: bool = False, base: str | None = None) -> Any:
        p = dict(params)
        headers = {}
        if self.token and self.bearer:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.token:
            p["auth"] = self.token
        b = base or self.base
        if post:
            res = self.http.request("POST", f"{b}/{method}", data=p, raw=raw, headers=headers)
        else:
            res = self.http.request("GET", f"{b}/{method}?" + urllib.parse.urlencode(p), raw=raw, headers=headers)
        if raw:
            assert isinstance(res, bytes)
            if res[:1] == b"{":
                j = json.loads(res.decode("utf-8"))
                raise CloudError(tr('pCloud: {0} ({1})').format(j.get('error', 'Fehler'), j.get('result')))
            return res
        if res.get("result", 0) != 0:
            e = CloudError(tr('pCloud: {0} ({1})').format(res.get('error', 'Fehler'), res.get('result')))
            e.result = res.get("result")  # type: ignore[attr-defined]
            e.payload = res  # type: ignore[attr-defined]
            raise e
        return res

    @staticmethod
    def _is_2fa(e: CloudError) -> bool:
        res = getattr(e, "payload", {}) or {}
        txt = str(res.get("error", "")).lower()
        return res.get("result") in (2297,) or "2fa" in txt or "factor" in txt or "tfa" in txt

    def login(self, username: str, password: str) -> str:
        """Anmeldung mit E-Mail/Passwort. Bei Konten mit 2FA wird TwoFactorRequired ausgelöst."""
        try:
            res = self._call("userinfo", {"getauth": 1, "logout": 1, "username": username, "password": password},
                             post=True)
        except CloudError as e:
            if self._is_2fa(e):
                pl = getattr(e, "payload", {}) or {}
                raise TwoFactorRequired(tr("pCloud verlangt einen Sicherheitscode (Zwei-Faktor-Anmeldung)."),
                                        str(pl.get("token", "")), bool(pl.get("sms") or pl.get("viasms"))) from None
            raise
        self.token = res.get("auth", "")
        self.bearer = False
        if not self.token:
            raise CloudError(tr('pCloud: keine Anmeldung erhalten'))
        return self.save_token()

    def login_2fa(self, tfa_token: str, code: str, trust_device: bool = True) -> str:
        """Zweiter Schritt der Passwort-Anmeldung: Sicherheitscode (App/SMS) oder Wiederherstellungscode."""
        code = "".join(ch for ch in str(code) if ch.isalnum())
        params = {"token": tfa_token, "code": code, "getauth": 1}
        if trust_device:
            params["trustdevice"] = 1
        res = self._call("tfa_login", params, post=True)
        self.token = res.get("auth", "")
        self.bearer = False
        if not self.token:
            raise CloudError(tr('pCloud: keine Anmeldung erhalten'))
        return self.save_token()

    @staticmethod
    def oauth_url(client_id: str, state: str = "") -> str:
        """Adresse der pCloud-Anmeldeseite (OAuth 2.0, Code wird dem Nutzer angezeigt)."""
        q = {"client_id": client_id.strip(), "response_type": "code"}
        if state:
            q["state"] = state
        return PCLOUD_AUTHORIZE + "?" + urllib.parse.urlencode(q)

    def oauth_finish(self, client_id: str, client_secret: str, code: str) -> str:
        """Code gegen Zugriffstoken tauschen. Der Server-Standort (EU/US) wird automatisch ermittelt."""
        last = None
        params = {"client_id": client_id.strip(), "client_secret": client_secret.strip(), "code": code.strip()}
        for host in self._hosts:
            try:
                res = self._call("oauth2_token", params, base=host)
            except CloudError as e:
                last = e
                continue
            tok = res.get("access_token", "")
            if tok:
                self.base, self.token, self.bearer = host, tok, True
                self.region = next((k for k, h in PCLOUD_HOSTS.items() if h == host), self.region)
                return self.save_token()
        raise last or CloudError(tr('pCloud: keine Anmeldung erhalten'))

    def save_token(self) -> str:
        """Token-Zeichenkette zum (verschlüsselten) Merken – enthält Art und Server."""
        return f"oauth|{self.base}|{self.token}" if self.bearer else self.token

    def set_token(self, token: str) -> None:
        if token.startswith("oauth|"):
            _, host, tok = token.split("|", 2)
            if host in PCLOUD_HOSTS.values() or urllib.parse.urlsplit(host).hostname in _LOCAL_TEST_HOSTS:
                self.base = host
            self.token, self.bearer = tok, True
        else:
            self.token, self.bearer = token, False

    def account(self) -> str:
        return str(self._call("userinfo", {}).get("email", ""))

    def logout(self) -> None:
        try:
            if not self.bearer:
                self._call("logout", {})
        finally:
            self.token, self.bearer = "", False

    def list_files(self, path: str, cancel=None) -> list[CloudItem]:
        path = _norm_path(path)
        res = self._call("listfolder", {"path": path, "recursive": 1, "noshares": 1})
        out: list[CloudItem] = []

        def walk(node, base):
            for c in node.get("contents", []) or []:
                if cancel is not None and cancel.is_set():
                    return
                p = posixpath.join(base, c.get("name", ""))
                if c.get("isfolder"):
                    walk(c, p)
                else:
                    out.append(CloudItem(c.get("fileid"), c.get("name", ""), p, c.get("parentfolderid", 0),
                                         c.get("size", 0), _parse_rfc1123(c.get("modified", "")), c.get("hash")))

        walk(res.get("metadata", {}), path)
        return out

    def strong_hash(self, item: CloudItem) -> str:
        res = self._call("checksumfile", {"fileid": item.id})
        h = res.get("sha256") or res.get("sha1")
        if not h:
            raise CloudError(tr('pCloud: keine Prüfsumme erhalten'))
        return h

    def stat(self, item_id: str) -> CloudItem | None:
        try:
            m = self._call("stat", {"fileid": item_id}).get("metadata", {})
        except CloudError:
            return None
        if not m or m.get("isdeleted"):
            return None
        return CloudItem(m.get("fileid"), m.get("name", ""), m.get("path", ""), m.get("parentfolderid", 0),
                         m.get("size", 0), _parse_rfc1123(m.get("modified", "")), m.get("hash"))

    def ensure_folder(self, path: str) -> str:
        path = _norm_path(path)
        if path == "/":
            return "0"
        folder_id = "0"
        for part in path.strip("/").split("/"):
            res = self._call("createfolderifnotexists", {"folderid": folder_id, "name": part})
            folder_id = str(res.get("metadata", {}).get("folderid"))
        return folder_id

    def _names_in(self, folder_id: str) -> set[str]:
        res = self._call("listfolder", {"folderid": folder_id})
        return {str(c.get("name", "")).lower() for c in res.get("metadata", {}).get("contents", []) or []}

    def move(self, item_id: str, folder_id: str, name: str) -> CloudItem:
        # Zielnamen vorher prüfen: es wird nie eine vorhandene Datei überschrieben
        taken = self._names_in(folder_id)
        stem, ext = posixpath.splitext(name)
        new = name
        i = 1
        while new.lower() in taken:
            new = f"{stem} ({i}){ext}"
            i += 1
            if i > 9999:
                raise CloudError(tr('Kein freier Dateiname im Zielordner'))
        m = self._call("renamefile", {"fileid": item_id, "tofolderid": folder_id, "toname": new})
        md = m.get("metadata", {})
        return CloudItem(md.get("fileid", item_id), md.get("name", new), md.get("path", ""), folder_id,
                         md.get("size", 0), 0, md.get("hash"))

    def thumbnail(self, item_id: str, size: int = 512) -> bytes:
        data = self._call("getthumb", {"fileid": item_id, "size": f"{size}x{size}", "type": "jpg"}, raw=True)
        return data if isinstance(data, bytes) else b""


# --------------------------------------------------------------------------- OneDrive

class OneDrive:
    kind = "onedrive"
    strong_algo = "quickXorHash"
    SCOPE = "Files.ReadWrite offline_access User.Read"

    def __init__(self, client_id: str = "", graph: str = GRAPH, login: str = MS_LOGIN, http: Http | None = None):
        self.client_id = client_id.strip()
        self.graph, self.login_url = graph, login
        self.http = http or Http()
        self.token = ""
        self.refresh_token = ""
        self._expires = 0.0
        self._lock = threading.Lock()

    def _auth(self):
        if self.refresh_token and time.time() > self._expires - 120:
            self.refresh()
        if not self.token:
            raise CloudError(tr('OneDrive: nicht angemeldet'))
        return {"Authorization": f"Bearer {self.token}"}

    def device_login(self, on_code, cancel=None) -> str:
        """Gerätecode-Anmeldung. on_code(user_code, verification_uri, message) zeigt den Code an."""
        if not self.client_id:
            raise CloudError(tr('OneDrive: Bitte zuerst eine Client-ID (App-Registrierung) eintragen.'))
        r = self.http.request("POST", f"{self.login_url}/devicecode",
                              data={"client_id": self.client_id, "scope": self.SCOPE})
        on_code(r.get("user_code", ""), r.get("verification_uri", ""), r.get("message", ""))
        interval = max(1, int(r.get("interval", 5)))
        deadline = time.time() + int(r.get("expires_in", 900))
        while time.time() < deadline:
            if cancel is not None and cancel.is_set():
                raise CloudError(tr('Anmeldung abgebrochen'))
            time.sleep(interval)
            try:
                t = self.http.request("POST", f"{self.login_url}/token", retries=0, data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.client_id, "device_code": r.get("device_code", "")})
            except CloudError as e:
                code = (getattr(e, "payload", {}) or {}).get("error", "")
                if code == "authorization_pending":
                    continue
                if code == "slow_down":
                    interval += 5
                    continue
                raise
            self._set_tokens(t)
            return self.refresh_token
        raise CloudError(tr('OneDrive: Code abgelaufen – bitte erneut anmelden'))

    def _set_tokens(self, t: dict):
        self.token = t.get("access_token", "")
        self.refresh_token = t.get("refresh_token", self.refresh_token)
        self._expires = time.time() + int(t.get("expires_in", 3600))

    def refresh(self):
        with self._lock:
            if self.token and time.time() < self._expires - 120:
                return
            t = self.http.request("POST", f"{self.login_url}/token", data={
                "grant_type": "refresh_token", "client_id": self.client_id,
                "refresh_token": self.refresh_token, "scope": self.SCOPE})
            self._set_tokens(t)

    def set_token(self, refresh_token: str) -> None:
        self.refresh_token = refresh_token
        self.token = ""
        self._expires = 0

    def logout(self) -> None:
        self.token = self.refresh_token = ""

    def _get(self, url: str):
        return self.http.request("GET", url if url.startswith("http") else self.graph + url, headers=self._auth())

    @staticmethod
    def _q(path: str) -> str:
        return urllib.parse.quote(path.strip("/"), safe="/")

    def account(self) -> str:
        me = self._get("/me")
        return str(me.get("userPrincipalName") or me.get("mail") or me.get("displayName") or "")

    def _item_by_path(self, path: str):
        path = _norm_path(path)
        return self._get("/me/drive/root" if path == "/" else f"/me/drive/root:/{self._q(path)}")

    def list_files(self, path: str, cancel=None) -> list[CloudItem]:
        path = _norm_path(path)
        root = self._item_by_path(path)
        out: list[CloudItem] = []
        stack = [(root["id"], path)]
        sel = "$select=id,name,size,file,folder,parentReference,lastModifiedDateTime&$top=999"
        while stack:
            if cancel is not None and cancel.is_set():
                break
            fid, base = stack.pop()
            url = f"/me/drive/items/{fid}/children?{sel}"
            while url:
                page = self._get(url)
                for c in page.get("value", []):
                    p = posixpath.join(base, c.get("name", ""))
                    if "folder" in c:
                        stack.append((c["id"], p))
                    elif "file" in c:
                        h = (c.get("file", {}).get("hashes") or {})
                        out.append(CloudItem(c["id"], c.get("name", ""), p, fid, c.get("size", 0),
                                             _parse_iso(c.get("lastModifiedDateTime", "")),
                                             h.get("quickXorHash") or h.get("sha1Hash") or ""))
                url = page.get("@odata.nextLink", "")
        return out

    def strong_hash(self, item: CloudItem) -> str:
        if not item.qhash:
            raise CloudError(tr('OneDrive: keine Prüfsumme für diese Datei'))
        return item.qhash

    def stat(self, item_id: str) -> CloudItem | None:
        try:
            c = self._get(f"/me/drive/items/{item_id}")
        except CloudError as e:
            if getattr(e, "status", 0) == 404:
                return None
            raise
        h = (c.get("file", {}) or {}).get("hashes") or {}
        return CloudItem(c["id"], c.get("name", ""), "", (c.get("parentReference") or {}).get("id", ""),
                         c.get("size", 0), _parse_iso(c.get("lastModifiedDateTime", "")),
                         h.get("quickXorHash") or h.get("sha1Hash") or "")

    def ensure_folder(self, path: str) -> str:
        path = _norm_path(path)
        cur = self._item_by_path("/")
        built = ""
        for part in [p for p in path.strip("/").split("/") if p]:
            built += "/" + part
            try:
                cur = self._item_by_path(built)
            except CloudError as e:
                if getattr(e, "status", 0) != 404:
                    raise
                cur = self.http.request("POST", f"{self.graph}/me/drive/items/{cur['id']}/children",
                                        data={"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
                                        headers={**self._auth(), "Content-Type": "application/json"})
        return cur["id"]

    def move(self, item_id: str, folder_id: str, name: str) -> CloudItem:
        for i in range(0, 50):
            new = name if i == 0 else f"{posixpath.splitext(name)[0]} ({i}){posixpath.splitext(name)[1]}"
            try:
                c = self.http.request("PATCH", f"{self.graph}/me/drive/items/{item_id}",
                                      data={"parentReference": {"id": folder_id}, "name": new},
                                      headers={**self._auth(), "Content-Type": "application/json"})
                return CloudItem(c.get("id", item_id), c.get("name", new), "", folder_id, c.get("size", 0), 0, "")
            except CloudError as e:
                if getattr(e, "status", 0) != 409:
                    raise
        raise CloudError(tr('Verschieben fehlgeschlagen (Namenskonflikt)'))

    def thumbnail(self, item_id: str, size: int = 512) -> bytes:
        data = self.http.request("GET", f"{self.graph}/me/drive/items/{item_id}/thumbnails/0/large/content",
                                 headers=self._auth(), raw=True)
        return data if isinstance(data, bytes) else b""


def make_client(provider: str, client_id: str = ""):
    if provider == "onedrive":
        return OneDrive(client_id)
    return PCloud(provider)


# --------------------------------------------------------------------------- Suche

def scan(client, root: str, images_only=True, include_videos=False, min_size=1024, keep_rule="oldest",
         folder_rules=(), workers=4, progress=None, log=None, cancel=None) -> list[DuplicateGroup]:
    progress = progress or (lambda *a: None)
    log = log or (lambda *a: None)
    root = _norm_path(root)
    progress("Cloud: Dateiliste laden", 0, 0)
    items = client.list_files(root, cancel)
    files = [i for i in items if i.size >= min_size and
             (not images_only or is_image(i.name) or (include_videos and is_video(i.name)))]
    log("info", tr('Cloud: {0} Dateien gelistet, {1} werden verglichen.').format(len(items), len(files)))
    # Stufe 1: Größe + Listen-Hash (ohne zusätzliche Anfragen)
    buckets = defaultdict(list)
    for i in files:
        buckets[(i.size, i.qhash or f"nohash:{i.id}")].append(i)
    cand = [lst for lst in buckets.values() if len(lst) > 1]
    flat = [i for lst in cand for i in lst]
    # Stufe 2: starke Prüfsumme vom Server (pCloud: SHA-256/SHA-1; OneDrive: quickXorHash)
    if flat:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(client.strong_hash, i): i for i in flat}
            for n, fut in enumerate(futs, 1):
                if cancel is not None and cancel.is_set():
                    for x in futs:
                        x.cancel()
                    break
                try:
                    futs[fut].strong = fut.result()
                except CloudError as e:
                    log("warn", tr('Prüfsumme fehlt: {0} ({1})').format(futs[fut].path, e))
                progress("Cloud: Server-Prüfsummen", n, len(flat))
    groups = []
    for lst in cand:
        by = defaultdict(list)
        for i in lst:
            if i.strong:
                by[i.strong].append(i)
        for same in by.values():
            if len(same) < 2:
                continue
            entries = []
            for i in same:
                f = FileEntry(i.path, i.size, int(i.mtime * 1e9), root, 0, digest=i.strong)
                f.cloud = i  # type: ignore[attr-defined]
                entries.append(f)
            g = DuplicateGroup(0, "bytes", entries)
            apply_keep_rule(g, keep_rule, folder_rules)
            groups.append(g)
    groups.sort(key=lambda g: -g.savable)
    for n, g in enumerate(groups, 1):
        g.gid = n
    return groups


# --------------------------------------------------------------------------- Archiv & Rückgängig

class CloudJournal:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def append(self, rec: dict) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

    def active(self, provider: str = "") -> list[dict]:
        moves: dict[str, dict] = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("op") == "move" and (not provider or r.get("provider") == provider):
                        moves[r.get("rid", "")] = r
                    elif r.get("op") == "restore":
                        moves.pop(r.get("rid", ""), None)
        except FileNotFoundError:
            pass
        return list(moves.values())


class CloudArchive:
    def __init__(self, client, archive_root: str, journal_path: str, provider: str, account: str = ""):
        self.c = client
        self.root = _norm_path(archive_root)
        self.journal = CloudJournal(journal_path)
        self.provider = provider
        self.account = account
        self._folders: dict[str, str] = {}

    def _folder(self, path: str) -> str:
        if path not in self._folders:
            self._folders[path] = self.c.ensure_folder(path)
        return self._folders[path]

    def verify(self, dup: FileEntry, keep: FileEntry) -> tuple[bool, str]:
        d, k = dup.cloud, keep.cloud  # type: ignore[attr-defined]
        if dup.path == keep.path or d.id == k.id:
            return False, tr('dieselbe Datei')
        sd, sk = self.c.stat(d.id), self.c.stat(k.id)
        if sd is None:
            return False, tr('Duplikat existiert nicht mehr in der Cloud')
        if sk is None:
            return False, tr('Original existiert nicht mehr in der Cloud')
        if sd.size != d.size or (sd.qhash and d.qhash and sd.qhash != d.qhash):
            return False, tr('Duplikat wurde seit der Suche verändert')
        if sk.size != k.size or (sk.qhash and k.qhash and sk.qhash != k.qhash):
            return False, tr('Original wurde seit der Suche verändert')
        if self.c.kind == "pcloud":
            if self.c.strong_hash(d) != self.c.strong_hash(k):
                return False, tr('Server-Prüfsummen unterscheiden sich')
        return True, tr('Server-Prüfsumme bestätigt')

    def archive(self, dup: FileEntry, keep: FileEntry, session: str) -> tuple[bool, str]:
        if dup.path == self.root or dup.path.startswith(self.root.rstrip("/") + "/"):
            return False, tr('liegt bereits im Cloud-Archiv')
        ok, why = self.verify(dup, keep)
        if not ok:
            return False, why
        d = dup.cloud  # type: ignore[attr-defined]
        rel_dir = posixpath.dirname(d.path).strip("/")
        target_dir = posixpath.join(self.root, rel_dir) if rel_dir else self.root
        moved = self.c.move(d.id, self._folder(target_dir), d.name)
        self.journal.append({
            "v": 1, "op": "move", "rid": uuid.uuid4().hex, "time": _dt.datetime.now().isoformat(timespec="seconds"),
            "provider": self.provider, "account": self.account, "id": moved.id, "src": d.path,
            "src_parent": d.parent_id, "name": d.name, "dst": posixpath.join(target_dir, moved.name),
            "keep": keep.path, "size": d.size, "hash": d.strong or d.qhash, "session": session,
        })
        return True, why

    def entries(self) -> list[dict]:
        return self.journal.active(self.provider)

    def last_session(self) -> tuple[str, list[dict]]:
        sess: dict[str, list[dict]] = {}
        order: dict[str, int] = {}
        for n, e in enumerate(self.entries()):
            sid = e.get("session") or ""
            if sid:
                sess.setdefault(sid, []).append(e)
                order[sid] = n
        if not sess:
            return "", []
        sid = max(order, key=lambda k: order[k])
        return sid, sess[sid]

    def restore(self, rec: dict) -> str:
        item = self.c.move(rec["id"], rec["src_parent"], rec["name"])
        self.journal.append({"v": 1, "op": "restore", "rid": rec["rid"], "provider": self.provider,
                             "time": _dt.datetime.now().isoformat(timespec="seconds"), "name": item.name})
        return posixpath.join(posixpath.dirname(rec["src"]), item.name)

    def undo_session(self, session: str) -> tuple[int, list[str]]:
        n, errors = 0, []
        for e in self.entries():
            if e.get("session") == session:
                try:
                    self.restore(e)
                    n += 1
                except CloudError as ex:
                    errors.append(f"{e.get('src')}: {ex}")
        return n, errors
