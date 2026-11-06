"""Record metrics and manage alert rules on a deployment, locally or
remotely."""

from __future__ import annotations

from typing import Any, Dict

from .alerts import _evaluate_alerts_local
from .inspection import get_deployment_status
from .metrics import _compute_autoscaling_signals, _metrics_history_for
from .state import _load_state, _now_iso, _save_state
from .traffic import _find_local_target
from .transport import _is_remote_control_plane, _remote_url, _request_json


def record_deployment_metrics(ref: str, metrics: Dict[str, Any], state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    payload = {'ref': ref, 'metrics': dict(metrics or {})}
    if _is_remote_control_plane(control_plane):
        return _request_json('POST', _remote_url(str(control_plane), '/deployments/metrics'), payload=payload, token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    target['metrics'] = dict(metrics or {})
    target['metrics']['recorded_at'] = _now_iso()
    history = _metrics_history_for(target)
    history.append({'at': _now_iso(), 'metrics': dict(target['metrics'])})
    if len(history) > 50:
        del history[:-50]
    autoscaling = _compute_autoscaling_signals(target)
    alerts = _evaluate_alerts_local(target)
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'metrics': dict(target['metrics']), 'autoscaling': autoscaling, 'alerts': alerts, 'state_path': str(state_path), 'remote': False}


def get_deployment_metrics(ref: str, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return _request_json('GET', _remote_url(str(control_plane), '/deployments/metrics', ref=ref), token=api_token)
    status = get_deployment_status(ref, state_dir=state_dir)
    if not status.get('ok'):
        return status
    dep = status['deployment']
    return {'ok': True, 'deployment': dep, 'metrics': dict(dep.get('metrics') or {}), 'history': list(dep.get('metrics_history') or []), 'remote': False}


def get_autoscaling_signals(ref: str, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return _request_json('GET', _remote_url(str(control_plane), '/deployments/autoscaling', ref=ref), token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    signals = _compute_autoscaling_signals(target)
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'autoscaling': signals, 'state_path': str(state_path), 'remote': False}


def set_alert_rules(ref: str, rules: list[Dict[str, Any]], state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    payload = {'ref': ref, 'rules': list(rules or [])}
    if _is_remote_control_plane(control_plane):
        return _request_json('POST', _remote_url(str(control_plane), '/deployments/alert-rules'), payload=payload, token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    target['alert_rules'] = list(rules or [])
    alerts = _evaluate_alerts_local(target)
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'rules': target['alert_rules'], 'alerts': alerts, 'state_path': str(state_path), 'remote': False}


def evaluate_alerts(ref: str, state_dir: str | Path | None = None, *, control_plane: str | None = None, api_token: str | None = None) -> Dict[str, Any]:
    if _is_remote_control_plane(control_plane):
        return _request_json('GET', _remote_url(str(control_plane), '/deployments/alerts', ref=ref), token=api_token)
    state = _load_state(state_dir)
    target = _find_local_target(state, ref)
    if not target:
        return {'ok': False, 'error': f'deployment not found: {ref}', 'remote': False}
    alerts = _evaluate_alerts_local(target)
    state_path = _save_state(state, state_dir)
    return {'ok': True, 'deployment': target, 'alerts': alerts, 'rules': list(target.get('alert_rules') or []), 'state_path': str(state_path), 'remote': False}
