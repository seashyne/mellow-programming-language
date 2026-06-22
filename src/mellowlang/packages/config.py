from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from .metadata import normalize_name

DEFAULT_REGISTRY = os.environ.get(
    "MELLOW_REGISTRY_URL",
    "https://mellow-public-registry.jirayut-wh.workers.dev",
)
ALIASES_FILE_NAME = ".mellow_aliases.json"

def config_home_path() -> Path:
    return Path(os.environ.get("MELLOW_CONFIG_DIR", str(Path.home() / ".mellow")))


def config_file_path() -> Path:
    return config_home_path() / "config.json"


def cache_root_path() -> Path:
    return config_home_path() / "cache" / "packages"


def keys_dir_path() -> Path:
    return config_home_path() / "keys"


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _aliases_path(project_dir: str | Path | None = None) -> Path:
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ALIASES_FILE_NAME


def load_aliases(project_dir: str | Path | None = None) -> Dict[str, Any]:
    data = _json_load(_aliases_path(project_dir), {"aliases": {}, "packages": {}})
    if not isinstance(data, dict):
        data = {"aliases": {}, "packages": {}}
    data.setdefault("aliases", {})
    data.setdefault("packages", {})
    return data


def save_aliases(data: Dict[str, Any], project_dir: str | Path | None = None) -> Path:
    path = _aliases_path(project_dir)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def suggest_aliases_for_package(name: str) -> List[str]:
    norm = normalize_name(name)
    bare = norm[1:].split('/', 1)[1] if norm.startswith('@') and '/' in norm else norm
    pieces = [p for p in re.split(r"[-_/]+", bare) if p]
    out: List[str] = []
    for candidate in [bare.replace('-', '_'), bare.replace('-', ''), pieces[-1] if pieces else bare, pieces[0] if pieces else bare]:
        candidate = re.sub(r"[^a-zA-Z0-9_]", "_", candidate or "")
        if candidate and candidate not in out:
            out.append(candidate)
    return out[:8] or ["pkg"]


def _default_alias(name: str) -> str:
    return suggest_aliases_for_package(name)[0]


def remember_alias(name: str, alias: str | None = None, project_dir: str | Path | None = None) -> Path:
    pkg_name = normalize_name(name)
    chosen = alias or _default_alias(pkg_name)
    data = load_aliases(project_dir)
    data.setdefault("aliases", {})[chosen] = pkg_name
    data.setdefault("packages", {})[pkg_name] = chosen
    return save_aliases(data, project_dir)


def resolve_alias(name_or_alias: str, project_dir: str | Path | None = None) -> str:
    norm = normalize_name(name_or_alias)
    data = load_aliases(project_dir)
    aliases = data.get("aliases", {}) or {}
    packages = data.get("packages", {}) or {}
    if norm in aliases:
        return normalize_name(aliases[norm])
    if norm in packages:
        return norm
    return norm


def ensure_user_dirs() -> None:
    config_home_path().mkdir(parents=True, exist_ok=True)
    cache_root_path().mkdir(parents=True, exist_ok=True)
    keys_dir_path().mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    ensure_user_dirs()
    cfg = _json_load(config_file_path(), {})
    cfg.setdefault("registry", DEFAULT_REGISTRY)
    cfg.setdefault("auth", {})
    cfg.setdefault("default_scope", "public")
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    ensure_user_dirs()
    config_file_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_registry(url: str) -> Dict[str, Any]:
    cfg = load_config()
    cfg["registry"] = url.rstrip("/")
    save_config(cfg)
    return {"registry": cfg["registry"], "config": str(config_file_path())}


def get_registry_url(explicit: str | None = None) -> str:
    return (explicit or load_config().get("registry") or DEFAULT_REGISTRY).rstrip("/")


def get_auth_token(registry: str | None = None) -> str | None:
    reg = get_registry_url(registry)
    env_token = os.environ.get("MELLOW_PUBLISH_TOKEN") or os.environ.get("MELLOW_REGISTRY_TOKEN")
    if env_token:
        return env_token
    cfg = load_config()
    return cfg.get("auth", {}).get(reg)


def set_auth_token(registry: str, token: str) -> None:
    cfg = load_config()
    cfg.setdefault("auth", {})[registry.rstrip("/")] = token
    save_config(cfg)


def clear_auth_token(registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    cfg = load_config()
    auth = cfg.setdefault("auth", {})
    auth.pop(reg, None)
    save_config(cfg)
    return {"ok": True, "registry": reg, "saved_to": str(config_file_path())}


def trusted_authors() -> List[str]:
    cfg = load_config()
    values = cfg.get("trusted_authors", [])
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def trust_author(author: str, *, remove: bool = False) -> Dict[str, Any]:
    name = str(author or "").strip()
    if not name:
        return {"ok": False, "error": "author name is required"}
    cfg = load_config()
    authors = trusted_authors()
    if remove:
        authors = [a for a in authors if a.lower() != name.lower()]
    elif not any(a.lower() == name.lower() for a in authors):
        authors.append(name)
    cfg["trusted_authors"] = authors
    save_config(cfg)
    return {"ok": True, "author": name, "trusted_authors": authors, "saved_to": str(config_file_path())}
