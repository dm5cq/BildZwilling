# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests der Cloud-Anbindung gegen einen lokalen Testserver (pCloud- und Graph-Nachbildung)."""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bildzwilling.core import cloud  # noqa: E402

TOKEN = "TOKEN123"


class FakePCloud:
    def __init__(self):
        self.folders = {0: ("", None), 1: ("Fotos", 0), 2: ("Urlaub", 1)}
        self.files = {
            10: dict(name="a.jpg", parent=1, size=5000, hash=111, sha="S1"),
            11: dict(name="kopie von a.jpg", parent=2, size=5000, hash=111, sha="S1"),
            12: dict(name="b.jpg", parent=1, size=5000, hash=222, sha="S2"),
            13: dict(name="kollision.jpg", parent=2, size=5000, hash=111, sha="S9"),   # Listen-Hash gleich, SHA nicht
            14: dict(name="notiz.txt", parent=1, size=5000, hash=111, sha="S1"),
        }
        self.next_id = 100

    def meta_folder(self, fid, recursive):
        name, parent = self.folders[fid]
        m = {"isfolder": True, "folderid": fid, "name": name, "parentfolderid": parent, "contents": []}
        for k, (n, p) in self.folders.items():
            if p == fid:
                m["contents"].append(self.meta_folder(k, recursive) if recursive else
                                     {"isfolder": True, "folderid": k, "name": n})
        for k, f in self.files.items():
            if f["parent"] == fid:
                m["contents"].append(self.meta_file(k))
        return m

    def meta_file(self, k):
        f = self.files[k]
        return {"isfolder": False, "fileid": k, "name": f["name"], "parentfolderid": f["parent"],
                "size": f["size"], "hash": f["hash"], "modified": "Fri, 26 Apr 2013 14:52:02 +0000"}

    def path_to_id(self, path):
        cur = 0
        for part in [p for p in path.strip("/").split("/") if p]:
            cur = next(k for k, (n, p) in self.folders.items() if p == cur and n == part)
        return cur

    def handle(self, method, q, bearer=None):
        if method == "userinfo":
            if "username" in q:
                if q.get("password") != "geheim":
                    return {"result": 2000, "error": "Log in failed."}
                if q["username"].startswith("2fa"):
                    return {"result": 2297, "error": "Please provide 2FA code.", "token": "TFATOK"}
                return {"result": 0, "auth": TOKEN, "email": q["username"]}
            if bearer == "Bearer OAT" or q.get("auth") == TOKEN:
                return {"result": 0, "email": "stefan@example.org"}
            return {"result": 1000, "error": "Log in required."}
        if method == "tfa_login":
            if q.get("token") == "TFATOK" and q.get("code") == "123456":
                return {"result": 0, "auth": TOKEN}
            return {"result": 2064, "error": "Invalid code."}
        if method == "oauth2_token":
            if (q.get("client_id"), q.get("client_secret"), q.get("code")) == ("app", "sec", "CODE"):
                return {"result": 0, "access_token": "OAT", "token_type": "bearer", "uid": 1}
            return {"result": 2012, "error": "Invalid code."}
        if q.get("auth") != TOKEN and bearer != "Bearer OAT":
            return {"result": 1000, "error": "Log in required."}
        if method == "listfolder":
            fid = int(q["folderid"]) if "folderid" in q else self.path_to_id(q["path"])
            return {"result": 0, "metadata": self.meta_folder(fid, q.get("recursive") == "1")}
        if method == "checksumfile":
            return {"result": 0, "sha256": self.files[int(q["fileid"])]["sha"]}
        if method == "stat":
            k = int(q["fileid"])
            if k not in self.files:
                return {"result": 2009, "error": "File not found."}
            return {"result": 0, "metadata": self.meta_file(k)}
        if method == "createfolderifnotexists":
            parent, name = int(q["folderid"]), q["name"]
            for k, (n, p) in self.folders.items():
                if p == parent and n == name:
                    return {"result": 0, "metadata": {"folderid": k}}
            self.next_id += 1
            self.folders[self.next_id] = (name, parent)
            return {"result": 0, "metadata": {"folderid": self.next_id}}
        if method == "renamefile":
            k, to, name = int(q["fileid"]), int(q["tofolderid"]), q["toname"]
            if any(f["parent"] == to and f["name"] == name for f in self.files.values()):
                return {"result": 2004, "error": "File or folder alredy exists."}
            self.files[k].update(parent=to, name=name)
            return {"result": 0, "metadata": self.meta_file(k)}
        if method == "getthumb":
            return b"\xff\xd8\xff\xe0FAKEJPEG"
        return {"result": 2000, "error": "unknown"}


class FakeGraph:
    def __init__(self):
        self.items = {"root": dict(name="root", parent=None, folder=True)}
        self.add("F1", "Bilder", "root", folder=True)
        self.add("F2", "Alt", "F1", folder=True)
        for i, (n, p, h) in enumerate([("x.jpg", "F1", "QX1"), ("x - Kopie.jpg", "F2", "QX1"), ("y.jpg", "F1", "QY"),
                                       ("z.jpg", "F2", "QX1"), ("w.jpg", "F1", "QW")]):
            self.add(f"I{i}", n, p, size=7000, qx=h)
        self.polls = 0
        self.tokens_issued = 0

    def add(self, id, name, parent, folder=False, size=0, qx=None):
        self.items[id] = dict(name=name, parent=parent, folder=folder, size=size, qx=qx)

    def item_json(self, id):
        it = self.items[id]
        j = {"id": id, "name": it["name"], "parentReference": {"id": it["parent"]},
             "lastModifiedDateTime": "2026-11-17T10:00:00Z"}
        if it["folder"]:
            j["folder"] = {}
        else:
            j["size"] = it["size"]
            j["file"] = {"hashes": {"quickXorHash": it["qx"]}}
        return j

    def by_path(self, path):
        cur = "root"
        for part in [p for p in path.strip("/").split("/") if p]:
            nxt = [k for k, v in self.items.items() if v["parent"] == cur and v["name"] == part]
            if not nxt:
                return None
            cur = nxt[0]
        return cur


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json", headers=None):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        if self.headers.get("Content-Type", "").startswith("application/json"):
            return json.loads(raw or b"{}")
        return dict(urllib.parse.parse_qsl(raw.decode()))

    def route(self, method):
        srv = self.server
        u = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        srv.seen_headers.append(dict(self.headers))
        if u.path.startswith("/pc/"):
            if method == "POST":
                q.update(self._body())
            res = srv.pc.handle(u.path[4:], q, self.headers.get("Authorization"))
            return self._send(200, res, "image/jpeg" if isinstance(res, bytes) else "application/json")
        if u.path == "/redirect":
            return self._send(302, b"", headers={"Location": srv.other + "/echo"})
        if u.path == "/echo":
            return self._send(200, {"auth": self.headers.get("Authorization")})
        g = srv.g
        if u.path == "/login/devicecode":
            return self._send(200, {"user_code": "ABCD-1234", "verification_uri": "https://microsoft.com/devicelogin",
                                    "device_code": "DC", "interval": 1, "expires_in": 60, "message": "Code eingeben"})
        if u.path == "/login/token":
            b = self._body()
            if b.get("grant_type", "").endswith("device_code"):
                g.polls += 1
                if g.polls < 2:
                    return self._send(400, {"error": "authorization_pending"})
            g.tokens_issued += 1
            return self._send(200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
        if self.headers.get("Authorization") != "Bearer AT":
            return self._send(401, {"error": {"code": "unauthenticated", "message": "no"}})
        p = urllib.parse.unquote(u.path[len("/graph"):])
        if p == "/me":
            return self._send(200, {"userPrincipalName": "stefan@outlook.de"})
        if p == "/me/drive/root":
            return self._send(200, g.item_json("root"))
        if p.startswith("/me/drive/root:/"):
            id = g.by_path(p[len("/me/drive/root:"):])
            return self._send(200, g.item_json(id)) if id else self._send(404, {"error": {"code": "itemNotFound",
                                                                                          "message": "nf"}})
        parts = p.split("/")
        if p.startswith("/me/drive/items/") and p.endswith("/children"):
            fid = parts[4]
            if method == "POST":
                b = self._body()
                if any(v["parent"] == fid and v["name"] == b["name"] for v in g.items.values()):
                    return self._send(409, {"error": {"code": "nameAlreadyExists", "message": "exists"}})
                nid = f"N{len(g.items)}"
                g.add(nid, b["name"], fid, folder=True)
                return self._send(201, g.item_json(nid))
            kids = sorted(k for k, v in g.items.items() if v["parent"] == fid)
            skip = int(q.get("skip", 0))
            page = kids[skip:skip + 2]
            res = {"value": [g.item_json(k) for k in page]}
            if skip + 2 < len(kids):
                res["@odata.nextLink"] = f"{srv.base}/graph/me/drive/items/{fid}/children?skip={skip + 2}"
            return self._send(200, res)
        if p.startswith("/me/drive/items/"):
            id = parts[4]
            if id not in g.items:
                return self._send(404, {"error": {"code": "itemNotFound", "message": "nf"}})
            if method == "PATCH":
                b = self._body()
                to, name = b["parentReference"]["id"], b["name"]
                if any(v["parent"] == to and v["name"] == name for k, v in g.items.items() if k != id):
                    return self._send(409, {"error": {"code": "nameAlreadyExists", "message": "exists"}})
                g.items[id].update(parent=to, name=name)
            return self._send(200, g.item_json(id))
        return self._send(404, {"error": {"code": "x", "message": p}})

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PATCH(self):
        self.route("PATCH")


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
    srv.pc, srv.g, srv.seen_headers, srv.other = FakePCloud(), FakeGraph(), [], ""
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class CloudTest(unittest.TestCase):
    def setUp(self):
        self.srv = start_server()
        self.tmp = tempfile.mkdtemp()
        self.journal = os.path.join(self.tmp, "cloud_journal.jsonl")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_https_only(self):
        with self.assertRaises(cloud.CloudError):
            cloud.Http().request("GET", "http://example.org/x")

    def test_no_auth_leak_on_redirect(self):
        other = start_server()
        try:
            self.srv.other = other.base.replace("127.0.0.1", "localhost")
            r = cloud.Http().request("GET", self.srv.base + "/redirect", headers={"Authorization": "Bearer AT"})
            self.assertIsNone(r["auth"])
        finally:
            other.shutdown()
            other.server_close()

    def test_pcloud(self):
        pc = cloud.PCloud("pcloud_eu", base=self.srv.base + "/pc")
        with self.assertRaises(cloud.CloudError):
            pc.login("stefan@example.org", "falsch")
        self.assertEqual(pc.login("stefan@example.org", "geheim"), TOKEN)
        groups = cloud.scan(pc, "/Fotos", min_size=1, keep_rule="shortest_path")
        self.assertEqual(len(groups), 1)                        # Kollision mit anderem SHA nicht gruppiert
        g = groups[0]
        self.assertEqual({f.path for f in g.files}, {"/Fotos/a.jpg", "/Fotos/Urlaub/kopie von a.jpg"})
        self.assertEqual(g.keepers[0].path, "/Fotos/a.jpg")
        # Namenskonflikt im Archiv: vorhandene Datei darf nicht überschrieben werden
        aid = pc.ensure_folder("/BildZwilling_Archiv/Fotos/Urlaub")
        self.srv.pc.files[50] = dict(name="kopie von a.jpg", parent=int(aid), size=1, hash=9, sha="X")
        ca = cloud.CloudArchive(pc, "/BildZwilling_Archiv", self.journal, "pcloud_eu")
        ok, why = ca.archive(g.to_archive[0], g.keepers[0], "S1")
        self.assertTrue(ok, why)
        moved = self.srv.pc.files[11]
        self.assertEqual((moved["parent"], moved["name"]), (int(aid), "kopie von a (1).jpg"))
        self.assertEqual(self.srv.pc.files[50]["name"], "kopie von a.jpg")   # unverändert
        sid, items = ca.last_session()
        self.assertEqual((sid, len(items)), ("S1", 1))
        self.assertEqual(ca.undo_session(sid), (1, []))
        self.assertEqual((self.srv.pc.files[11]["parent"], self.srv.pc.files[11]["name"]), (2, "kopie von a.jpg"))
        self.assertEqual(ca.last_session(), ("", []))
        # Datei nach der Suche verändert -> nicht verschieben
        self.srv.pc.files[11]["hash"] = 999
        ok, why = ca.archive(g.to_archive[0], g.keepers[0], "S2")
        self.assertFalse(ok)
        self.assertIn("verändert", why)
        self.assertTrue(pc.thumbnail("10").startswith(b"\xff\xd8"))

    def test_pcloud_2fa_and_oauth(self):
        pc = cloud.PCloud("pcloud_eu", base=self.srv.base + "/pc")
        with self.assertRaises(cloud.TwoFactorRequired) as cm:
            pc.login("2fa@example.org", "geheim")
        self.assertEqual(cm.exception.tfa_token, "TFATOK")
        with self.assertRaises(cloud.CloudError):
            pc.login_2fa("TFATOK", "999999")
        tok = pc.login_2fa("TFATOK", "123 456")              # Leerzeichen im Code erlaubt
        self.assertEqual(tok, TOKEN)
        self.assertEqual(len(cloud.scan(pc, "/Fotos", min_size=1)), 1)
        # OAuth (Browser-Anmeldung, funktioniert mit 2FA): Code gegen Token tauschen
        url = cloud.PCloud.oauth_url("app", "xyz")
        self.assertTrue(url.startswith("https://my.pcloud.com/oauth2/authorize?"))
        self.assertIn("response_type=code", url)
        po = cloud.PCloud("pcloud_eu", base=self.srv.base + "/pc")
        with self.assertRaises(cloud.CloudError):
            po.oauth_finish("app", "sec", "FALSCH")
        saved = po.oauth_finish("app", "sec", " CODE ")
        self.assertTrue(saved.startswith("oauth|"))
        self.assertTrue(po.bearer)
        self.assertEqual(po.account(), "stefan@example.org")
        p2 = cloud.PCloud("pcloud_eu", base=self.srv.base + "/pc")
        p2.set_token(saved)                                   # gespeicherte Anmeldung wiederherstellen
        self.assertEqual(len(cloud.scan(p2, "/Fotos", min_size=1)), 1)
        self.assertIn("Bearer OAT", [h.get("Authorization") for h in self.srv.seen_headers])
        self.assertFalse(any("OAT" in str(h) for h in [self.srv.seen_headers[-1].get("auth")]))

    def test_onedrive(self):
        od = cloud.OneDrive("client-123", graph=self.srv.base + "/graph", login=self.srv.base + "/login")
        codes = []
        rt = od.device_login(lambda c, u, m: codes.append(c))
        self.assertEqual((codes, rt), (["ABCD-1234"], "RT"))
        self.assertEqual(od.account(), "stefan@outlook.de")
        groups = cloud.scan(od, "/Bilder", min_size=1, keep_rule="shortest_path")   # mit Seitenumbruch
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(len(g.files), 3)
        ca = cloud.CloudArchive(od, "/Archiv", self.journal, "onedrive")
        for d in g.to_archive:
            ok, why = ca.archive(d, g.keepers[0], "S1")
            self.assertTrue(ok, why)
        arch = self.srv.g.by_path("/Archiv/Bilder/Alt")
        self.assertEqual(sorted(v["name"] for v in self.srv.g.items.values() if v["parent"] == arch),
                         ["x - Kopie.jpg", "z.jpg"])
        # Konflikt beim Rückgängig: am Ursprungsort liegt inzwischen eine gleichnamige Datei
        self.srv.g.add("NEU", "z.jpg", "F2", size=1, qx="Q")
        n, err = ca.undo_session("S1")
        self.assertEqual((n, err), (2, []))
        names = sorted(v["name"] for v in self.srv.g.items.values() if v["parent"] == "F2")
        self.assertEqual(names, ["x - Kopie.jpg", "z (1).jpg", "z.jpg"])
        od2 = cloud.OneDrive("client-123", graph=self.srv.base + "/graph", login=self.srv.base + "/login")
        od2.set_token("RT")
        self.assertEqual(od2.account(), "stefan@outlook.de")   # Erneuerung über Refresh-Token


if __name__ == "__main__":
    unittest.main()
