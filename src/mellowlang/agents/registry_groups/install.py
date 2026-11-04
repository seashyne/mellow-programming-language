"""Extract a verified archive into the installed tree, dependencies first."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Set

from ..manifests import AgentPackage, load_agent_package, version_satisfies

from .catalog import agent_manifest_dict, list_local_agent_versions
from .integrity import (_read_manifest_json, _sha256_bytes,
                        verify_agent_manifest_signature)
from .layout import (AGENT_INSTALLED_ROOT, AGENT_REGISTRY_ROOT, LOCKFILE_NAME,
                     ensure_agent_dirs, normalize_agent_name)
from .lock import _local_archive_and_sha, read_agent_lock


def _extract_agent_archive(name: str, version: str, raw: bytes, target_root: Path | None = None, *, verify_key: str | None = None, expected_sha256: str | None = None) -> Dict[str, Any]:
    ensure_agent_dirs()
    actual_sha256 = _sha256_bytes(raw)
    if expected_sha256 and actual_sha256 != expected_sha256.lower():
        return {'ok': False, 'error': 'agent package checksum mismatch', 'expected': expected_sha256.lower(), 'actual': actual_sha256}
    target = (target_root or AGENT_INSTALLED_ROOT) / normalize_agent_name(name) / version
    if target.exists():
        shutil.rmtree(target)
    pkg_root = target / 'package'
    pkg_root.mkdir(parents=True, exist_ok=True)
    pkg_root_resolved = pkg_root.resolve()
    with zipfile.ZipFile(io.BytesIO(raw), 'r') as zf:
        for member in zf.infolist():
            member_name = member.filename.replace('\\', '/')
            member_path = Path(member_name)
            if member_path.is_absolute() or '..' in member_path.parts:
                return {'ok': False, 'error': f'unsafe archive entry: {member.filename}'}
            dest = (pkg_root / member_path).resolve()
            if pkg_root_resolved not in dest.parents and dest != pkg_root_resolved:
                return {'ok': False, 'error': f'unsafe archive entry: {member.filename}'}
        zf.extractall(pkg_root)
    manifest = agent_manifest_dict(pkg_root)
    stored_manifest = None
    try:
        with zipfile.ZipFile(io.BytesIO(raw), 'r') as zf:
            if 'agent-manifest.json' in zf.namelist():
                stored_manifest = json.loads(zf.read('agent-manifest.json').decode('utf-8'))
    except Exception:
        stored_manifest = None
    if stored_manifest:
        manifest.update({k: v for k, v in stored_manifest.items() if k in {'signature', 'signed_by', 'dependencies', 'archive_sha256'}})
    if verify_key and manifest.get('signature') and not verify_agent_manifest_signature(manifest, verify_key):
        return {'ok': False, 'error': f'agent signature verification failed for {name}@{version}'}
    manifest['archive_sha256'] = actual_sha256
    (target / 'agent-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'ok': True, 'name': name, 'version': version, 'installed_to': str(target), 'sha256': actual_sha256}


def install_agent_package(name: str, version: str | None = None, *, target_dir: str | Path | None = None, verify_key: str | None = None, expected_sha256: str | None = None, _seen: Set[str] | None = None) -> Dict[str, Any]:
    ensure_agent_dirs()
    base_name = normalize_agent_name(name)
    versions = list_local_agent_versions(base_name)
    if not versions:
        return {'ok': False, 'error': f'agent package not found in local registry: {base_name}'}
    chosen = version or versions[-1]
    src = AGENT_REGISTRY_ROOT / base_name / chosen
    if not src.exists():
        return {'ok': False, 'error': f'version not found: {base_name}@{chosen}'}
    _seen = _seen or set()
    key = f'{base_name}@{chosen}'
    if key in _seen:
        return {'ok': True, 'name': base_name, 'version': chosen, 'installed_to': str((Path(target_dir) if target_dir else AGENT_INSTALLED_ROOT) / base_name / chosen), 'cycle': True}
    _seen.add(key)
    manifest_path = src / 'agent-manifest.json'
    manifest = _read_manifest_json(manifest_path) if manifest_path.exists() else agent_manifest_dict(src)
    for dep_name, constraint in (manifest.get('dependencies') or {}).items():
        dep_versions = list_local_agent_versions(dep_name)
        chosen_dep = None
        for cand in reversed(dep_versions):
            if version_satisfies(cand, constraint):
                chosen_dep = cand
                break
        if not chosen_dep:
            return {'ok': False, 'error': f'unsatisfied dependency: {dep_name} {constraint}'}
        dep_res = install_agent_package(dep_name, version=chosen_dep, target_dir=target_dir, verify_key=verify_key, _seen=_seen)
        if not dep_res.get('ok'):
            return dep_res
    archive, local_sha = _local_archive_and_sha(base_name, chosen)
    if expected_sha256 and local_sha and local_sha != expected_sha256.lower():
        return {'ok': False, 'error': 'agent package checksum mismatch', 'expected': expected_sha256.lower(), 'actual': local_sha}
    if archive and archive.exists():
        res = _extract_agent_archive(base_name, chosen, archive.read_bytes(), Path(target_dir) if target_dir else None, verify_key=verify_key, expected_sha256=expected_sha256 or local_sha)
        if not res.get('ok'):
            return res
    else:
        dst_root = Path(target_dir) if target_dir else AGENT_INSTALLED_ROOT
        dst = dst_root / base_name / chosen / 'package'
        if dst.parent.exists():
            shutil.rmtree(dst.parent)
        shutil.copytree(src, dst)
        copied_manifest = dict(manifest)
        if verify_key and copied_manifest.get('signature') and not verify_agent_manifest_signature(copied_manifest, verify_key):
            return {'ok': False, 'error': f'agent signature verification failed for {base_name}@{chosen}'}
        (dst.parent / 'agent-manifest.json').write_text(json.dumps(copied_manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        res = {'ok': True, 'name': base_name, 'version': chosen, 'installed_to': str(dst.parent), 'dependencies': manifest.get('dependencies', {}), 'sha256': local_sha}
    return {'ok': True, 'name': base_name, 'version': chosen, 'installed_to': str((Path(target_dir) if target_dir else AGENT_INSTALLED_ROOT) / base_name / chosen), 'dependencies': manifest.get('dependencies', {}), 'sha256': expected_sha256 or local_sha}


def install_agent_with_lock(path_or_dir: str | Path, *, target_dir: str | Path | None = None, verify_key: str | None = None, frozen: bool = False) -> Dict[str, Any]:
    lock = read_agent_lock(path_or_dir)
    pkg_dir = Path(path_or_dir) if Path(path_or_dir).is_dir() else Path(path_or_dir).parent
    if frozen and pkg_dir.exists() and (pkg_dir / 'agent.toml').exists():
        current = agent_manifest_dict(pkg_dir)
        root = lock.get('package') or {}
        lock_entry_map = {str(item.get('name')): str(item.get('version')) for item in (lock.get('packages') or [])}
        current_deps = dict(current.get('dependencies') or {})
        expected_deps = {}
        for dep_name, constraint in current_deps.items():
            # frozen mode expects the current manifest dependency set to still match the pinned lock graph
            if dep_name not in lock_entry_map:
                return {'ok': False, 'error': 'agent lock is out of date with agent.toml', 'hint': 'run `mellow agent package lock <dir>`'}
            expected_deps[dep_name] = lock_entry_map[dep_name]
        if normalize_agent_name(current['name']) != normalize_agent_name(root.get('name', '')) or str(current['version']) != str(root.get('version', '')):
            return {'ok': False, 'error': 'agent lock is out of date with agent.toml', 'hint': 'run `mellow agent package lock <dir>`'}
        # also ensure the current constraints still accept the exact pinned versions
        for dep_name, pinned_version in expected_deps.items():
            if not version_satisfies(pinned_version, current_deps.get(dep_name)):
                return {'ok': False, 'error': 'agent lock is out of date with agent.toml', 'hint': 'run `mellow agent package lock <dir>`'}
    installed = []
    for item in lock.get('packages') or []:
        res = install_agent_package(item['name'], version=item.get('version'), target_dir=target_dir, verify_key=verify_key, expected_sha256=item.get('sha256'))
        if not res.get('ok'):
            return res
        installed.append({'name': item['name'], 'version': item.get('version'), 'sha256': item.get('sha256')})
    root = lock.get('package') or {}
    return {'ok': True, 'name': root.get('name'), 'version': root.get('version'), 'installed': installed, 'lockfile': str((pkg_dir / LOCKFILE_NAME).resolve())}


def load_installed_agent(name: str, version: str | None = None) -> AgentPackage | None:
    base = AGENT_INSTALLED_ROOT / normalize_agent_name(name)
    if not base.exists():
        return None
    versions = sorted([p.name for p in base.iterdir() if p.is_dir()])
    if not versions:
        return None
    chosen = version or versions[-1]
    pkg_dir = base / chosen / 'package'
    if not pkg_dir.exists():
        return None
    return load_agent_package(pkg_dir)
