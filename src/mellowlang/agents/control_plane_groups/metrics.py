"""Coerce recorded metrics and derive the autoscaling signals from them."""

from __future__ import annotations

from typing import Any, Dict

from .state import _now_iso


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
