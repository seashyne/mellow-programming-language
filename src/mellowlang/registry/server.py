from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict


def _json_load(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _authors_from_manifest(manifest: Dict[str, Any] | None) -> list[str]:
    data = manifest or {}
    value = data.get("authors") or data.get("author") or data.get("creator") or data.get("publisher") or data.get("maintainer") or data.get("owner")
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _creator_from_manifest(manifest: Dict[str, Any] | None) -> str:
    authors = _authors_from_manifest(manifest)
    return ", ".join(authors) if authors else "unknown"


def _list_from_manifest(manifest: Dict[str, Any] | None, key: str) -> list[str]:
    value = (manifest or {}).get(key)
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _package_badges(manifest: Dict[str, Any] | None, *, signed: bool = False) -> list[str]:
    data = manifest or {}
    badges = _list_from_manifest(data, "badges")
    if data.get("official") and "official" not in badges:
        badges.append("official")
    if signed and "verified" not in badges:
        badges.append("verified")
    if data.get("deprecated") and "deprecated" not in badges:
        badges.append("deprecated")
    return badges


class RegistryStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.packages_dir = self.data_dir / "packages"
        self.index_file = self.data_dir / "index.json"
        self.users_file = self.data_dir / "users.json"
        self.tokens_file = self.data_dir / "tokens.json"
        self.init()

    def init(self):
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self.index_file.write_text(json.dumps({"packages": {}}, indent=2) + "\n", encoding="utf-8")
        if not self.users_file.exists():
            self.users_file.write_text(json.dumps({"admin": {"password": "admin", "scopes": ["publish", "read"]}}, indent=2) + "\n", encoding="utf-8")
        if not self.tokens_file.exists():
            bootstrap = {os.environ.get("MELLOW_BOOTSTRAP_TOKEN", "dev-publish-token"): {"username": "admin", "scopes": ["publish", "read"], "source": "bootstrap"}}
            self.tokens_file.write_text(json.dumps(bootstrap, indent=2) + "\n", encoding="utf-8")

    def load_index(self) -> Dict[str, Any]:
        data = _json_load(self.index_file, {"packages": {}})
        data.setdefault("packages", {})
        return data

    def save_index(self, data: Dict[str, Any]) -> None:
        self.index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load_users(self) -> Dict[str, Any]:
        return _json_load(self.users_file, {})

    def load_tokens(self) -> Dict[str, Any]:
        return _json_load(self.tokens_file, {})

    def save_tokens(self, data: Dict[str, Any]) -> None:
        self.tokens_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def login(self, username: str, password: str) -> Dict[str, Any]:
        users = self.load_users()
        user = users.get(username)
        if not user or user.get("password") != password:
            return {"ok": False, "error": "invalid credentials"}
        token = secrets.token_urlsafe(24)
        tokens = self.load_tokens()
        tokens[token] = {"username": username, "scopes": user.get("scopes", ["read"])}
        self.save_tokens(tokens)
        return {"ok": True, "token": token, "username": username, "scopes": user.get("scopes", ["read"])}

    def whoami(self, token: str | None) -> Dict[str, Any]:
        if not token:
            return {"ok": False, "error": "missing bearer token"}
        record = self.load_tokens().get(token)
        if not record:
            return {"ok": False, "error": "invalid token"}
        return {"ok": True, **record}

    def publish(self, token: str | None, manifest: Dict[str, Any], archive: bytes, sha256: str | None, filename: str | None) -> Dict[str, Any]:
        auth = self.whoami(token)
        if not auth.get("ok"):
            return auth
        if "publish" not in auth.get("scopes", []):
            return {"ok": False, "error": "token missing publish scope"}
        name = str(manifest.get("name") or "pkg").strip()
        version = str(manifest.get("version") or "0.1.0").strip()
        if not name or not version:
            return {"ok": False, "error": "manifest requires name and version"}
        real_sha = hashlib.sha256(archive).hexdigest()
        if sha256 and sha256 != real_sha:
            return {"ok": False, "error": "sha256 mismatch", "expected": real_sha}
        dest_dir = self.packages_dir / name / version
        dest_dir.mkdir(parents=True, exist_ok=True)
        archive_path = dest_dir / (filename or f"{name}-{version}.mpkg")
        archive_path.write_bytes(archive)
        meta = {
            "name": name,
            "version": version,
            "manifest": manifest,
            "sha256": real_sha,
            "filename": archive_path.name,
            "published_by": auth.get("username"),
            "published_at": __import__("datetime").datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        }
        (dest_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index = self.load_index()
        pkgs = index.setdefault("packages", {})
        pkg = pkgs.setdefault(name, {"name": name, "versions": {}, "latest": version})
        pkg["versions"][version] = {
            "sha256": real_sha,
            "filename": archive_path.name,
            "description": manifest.get("description", ""),
            "entry": manifest.get("entry", "src/main.mellow"),
            "authors": _authors_from_manifest(manifest),
            "creator": _creator_from_manifest(manifest),
            "license": manifest.get("license", ""),
            "keywords": _list_from_manifest(manifest, "keywords"),
            "badges": _package_badges(manifest, signed=bool(manifest.get("signing"))),
            "published_by": auth.get("username"),
            "published_at": meta["published_at"],
            "downloads": 0,
        }
        pkg["latest"] = version
        self.save_index(index)
        return {"ok": True, "name": name, "version": version, "latest": version, "sha256": real_sha, "authors": _authors_from_manifest(manifest), "creator": _creator_from_manifest(manifest), "published_by": auth.get("username")}

    def search(self, q: str) -> Dict[str, Any]:
        q = (q or "").strip().lower()
        index = self.load_index().get("packages", {})
        rows = []
        for name, info in sorted(index.items()):
            latest = ((info.get("versions") or {}).get(info.get("latest"), {}) or {})
            blob = " ".join([name, info.get("latest", ""), str(info.get("versions", {})), str(latest.get("creator", "")), str(latest.get("authors", "")), str(latest.get("keywords", "")), str(latest.get("badges", ""))]).lower()
            if not q or q in blob:
                rows.append({
                    "name": name,
                    "latest": info.get("latest"),
                    "versions": sorted((info.get("versions") or {}).keys()),
                    "description": latest.get("description", ""),
                    "authors": latest.get("authors", []),
                    "creator": latest.get("creator") or "unknown",
                    "license": latest.get("license", ""),
                    "keywords": latest.get("keywords", []),
                    "badges": latest.get("badges", []),
                    "downloads": int(latest.get("downloads") or 0),
                    "published_at": latest.get("published_at"),
                    "published_by": latest.get("published_by"),
                })
        return {"ok": True, "query": q, "count": len(rows), "items": rows}

    def author_profile(self, author: str) -> Dict[str, Any]:
        needle = (author or "").strip().lower()
        rows = []
        for name, info in sorted(self.load_index().get("packages", {}).items()):
            latest = ((info.get("versions") or {}).get(info.get("latest"), {}) or {})
            haystack = [str(latest.get("creator") or ""), str(latest.get("published_by") or "")]
            haystack.extend(str(a) for a in (latest.get("authors") or []))
            if needle and not any(needle == h.lower() or needle in h.lower() for h in haystack):
                continue
            rows.append({
                "name": name,
                "latest": info.get("latest"),
                "description": latest.get("description", ""),
                "creator": latest.get("creator") or "unknown",
                "authors": latest.get("authors", []),
                "license": latest.get("license", ""),
                "keywords": latest.get("keywords", []),
                "badges": latest.get("badges", []),
                "downloads": int(latest.get("downloads") or 0),
                "published_at": latest.get("published_at"),
            })
        return {"ok": True, "author": author, "count": len(rows), "items": rows}

    def package_meta(self, name: str) -> Dict[str, Any]:
        index = self.load_index().get("packages", {})
        if name not in index:
            return {"ok": False, "error": f"package not found: {name}"}
        info = index[name]
        latest = ((info.get("versions") or {}).get(info.get("latest"), {}) or {})
        return {
            "ok": True,
            "name": name,
            "latest": info.get("latest"),
            "versions": sorted((info.get("versions") or {}).keys()),
            "description": latest.get("description", ""),
            "authors": latest.get("authors", []),
            "creator": latest.get("creator") or "unknown",
            "license": latest.get("license", ""),
            "keywords": latest.get("keywords", []),
            "badges": latest.get("badges", []),
            "downloads": int(latest.get("downloads") or 0),
            "published_at": latest.get("published_at"),
            "published_by": latest.get("published_by"),
            "metadata": info,
        }

    def version_meta(self, name: str, version: str) -> Dict[str, Any]:
        meta_path = self.packages_dir / name / version / "meta.json"
        if not meta_path.exists():
            return {"ok": False, "error": f"version not found: {name}@{version}"}
        payload = _json_load(meta_path, {})
        manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
        return {"ok": True, **payload, "authors": _authors_from_manifest(manifest), "creator": _creator_from_manifest(manifest), "license": manifest.get("license", ""), "keywords": _list_from_manifest(manifest, "keywords"), "badges": _package_badges(manifest, signed=bool(manifest.get("signing")))}

    def signature_meta(self, name: str, version: str) -> Dict[str, Any]:
        meta = self.version_meta(name, version)
        if not meta.get("ok"):
            return meta
        manifest = meta.get("manifest") if isinstance(meta.get("manifest"), dict) else {}
        signing = manifest.get("signing") if isinstance(manifest, dict) else {}
        return {
            "ok": True,
            "name": name,
            "version": version,
            "sha256": meta.get("sha256"),
            "manifest": manifest,
            "signed": bool(signing),
            "algorithm": (signing or {}).get("algorithm"),
            "signature_b64": (signing or {}).get("signature_b64"),
            "public_key_pem": (signing or {}).get("public_key_pem"),
            "creator": _creator_from_manifest(manifest),
            "authors": _authors_from_manifest(manifest),
            "published_by": meta.get("published_by"),
            "published_at": meta.get("published_at"),
        }

    def archive_bytes(self, name: str, version: str) -> bytes | None:
        meta = self.version_meta(name, version)
        if not meta.get("ok"):
            return None
        path = self.packages_dir / name / version / meta.get("filename", f"{name}-{version}.mpkg")
        if not path.exists():
            return None
        index = self.load_index()
        latest = (((index.get("packages") or {}).get(name) or {}).get("versions") or {}).get(version)
        if isinstance(latest, dict):
            latest["downloads"] = int(latest.get("downloads") or 0) + 1
            self.save_index(index)
        return path.read_bytes()


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


def run_registry_server(host: str = "127.0.0.1", port: int = 8089, data_dir: str | None = None):
    store = RegistryStore(data_dir or os.environ.get("MELLOW_REGISTRY_DATA", "mellow_registry_data"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.store = store  # type: ignore[attr-defined]
    print(f"Mellow Registry running on http://{host}:{port}")
    print(f"Data dir: {store.data_dir}")
    print("Default login: admin / admin")
    print("Bootstrap publish token:", os.environ.get("MELLOW_BOOTSTRAP_TOKEN", "dev-publish-token"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down registry...")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mellow package registry server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8089)
    ap.add_argument("--data-dir", default=os.environ.get("MELLOW_REGISTRY_DATA", "mellow_registry_data"))
    ns = ap.parse_args(argv)
    run_registry_server(ns.host, ns.port, ns.data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
