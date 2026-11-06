from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .. import __version__
from .config import _json_load, get_registry_url, resolve_alias
from .manifest import _manifest_paths, read_manifest
from .metadata import normalize_name, package_authors, package_creator
from .project import _project_installed_root

LOCKFILE_NAME = "mellow.lock"
IMPORT_MAP_NAME = ".mellow_imports.json"
RUNTIME_MAP_NAME = ".mellow_runtime.json"

def _find_project_root(start: str | Path | None = None) -> Path | None:
    if start is None:
        p = Path.cwd()
    else:
        p = Path(start)
    if p.is_file():
        p = p.parent
    candidates = [p, *p.parents]
    for parent in candidates:
        if any((parent / name).exists() for name in ("mellow.json", "mellow.toml", "mellow.pkg.json")):
            return parent
    return None


def _project_base(project_dir: str | Path | None = None) -> Path:
    if project_dir is None:
        return Path.cwd()
    return _find_project_root(project_dir) or Path(project_dir)

def _lockfile_path(project_dir: str | Path | None = None) -> Path:
    return _project_base(project_dir) / LOCKFILE_NAME


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
    ignored_dirs = {
        ".git",
        ".mellow",
        ".pytest_cache",
        "__pycache__",
        "build",
        "dist",
        "mellow_packages",
        "node_modules",
    }
    scan_base = base
    for manifest_path in _manifest_paths(base):
        if not manifest_path.exists():
            continue
        try:
            entry = str(read_manifest(manifest_path).get("entry") or "").strip()
        except Exception:
            entry = ""
        if entry:
            entry_path = base / entry
            if entry_path.exists():
                scan_base = entry_path.parent if entry_path.is_file() else entry_path
            break
    for pattern in ("*.mellow", "*.mel"):
        for file in scan_base.rglob(pattern):
            try:
                rel_parts = set(file.relative_to(base).parts[:-1])
            except ValueError:
                rel_parts = set(file.parts[:-1])
            if rel_parts & ignored_dirs:
                continue
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
    mapping: Dict[str, Any] = {"imports": {}, "generated_by": f"mellow-{__version__}"}
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
    return _project_base(project_dir) / RUNTIME_MAP_NAME


def _load_runtime_map(project_dir: str | Path | None = None) -> Dict[str, Any]:
    return _json_load(_runtime_map_path(project_dir), {"imports": {}, "missing": []})


def resolve_import_entry(name: str, project_dir: str | Path | None = None) -> str | None:
    base = _project_base(project_dir)
    norm = normalize_name(resolve_alias(name, base))
    runtime_map = _load_runtime_map(base)
    for key in {name, norm}:
        row = (runtime_map.get("imports") or {}).get(key)
        if isinstance(row, dict) and row.get("entry"):
            return str(row["entry"])
    import_map = _json_load(base / IMPORT_MAP_NAME, {"imports": {}})
    for key in {name, norm}:
        row = (import_map.get("imports") or {}).get(key)
        if isinstance(row, dict) and row.get("entry"):
            return str(row["entry"])
    installed_manifest = _project_installed_root(base) / norm / "current" / "manifest.json"
    if installed_manifest.exists():
        try:
            manifest = json.loads(installed_manifest.read_text(encoding="utf-8"))
            pkg_dir = _project_installed_root(base) / norm / "current" / "package"
            return str((pkg_dir / manifest.get("entry", "src/main.mellow")).resolve())
        except Exception:
            return None
    return None
