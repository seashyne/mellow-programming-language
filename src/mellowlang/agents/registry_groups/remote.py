"""Search, publish and install against a registry over HTTP."""

from __future__ import annotations

import base64
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Dict

from ... import package_manager as pm

from .archive import agent_manifest_dict, build_agent_archive
from .auth import get_agent_auth_token, get_agent_registry_url
from .integrity import _sha256_bytes, sign_agent_manifest
from .install import _extract_agent_archive
from .layout import (ARCHIVE_EXT, _agent_cache_root, normalize_agent_name)


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
    cache_path = _agent_cache_root() / base_name.replace('/', '_') / f'{chosen}{ARCHIVE_EXT}'
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
