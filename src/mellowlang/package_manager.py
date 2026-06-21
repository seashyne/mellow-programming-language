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

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None

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
DEFAULT_REGISTRY = os.environ.get(
    "MELLOW_REGISTRY_URL",
    "https://mellow-public-registry.jirayut-wh.workers.dev",
)
CLIENT_USER_AGENT = f"MellowCLI/{os.environ.get('MELLOW_CLI_VERSION', '2.9.0')} (+https://mellowlang.org)"
REQUEST_TIMEOUT = int(os.environ.get("MELLOW_HTTP_TIMEOUT", "30"))
CONFIG_HOME = Path(os.environ.get("MELLOW_CONFIG_DIR", str(Path.home() / ".mellow")))
CONFIG_FILE = CONFIG_HOME / "config.json"
LOCKFILE_NAME = "mellow.lock"
IMPORT_MAP_NAME = ".mellow_imports.json"
RUNTIME_MAP_NAME = ".mellow_runtime.json"
ALIASES_FILE_NAME = ".mellow_aliases.json"
CACHE_ROOT = CONFIG_HOME / "cache" / "packages"
KEYS_DIR = CONFIG_HOME / "keys"
HOST_DEP_SENTINELS = {"host", "builtin", "built-in", "internal"}


def _normalize_authors(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
        return out
    return [str(value).strip()] if str(value).strip() else []


def package_authors(manifest_or_item: Dict[str, Any] | None) -> List[str]:
    data = manifest_or_item or {}
    authors = _normalize_authors(data.get("authors"))
    for key in ("author", "creator", "publisher", "maintainer", "owner"):
        if not authors:
            authors = _normalize_authors(data.get(key))
    metadata = data.get("metadata")
    if not authors and isinstance(metadata, dict):
        authors = package_authors(metadata)
    manifest = data.get("manifest")
    if not authors and isinstance(manifest, dict):
        authors = package_authors(manifest)
    return authors


def package_creator(manifest_or_item: Dict[str, Any] | None) -> str:
    authors = package_authors(manifest_or_item)
    return ", ".join(authors) if authors else "unknown"


def config_home_path() -> Path:
    return Path(os.environ.get("MELLOW_CONFIG_DIR", str(Path.home() / ".mellow")))


def config_file_path() -> Path:
    return config_home_path() / "config.json"


def cache_root_path() -> Path:
    return config_home_path() / "cache" / "packages"


def keys_dir_path() -> Path:
    return config_home_path() / "keys"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


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


def split_namespace(name: str) -> tuple[str | None, str]:
    norm = normalize_name(name)
    if norm.startswith('@') and '/' in norm:
        ns, rest = norm[1:].split('/', 1)
        return ns or None, rest
    return None, norm


def canonical_package_name(name: str) -> str:
    return normalize_name(name)


def bare_package_name(name: str) -> str:
    return split_namespace(name)[1]


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


def _project_package_root(project_dir: str | Path | None = None) -> Path:
    if project_dir is None:
        return PKG_ROOT
    return Path(project_dir) / "mellow_packages"


def _project_registry_root(project_dir: str | Path | None = None) -> Path:
    if project_dir is None:
        return REGISTRY_ROOT
    return _project_package_root(project_dir) / "registry"


def _project_installed_root(project_dir: str | Path | None = None) -> Path:
    if project_dir is None:
        return INSTALLED_ROOT
    return _project_package_root(project_dir) / "installed"


def _repo_registry_root() -> Path:
    return _repo_root() / "mellow_packages" / "registry"


def _repo_starter_packages_root() -> Path:
    return _repo_root() / "starter_packages"


def _entry_candidates(entry: str) -> list[str]:
    entry = str(entry or "src/main.mel").replace("\\", "/")
    out = [entry]
    if entry.endswith(".mellow"):
        out.append(entry[:-7] + ".mel")
    elif entry.endswith(".mel"):
        out.append(entry[:-4] + ".mellow")
    return list(dict.fromkeys(out))


def _resolve_existing_entry(package_dir: Path, manifest: Dict[str, Any]) -> str:
    entry = str(manifest.get("entry", "src/main.mel"))
    for candidate in _entry_candidates(entry):
        if (package_dir / candidate).exists():
            return candidate
    return entry


def _load_manifest_from_source_dir(src: Path) -> Dict[str, Any]:
    manifest = read_manifest(src)
    manifest = dict(manifest)
    manifest["entry"] = _resolve_existing_entry(src, manifest)
    return manifest


def _find_local_package_source(name: str, version: str | None = None, project_dir: str | Path | None = None) -> tuple[Path | None, str | None, str | None]:
    base_name, version_from_ref = _split_pkg_ref(name)
    chosen_version = version or version_from_ref
    roots = []
    if project_dir is not None:
        roots.append(_project_registry_root(project_dir))
    roots.extend([REGISTRY_ROOT, _repo_registry_root()])
    for root in roots:
        pkg_root = root / base_name
        if not pkg_root.exists():
            continue
        versions = sorted([p.name for p in pkg_root.iterdir() if p.is_dir()])
        if not versions:
            continue
        ver = chosen_version or versions[-1]
        src = pkg_root / ver
        if src.exists():
            return src, ver, "registry"
    starter = _repo_starter_packages_root() / base_name
    if starter.exists():
        return starter, chosen_version or str(read_manifest(starter).get("version", "0.1.0")), "starter"
    return None, None, None


def install_local_package_into_project(name: str, project_dir: str | Path, version: str | None = None, *, with_deps: bool = True, _visited: set[str] | None = None) -> Dict[str, Any]:
    base = Path(project_dir)
    base_name, version_from_ref = _split_pkg_ref(name)
    chosen_version = version or version_from_ref
    src, resolved_version, source_kind = _find_local_package_source(base_name, chosen_version, project_dir=base)
    if src is None:
        return {"ok": False, "error": f"local package not found: {base_name}"}
    manifest = _load_manifest_from_source_dir(src)
    resolved_version = resolved_version or str(manifest.get("version", "0.1.0"))
    installed_root = _project_installed_root(base)
    dst = installed_root / base_name / "current"
    if dst.parent.exists():
        shutil.rmtree(dst.parent)
    (dst / "package").mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst / "package", dirs_exist_ok=True)
    (dst / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    alias_path = remember_alias(base_name, project_dir=base)
    lockfile_path = _update_lock_entry(base_name, resolved_version, manifest, registry="local", project_dir=base)
    installed = [{"name": base_name, "version": resolved_version}]
    visited = _visited or set()
    visit_key = f"{base_name}@{resolved_version}"
    if visit_key in visited:
        return {"ok": True, "name": base_name, "version": resolved_version, "installed_to": str(dst.parent), "entry": str(manifest.get("entry", "")), "authors": package_authors(manifest), "creator": package_creator(manifest), "installed": installed, "lockfile": str(lockfile_path), "aliases_file": str(alias_path), "source_kind": source_kind}
    visited.add(visit_key)
    if with_deps:
        for dep_name, dep_spec in (manifest.get("dependencies", {}) or {}).items():
            if str(dep_spec).strip().lower() in HOST_DEP_SENTINELS:
                continue
            dep_res = install_local_package_into_project(dep_name, base, version=str(dep_spec), with_deps=True, _visited=visited)
            if not dep_res.get("ok"):
                return dep_res
            installed.extend(dep_res.get("installed", [{"name": dep_name, "version": dep_res.get("version")}]))
    return {"ok": True, "name": base_name, "version": resolved_version, "installed_to": str(dst.parent), "entry": str(manifest.get("entry", "")), "authors": package_authors(manifest), "creator": package_creator(manifest), "installed": installed, "lockfile": str(lockfile_path), "aliases_file": str(alias_path), "source_kind": source_kind}



def _preset_dependencies(preset: str = "starter") -> Dict[str, str]:
    preset = (preset or "starter").strip().lower()
    presets: Dict[str, Dict[str, str]] = {
        "starter": {
            "core-print": "^0.2.0",
            "core-strings": "^0.2.0",
            "core-collections": "^0.2.0",
            "core-math": "^0.2.0",
            "core-json": "^0.2.0",
            "core-time": "^0.2.0",
        },
        "app": {
            "core-print": "^0.2.0",
            "core-strings": "^0.2.0",
            "core-storage": "^0.2.0",
            "core-window": "^0.2.0",
        },
        "automation": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-time": "^0.2.0",
            "core-workflow": "^0.2.0",
        },
        "ai-agent": {
            "core-print": "^0.2.0",
            "core-strings": "^0.2.0",
            "core-json": "^0.2.0",
            "core-ai": "^0.2.0",
        },
        "gamekit": {
            "core-print": "^0.2.0",
            "core-math": "^0.2.0",
            "core-gamekit": "^0.2.0",
        },
        "api-webhook": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-http": "^0.2.0",
            "core-workflow": "^0.2.0",
        },
        "finance": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-money": "^0.1.0",
            "core-ledger": "^0.1.0",
        },
        "data": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-data": "^0.1.0",
        },
    }
    return dict(presets.get(preset, presets["starter"]))


def _default_starter_dependencies() -> Dict[str, str]:
    return _preset_dependencies("starter")


def _preset_entry_source(preset: str = "starter") -> str:
    preset = (preset or "starter").strip().lower()
    samples: Dict[str, str] = {
        "starter": """import "pkg:core-print" as out
import "pkg:core-strings" as text
import "pkg:core-math" as mathx
import "pkg:core-workflow" as wf

out.banner(text.upper("mellow starter"))
keep task = wf.job("demo.run", {"score": mathx.clamp01(2)})
out.kv("task", wf.to_json(task))
out.success("starter packages ready")
""",
        "app": """import "pkg:core-print" as out
import "pkg:core-window" as win

keep count = 0
keep name = "Mellow"

keep app = win.window("Mellow Desktop App", 960, 640)
win.menu(app, "File", ["About"])
win.menu_item(app, "File", "Quit", "close")
win.label(app, "Hello Mellow")
win.input(app, "Mellow")
win.button(app, "Count +1", "inc:count")
win.label(app, "Count = {{state.count}}")
win.button(app, "Close", "close")
win.run(app)
out.success("desktop app spec ready")
""",
        "automation": """import "pkg:core-print" as out
import "pkg:core-json" as jsonx
import "pkg:core-time" as time
import "pkg:core-workflow" as wf

keep payload = {"kind": "nightly.sync", "at": time.unix()}
keep job = wf.job("sync.users", payload)
out.kv("job", wf.to_json(job))
out.kv("payload", jsonx.pretty(payload))
""",
        "ai-agent": """import "pkg:core-print" as out
import "pkg:core-ai" as ai

keep plan = ai.prompt("Summarize user onboarding steps for a small SaaS")
out.banner("AI Agent Preset")
out.kv("prompt", plan)
""",
        "gamekit": """import "pkg:core-print" as out
import "pkg:core-gamekit" as game
import "pkg:core-math" as mathx

keep hero = game.entity("hero", {"x": 10, "y": 5, "speed": mathx.clamp01(1)})
out.kv("hero", game.to_json(hero))
out.success("gamekit preset ready")
""",
        "api-webhook": """import "pkg:core-print" as out
import "pkg:core-http" as http
import "pkg:core-json" as jsonx

keep route = http.route("POST", "/webhooks/orders")
keep sample = {"route": route, "body": {"ok": true}}
out.kv("webhook", jsonx.pretty(sample))
""",
        "finance": """import "pkg:core-print" as out
import "pkg:core-money" as money
import "pkg:core-ledger" as ledger

keep book = ledger.create("USD")
keep amount = money.of("125.50", "USD")
ledger.post(book, "cash", "revenue", amount, "sale-001")
out.kv("balance", money.format(ledger.balance(book, "cash")))
""",
        "data": """import "pkg:core-print" as out
import "pkg:core-data" as data

keep rows = [{"kind": "sale", "amount": 10}, {"kind": "sale", "amount": 15}]
keep sales = data.where(rows, "kind", "eq", "sale")
out.kv("total", data.sum(sales, "amount"))
""",
    }
    return samples.get(preset, samples["starter"])

def ensure_project_starter_packages(project_dir: str | Path, packages: List[str] | None = None, *, resolve_runtime_map: bool = True) -> Dict[str, Any]:
    base = Path(project_dir)
    selected = [normalize_name(p) for p in (packages or list(_default_starter_dependencies().keys()))]
    installed_rows: List[Dict[str, Any]] = []
    for pkg in selected:
        res = install_local_package_into_project(pkg, base, with_deps=True)
        if not res.get("ok"):
            return res
        installed_rows.extend(res.get("installed", [{"name": pkg, "version": res.get("version")}]))
    runtime = None
    if resolve_runtime_map:
        runtime = resolve_project_runtime(base, install_missing=False, strict=False)
    return {"ok": True, "project_dir": str(base), "packages": selected, "installed": installed_rows, "runtime": runtime}



def scaffold_project(target_dir: str | Path, *, force: bool = False, with_core: bool = True, preset: str = "starter") -> Dict[str, Any]:
    dest = Path(target_dir).resolve()
    template = _repo_root() / "project_template"
    if not template.exists():
        return {"ok": False, "error": "project_template not found"}
    if dest.exists() and any(dest.iterdir()) and not force:
        return {"ok": False, "error": "destination not empty. Use --force."}
    if dest.exists() and force:
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, dest, dirs_exist_ok=True)

    preset_name = (preset or "starter").strip().lower()
    deps = _preset_dependencies(preset_name) if with_core else {}

    src_dir = dest / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    entry_name = "src/main.mel"
    (src_dir / "main.mel").write_text(_preset_entry_source(preset_name), encoding="utf-8")

    if preset_name == "app":
        desktop_dir = dest / "desktop"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        (desktop_dir / "window.json").write_text(json.dumps({
            "title": f"{dest.name} App",
            "width": 960,
            "height": 640,
            "source": entry_name,
            "engine": "tkinter-host",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif preset_name == "api-webhook":
        api_dir = dest / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        (api_dir / "routes.json").write_text(json.dumps({
            "routes": [{"method": "POST", "path": "/webhooks/orders", "source": entry_name}],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mj = dest / "mellow.json"
    if mj.exists():
        try:
            data = json.loads(mj.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data["entry"] = entry_name
        data["name"] = normalize_name(dest.name)
        data["preset"] = preset_name
        data["starter_packages"] = list(deps.keys()) if with_core else []
        mj.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "name": normalize_name(dest.name),
        "version": "0.1.0",
        "description": f"Mellow {preset_name} project scaffold",
        "entry": entry_name,
        "license": "MIT",
        "visibility": "private",
        "namespace": "",
        "preset": preset_name,
        "dependencies": deps,
    }
    _write_toml(dest / "mellow.toml", manifest)

    readme_text = (
        f"# {dest.name}\n\n"
        f"Scaffolded with `mellow new --preset {preset_name}`.\n\n"
        "## Run\n\n"
        "```bash\n"
        "mellow run src/main.mel\n"
        "```\n\n"
    )
    if preset_name == "app":
        readme_text += (
            "## Desktop window\n\n"
            "```bash\n"
            "mellow desktop run src/main.mel\n"
            "```\n\n"
        )
    readme_text += "## Starter packages\n\n"
    if with_core and deps:
        readme_text += ''.join(f"- {name}\n" for name in deps.keys())
    else:
        readme_text += "No starter packages preloaded.\n"
    (dest / "README.md").write_text(readme_text, encoding="utf-8")

    result = {
        "ok": True,
        "project_dir": str(dest),
        "manifest": str(dest / "mellow.toml"),
        "entry": entry_name,
        "preset": preset_name,
        "with_core": with_core,
    }
    if with_core and deps:
        preload = ensure_project_starter_packages(dest, packages=list(deps.keys()), resolve_runtime_map=True)
        if not preload.get("ok"):
            return preload
        result["preload"] = preload
    return result

def ensure_user_dirs() -> None:
    config_home_path().mkdir(parents=True, exist_ok=True)
    cache_root_path().mkdir(parents=True, exist_ok=True)
    keys_dir_path().mkdir(parents=True, exist_ok=True)


def ensure_dirs() -> None:
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    INSTALLED_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_user_dirs()


def normalize_name(name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() or ch in "-_/@." else "-" for ch in (name or "pkg"))
    return safe.strip("-") or "pkg"


def _split_pkg_ref(name: str) -> Tuple[str, str | None]:
    if "@" in name[1:]:
        base, ver = name.rsplit("@", 1)
        if re.match(r"^[0-9A-Za-z][0-9A-Za-z.+\-]{0,63}$", ver or ""):
            return normalize_name(base), ver
    return normalize_name(name), None


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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


def _manifest_paths(package_dir: Path) -> List[Path]:
    return [package_dir / "mellow.toml", package_dir / "mellow.pkg.json"]


def _parse_toml(path: Path) -> Dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("tomllib not available; use mellow.pkg.json or Python 3.11+")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {
        "name": data.get("name", path.parent.name),
        "version": data.get("version", "0.1.0"),
        "entry": data.get("entry", "src/main.mellow"),
        "description": data.get("description", "Mellow package"),
        "authors": data.get("authors", []),
        "license": data.get("license", "MIT"),
        "keywords": data.get("keywords", ["mellow"]),
        "badges": data.get("badges", []),
        "official": bool(data.get("official", False)),
        "deprecated": bool(data.get("deprecated", False)),
        "dependencies": data.get("dependencies", {}) or {},
        "visibility": data.get("visibility", "public"),
        "namespace": data.get("namespace", ""),
    }


def _write_toml(path: Path, manifest: Dict[str, Any]) -> None:
    deps = manifest.get("dependencies", {}) or {}
    lines = [
        f'name = "{manifest.get("name", path.parent.name)}"',
        f'version = "{manifest.get("version", "0.1.0")}"',
        f'description = "{manifest.get("description", "Mellow package")}"',
        f'entry = "{manifest.get("entry", "src/main.mellow")}"',
        f'license = "{manifest.get("license", "MIT")}"',
        f'visibility = "{manifest.get("visibility", "public")}"',
    ]
    namespace = (manifest.get("namespace") or "").strip()
    if namespace:
        lines.append(f'namespace = "{namespace}"')
    authors = manifest.get("authors", []) or []
    if authors:
        lines.append("authors = [" + ", ".join(json.dumps(a, ensure_ascii=False) for a in authors) + "]")
    keywords = manifest.get("keywords", []) or []
    if keywords:
        lines.append("keywords = [" + ", ".join(json.dumps(k, ensure_ascii=False) for k in keywords) + "]")
    badges = manifest.get("badges", []) or []
    if badges:
        lines.append("badges = [" + ", ".join(json.dumps(b, ensure_ascii=False) for b in badges) + "]")
    if manifest.get("official"):
        lines.append("official = true")
    if manifest.get("deprecated"):
        lines.append("deprecated = true")
    lines.append("")
    lines.append("[dependencies]")
    if deps:
        for k, v in deps.items():
            lines.append(f'{k} = "{v}"')
    else:
        lines.append("# add package = \"^1.0.0\"")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_manifest(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if p.is_dir():
        for cand in _manifest_paths(p):
            if cand.exists():
                p = cand
                break
        else:
            raise FileNotFoundError(f"no package manifest found in {p}; expected one of: mellow.toml, mellow.pkg.json")
    if not p.exists():
        raise FileNotFoundError(f"manifest not found: {p}")
    if p.is_dir():
        raise IsADirectoryError(f"expected a manifest file, got directory: {p}")
    data = _parse_toml(p) if p.suffix == ".toml" else json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("name", p.parent.name)
    data.setdefault("version", "0.1.0")
    data.setdefault("entry", "src/main.mellow")
    data.setdefault("description", "Mellow package")
    data.setdefault("authors", [])
    data.setdefault("dependencies", {})
    data.setdefault("visibility", "public")
    data.setdefault("namespace", "")
    data["authors"] = package_authors(data)
    data["creator"] = package_creator(data)
    return data


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




def _version_key(version: str) -> Tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", version or "0")[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def _version_satisfies(version: str, spec: str | None) -> bool:
    spec = (spec or "").strip()
    if not spec or spec in {"*", "latest"}:
        return True
    if spec in HOST_DEP_SENTINELS:
        return True
    parts = [p.strip() for p in re.split(r"[, ]+", spec) if p.strip()]
    vkey = _version_key(version)

    def _one(part: str) -> bool:
        if part in {"*", "latest"}:
            return True
        if part.startswith("^"):
            base = part[1:].strip()
            major = _version_key(base)[0]
            return vkey[0] == major and vkey >= _version_key(base)
        if part.startswith("~"):
            base = part[1:].strip()
            bkey = _version_key(base)
            return vkey[:2] == bkey[:2] and vkey >= bkey
        for op in (">=", "<=", ">", "<"):
            if part.startswith(op):
                rhs = _version_key(part[len(op):].strip())
                return {">=": vkey >= rhs, "<=": vkey <= rhs, ">": vkey > rhs, "<": vkey < rhs}[op]
        return version == part

    return all(_one(part) for part in parts)


def _choose_version(versions: List[str], spec: str | None) -> str | None:
    if not versions:
        return None
    ordered = sorted(versions, key=_version_key)
    candidates = [v for v in ordered if _version_satisfies(v, spec)]
    if candidates:
        return candidates[-1]
    if spec and spec not in {"*", "latest"}:
        return None
    return ordered[-1]


def _normalized_versions(value: Any, latest: Any = None) -> List[str]:
    if isinstance(value, dict):
        versions = [str(v) for v in value.keys()]
    elif isinstance(value, (list, tuple, set)):
        versions = [str(v) for v in value]
    elif isinstance(value, str) and value.strip():
        versions = [value.strip()]
    else:
        versions = []
    latest_text = str(latest).strip() if latest is not None else ""
    if latest_text and latest_text not in versions:
        versions.append(latest_text)
    return sorted(versions, key=_version_key)


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


def _lockfile_path(project_dir: str | Path | None = None) -> Path:
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / LOCKFILE_NAME


def _load_lockfile(project_dir: str | Path | None = None) -> Dict[str, Any]:
    path = _lockfile_path(project_dir)
    data = _json_load(path, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("lockfile_version", 1)
    data.setdefault("registry", get_registry_url())
    data.setdefault("packages", {})
    data.setdefault("root", {"dependencies": {}, "imports": []})
    return data


def _save_lockfile(data: Dict[str, Any], project_dir: str | Path | None = None) -> Path:
    path = _lockfile_path(project_dir)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _update_lock_entry(name: str, version: str, manifest: Dict[str, Any], *, registry: str, project_dir: str | Path | None = None, sha256: str | None = None) -> Path:
    lock = _load_lockfile(project_dir)
    lock["registry"] = registry
    lock.setdefault("packages", {})[normalize_name(name)] = {
        "version": version,
        "entry": manifest.get("entry", "src/main.mellow"),
        "authors": package_authors(manifest),
        "creator": package_creator(manifest),
        "dependencies": manifest.get("dependencies", {}) or {},
        "sha256": sha256,
    }
    root_deps = lock.setdefault("root", {}).setdefault("dependencies", {})
    root_deps.setdefault(normalize_name(name), version)
    return _save_lockfile(lock, project_dir)


def _scan_imports(project_dir: str | Path) -> List[str]:
    base = Path(project_dir)
    found: List[str] = []
    seen = set()
    for pattern in ("*.mellow", "*.mel"):
        for file in base.rglob(pattern):
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for line in lines:
                stripped = line.strip()
                for keyword in ("import ", "use ", "need "):
                    if not stripped.startswith(keyword):
                        continue
                    rest = stripped[len(keyword):].strip()
                    mod_src = rest.split(" as ", 1)[0].strip() if " as " in rest else rest
                    if (mod_src.startswith('"') and mod_src.endswith('"')) or (mod_src.startswith("'") and mod_src.endswith("'")):
                        mod_src = mod_src[1:-1]
                    if mod_src.startswith("pkg:"):
                        mod_src = mod_src[4:]
                    if mod_src.endswith(".mellow") or mod_src.endswith(".mel"):
                        break
                    name = normalize_name(mod_src)
                    if name and name not in seen:
                        seen.add(name)
                        found.append(name)
                    break
    return found


def _read_project_manifest_if_present(project_dir: str | Path) -> Dict[str, Any] | None:
    for mp in _manifest_paths(Path(project_dir)):
        if mp.exists():
            return read_manifest(mp)
    return None


def _save_import_map(project_dir: str | Path, imports: List[str]) -> Path:
    base = Path(project_dir)
    mapping: Dict[str, Any] = {"imports": {}, "generated_by": "mellow-1.5.9"}
    for name in imports:
        installed_manifest = _project_installed_root(base) / normalize_name(name) / "current" / "manifest.json"
        if installed_manifest.exists():
            manifest = json.loads(installed_manifest.read_text(encoding="utf-8"))
            pkg_dir = _project_installed_root(base) / normalize_name(name) / "current" / "package"
            mapping["imports"][name] = {
                "entry": str(pkg_dir / manifest.get("entry", "src/main.mellow")),
                "version": manifest.get("version"),
                "package_dir": str(pkg_dir),
            }
    path = base / IMPORT_MAP_NAME
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _runtime_map_path(project_dir: str | Path | None = None) -> Path:
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / RUNTIME_MAP_NAME


def _load_runtime_map(project_dir: str | Path | None = None) -> Dict[str, Any]:
    return _json_load(_runtime_map_path(project_dir), {"imports": {}, "missing": []})


def resolve_import_entry(name: str, project_dir: str | Path | None = None) -> str | None:
    norm = normalize_name(resolve_alias(name, project_dir))
    runtime_map = _load_runtime_map(project_dir)
    for key in {name, norm}:
        row = (runtime_map.get("imports") or {}).get(key)
        if isinstance(row, dict) and row.get("entry"):
            return str(row["entry"])
    import_map = _json_load((Path(project_dir) if project_dir else Path.cwd()) / IMPORT_MAP_NAME, {"imports": {}})
    for key in {name, norm}:
        row = (import_map.get("imports") or {}).get(key)
        if isinstance(row, dict) and row.get("entry"):
            return str(row["entry"])
    installed_manifest = _project_installed_root(project_dir) / norm / "current" / "manifest.json"
    if installed_manifest.exists():
        try:
            manifest = json.loads(installed_manifest.read_text(encoding="utf-8"))
            pkg_dir = _project_installed_root(project_dir) / norm / "current" / "package"
            return str((pkg_dir / manifest.get("entry", "src/main.mellow")).resolve())
        except Exception:
            return None
    return None


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
