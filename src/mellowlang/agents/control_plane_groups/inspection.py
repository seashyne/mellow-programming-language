"""Read back what the control plane knows: listings, status, revisions
and health."""

from __future__ import annotations

from typing import Any, Dict

from .state import _load_state, _now_iso, _save_state
from .traffic import _find_local_target, _rev_status_for
from .transport import _is_remote_control_plane, _remote_url, _request_json


def list_deployments(state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return _request_json('GET', _remote_url(str(control_plane), '/deployments'), token=api_token)
    state = _load_state(state_dir)
    items = list((state.get('deployments') or {}).values())
    return {'ok': True, 'items': items, 'count': len(items), 'remote': False}


def get_deployment_status(ref: str, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return _request_json('GET', _remote_url(str(control_plane), '/deployments/status', ref=ref), token=api_token)
    state = _load_state(state_dir)
    for item in (state.get('deployments') or {}).values():
        if item.get('id') == ref or item.get('package', {}).get('name') == ref:
            return {'ok': True, 'deployment': item, 'remote': False}
    return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}


def list_revisions(ref: str, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return _request_json('GET', _remote_url(str(control_plane), '/deployments/revisions', ref=ref), token=api_token)
    status = get_deployment_status(ref, state_dir=state_dir)
    if not status.get('ok'):
        return status
    item = status['deployment']
    revisions = [dict(r, status=_rev_status_for(item, int(r.get('revision', 0)))) for r in list(item.get('revisions') or [])]
    return {'ok': True, 'deployment_id': item['id'], 'package': item['package'], 'current_revision': item.get('current_revision'), 'items': revisions, 'count': len(revisions), 'traffic_split': dict(item.get('traffic_split') or {'stable': 100, 'canary': 0}), 'remote': False}


def run_health_check(ref: str, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return _request_json('GET', _remote_url(str(control_plane), '/deployments/health', ref=ref), token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    current_rev = int(target.get('current_revision') or 0)
    revision = next((r for r in (target.get('revisions') or []) if int(r.get('revision', 0)) == current_rev), None)
    details = {
        'provider': target.get('provider'),
        'public_url': target.get('public_url'),
        'revision': current_rev,
    }
    status = 'healthy' if current_rev > 0 else 'unknown'
    checked_at = _now_iso()
    health = {'status': status, 'checked_at': checked_at, 'details': details}
    target['health'] = health
    if revision is not None:
        revision['health'] = health
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'health': health, 'state_path': str(state_path), 'remote': False}
