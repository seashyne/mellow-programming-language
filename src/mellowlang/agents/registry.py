from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import tempfile
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Set

from .. import package_manager as pm
from .manifests import AgentPackage, load_agent_package, version_satisfies

AGENT_ROOT = Path('mellow_agent_packages')
AGENT_REGISTRY_ROOT = AGENT_ROOT / 'registry'
AGENT_INSTALLED_ROOT = AGENT_ROOT / 'installed'
AGENT_CACHE_ROOT = pm.CONFIG_HOME / 'cache' / 'agent_packages'
ARCHIVE_EXT = '.magent'
LOCKFILE_NAME = 'agent.lock'
REPRO_ZIP_TIMESTAMP = (2024, 1, 1, 0, 0, 0)


def _canonical_json(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def sign_agent_manifest(manifest: Dict[str, Any], signing_key: str, signer: str | None = None) -> Dict[str, Any]:
    base = dict(manifest)
    base.pop('signature', None)
    base.pop('signed_by', None)
    sig = hashlib.sha256(signing_key.encode('utf-8') + b'|' + _canonical_json(base)).hexdigest()
    base['signature'] = sig
    if signer:
        base['signed_by'] = signer
    return base


def verify_agent_manifest_signature(manifest: Dict[str, Any], signing_key: str) -> bool:
    sig = str(manifest.get('signature') or '')
    if not sig or not signing_key:
        return False
    base = dict(manifest)
    base.pop('signature', None)
    base.pop('signed_by', None)
    expected = hashlib.sha256(signing_key.encode('utf-8') + b'|' + _canonical_json(base)).hexdigest()
    return expected == sig


def _read_manifest_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def get_agent_registry_url(explicit: str | None = None) -> str:
    cfg = pm.load_config()
    return (explicit or cfg.get('agent_registry') or pm.get_registry_url()).rstrip('/')


def get_agent_auth_token(registry: str | None = None, *, private: bool = False) -> str | None:
    reg = get_agent_registry_url(registry)
    env_names = ['MELLOW_AGENT_PRIVATE_TOKEN', 'MELLOW_AGENT_TOKEN', 'MELLOW_PUBLISH_TOKEN', 'MELLOW_REGISTRY_TOKEN'] if private else ['MELLOW_AGENT_TOKEN', 'MELLOW_AGENT_READ_TOKEN', 'MELLOW_PUBLISH_TOKEN', 'MELLOW_REGISTRY_TOKEN']
    for name in env_names:
        value = pm.os.environ.get(name)
        if value:
            return value
    cfg = pm.load_config()
    key = 'agent_private_auth' if private else 'agent_auth'
    return ((cfg.get(key) or {}).get(reg)) or ((cfg.get('auth') or {}).get(reg))


def set_agent_auth_token(registry: str, token: str, *, private: bool = False) -> Dict[str, Any]:
    cfg = pm.load_config()
    key = 'agent_private_auth' if private else 'agent_auth'
    cfg.setdefault(key, {})[registry.rstrip('/')] = token
    if 'agent_registry' not in cfg:
        cfg['agent_registry'] = registry.rstrip('/')
    pm.save_config(cfg)
    return {'ok': True, 'registry': registry.rstrip('/'), 'private': private, 'saved_to': str(pm.CONFIG_FILE)}


def clear_agent_auth_token(registry: str | None = None, *, private: bool = False) -> Dict[str, Any]:
    reg = get_agent_registry_url(registry)
    cfg = pm.load_config()
    key = 'agent_private_auth' if private else 'agent_auth'
    cfg.setdefault(key, {}).pop(reg, None)
    pm.save_config(cfg)
    return {'ok': True, 'registry': reg, 'private': private, 'saved_to': str(pm.CONFIG_FILE)}


def agent_registry_whoami(registry: str | None = None) -> Dict[str, Any]:
    reg = get_agent_registry_url(registry)
    read_token = get_agent_auth_token(reg, private=False)
    private_token = get_agent_auth_token(reg, private=True)
    return {
        'ok': True,
        'registry': reg,
        'read_auth': bool(read_token),
        'private_auth': bool(private_token),
        'config': str(pm.CONFIG_FILE),
    }


def _collect_graph_local(name: str, version: str | None = None, _seen: Set[str] | None = None) -> Dict[str, Any]:
    ensure_agent_dirs()
    _seen = _seen or set()
    base_name = normalize_agent_name(name)
    versions = list_local_agent_versions(base_name)
    if not versions:
        return {'name': base_name, 'error': 'not found', 'dependencies': []}
    chosen = version or versions[-1]
    key = f'{base_name}@{chosen}'
    if key in _seen:
        return {'name': base_name, 'version': chosen, 'cycle': True, 'dependencies': []}
    _seen.add(key)
    mpath = AGENT_REGISTRY_ROOT / base_name / chosen / 'agent-manifest.json'
    data = _read_manifest_json(mpath)
    deps = []
    for dep_name, constraint in (data.get('dependencies') or {}).items():
        dep_versions = list_local_agent_versions(dep_name)
        match = None
        for cand in reversed(dep_versions):
            if version_satisfies(cand, constraint):
                match = cand
                break
        node = _collect_graph_local(dep_name, match, _seen) if match else {'name': dep_name, 'constraint': constraint, 'error': 'unsatisfied', 'dependencies': []}
        node['constraint'] = constraint
        deps.append(node)
    return {'name': base_name, 'version': chosen, 'dependencies': deps}


def agent_dependency_graph(name_or_dir: str) -> Dict[str, Any]:
    p = Path(name_or_dir)
    if p.exists():
        manifest = agent_manifest_dict(p)
        root = {'name': manifest['name'], 'version': manifest['version'], 'dependencies': []}
        for dep_name, constraint in (manifest.get('dependencies') or {}).items():
            root['dependencies'].append(_collect_graph_local(dep_name, None, set()) | {'constraint': constraint})
        return {'ok': True, 'graph': root}
    return {'ok': True, 'graph': _collect_graph_local(name_or_dir)}


def ensure_agent_dirs() -> None:
    AGENT_REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    AGENT_INSTALLED_ROOT.mkdir(parents=True, exist_ok=True)
    AGENT_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    pm.CONFIG_HOME.mkdir(parents=True, exist_ok=True)


def normalize_agent_name(name: str) -> str:
    return pm.normalize_name(name)


def _iter_agent_files(package_dir: Path):
    ignore_names = {'.git', '.pytest_cache', '__pycache__', '.DS_Store'}
    items: list[Path] = []
    for sub in package_dir.rglob('*'):
        if any(part in ignore_names for part in sub.parts):
            continue
        if sub.is_file() and sub.name != '.DS_Store':
            items.append(sub)
    for sub in sorted(items, key=lambda p: str(p.relative_to(package_dir)).replace('\\', '/')):
        yield sub


def agent_manifest_dict(package_dir: str | Path) -> Dict[str, Any]:
    pkg = load_agent_package(package_dir)
    return {
        'name': pkg.name,
        'version': pkg.version,
        'model': pkg.model,
        'prompt_file': pkg.prompt_file,
        'tool_manifest': pkg.tool_manifest,
        'memory_path': pkg.memory_path,
        'obs_path': pkg.obs_path,
        'tags': list(pkg.tags),
        'dependencies': dict(pkg.dependencies),
    }


def _write_reproducible_zip(zf: zipfile.ZipFile, arcname: str, raw: bytes) -> None:
    info = zipfile.ZipInfo(filename=arcname, date_time=REPRO_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o644 << 16
    zf.writestr(info, raw)


def build_agent_archive(package_dir: str | Path, out_path: str | Path | None = None, *, signing_key: str | None = None, signer: str | None = None) -> Dict[str, Any]:
    pd = Path(package_dir)
    manifest = agent_manifest_dict(pd)
    if signing_key:
        manifest = sign_agent_manifest(manifest, signing_key, signer=signer)
    out = Path(out_path) if out_path else pd / f"{normalize_agent_name(manifest['name']).replace('/', '_')}-{manifest['version']}{ARCHIVE_EXT}"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        _write_reproducible_zip(zf, 'agent-manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode('utf-8'))
        for sub in _iter_agent_files(pd):
            if out.resolve() == sub.resolve():
                continue
            arcname = str(sub.relative_to(pd)).replace('\\', '/')
            _write_reproducible_zip(zf, arcname, sub.read_bytes())
    sha256 = _sha256_file(out)
    return {'ok': True, 'name': manifest['name'], 'version': manifest['version'], 'archive': str(out), 'sha256': sha256, 'manifest': manifest, 'signed': bool(signing_key), 'reproducible': True}


def publish_agent_from_dir(package_dir: str | Path, *, signing_key: str | None = None, signer: str | None = None) -> Dict[str, Any]:
    ensure_agent_dirs()
    pd = Path(package_dir)
    manifest = agent_manifest_dict(pd)
    if signing_key:
        manifest = sign_agent_manifest(manifest, signing_key, signer=signer)
    name = normalize_agent_name(manifest['name'])
    version = str(manifest['version'])
    out_dir = AGENT_REGISTRY_ROOT / name / version
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(pd, out_dir)
    built = build_agent_archive(pd, out_dir / f'{name.replace("/", "_")}-{version}{ARCHIVE_EXT}', signing_key=signing_key, signer=signer)
    manifest['archive_sha256'] = built['sha256']
    (out_dir / 'agent-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'ok': True, 'name': name, 'version': version, 'published_to': str(out_dir), 'archive': built['archive'], 'sha256': built['sha256'], 'signed': bool(signing_key), 'reproducible': True}


def list_local_agent_versions(name: str) -> List[str]:
    pkg_dir = AGENT_REGISTRY_ROOT / normalize_agent_name(name)
    if not pkg_dir.exists():
        return []
    return sorted([p.name for p in pkg_dir.iterdir() if p.is_dir()])


def search_agent_local(query: str) -> Dict[str, Any]:
    ensure_agent_dirs()
    q = (query or '').strip().lower()
    items: List[Dict[str, Any]] = []
    for manifest_path in sorted(AGENT_REGISTRY_ROOT.glob('*/ */agent-manifest.json'.replace(' ', ''))):
        try:
            data = json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        hay = ' '.join([
            str(data.get('name', '')),
            str(data.get('model', '')),
            ' '.join(data.get('tags', []) or []),
        ]).lower()
        if not q or q in hay:
            data['registry'] = 'local'
            items.append(data)
    return {'ok': True, 'query': query, 'items': items[:20]}


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


def search_agent_remote(query: str, registry: str | None = None, *, private: bool = False) -> Dict[str, Any]:
    reg = get_agent_registry_url(registry)
    token = get_agent_auth_token(reg, private=private)
    params = {'q': query}
    if private:
        params['scope'] = 'private'
    return pm._request_json('GET', reg + '/api/v1/agents/search?' + urllib.parse.urlencode(params), token=token)


def publish_agent_remote(package_dir: str | Path, registry: str | None = None, token: str | None = None, *, signing_key: str | None = None, signer: str | None = None, private: bool = False) -> Dict[str, Any]:
    reg = get_agent_registry_url(registry)
    auth = token or get_agent_auth_token(reg, private=private)
    if not auth:
        return {'ok': False, 'error': f'missing publish token for registry {reg}', 'hint': 'use `mellow agent registry login --token <token>` or set MELLOW_AGENT_TOKEN'}
    pd = Path(package_dir)
    manifest = agent_manifest_dict(pd)
    if signing_key:
        manifest = sign_agent_manifest(manifest, signing_key, signer=signer)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / ('agent' + ARCHIVE_EXT)
        built = build_agent_archive(pd, tmp, signing_key=signing_key, signer=signer)
        raw = tmp.read_bytes()
    payload = {
        'manifest': manifest,
        'filename': Path(built['archive']).name,
        'archive_b64': base64.b64encode(raw).decode('ascii'),
        'sha256': built['sha256'],
        'kind': 'agent-package',
        'visibility': 'private' if private else 'public',
    }
    return pm._request_json('POST', reg + '/api/v1/agents/publish', payload=payload, token=auth)


def install_agent_remote(name: str, version: str | None = None, registry: str | None = None, *, target_dir: str | Path | None = None, verify_key: str | None = None, expected_sha256: str | None = None, private: bool = False) -> Dict[str, Any]:
    reg = get_agent_registry_url(registry)
    token = get_agent_auth_token(reg, private=private)
    base_name = normalize_agent_name(name)
    suffix = '?scope=private' if private else ''
    meta = pm._request_json('GET', reg + f'/api/v1/agents/{urllib.parse.quote(base_name, safe="@/_-.")}{suffix}', token=token)
    if not meta.get('ok'):
        return meta
    versions = list(meta.get('versions') or [])
    chosen = version or (versions[-1] if versions else None)
    if not chosen:
        return {'ok': False, 'error': f'no version available for {base_name}'}
    version_meta = pm._request_json('GET', reg + f'/api/v1/agents/{urllib.parse.quote(base_name, safe="@/_-.")}/versions/{urllib.parse.quote(chosen)}{suffix}', token=token)
    if not version_meta.get('ok'):
        return version_meta
    remote_sha256 = str(version_meta.get('sha256') or '').strip().lower()
    effective_sha256 = (expected_sha256 or remote_sha256 or '').lower() or None
    cache_path = AGENT_CACHE_ROOT / base_name.replace('/', '_') / f'{chosen}{ARCHIVE_EXT}'
    raw = b''
    if cache_path.exists():
        raw = cache_path.read_bytes()
        if effective_sha256 and _sha256_bytes(raw) != effective_sha256:
            raw = b''
    if not raw:
        url = reg + f'/api/v1/agents/{urllib.parse.quote(base_name, safe="@/_-.")}/download/{urllib.parse.quote(chosen)}'
        if private:
            url += '?scope=private'
        try:
            raw = pm._download_bytes(url, token=token)
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(raw)
    res = _extract_agent_archive(base_name, chosen, raw, Path(target_dir) if target_dir else None, verify_key=verify_key, expected_sha256=effective_sha256)
    if res.get('ok'):
        res['sha256'] = _sha256_bytes(raw)
        res['registry'] = reg
    return res
