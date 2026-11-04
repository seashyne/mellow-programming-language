"""The HTTP surface: the package page, the JSON API, and the request body
and bearer-token readers every endpoint shares."""

from __future__ import annotations

import base64
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict

from .store import RegistryStore


class Handler(BaseHTTPRequestHandler):
    server_version = "MellowRegistry/1.5.3"

    @property
    def store(self) -> RegistryStore:
        return self.server.store  # type: ignore[attr-defined]

    def _send_json(self, payload: Dict[str, Any], status: int = 200):
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str, status: int = 200):
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _registry_page(self, query: str = "") -> str:
        res = self.store.search(query)
        rows = res.get("items") or []
        items = []
        for item in rows:
            badges = " ".join(f"<span class='badge'>{str(b)}</span>" for b in (item.get("badges") or []))
            keywords = ", ".join(str(k) for k in (item.get("keywords") or []))
            items.append(
                "<article class='pkg'>"
                f"<h2>{item.get('name')}</h2>"
                f"<p>{item.get('description') or ''}</p>"
                f"<div class='meta'>latest {item.get('latest') or '-'} · by {item.get('creator') or 'unknown'} · downloads {item.get('downloads') or 0}</div>"
                f"<div>{badges}</div>"
                f"<div class='meta'>license {item.get('license') or '-'} · keywords {keywords or '-'}</div>"
                f"<code>mellow install {item.get('name')}</code>"
                "</article>"
            )
        body = "\n".join(items) or "<p>No packages found.</p>"
        q = query.replace('"', "&quot;")
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mellow Registry</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; color: #17202a; background: #f7f8fb; }}
    header {{ background: #18212f; color: white; padding: 28px 32px; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    form {{ display: flex; gap: 8px; margin: 18px 0 4px; }}
    input {{ flex: 1; padding: 10px 12px; border: 1px solid #c8d0dc; border-radius: 6px; }}
    button {{ padding: 10px 14px; border: 0; border-radius: 6px; background: #246bfe; color: white; }}
    .pkg {{ background: white; border: 1px solid #d9e0ea; border-radius: 8px; padding: 18px; margin: 14px 0; }}
    .pkg h2 {{ margin: 0 0 8px; font-size: 20px; }}
    .meta {{ color: #596579; font-size: 14px; margin: 8px 0; }}
    .badge {{ display: inline-block; border: 1px solid #b8c4d6; border-radius: 999px; padding: 2px 8px; margin-right: 6px; font-size: 12px; }}
    code {{ display: inline-block; margin-top: 8px; background: #eef2f7; padding: 6px 8px; border-radius: 6px; }}
  </style>
</head>
<body>
  <header><h1>Mellow Registry</h1><p>Browse, search, and install Mellow packages.</p></header>
  <main>
    <form method="get" action="/packages"><input name="q" value="{q}" placeholder="Search packages"><button>Search</button></form>
    {body}
  </main>
</body>
</html>"""

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b"{}"
        return json.loads(body.decode("utf-8"))

    def _bearer(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        return auth.split(" ", 1)[1].strip() if auth.startswith("Bearer ") else None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)
        if path in {"/", "/packages"}:
            return self._send_html(self._registry_page((query.get("q") or [""])[0]))
        if path == "/health":
            return self._send_json({"ok": True, "service": "mellow-registry", "version": "1.5.3", "mode": "public-registry-compatible"})
        if path == "/api/v1/auth/whoami":
            payload = self.store.whoami(self._bearer())
            return self._send_json(payload, 200 if payload.get("ok") else 401)
        if path == "/api/v1/packages/search":
            return self._send_json(self.store.search((query.get("q") or [""])[0]))
        if path.startswith("/api/v1/authors/"):
            author = urllib.parse.unquote(path.split("/", 4)[4])
            return self._send_json(self.store.author_profile(author))
        parts = path.split("/")
        if len(parts) >= 5 and parts[1:4] == ["api", "v1", "packages"]:
            name = urllib.parse.unquote(parts[4])
            if len(parts) == 5:
                payload = self.store.package_meta(name)
                return self._send_json(payload, 200 if payload.get("ok") else 404)
            if len(parts) == 7 and parts[5] == "versions":
                payload = self.store.version_meta(name, urllib.parse.unquote(parts[6]))
                return self._send_json(payload, 200 if payload.get("ok") else 404)
            if len(parts) == 8 and parts[5] == "versions" and parts[7] == "signature":
                payload = self.store.signature_meta(name, urllib.parse.unquote(parts[6]))
                return self._send_json(payload, 200 if payload.get("ok") else 404)
            if len(parts) == 7 and parts[5] == "download":
                raw = self.store.archive_bytes(name, urllib.parse.unquote(parts[6]))
                if raw is None:
                    return self._send_json({"ok": False, "error": f"package not found: {name}"}, 404)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
        return self._send_json({"ok": False, "error": "not found", "path": path}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if path == "/api/v1/auth/login":
            body = self._read_json()
            payload = self.store.login(str(body.get("username", "")), str(body.get("password", "")))
            return self._send_json(payload, 200 if payload.get("ok") else 401)
        if path == "/api/v1/packages/publish":
            body = self._read_json()
            try:
                raw = base64.b64decode(body.get("archive_b64", ""))
            except Exception:
                return self._send_json({"ok": False, "error": "invalid archive_b64"}, 400)
            payload = self.store.publish(self._bearer(), body.get("manifest") or {}, raw, body.get("sha256"), body.get("filename"))
            return self._send_json(payload, 200 if payload.get("ok") else 400)
        return self._send_json({"ok": False, "error": "not found", "path": path}, 404)

    def log_message(self, fmt: str, *args):
        sys.stderr.write("[registry] " + (fmt % args) + "\n")
