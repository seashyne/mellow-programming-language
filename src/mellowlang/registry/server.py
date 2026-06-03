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
        }
        pkg["latest"] = version
        self.save_index(index)
        return {"ok": True, "name": name, "version": version, "latest": version, "sha256": real_sha}

    def search(self, q: str) -> Dict[str, Any]:
        q = (q or "").strip().lower()
        index = self.load_index().get("packages", {})
        rows = []
        for name, info in sorted(index.items()):
            blob = " ".join([name, info.get("latest", ""), str(info.get("versions", {}))]).lower()
            if not q or q in blob:
                rows.append({
                    "name": name,
                    "latest": info.get("latest"),
                    "versions": sorted((info.get("versions") or {}).keys()),
                    "description": ((info.get("versions") or {}).get(info.get("latest"), {}) or {}).get("description", ""),
                })
        return {"ok": True, "query": q, "count": len(rows), "items": rows}

    def package_meta(self, name: str) -> Dict[str, Any]:
        index = self.load_index().get("packages", {})
        if name not in index:
            return {"ok": False, "error": f"package not found: {name}"}
        info = index[name]
        return {"ok": True, "name": name, "latest": info.get("latest"), "versions": sorted((info.get("versions") or {}).keys()), "metadata": info}

    def version_meta(self, name: str, version: str) -> Dict[str, Any]:
        meta_path = self.packages_dir / name / version / "meta.json"
        if not meta_path.exists():
            return {"ok": False, "error": f"version not found: {name}@{version}"}
        return {"ok": True, **_json_load(meta_path, {})}

    def archive_bytes(self, name: str, version: str) -> bytes | None:
        meta = self.version_meta(name, version)
        if not meta.get("ok"):
            return None
        path = self.packages_dir / name / version / meta.get("filename", f"{name}-{version}.mpkg")
        return path.read_bytes() if path.exists() else None


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
        if path == "/health":
            return self._send_json({"ok": True, "service": "mellow-registry", "version": "1.5.3", "mode": "public-registry-compatible"})
        if path == "/api/v1/auth/whoami":
            payload = self.store.whoami(self._bearer())
            return self._send_json(payload, 200 if payload.get("ok") else 401)
        if path == "/api/v1/packages/search":
            return self._send_json(self.store.search((query.get("q") or [""])[0]))
        parts = path.split("/")
        if len(parts) >= 5 and parts[1:4] == ["api", "v1", "packages"]:
            name = urllib.parse.unquote(parts[4])
            if len(parts) == 5:
                payload = self.store.package_meta(name)
                return self._send_json(payload, 200 if payload.get("ok") else 404)
            if len(parts) == 7 and parts[5] == "versions":
                payload = self.store.version_meta(name, urllib.parse.unquote(parts[6]))
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
