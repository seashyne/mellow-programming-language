"""Pin the dependency graph into agent.lock, and read it back."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

from ..manifests import load_agent_package, version_satisfies

from .auth import get_agent_registry_url
from .catalog import agent_manifest_dict, list_local_agent_versions
from .integrity import _read_manifest_json, _sha256_file
from .layout import (AGENT_REGISTRY_ROOT, ARCHIVE_EXT, LOCKFILE_NAME,
                     ensure_agent_dirs, normalize_agent_name)


def _local_archive_and_sha(name: str, version: str) -> tuple[Path | None, str | None]:
    src = AGENT_REGISTRY_ROOT / normalize_agent_name(name) / version
    archive = next(src.glob(f'*{ARCHIVE_EXT}'), None)
    if archive and archive.exists():
        return archive, _sha256_file(archive)
    manifest_path = src / 'agent-manifest.json'
    if manifest_path.exists():
        data = _read_manifest_json(manifest_path)
        if data.get('archive_sha256'):
            return archive, str(data['archive_sha256'])
    return archive, None


def _resolve_local_lock_entries(name: str, version: str | None = None, _seen: Set[str] | None = None) -> List[Dict[str, Any]]:
    ensure_agent_dirs()
    base_name = normalize_agent_name(name)
    versions = list_local_agent_versions(base_name)
    if not versions:
        raise FileNotFoundError(f'agent package not found in local registry: {base_name}')
    chosen = version or versions[-1]
    key = f'{base_name}@{chosen}'
    _seen = _seen or set()
    if key in _seen:
        return []
    _seen.add(key)
    src = AGENT_REGISTRY_ROOT / base_name / chosen
    manifest_path = src / 'agent-manifest.json'
    manifest = _read_manifest_json(manifest_path) if manifest_path.exists() else agent_manifest_dict(src)
    archive, sha256 = _local_archive_and_sha(base_name, chosen)
    items = [{
        'name': base_name,
        'version': chosen,
        'sha256': sha256,
        'dependencies': dict(manifest.get('dependencies') or {}),
    }]
    for dep_name, constraint in (manifest.get('dependencies') or {}).items():
        dep_versions = list_local_agent_versions(dep_name)
        chosen_dep = None
        for cand in reversed(dep_versions):
            if version_satisfies(cand, constraint):
                chosen_dep = cand
                break
        if not chosen_dep:
            raise RuntimeError(f'unsatisfied dependency: {dep_name} {constraint}')
        items.extend(_resolve_local_lock_entries(dep_name, chosen_dep, _seen))
    return items


def generate_agent_lock(package_dir: str | Path, *, registry: str | None = None, online: bool = False) -> Dict[str, Any]:
    pkg = load_agent_package(package_dir)
    entries = _resolve_local_lock_entries(pkg.name, pkg.version)
    unique: Dict[str, Dict[str, Any]] = {}
    for item in entries:
        unique[f"{item['name']}@{item['version']}"] = item
    lock = {
        'lock_version': 1,
        'package': {'name': pkg.name, 'version': pkg.version},
        'registry': get_agent_registry_url(registry),
        'packages': sorted(unique.values(), key=lambda x: (x['name'], x['version'])),
        'generated_by': 'mellow-agent-lock',
    }
    return {'ok': True, 'lock': lock}


def write_agent_lock(package_dir: str | Path, lock: Dict[str, Any]) -> Path:
    path = Path(package_dir) / LOCKFILE_NAME
    path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def read_agent_lock(path_or_dir: str | Path) -> Dict[str, Any]:
    p = Path(path_or_dir)
    if p.is_dir():
        p = p / LOCKFILE_NAME
    return json.loads(p.read_text(encoding='utf-8'))
