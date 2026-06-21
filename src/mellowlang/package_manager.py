from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .host.modules import MODULE_ALLOWLIST
from .packages.config import (
    DEFAULT_REGISTRY, _aliases_path, _default_alias, cache_root_path, clear_auth_token, config_file_path,
    config_home_path, ensure_user_dirs, get_auth_token, get_registry_url,
    keys_dir_path, load_aliases, load_config as _load_config_impl, remember_alias, resolve_alias,
    save_aliases, save_config as _save_config_impl, set_auth_token, set_registry,
    suggest_aliases_for_package, trust_author, trusted_authors,
)
from .packages.metadata import (
    HOST_DEP_SENTINELS, _choose_version, _normalized_versions, _split_pkg_ref,
    _version_key, _version_satisfies, bare_package_name, canonical_package_name,
    normalize_name, package_authors, package_creator, split_namespace,
)
from .packages.project import (
    _project_installed_root, _project_registry_root, _repo_registry_root,
    _repo_starter_packages_root, ensure_project_starter_packages,
    install_local_package_into_project, scaffold_project,
)
from .packages.manifest import _manifest_paths, _write_toml, read_manifest
from .packages.lockfile import (
    _load_lockfile, _load_runtime_map, _lockfile_path, _read_project_manifest_if_present,
    _runtime_map_path, _save_import_map, _save_lockfile, _scan_imports,
    _update_lock_entry, resolve_import_entry,
)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
except Exception:  # pragma: no cover
    Ed25519PrivateKey = None
    Ed25519PublicKey = None
    serialization = None

PKG_ROOT = Path("mellow_packages")
REGISTRY_ROOT = PKG_ROOT / "registry"
INSTALLED_ROOT = PKG_ROOT / "installed"
CLIENT_USER_AGENT = f"MellowCLI/{os.environ.get('MELLOW_CLI_VERSION', '2.9.0')} (+https://mellowlang.org)"
REQUEST_TIMEOUT = int(os.environ.get("MELLOW_HTTP_TIMEOUT", "30"))
LOCKFILE_NAME = "mellow.lock"
IMPORT_MAP_NAME = ".mellow_imports.json"
RUNTIME_MAP_NAME = ".mellow_runtime.json"
ALIASES_FILE_NAME = ".mellow_aliases.json"
_DEFAULT_CONFIG_HOME = config_home_path()
_DEFAULT_CONFIG_FILE = config_file_path()
CONFIG_HOME = _DEFAULT_CONFIG_HOME
CONFIG_FILE = _DEFAULT_CONFIG_FILE
def load_config() -> Dict[str, Any]:
    path = Path(CONFIG_FILE)
    if path == _DEFAULT_CONFIG_FILE and Path(CONFIG_HOME) == _DEFAULT_CONFIG_HOME:
        return _load_config_impl()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        cfg = {}
    cfg.setdefault("registry", DEFAULT_REGISTRY)
    cfg.setdefault("auth", {})
    cfg.setdefault("default_scope", "public")
    return cfg
def save_config(cfg: Dict[str, Any]) -> None:
    path = Path(CONFIG_FILE)
    if path == _DEFAULT_CONFIG_FILE and Path(CONFIG_HOME) == _DEFAULT_CONFIG_HOME:
        _save_config_impl(cfg)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

def autocomplete_remote_name(name: str, registry: str | None = None) -> Dict[str, Any]:
    norm = normalize_name(name)
    suggestions: List[str] = []
    for root in (_project_registry_root(Path.cwd()), REGISTRY_ROOT, _repo_registry_root(), _repo_starter_packages_root()):
        if not root.exists():
            continue
        items = []
        if root.name == 'starter_packages':
            items = [p.name for p in root.iterdir() if p.is_dir()]
        else:
            items = [p.name for p in root.iterdir() if p.is_dir()]
        for item in items:
            if item == norm:
                return {"ok": True, "query": norm, "selected": item, "suggestions": [item], "count": 1, "items": [{"name": item}], "registry": get_registry_url(registry)}
            if item.startswith(norm) or bare_package_name(item).startswith(bare_package_name(norm)):
                if item not in suggestions:
                    suggestions.append(item)
    return {"ok": bool(suggestions), "query": norm, "selected": suggestions[0] if len(suggestions) == 1 else None, "suggestions": suggestions[:8], "count": len(suggestions), "items": [{"name": s} for s in suggestions[:20]], "registry": get_registry_url(registry)}

def interactive_pick_package(query: str, registry: str | None = None, limit: int = 10) -> Dict[str, Any]:
    res = autocomplete_remote_name(query, registry)
    items = list(res.get("items") or [])[:limit]
    if not items:
        return {"ok": False, "error": f"package not found: {query}", "suggestions": res.get("suggestions", [])}
    if len(items) == 1:
        item = items[0]
        return {"ok": True, "selected": str(item.get("name")), "item": item, "index": 0, "suggestions": res.get("suggestions", [])}
    return {"ok": True, "interactive": True, "items": items, "suggestions": res.get("suggestions", [])}

def diagnose_imports(project_dir: str | Path, registry: str | None = None) -> Dict[str, Any]:
    base = Path(project_dir)
    imports = _scan_imports(base)
    declared = (_read_project_manifest_if_present(base) or {}).get("dependencies", {}) or {}
    installed_root = _project_installed_root(base)
    installed = {p.name for p in installed_root.iterdir() if p.is_dir()} if installed_root.exists() else set()
    rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    suggestions: Dict[str, List[str]] = {}
    for name in imports:
        resolved = resolve_alias(name, base)
        status = 'ok'
        detail = 'installed'
        if resolved in MODULE_ALLOWLIST or name in MODULE_ALLOWLIST:
            detail = 'host module'
        elif resolved in declared or name in declared:
            if normalize_name(resolved) not in installed:
                status = 'missing-install'
                detail = 'declared in manifest but not installed'
                missing.append(name)
        elif normalize_name(resolved) not in installed:
            status = 'missing-dependency'
            detail = 'not declared in manifest'
            missing.append(name)
            auto = autocomplete_remote_name(resolved, registry)
            if auto.get('suggestions'):
                suggestions[name] = list(auto.get('suggestions') or [])
        rows.append({"import": name, "resolved": resolved, "status": status, "detail": detail})
    return {"ok": True, "project_dir": str(base), "imports": imports, "rows": rows, "missing": missing, "suggestions": suggestions, "aliases_file": str(_aliases_path(base))}

def ensure_dirs() -> None:
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    INSTALLED_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_user_dirs()

def init_package(target_dir: str | Path, name: str | None = None, entry: str = "main.mellow", author: str | None = None) -> Dict[str, Any]:
    ensure_dirs()
    td = Path(target_dir)
    td.mkdir(parents=True, exist_ok=True)
    pkg_name = normalize_name(name or td.name)
    (td / "src").mkdir(exist_ok=True)
    (td / "tests").mkdir(exist_ok=True)
    author_name = (author or os.environ.get("MELLOW_AUTHOR") or "").strip()
    manifest = {
        "name": pkg_name,
        "version": "0.1.0",
        "entry": f"src/{entry}",
        "description": "Mellow package",
        "authors": [author_name] if author_name else [],
        "license": "MIT",
        "dependencies": {},
        "keywords": ["mellow", "package"],
        "visibility": "public",
        "namespace": "",
    }
    _write_toml(td / "mellow.toml", manifest)
    (td / "mellow.pkg.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mf = td / manifest["entry"]
    if not mf.exists():
        mf.write_text(f'def hello():\n    print("Hello from {pkg_name}")\n', encoding="utf-8")
    if not (td / "README.md").exists():
        (td / "README.md").write_text(f"# {pkg_name}\n\nGenerated by Mellow package manager.\n", encoding="utf-8")
    if not (td / "tests" / "basic_test.mellow").exists():
        (td / "tests" / "basic_test.mellow").write_text('print("basic package test")\n', encoding="utf-8")
    return manifest

def _pkg_cache_path(name: str, version: str) -> Path:
    ensure_user_dirs()
    return cache_root_path() / normalize_name(name).replace("/", "__").replace("@", "at_") / f"{version}.mpkg"

def _select_meta_candidate(registry: str, auth_token: str | None, name: str) -> Tuple[Dict[str, Any], str | None]:
    norm = normalize_name(name)
    queries: list[str] = []
    bare = bare_package_name(norm)
    for candidate in (norm, bare):
        candidate = (candidate or '').strip()
        if candidate and candidate not in queries:
            queries.append(candidate)
    meta_error: Dict[str, Any] | None = None
    for candidate in queries or [norm]:
        url = registry + f"/api/v1/packages/{urllib.parse.quote(candidate, safe='@/_-.')}"
        meta = _request_json("GET", url, token=auth_token)
        if meta.get("ok"):
            selected = normalize_name(str(meta.get("name") or candidate))
            return meta, selected
        meta_error = meta
    auto = autocomplete_remote_name(norm, registry)
    picked = auto.get("selected")
    if picked:
        url = registry + f"/api/v1/packages/{urllib.parse.quote(str(picked), safe='@/_-.')}"
        meta = _request_json("GET", url, token=auth_token)
        if meta.get("ok"):
            selected = normalize_name(str(meta.get("name") or picked))
            return meta, selected
        meta_error = meta
    if meta_error is None:
        meta_error = {"ok": False, "error": f"package not found: {norm}"}
    if auto.get("suggestions") and "suggestions" not in meta_error:
        meta_error["suggestions"] = list(auto.get("suggestions") or [])
    return meta_error, None

def _signature_payload(manifest: Dict[str, Any], sha256: str) -> bytes:
    payload = {
        "name": normalize_name(str(manifest.get("name", "pkg"))),
        "version": str(manifest.get("version", "0.0.0")),
        "entry": str(manifest.get("entry", "src/main.mellow")),
        "sha256": sha256.lower(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

def ensure_signing_keypair() -> Dict[str, str]:
    ensure_user_dirs()
    key_dir = keys_dir_path()
    priv_path = key_dir / "ed25519_private.pem"
    pub_path = key_dir / "ed25519_public.pem"
    if priv_path.exists() and pub_path.exists():
        return {"private": str(priv_path), "public": str(pub_path)}
    if Ed25519PrivateKey is None or serialization is None:
        raise RuntimeError("cryptography with Ed25519 support is required for package signing")
    key = Ed25519PrivateKey.generate()
    priv_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path.write_bytes(priv_bytes)
    pub_path.write_bytes(pub_bytes)
    return {"private": str(priv_path), "public": str(pub_path)}

def sign_manifest(manifest: Dict[str, Any], sha256: str) -> Dict[str, Any]:
    if Ed25519PrivateKey is None or serialization is None:
        return manifest
    ensure_signing_keypair()
    key_dir = keys_dir_path()
    priv = serialization.load_pem_private_key((key_dir / "ed25519_private.pem").read_bytes(), password=None)
    pub_bytes = (key_dir / "ed25519_public.pem").read_bytes()
    signature = priv.sign(_signature_payload(manifest, sha256))
    signed = dict(manifest)
    signed["signing"] = {
        "algorithm": "ed25519",
        "public_key_pem": pub_bytes.decode("utf-8"),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    return signed

def verify_signed_manifest(manifest: Dict[str, Any], sha256: str) -> Dict[str, Any]:
    info = dict((manifest or {}).get("signing") or {})
    if not info:
        return {"ok": True, "signed": False}
    if Ed25519PublicKey is None or serialization is None:
        return {"ok": False, "signed": True, "error": "cryptography with Ed25519 support is required for signature verification"}
    try:
        pub = serialization.load_pem_public_key(str(info.get("public_key_pem", "")).encode("utf-8"))
        sig = base64.b64decode(str(info.get("signature_b64", "")))
        pub.verify(sig, _signature_payload(manifest, sha256))
        return {"ok": True, "signed": True, "algorithm": info.get("algorithm", "ed25519")}
    except Exception as e:
        return {"ok": False, "signed": True, "error": f"signature verification failed: {e}"}

def package_signature_remote(name: str, registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    token = get_auth_token(reg)
    base_name, version_from_ref = _split_pkg_ref(name)
    meta, selected_name = _select_meta_candidate(reg, token, base_name)
    if selected_name:
        base_name = selected_name
    if not meta.get("ok"):
        return meta
    versions = _normalized_versions(meta.get("versions"), meta.get("latest"))
    chosen = _choose_version(versions, version_from_ref) if version_from_ref else (str(meta.get("latest") or "") or (versions[-1] if versions else ""))
    if not chosen:
        return {"ok": False, "error": f"package has no versions: {base_name}"}
    version_meta = _request_json("GET", reg + f"/api/v1/packages/{urllib.parse.quote(base_name, safe='@/_-.')}/versions/{urllib.parse.quote(chosen)}/signature", token=token)
    if not version_meta.get("ok"):
        version_meta = _request_json("GET", reg + f"/api/v1/packages/{urllib.parse.quote(base_name, safe='@/_-.')}/versions/{urllib.parse.quote(chosen)}", token=token)
    if not version_meta.get("ok"):
        return version_meta
    manifest = version_meta.get("manifest") if isinstance(version_meta.get("manifest"), dict) else {}
    sha256 = str(version_meta.get("sha256") or version_meta.get("archive_sha256") or "").strip().lower()
    verify = verify_signed_manifest(manifest, sha256) if manifest else {"ok": True, "signed": False}
    return {
        "ok": bool(verify.get("ok")),
        "name": normalize_name(str(version_meta.get("name") or base_name)),
        "version": str(version_meta.get("version") or chosen),
        "registry": reg,
        "sha256": sha256,
        "signed": bool(verify.get("signed")),
        "verified": bool(verify.get("ok")),
        "algorithm": verify.get("algorithm") or ((manifest.get("signing") or {}).get("algorithm") if isinstance(manifest, dict) else None),
        "creator": package_creator(version_meta if isinstance(version_meta, dict) else manifest),
        "authors": package_authors(version_meta if isinstance(version_meta, dict) else manifest),
        "published_by": version_meta.get("published_by"),
        "published_at": version_meta.get("published_at"),
        "error": verify.get("error"),
    }

def package_signature_installed(name: str, project_dir: str | Path | None = None) -> Dict[str, Any]:
    base_name, _ = _split_pkg_ref(name)
    norm = normalize_name(resolve_alias(base_name, project_dir))
    target = _project_installed_root(project_dir) / norm / "current"
    manifest_path = target / "manifest.json"
    archive_path = target / "package.mpkg"
    if not manifest_path.exists():
        return {"ok": False, "error": f"package not installed: {norm}"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest() if archive_path.exists() else ""
    verify = verify_signed_manifest(manifest, sha256) if sha256 else {"ok": True, "signed": False}
    return {
        "ok": bool(verify.get("ok")),
        "name": norm,
        "version": str(manifest.get("version") or ""),
        "installed_to": str(target.parent),
        "archive": str(archive_path) if archive_path.exists() else None,
        "sha256": sha256,
        "signed": bool(verify.get("signed")),
        "verified": bool(verify.get("ok")),
        "algorithm": verify.get("algorithm") or ((manifest.get("signing") or {}).get("algorithm") if isinstance(manifest, dict) else None),
        "creator": package_creator(manifest),
        "authors": package_authors(manifest),
        "error": verify.get("error"),
    }

def add_dependency(
    name: str,
    spec: str | None = None,
    project_dir: str | Path = '.',
    registry: str | None = None,
    with_deps: bool = True,
    alias: str | None = None,
    interactive: bool = False,
) -> Dict[str, Any]:
    base = Path(project_dir)
    manifest_path = next((p for p in _manifest_paths(base) if p.exists()), base / 'mellow.toml')
    if manifest_path.exists():
        manifest = read_manifest(manifest_path)
    else:
        manifest = {"name": normalize_name(base.name), "version": "0.1.0", "entry": "src/main.mellow", "description": "Mellow project", "dependencies": {}, "visibility": "public", "namespace": ""}
    dep_name, _ = _split_pkg_ref(name)
    chosen_spec = spec
    reg = get_registry_url(registry)
    auth = get_auth_token(reg)
    meta, selected_name = _select_meta_candidate(reg, auth, dep_name)
    suggestions: List[str] = []
    if not selected_name:
        auto = autocomplete_remote_name(dep_name, reg)
        suggestions = list(auto.get("suggestions") or [])
        if auto.get("selected"):
            dep_name = str(auto.get("selected"))
            meta, selected_name = _select_meta_candidate(reg, auth, dep_name)
        elif suggestions:
            return {"ok": False, "error": f"package not found: {dep_name}", "suggestions": suggestions, "hint": "Try one of the suggested namespace packages or use the full @owner/pkg name."}
    else:
        dep_name = selected_name
    resolved = None
    if meta.get("ok"):
        resolved = _choose_version(meta.get("versions", []) or [], spec or "latest")
    if not chosen_spec:
        chosen_spec = f"^{resolved}" if resolved else "*"
    manifest.setdefault("dependencies", {})[dep_name] = chosen_spec
    if manifest_path.suffix == '.json':
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    else:
        _write_toml(manifest_path, manifest)
    install_res = install_remote(dep_name, version=chosen_spec, registry=reg, with_deps=with_deps, project_dir=base)
    chosen_alias = (alias or '').strip() or None
    if install_res.get("ok") and dep_name:
        try:
            alias_path = remember_alias(dep_name, alias=chosen_alias, project_dir=base)
            install_res["aliases_file"] = str(alias_path)
            install_res["alias"] = chosen_alias or _default_alias(dep_name)
            install_res["alias_suggestions"] = suggest_aliases_for_package(dep_name)
        except Exception:
            pass
    install_res["interactive"] = bool(interactive)
    install_res["manifest"] = str(manifest_path)
    install_res["added"] = dep_name
    install_res["spec"] = chosen_spec
    if suggestions:
        install_res["suggestions"] = suggestions
    return install_res

def remove_dependency(name: str, project_dir: str | Path = '.') -> Dict[str, Any]:
    base = Path(project_dir)
    manifest_path = next((p for p in _manifest_paths(base) if p.exists()), None)
    if not manifest_path:
        return {"ok": False, "error": f"no package manifest found in {base}"}
    manifest = read_manifest(manifest_path)
    dep_name, _ = _split_pkg_ref(name)
    removed = manifest.setdefault("dependencies", {}).pop(dep_name, None)
    if manifest_path.suffix == '.json':
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    else:
        _write_toml(manifest_path, manifest)
    uninstall_res = uninstall_package(dep_name, project_dir=base)
    aliases = load_aliases(base)
    pkg_name = canonical_package_name(dep_name)
    alias_name = (aliases.get('packages', {}) or {}).pop(pkg_name, None)
    if alias_name:
        (aliases.get('aliases', {}) or {}).pop(alias_name, None)
        save_aliases(aliases, base)
    uninstall_res["manifest"] = str(manifest_path)
    uninstall_res["removed_spec"] = removed
    uninstall_res["removed_alias"] = alias_name
    return uninstall_res

def uninstall_package(name: str, project_dir: str | Path | None = None) -> Dict[str, Any]:
    ensure_dirs()
    base_name, _ = _split_pkg_ref(name)
    target_root = INSTALLED_ROOT / normalize_name(base_name)
    if not target_root.exists():
        return {"ok": False, "error": f"package not installed: {base_name}"}
    shutil.rmtree(target_root)
    lock = _load_lockfile(project_dir)
    lock.get("packages", {}).pop(normalize_name(base_name), None)
    lock.get("root", {}).get("dependencies", {}).pop(normalize_name(base_name), None)
    lock_path = _save_lockfile(lock, project_dir)
    return {"ok": True, "name": base_name, "removed": str(target_root), "lockfile": str(lock_path)}

def _installed_version(name: str, project_dir: str | Path | None = None) -> str | None:
    norm = normalize_name(resolve_alias(name, project_dir))
    manifest_path = _project_installed_root(project_dir) / norm / "current" / "manifest.json"
    if manifest_path.exists():
        try:
            return str(json.loads(manifest_path.read_text(encoding="utf-8")).get("version") or "")
        except Exception:
            return None
    for row in list_installed():
        if normalize_name(str(row.get("name"))) == norm:
            return str(row.get("version") or "")
    return None

def package_update_plan(name: str | None = None, registry: str | None = None, *, project_dir: str | Path | None = None, all_packages: bool = False) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    lock = _load_lockfile(project_dir)
    root_deps = dict((lock.get("root") or {}).get("dependencies", {}) or {})
    targets: List[Tuple[str, str | None]] = []
    if name:
        targets.append((_split_pkg_ref(name)[0], None))
    elif all_packages:
        targets.extend([(row["name"], None) for row in list_installed()])
        for key, spec in root_deps.items():
            norm = normalize_name(key)
            if not any(t[0] == norm for t in targets):
                targets.append((norm, str(spec)))
    elif root_deps:
        targets.extend([(normalize_name(k), str(v)) for k, v in root_deps.items()])
    else:
        targets.extend([(row["name"], None) for row in list_installed()])
    items: List[Dict[str, Any]] = []
    seen = set()
    for pkg_name, spec in targets:
        if pkg_name in seen:
            continue
        seen.add(pkg_name)
        info = package_info_remote(pkg_name, registry=reg)
        if not info.get("ok"):
            items.append({"name": pkg_name, "ok": False, "error": info.get("error", "package info failed")})
            continue
        current = _installed_version(pkg_name, project_dir) or str((lock.get("packages") or {}).get(normalize_name(pkg_name), {}).get("version") or "")
        latest = str(info.get("latest") or "")
        needs_update = bool(latest and (not current or _version_key(latest) > _version_key(current)))
        items.append({
            "name": normalize_name(str(info.get("name") or pkg_name)),
            "current": current,
            "latest": latest,
            "spec": spec,
            "needs_update": needs_update,
            "creator": package_creator(info),
            "badges": info.get("badges", []),
        })
    return {"ok": True, "registry": reg, "items": items, "count": len(items), "updates": [i for i in items if i.get("needs_update")], "update_count": sum(1 for i in items if i.get("needs_update"))}

def update_packages(name: str | None = None, registry: str | None = None, *, project_dir: str | Path | None = None, with_deps: bool = True, check: bool = False, all_packages: bool = False) -> Dict[str, Any]:
    plan = package_update_plan(name, registry=registry, project_dir=project_dir, all_packages=all_packages)
    if not plan.get("ok") or check:
        return plan
    updated: List[Dict[str, Any]] = []
    for item in plan.get("items", []):
        if not item.get("needs_update"):
            continue
        pkg_name = str(item.get("name"))
        res = install_remote(pkg_name, version=str(item.get("latest") or ""), registry=plan["registry"], with_deps=with_deps, project_dir=project_dir)
        if not res.get("ok"):
            return res
        updated.extend(res.get("installed", [{"name": pkg_name, "version": res.get("version")}] ))
    return {"ok": True, "registry": plan["registry"], "plan": plan.get("items", []), "updated": updated, "count": len(updated), "lockfile": str(_lockfile_path(project_dir))}

def update_remote(name: str | None = None, registry: str | None = None, *, project_dir: str | Path | None = None, with_deps: bool = True) -> Dict[str, Any]:
    return update_packages(name, registry=registry, project_dir=project_dir, with_deps=with_deps)

def resolve_project_runtime(project_dir: str | Path, registry: str | None = None, *, install_missing: bool = True, strict: bool = False) -> Dict[str, Any]:
    base = Path(project_dir)
    project_json = base / "mellow.json"
    if project_json.exists():
        try:
            project_data = json.loads(project_json.read_text(encoding="utf-8"))
        except Exception:
            project_data = {}
        starter_packages = [normalize_name(p) for p in (project_data.get("starter_packages") or []) if str(p).strip()]
        if starter_packages:
            preload = ensure_project_starter_packages(base, packages=starter_packages, resolve_runtime_map=False)
            if not preload.get("ok"):
                return preload
    sync = sync_imports(base, registry=registry, install_missing=install_missing)
    if not sync.get("ok"):
        return sync
    imports = sync.get("imports", []) or []
    missing: List[str] = []
    runtime_map: Dict[str, Any] = {"generated_by": "mellow-1.5.9", "project_dir": str(base), "imports": {}, "missing": []}
    for name in imports:
        entry = resolve_import_entry(name, base)
        if entry:
            runtime_map["imports"][name] = {"entry": entry, "kind": "package", "resolved": True}
        elif name in MODULE_ALLOWLIST or normalize_name(name) in MODULE_ALLOWLIST:
            runtime_map["imports"][name] = {"kind": "host", "resolved": True}
        else:
            runtime_map["imports"][name] = {"kind": "missing", "resolved": False}
            missing.append(name)
    runtime_map["missing"] = missing
    path = _runtime_map_path(base)
    path.write_text(json.dumps(runtime_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if strict and missing:
        return {"ok": False, "error": f"missing imports: {', '.join(missing)}", "runtime_map": str(path), "missing": missing, "suggestions": sync.get("suggestions", {})}
    return {"ok": True, "runtime_map": str(path), "missing": missing, "imports": imports, "installed": sync.get("installed", []), "lockfile": sync.get("lockfile"), "auto_added": sync.get("auto_added", {}), "suggestions": sync.get("suggestions", {})}

def auto_fetch_for_run(target: str | Path, registry: str | None = None, *, strict: bool = False) -> Dict[str, Any]:
    path = Path(target)
    base = path if path.is_dir() else path.parent
    return resolve_project_runtime(base, registry=registry, install_missing=True, strict=strict)

def seed_core_packages(target_dir: str | Path, publish_local: bool = False) -> Dict[str, Any]:
    ensure_dirs()
    td = Path(target_dir)
    td.mkdir(parents=True, exist_ok=True)
    created: List[Dict[str, Any]] = []
    source_root = _repo_starter_packages_root()
    if not source_root.exists():
        return {"ok": False, "error": f"starter package source not found: {source_root}"}
    for source_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        if not any(path.exists() for path in _manifest_paths(source_dir)):
            continue
        manifest = read_manifest(source_dir)
        pkg_name = normalize_name(str(manifest.get("name") or source_dir.name))
        pkg_dir = td / pkg_name
        if source_dir.resolve() != pkg_dir.resolve():
            shutil.copytree(
                source_dir,
                pkg_dir,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "*.mpkg"),
            )
        row = {
            "name": pkg_name,
            "version": str(manifest.get("version", "0.1.0")),
            "dir": str(pkg_dir),
            "description": str(manifest.get("description", "")),
        }
        if publish_local:
            pub = publish_from_dir(pkg_dir)
            if not pub.get("ok", True):
                return pub
            row["published_to"] = pub.get("published_to")
        created.append(row)
    return {"ok": True, "root": str(td), "items": created, "published_local": publish_local}

def list_installed() -> List[Dict[str, Any]]:
    ensure_dirs()
    out: List[Dict[str, Any]] = []
    for p in sorted(INSTALLED_ROOT.glob("*/current/manifest.json")):
        try:
            man = json.loads(p.read_text(encoding="utf-8"))
            man["authors"] = package_authors(man)
            man["creator"] = package_creator(man)
            man["install_path"] = str(p.parent.parent)
            out.append(man)
        except Exception:
            continue
    return out

def _iter_package_files(package_dir: Path):
    ignore_names = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        ".DS_Store",
        ALIASES_FILE_NAME,
        IMPORT_MAP_NAME,
        LOCKFILE_NAME,
        RUNTIME_MAP_NAME,
    }
    for sub in package_dir.rglob("*"):
        if any(part in ignore_names for part in sub.parts):
            continue
        if sub.is_file() and sub.name != ".DS_Store":
            yield sub

def build_package_archive(package_dir: str | Path, out_path: str | Path | None = None) -> Dict[str, Any]:
    pd = Path(package_dir)
    manifest = read_manifest(pd)
    out = Path(out_path) if out_path else pd / f"{normalize_name(manifest['name']).replace('/', '_')}-{manifest['version']}.mpkg"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for sub in _iter_package_files(pd):
            if out.resolve() != sub.resolve():
                zf.write(sub, arcname=str(sub.relative_to(pd)))
    sha256 = hashlib.sha256(out.read_bytes()).hexdigest()
    return {"name": manifest["name"], "version": manifest["version"], "archive": str(out), "sha256": sha256}

def publish_from_dir(package_dir: str | Path) -> Dict[str, Any]:
    ensure_dirs()
    pd = Path(package_dir)
    manifest = read_manifest(pd)
    name = normalize_name(manifest["name"])
    version = str(manifest.get("version", "0.1.0"))
    out_dir = REGISTRY_ROOT / name / version
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(pd, out_dir)
    return {
        "name": name,
        "version": version,
        "published_to": str(out_dir),
        "authors": package_authors(manifest),
        "creator": package_creator(manifest),
    }

def install_package(name: str, version: str | None = None) -> Dict[str, Any]:
    ensure_dirs()
    name, version_from_ref = _split_pkg_ref(name)
    version = version or version_from_ref
    pkg_dir = REGISTRY_ROOT / name
    if not pkg_dir.exists():
        return {"error": f"package not found in local registry: {name}"}
    versions = sorted([p.name for p in pkg_dir.iterdir() if p.is_dir()])
    if not versions:
        return {"error": f"package has no published versions: {name}"}
    ver = version or versions[-1]
    src = pkg_dir / ver
    if not src.exists():
        return {"error": f"version not found: {name}@{ver}"}
    dst = INSTALLED_ROOT / name / "current"
    if dst.parent.exists():
        shutil.rmtree(dst.parent)
    (dst / "package").mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst / "package", dirs_exist_ok=True)
    manifest = read_manifest(src)
    (dst / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "name": name,
        "version": ver,
        "installed_to": str(dst.parent),
        "entry": str(manifest.get("entry", "")),
        "authors": package_authors(manifest),
        "creator": package_creator(manifest),
    }

def _request_json(method: str, url: str, payload: Dict[str, Any] | None = None, token: str | None = None, extra_headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": CLIENT_USER_AGENT,
    }
    if extra_headers:
        headers.update({k: str(v) for k, v in extra_headers.items()})
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {"ok": True}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        detail = body.strip()
        hint = None
        if e.code == 403 and ("browser's signature" in body.lower() or 'error code 1010' in body.lower() or 'browser integrity check' in body.lower()):
            hint = "Cloudflare blocked the Python client headers. Use v1.5.6+ headers or relax Browser Integrity Check / bot rules for /api/v1/* on your registry domain."
        return {"ok": False, "error": f"http {e.code}", "detail": detail, "hint": hint}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _normalize_auth_probe(payload: Dict[str, Any], registry: str) -> Dict[str, Any]:
    res = dict(payload or {})
    if 'ok' not in res:
        if res.get('username') and not res.get('error'):
            res['ok'] = True
        elif res.get('error'):
            res['ok'] = False
    res.setdefault('registry', registry)
    return res

def _download_bytes(url: str, token: str | None = None) -> bytes:
    headers = {
        'Accept': 'application/octet-stream,application/zip,application/json;q=0.9,*/*;q=0.8',
        'User-Agent': CLIENT_USER_AGENT,
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, method='GET', headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()

def login_remote(username: str, password: str, registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    res = _request_json("POST", reg + "/api/v1/auth/login", {"username": username, "password": password})
    token = res.get("token")
    if token:
        set_auth_token(reg, token)
        res["registry"] = reg
        res["saved_to"] = str(config_file_path())
    return res

def login_with_token(token: str, registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    probe = _normalize_auth_probe(_request_json("GET", reg + "/api/v1/auth/whoami", token=token), reg)
    if not probe.get("ok"):
        probe.setdefault("hint", "Verify the token exists in the registry and that TOKEN_HASH_SALT matches the deployed Worker.")
        return probe
    set_auth_token(reg, token)
    probe["saved_to"] = str(config_file_path())
    probe["token_saved"] = True
    return probe

def whoami_remote(registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    token = get_auth_token(reg)
    if not token:
        return {"ok": False, "error": f"not logged in for registry {reg}"}
    return _normalize_auth_probe(_request_json("GET", reg + "/api/v1/auth/whoami", token=token), reg)

def check_trust_policy(signature: Dict[str, Any], *, strict: bool = False) -> Dict[str, Any]:
    creator = package_creator(signature)
    trusted = trusted_authors()
    creator_trusted = any(creator.lower() == item.lower() for item in trusted)
    signed = bool(signature.get("signed"))
    verified = bool(signature.get("verified"))
    if strict and not signed:
        return {"ok": False, "error": f"strict trust failed: {signature.get('name')} is not signed", "creator": creator, "trusted_authors": trusted}
    if strict and not verified:
        return {"ok": False, "error": f"strict trust failed: {signature.get('name')} signature is not verified", "creator": creator, "trusted_authors": trusted}
    if strict and not creator_trusted:
        return {"ok": False, "error": f"strict trust failed: creator is not trusted: {creator}", "creator": creator, "trusted_authors": trusted}
    return {"ok": True, "creator": creator, "trusted": creator_trusted, "trusted_authors": trusted}

def search_remote(query: str, registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    token = get_auth_token(reg)
    res = _request_json("GET", reg + "/api/v1/packages/search?" + urllib.parse.urlencode({"q": query}), token=token)
    if res.get("ok", True) and isinstance(res.get("items"), list):
        items: list[Dict[str, Any]] = []
        for raw in res.get("items", []):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item["versions"] = _normalized_versions(item.get("versions"), item.get("latest"))
            if not item.get("latest") and item["versions"]:
                item["latest"] = item["versions"][-1]
            item["authors"] = package_authors(item)
            item["creator"] = package_creator(item)
            items.append(item)
        res["items"] = items
        res["count"] = len(items)
    return res

def package_info_remote(name: str, registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    token = get_auth_token(reg)
    base_name, version_from_ref = _split_pkg_ref(name)
    meta, selected_name = _select_meta_candidate(reg, token, base_name)
    if selected_name:
        base_name = selected_name
    if not meta.get("ok"):
        return meta
    versions = _normalized_versions(meta.get("versions"), meta.get("latest"))
    chosen = _choose_version(versions, version_from_ref) if version_from_ref else (str(meta.get("latest") or "") or (versions[-1] if versions else ""))
    metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    version_rows = metadata.get("versions", {}) if isinstance(metadata, dict) else {}
    latest_meta = version_rows.get(chosen, {}) if isinstance(version_rows, dict) and chosen else {}
    version_meta: Dict[str, Any] = {}
    if chosen:
        maybe_version = _request_json("GET", reg + f"/api/v1/packages/{urllib.parse.quote(base_name, safe='@/_-.')}/versions/{urllib.parse.quote(chosen)}", token=token)
        if maybe_version.get("ok"):
            version_meta = maybe_version
            manifest_meta = maybe_version.get("manifest") if isinstance(maybe_version.get("manifest"), dict) else {}
            if isinstance(manifest_meta, dict):
                latest_meta = {**manifest_meta, **latest_meta}
    merged_meta: Dict[str, Any] = {}
    if isinstance(meta, dict):
        merged_meta.update(meta)
    if isinstance(metadata, dict):
        merged_meta.update(metadata)
    if isinstance(latest_meta, dict):
        merged_meta.update(latest_meta)
    if isinstance(version_meta, dict):
        merged_meta.update(version_meta)
    authors = package_authors(merged_meta)
    return {
        "ok": True,
        "name": normalize_name(str(meta.get("name") or base_name)),
        "latest": str(meta.get("latest") or chosen or ""),
        "selected": chosen,
        "versions": versions,
        "description": latest_meta.get("description") or version_meta.get("description") or meta.get("description") or "",
        "entry": latest_meta.get("entry") or metadata.get("entry") or "",
        "authors": authors,
        "creator": ", ".join(authors) if authors else "unknown",
        "license": latest_meta.get("license") or version_meta.get("license") or metadata.get("license") or meta.get("license") or "",
        "keywords": latest_meta.get("keywords") or version_meta.get("keywords") or metadata.get("keywords") or meta.get("keywords") or [],
        "badges": latest_meta.get("badges") or version_meta.get("badges") or metadata.get("badges") or meta.get("badges") or [],
        "downloads": latest_meta.get("downloads") or version_meta.get("downloads") or metadata.get("downloads") or meta.get("downloads") or 0,
        "published_at": latest_meta.get("published_at") or version_meta.get("published_at") or metadata.get("published_at") or meta.get("published_at"),
        "published_by": latest_meta.get("published_by") or version_meta.get("published_by") or metadata.get("published_by") or meta.get("published_by"),
        "metadata": metadata or meta,
        "registry": reg,
    }

def author_profile_remote(author: str, registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    token = get_auth_token(reg)
    res = _request_json("GET", reg + "/api/v1/authors/" + urllib.parse.quote(str(author), safe="@._-"), token=token)
    if res.get("ok"):
        items: list[Dict[str, Any]] = []
        for raw in res.get("items", []) or []:
            if isinstance(raw, dict):
                item = dict(raw)
                item["authors"] = package_authors(item)
                item["creator"] = package_creator(item)
                items.append(item)
        res["items"] = items
        res["count"] = len(items)
        res["registry"] = reg
        return res
    fallback = search_remote("", registry=reg)
    if not fallback.get("ok"):
        return fallback
    needle = str(author or "").strip().lower()
    items = []
    for raw in fallback.get("items", []) or []:
        haystack = [str(raw.get("creator") or ""), str(raw.get("published_by") or "")]
        haystack.extend(str(a) for a in package_authors(raw))
        if needle and any(needle == h.lower() or needle in h.lower() for h in haystack):
            items.append(raw)
    return {"ok": True, "author": author, "count": len(items), "items": items, "registry": reg}

def publish_remote(package_dir: str | Path, registry: str | None = None, token: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    auth = token or get_auth_token(reg)
    if not auth:
        return {"ok": False, "error": f"missing publish token for registry {reg}", "hint": "use `mellow login --token <token>` or set MELLOW_PUBLISH_TOKEN"}
    pd = Path(package_dir)
    try:
        manifest = read_manifest(pd)
    except (FileNotFoundError, IsADirectoryError, PermissionError) as e:
        return {"ok": False, "error": str(e), "hint": "Publish a package directory that contains mellow.toml or mellow.pkg.json"}
    for field, candidates in (
        ("readme", ("README.md", "README.txt", "README")),
        ("changelog", ("CHANGELOG.md", "CHANGES.md", "CHANGELOG.txt")),
    ):
        if manifest.get(field):
            continue
        source = next((pd / filename for filename in candidates if (pd / filename).is_file()), None)
        if source is not None:
            manifest[field] = source.read_text(encoding="utf-8", errors="replace")[:131072]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "package.mpkg"
        built = build_package_archive(pd, tmp)
        raw = tmp.read_bytes()
    pkg_name = canonical_package_name(str(manifest.get("name", "")))
    ns_owner, _ = split_namespace(pkg_name)
    who = whoami_remote(reg)
    if ns_owner and who.get("ok") and who.get("username") and str(who.get("username")) != ns_owner:
        return {"ok": False, "error": f"namespace ownership mismatch: @{ns_owner}", "detail": f"logged in as {who.get('username')}"}
    manifest = sign_manifest(manifest, built["sha256"])
    payload = {
        "manifest": manifest,
        "filename": Path(built["archive"]).name,
        "archive_b64": base64.b64encode(raw).decode("ascii"),
        "sha256": built["sha256"],
    }
    res = _request_json("POST", reg + "/api/v1/packages/publish", payload=payload, token=auth)
    if isinstance(res, dict):
        res.setdefault("authors", package_authors(manifest))
        res.setdefault("creator", package_creator(manifest))
    return res

def _extract_archive_to_install(name: str, version: str, raw: bytes) -> Dict[str, Any]:
    ensure_dirs()
    target = INSTALLED_ROOT / normalize_name(name) / "current"
    if target.parent.exists():
        shutil.rmtree(target.parent)
    pkg_root = target / "package"
    pkg_root.mkdir(parents=True, exist_ok=True)
    archive_path = target / "package.mpkg"
    archive_path.write_bytes(raw)
    pkg_root_resolved = pkg_root.resolve()
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        for member in zf.infolist():
            member_name = member.filename.replace("\\", "/")
            member_path = Path(member_name)
            if member_path.is_absolute() or ".." in member_path.parts:
                return {"ok": False, "error": f"unsafe archive entry: {member.filename}"}
            dest = (pkg_root / member_path).resolve()
            if pkg_root_resolved not in dest.parents and dest != pkg_root_resolved:
                return {"ok": False, "error": f"unsafe archive entry: {member.filename}"}
        zf.extractall(pkg_root)
    manifest = read_manifest(pkg_root)
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "name": name,
        "version": version,
        "installed_to": str(target.parent),
        "entry": str(manifest.get("entry", "")),
        "authors": package_authors(manifest),
        "creator": package_creator(manifest),
    }

def install_remote(name: str, version: str | None = None, registry: str | None = None, *, with_deps: bool = True, project_dir: str | Path | None = None, _visited: set[str] | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    base_name, version_from_ref = _split_pkg_ref(name)
    requested_version = version or version_from_ref
    auth = get_auth_token(reg)
    meta, selected_name = _select_meta_candidate(reg, auth, base_name)
    if selected_name:
        base_name = selected_name
    if not meta.get("ok"):
        return meta
    versions = meta.get("versions", []) or []
    chosen_version = _choose_version(versions, requested_version)
    if not chosen_version:
        return {"ok": False, "error": f"no version of {base_name} matches {requested_version or 'latest'}"}
    url = reg + f"/api/v1/packages/{urllib.parse.quote(base_name, safe='@/_-.')}/download/{urllib.parse.quote(chosen_version)}"
    version_meta = _request_json("GET", reg + f"/api/v1/packages/{urllib.parse.quote(base_name, safe='@/_-.')}/versions/{urllib.parse.quote(chosen_version)}", token=auth)
    if not version_meta.get("ok"):
        return version_meta
    manifest_meta = version_meta.get("manifest") if isinstance(version_meta.get("manifest"), dict) else {}
    expected_sha256 = str(version_meta.get("sha256") or "").strip().lower()
    cache_path = _pkg_cache_path(base_name, chosen_version)
    raw = b''
    if cache_path.exists():
        raw = cache_path.read_bytes()
        if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256:
            raw = b''
    if not raw:
        try:
            raw = _download_bytes(url, token=auth)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(raw)
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and actual_sha256 != expected_sha256:
        return {"ok": False, "error": "package checksum mismatch", "expected": expected_sha256, "actual": actual_sha256}
    install_res = _extract_archive_to_install(base_name, chosen_version, raw)
    if not install_res.get("ok"):
        return install_res
    manifest = read_manifest(INSTALLED_ROOT / normalize_name(base_name) / "current" / "package")
    verify = verify_signed_manifest(manifest, actual_sha256)
    if not verify.get("ok"):
        return verify
    lockfile_path = _update_lock_entry(base_name, chosen_version, manifest, registry=reg, project_dir=project_dir, sha256=actual_sha256)
    installed: List[Dict[str, Any]] = [{"name": base_name, "version": chosen_version}]
    visited = _visited or set()
    visit_key = f"{base_name}@{chosen_version}"
    if visit_key in visited:
        install_res["lockfile"] = str(lockfile_path)
        install_res["installed"] = installed
        return install_res
    visited.add(visit_key)
    if with_deps:
        for dep_name, dep_spec in (manifest.get("dependencies", {}) or {}).items():
            if str(dep_spec).strip().lower() in HOST_DEP_SENTINELS:
                continue
            dep_res = install_remote(dep_name, version=str(dep_spec), registry=reg, with_deps=True, project_dir=project_dir, _visited=visited)
            if not dep_res.get("ok"):
                dep_res.setdefault("parent", base_name)
                return dep_res
            installed.extend(dep_res.get("installed", [{"name": dep_name, "version": dep_res.get("version")}]))
    alias_path = remember_alias(base_name, project_dir=project_dir) if project_dir else remember_alias(base_name)
    install_res["lockfile"] = str(lockfile_path)
    install_res["installed"] = installed
    install_res["cache"] = str(cache_path)
    install_res["aliases_file"] = str(alias_path)
    install_res["alias"] = _default_alias(base_name)
    install_res["alias_suggestions"] = suggest_aliases_for_package(base_name)
    install_res["authors"] = package_authors(manifest)
    install_res["creator"] = package_creator(manifest)
    install_res["badges"] = manifest.get("badges", [])
    install_res["published_by"] = version_meta.get("published_by")
    install_res["published_at"] = version_meta.get("published_at")
    return install_res

def sync_imports(project_dir: str | Path, registry: str | None = None, *, install_missing: bool = True) -> Dict[str, Any]:
    base = Path(project_dir)
    imports = _scan_imports(base)
    manifest_path = next((p for p in _manifest_paths(base) if p.exists()), None)
    manifest = _read_project_manifest_if_present(base)
    declared = (manifest or {}).get("dependencies", {}) or {}
    installed_now: List[Dict[str, Any]] = []
    auto_added: Dict[str, str] = {}
    suggestions: Dict[str, List[str]] = {}
    reg = get_registry_url(registry)
    alias_data = load_aliases(base)
    for name in imports:
        resolved_name = resolve_alias(name, base)
        installed_manifest = _project_installed_root(base) / normalize_name(resolved_name) / "current" / "manifest.json"
        if installed_manifest.exists() or name in MODULE_ALLOWLIST or normalize_name(name) in MODULE_ALLOWLIST or resolved_name in MODULE_ALLOWLIST:
            continue
        spec = declared.get(resolved_name) or declared.get(name) or declared.get(normalize_name(name))
        if install_missing and spec and str(spec).strip().lower() not in HOST_DEP_SENTINELS:
            res = install_local_package_into_project(resolved_name, base, version=str(spec), with_deps=True)
            if not res.get("ok"):
                res = install_remote(resolved_name, version=str(spec), registry=reg, with_deps=True, project_dir=base)
            if not res.get("ok"):
                return res
            installed_now.extend(res.get("installed", []))
            continue
        if install_missing and not spec:
            local_res = install_local_package_into_project(resolved_name, base, with_deps=True)
            if local_res.get("ok"):
                installed_now.extend(local_res.get("installed", []))
                installed_version = str(local_res.get("version") or "*")
                auto_added[str(resolved_name)] = f"^{installed_version}" if installed_version not in {"", "None"} else "*"
                continue
            auto = autocomplete_remote_name(resolved_name, reg)
            picked = auto.get("selected")
            if picked:
                res = install_remote(str(picked), version=None, registry=reg, with_deps=True, project_dir=base)
                if not res.get("ok"):
                    return res
                installed_now.extend(res.get("installed", []))
                installed_version = str(res.get("version") or "*")
                auto_added[str(picked)] = f"^{installed_version}" if installed_version not in {"", "None"} else "*"
                continue
            if auto.get("suggestions"):
                suggestions[name] = list(auto.get("suggestions") or [])
    if manifest is not None and auto_added:
        manifest.setdefault("dependencies", {}).update(auto_added)
        if manifest_path and manifest_path.suffix == '.json':
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
        elif manifest_path:
            _write_toml(manifest_path, manifest)
    import_map = _save_import_map(base, imports)
    lock = _load_lockfile(base)
    lock["registry"] = reg
    lock.setdefault("root", {})["imports"] = imports
    lock_path = _save_lockfile(lock, base)
    diagnostics = diagnose_imports(base, registry=reg)
    return {"ok": True, "project_dir": str(base), "imports": imports, "import_map": str(import_map), "lockfile": str(lock_path), "installed": installed_now, "auto_added": auto_added, "suggestions": suggestions, "manifest": str(manifest_path) if manifest_path else None, "diagnostics": diagnostics.get('rows', [])}

def resolve_package_url(name: str, version: str | None = None, registry: str | None = None) -> Dict[str, Any]:
    reg = get_registry_url(registry)
    base_name, version_from_ref = _split_pkg_ref(name)
    version = version or version_from_ref
    auth = get_auth_token(reg)
    meta, selected_name = _select_meta_candidate(reg, auth, base_name)
    if selected_name:
        base_name = selected_name
    if not meta.get("ok"):
        return meta
    versions = meta.get("versions", []) or []
    chosen = version or (versions[-1] if versions else None)
    if not chosen:
        return {"ok": False, "error": f"package has no versions: {base_name}"}
    return {
        "ok": True,
        "registry": reg,
        "name": base_name,
        "version": chosen,
        "download_url": reg + f"/api/v1/packages/{urllib.parse.quote(base_name, safe='@/_-.')}/download/{urllib.parse.quote(chosen)}",
    }
