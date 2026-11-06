"""Evaluate a deployment's alert rules against its recent metrics."""

from __future__ import annotations

from typing import Any, Dict

from .metrics import _coerce_float, _coerce_int
from .state import _now_iso


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
