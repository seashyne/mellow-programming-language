"""The on-disk registry: index, users and tokens, plus login, publish,
search, author profiles and the per-version metadata reads."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict

from .manifest import (_authors_from_manifest, _creator_from_manifest,
                       _json_load, _list_from_manifest, _package_badges)


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
