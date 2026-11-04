"""Create a deployment record and append revisions to it, locally or
through a remote control plane."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .state import _load_state, _now_iso, _save_state, _slugify
from .transport import _is_remote_control_plane, _remote_url, _request_json


def _ensure_revision(item: Dict[str, Any], manifest: Dict[str, Any], bundle_dir: str | Path, manifest_path: str | None = None, revision_notes: str | None = None) -> Dict[str, Any]:
    revisions = list(item.get('revisions') or [])
    rev_no = len(revisions) + 1
    runtime = dict(manifest.get('runtime') or {})
    revision = {
        'revision': rev_no,
        'created_at': _now_iso(),
        'provider': runtime.get('provider'),
        'manifest_version': manifest.get('manifest_version', 1),
        'manifest_path': str(manifest_path) if manifest_path else None,
        'bundle_dir': str(Path(bundle_dir).resolve()),
        'public_url': runtime.get('public_url'),
        'notes': revision_notes,
        'status': 'synced' if revisions else 'registered',
        'health': {'status': 'unknown', 'checked_at': None, 'details': None},
        'traffic_role': 'stable' if not revisions else 'candidate',
    }
    revisions.append(revision)
    item['revisions'] = revisions
    item['current_revision'] = item.get('current_revision') or rev_no
    item['latest_revision'] = rev_no
    item.setdefault('traffic_split', {'stable': 100, 'canary': 0})
    item.setdefault('health', {'status': 'unknown', 'checked_at': None, 'details': None})
    item.setdefault('rollout_history', [])
    return revision


def _upsert_local_deployment(manifest: Dict[str, Any], bundle_dir: str | Path, *, control_plane: str | None = None, state_dir: str | Path | None = None, manifest_path: str | None = None, revision_notes: str | None = None) -> Dict[str, Any]:
    state = _load_state(state_dir)
    name = manifest['package']['name']
    version = manifest['package']['version']
    provider = manifest['runtime']['provider']
    dep_id = _slugify(f"{name}-{provider}")
    deployments = state.setdefault('deployments', {})
    item = deployments.get(dep_id) or {
        'id': dep_id,
        'package': {'name': name, 'version': version},
        'provider': provider,
        'public_url': manifest['runtime'].get('public_url'),
        'bundle_dir': str(Path(bundle_dir).resolve()),
        'control_plane': control_plane or manifest.get('control_plane', {}).get('url'),
        'status': 'registered',
        'created_at': _now_iso(),
        'revisions': [],
    }
    item['package'] = {'name': name, 'version': version}
    item['provider'] = provider
    item['public_url'] = manifest['runtime'].get('public_url')
    item['bundle_dir'] = str(Path(bundle_dir).resolve())
    item['control_plane'] = control_plane or manifest.get('control_plane', {}).get('url')
    revision = _ensure_revision(item, manifest, bundle_dir, manifest_path=manifest_path, revision_notes=revision_notes)
    if item.get('current_revision') is None:
        item['current_revision'] = revision['revision']
    item['status'] = 'registered' if revision['revision'] == 1 else 'synced'
    deployments[dep_id] = item
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': item, 'revision': revision, 'state_path': str(state_path), 'remote': False}


def register_deployment(manifest: Dict[str, Any], bundle_dir: str | Path, *, control_plane: str | None = None, state_dir: str | Path | None = None, manifest_path: str | None = None, revision_notes: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return sync_deployment(manifest, bundle_dir, control_plane=control_plane, manifest_path=manifest_path, revision_notes=revision_notes)
    return _upsert_local_deployment(manifest, bundle_dir, control_plane=control_plane, state_dir=state_dir, manifest_path=manifest_path, revision_notes=revision_notes)


def sync_deployment(manifest: Dict[str, Any], bundle_dir: str | Path, *, control_plane: str | None, api_token: str | None = None, state_dir: str | Path | None = None, manifest_path: str | None = None, revision_notes: str | None = None) -> Dict[str, Any]:
    payload = {
        'manifest': manifest,
        'bundle_dir': str(Path(bundle_dir).resolve()),
        'manifest_path': str(manifest_path) if manifest_path else None,
        'revision_notes': revision_notes,
    }
    if _is_remote_control_plane(control_plane):
        return _request_json('POST', _remote_url(str(control_plane), '/deployments/sync'), payload=payload, token=api_token)
    return _upsert_local_deployment(manifest, bundle_dir, control_plane=control_plane, state_dir=state_dir, manifest_path=manifest_path, revision_notes=revision_notes)
