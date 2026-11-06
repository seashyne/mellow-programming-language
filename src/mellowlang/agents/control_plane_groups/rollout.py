"""Promote, rebalance and roll back revisions of a local deployment."""

from __future__ import annotations

from typing import Any, Dict

from .state import _load_state, _now_iso, _save_state
from .traffic import _find_local_target, _normalize_split
from .transport import _is_remote_control_plane, _remote_url, _request_json


def rollout_revision(ref: str, revision: int, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None, canary_percent: int | None = None) -> Dict[str, Any]:
    payload = {'ref': ref, 'revision': int(revision)}
    if canary_percent is not None:
        payload['canary_percent'] = int(canary_percent)
    if _is_remote_control_plane(control_plane):
        return _request_json('POST', _remote_url(str(control_plane), '/deployments/rollout'), payload=payload, token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    revisions = list(target.get('revisions') or [])
    chosen = next((r for r in revisions if int(r.get('revision', 0)) == int(revision)), None)
    if not chosen:
        return {'ok': False, 'error': f'revision not found: {revision}', 'remote': False}
    previous_revision = int(target.get('current_revision') or 0)
    target['current_revision'] = int(revision)
    target['status'] = 'rolled-out'
    target['canary'] = None
    target['traffic_split'] = {'stable': 100, 'canary': 0}
    chosen['status'] = 'active'
    chosen['traffic_role'] = 'stable'
    for rev in revisions:
        if rev is not chosen and rev.get('status') in ('active', 'canary'):
            rev['status'] = 'synced'
            rev['traffic_role'] = 'candidate'
    if canary_percent is not None and previous_revision and previous_revision != int(revision):
        canary = max(1, min(99, int(canary_percent)))
        target['current_revision'] = previous_revision
        target['status'] = 'canary'
        target['canary'] = {'revision': int(revision), 'traffic_split': {'stable': 100 - canary, 'canary': canary}, 'created_at': _now_iso()}
        target['traffic_split'] = {'stable': 100 - canary, 'canary': canary}
        chosen['status'] = 'canary'
        chosen['traffic_role'] = 'canary'
        stable_rev = next((r for r in revisions if int(r.get('revision', 0)) == previous_revision), None)
        if stable_rev:
            stable_rev['status'] = 'active'
            stable_rev['traffic_role'] = 'stable'
    target.setdefault('rollout_history', []).append({'at': _now_iso(), 'action': 'rollout', 'target_revision': int(revision), 'previous_revision': previous_revision, 'traffic_split': dict(target.get('traffic_split') or {'stable': 100, 'canary': 0})})
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'revision': chosen, 'state_path': str(state_path), 'remote': False}


def update_traffic_split(ref: str, stable_percent: int, canary_percent: int, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    split = _normalize_split({'stable': stable_percent, 'canary': canary_percent})
    if _is_remote_control_plane(control_plane):
        return _request_json('POST', _remote_url(str(control_plane), '/deployments/traffic'), payload={'ref': ref, 'traffic_split': split}, token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    canary = target.get('canary') or {}
    if not canary or not int(canary.get('revision') or 0):
        return {'ok': False, 'error': 'no canary revision active for deployment', 'remote': False}
    canary['traffic_split'] = split
    target['canary'] = canary
    target['traffic_split'] = split
    target['status'] = 'canary' if split.get('canary', 0) > 0 else 'rolled-out'
    target.setdefault('rollout_history', []).append({'at': _now_iso(), 'action': 'traffic', 'traffic_split': split})
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'traffic_split': split, 'state_path': str(state_path), 'remote': False}


def rollback_deployment(ref: str, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None, revision: int | None = None) -> Dict[str, Any]:
    payload = {'ref': ref}
    if revision is not None:
        payload['revision'] = int(revision)
    if _is_remote_control_plane(control_plane):
        return _request_json('POST', _remote_url(str(control_plane), '/deployments/rollback'), payload=payload, token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    revisions = list(target.get('revisions') or [])
    current = int(target.get('current_revision') or 0)
    if revision is None:
        candidates = [int(r.get('revision', 0)) for r in revisions if int(r.get('revision', 0)) != current]
        if not candidates:
            return {'ok': False, 'error': 'no revision available to roll back to', 'remote': False}
        revision = max(candidates)
    chosen = next((r for r in revisions if int(r.get('revision', 0)) == int(revision)), None)
    if not chosen:
        return {'ok': False, 'error': f'revision not found: {revision}', 'remote': False}
    previous = current
    target['current_revision'] = int(revision)
    target['status'] = 'rolled-back'
    target['canary'] = None
    target['traffic_split'] = {'stable': 100, 'canary': 0}
    chosen['status'] = 'active'
    chosen['traffic_role'] = 'stable'
    for rev in revisions:
        if rev is not chosen and rev.get('status') in ('active', 'canary'):
            rev['status'] = 'synced'
            rev['traffic_role'] = 'candidate'
    target.setdefault('rollout_history', []).append({'at': _now_iso(), 'action': 'rollback', 'target_revision': int(revision), 'previous_revision': previous, 'traffic_split': {'stable': 100, 'canary': 0}})
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'revision': chosen, 'state_path': str(state_path), 'remote': False}
