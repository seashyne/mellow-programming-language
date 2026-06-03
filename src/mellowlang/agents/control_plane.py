from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib import parse, request, error

CONTROL_PLANE_HOME = Path('.mellow/control-plane')


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _slugify(ref: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in '-_.' else '-' for ch in str(ref)).strip('-') or 'deployment'


def _is_remote_control_plane(url: str | None) -> bool:
    raw = str(url or '').strip().lower()
    return raw.startswith('http://') or raw.startswith('https://')


def _state_path(base: str | Path | None = None) -> Path:
    root = Path(base) if base else CONTROL_PLANE_HOME
    root.mkdir(parents=True, exist_ok=True)
    return root / 'state.json'


def _load_state(base: str | Path | None = None) -> Dict[str, Any]:
    p = _state_path(base)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data.setdefault('deployments', {})
                return data
        except Exception:
            pass
    return {'deployments': {}}


def _save_state(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    p = _state_path(base)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return p


def _normalize_split(split: Dict[str, Any] | None) -> Dict[str, int]:
    raw = dict(split or {})
    stable = int(raw.get('stable', 100) or 0)
    canary = int(raw.get('canary', 0) or 0)
    if stable < 0:
        stable = 0
    if canary < 0:
        canary = 0
    total = stable + canary
    if total <= 0:
        return {'stable': 100, 'canary': 0}
    if total != 100:
        stable = round((stable / total) * 100)
        canary = 100 - stable
    return {'stable': int(stable), 'canary': int(canary)}


def _rev_status_for(item: Dict[str, Any], rev_no: int) -> str:
    current = int(item.get('current_revision') or 0)
    canary = item.get('canary') or {}
    canary_rev = int(canary.get('revision') or 0) if canary else 0
    split = _normalize_split(canary.get('traffic_split')) if canary else {'stable': 100, 'canary': 0}
    if canary_rev == rev_no and split.get('canary', 0) > 0:
        return 'canary'
    if current == rev_no:
        return 'active'
    return 'synced'


def _find_local_target(state: Dict[str, Any], ref: str) -> Dict[str, Any] | None:
    deployments = state.get('deployments') or {}
    for dep_id, item in deployments.items():
        if dep_id == ref or item.get('package', {}).get('name') == ref:
            return item
    return None


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


def _request_json(method: str, url: str, payload: Dict[str, Any] | None = None, token: str | None = None) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = request.Request(url, data=data, method=method.upper())
    req.add_header('Accept', 'application/json')
    if payload is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body) if body else {'ok': True}
    except error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {'error': body or str(e)}
        parsed.setdefault('ok', False)
        parsed.setdefault('status', e.code)
        return parsed
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _remote_url(base: str, path: str, **query: Any) -> str:
    base = base.rstrip('/')
    url = base + path
    clean = {k: v for k, v in query.items() if v is not None}
    if clean:
        url += '?' + parse.urlencode(clean)
    return url


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



def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _metrics_history_for(target: Dict[str, Any]) -> list[Dict[str, Any]]:
    history = list(target.get('metrics_history') or [])
    target['metrics_history'] = history
    return history


def _compute_autoscaling_signals(target: Dict[str, Any]) -> Dict[str, Any]:
    metrics = dict(target.get('metrics') or {})
    current = max(1, _coerce_int(metrics.get('replicas'), _coerce_int(target.get('replicas'), 1) or 1))
    cpu = _coerce_float(metrics.get('cpu'), 0.0)
    memory = _coerce_float(metrics.get('memory'), 0.0)
    p95_ms = _coerce_float(metrics.get('p95_ms'), 0.0)
    error_rate = _coerce_float(metrics.get('error_rate'), 0.0)
    queued = _coerce_int(metrics.get('queued_requests'), 0)
    rps = _coerce_float(metrics.get('rps'), 0.0)
    pressure = max(cpu / 75.0 if cpu else 0.0, memory / 80.0 if memory else 0.0, p95_ms / 800.0 if p95_ms else 0.0, queued / 100.0 if queued else 0.0)
    desired = current
    reasons: list[str] = []
    if cpu >= 75:
        desired = max(desired, current + 1)
        reasons.append(f'cpu={cpu:.1f}%')
    if memory >= 80:
        desired = max(desired, current + 1)
        reasons.append(f'memory={memory:.1f}%')
    if p95_ms >= 800:
        desired = max(desired, current + 1)
        reasons.append(f'p95_ms={p95_ms:.0f}')
    if queued >= 100:
        desired = max(desired, current + 1)
        reasons.append(f'queue={queued}')
    if rps >= max(50.0, current * 50.0):
        desired = max(desired, current + 1)
        reasons.append(f'rps={rps:.1f}')
    if error_rate >= 0.08:
        reasons.append(f'error_rate={error_rate:.3f}')
    if not reasons and cpu <= 25 and memory <= 35 and p95_ms <= 250 and queued <= 5 and current > 1:
        desired = max(1, current - 1)
        reasons.append('low-utilization')
    if desired > current:
        action = 'scale-out'
    elif desired < current:
        action = 'scale-in'
    else:
        action = 'hold'
    result = {
        'current_replicas': current,
        'desired_replicas': desired,
        'action': action,
        'reasons': reasons,
        'pressure': round(pressure, 3),
        'computed_at': _now_iso(),
    }
    target['autoscaling'] = result
    target['replicas'] = desired if action in ('scale-out', 'scale-in') else current
    return result


def _evaluate_alerts_local(target: Dict[str, Any]) -> Dict[str, Any]:
    metrics = dict(target.get('metrics') or {})
    rules = list(target.get('alert_rules') or [])
    history = list(target.get('metrics_history') or [])
    active = []
    recent = history[-10:]
    for raw_rule in rules:
        rule = dict(raw_rule or {})
        metric = str(rule.get('metric') or '').strip()
        name = str(rule.get('name') or metric or 'rule').strip() or 'rule'
        op = str(rule.get('op') or '>=').strip() or '>='
        threshold = _coerce_float(rule.get('threshold'), 0.0)
        level = str(rule.get('level') or 'warn').strip() or 'warn'
        window = max(1, _coerce_int(rule.get('window'), 1))
        series = recent[-window:] if recent else []
        values = []
        if series:
            for item in series:
                values.append(_coerce_float((item.get('metrics') or {}).get(metric), metrics.get(metric, 0.0)))
        else:
            values = [_coerce_float(metrics.get(metric), 0.0)]
        def ok(v: float) -> bool:
            if op == '>=':
                return v >= threshold
            if op == '>':
                return v > threshold
            if op == '<=':
                return v <= threshold
            if op == '<':
                return v < threshold
            if op == '==':
                return abs(v - threshold) < 1e-9
            return v >= threshold
        if values and all(ok(v) for v in values):
            active.append({
                'name': name,
                'metric': metric,
                'op': op,
                'threshold': threshold,
                'level': level,
                'window': window,
                'values': values,
                'message': rule.get('message') or f'{metric} {op} {threshold}',
                'triggered_at': _now_iso(),
            })
    summary = {'active': active, 'count': len(active), 'status': 'firing' if active else 'ok', 'checked_at': _now_iso(), 'rules_count': len(rules)}
    target['alerts'] = summary
    return summary


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
