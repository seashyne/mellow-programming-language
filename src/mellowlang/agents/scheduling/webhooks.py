"""The inbound event surface: named webhooks with a token, the filter match on a payload, and the
   emit/receive pair that turns an event into queue items."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict

from .paths import _now_iso
from .state import (
    _load_triggers,
    _load_webhooks,
    _save_triggers,
    _save_webhooks,
)
from .jobs import add_trigger
from .queue import enqueue_job


def add_webhook(name: str, event: str, *, token: str | None = None, state_dir: str | Path | None = None, **job_kwargs: Any) -> Dict[str, Any]:
    token = token or uuid.uuid4().hex
    webhooks = _load_webhooks(state_dir)
    hook = {
        'id': uuid.uuid4().hex[:10],
        'name': name,
        'event': event,
        'token': token,
        'created_at': _now_iso(),
        'enabled': True,
    }
    webhooks['webhooks'].append(hook)
    _save_webhooks(webhooks, state_dir)
    trig = add_trigger(name=name, event=event, state_dir=state_dir, **job_kwargs)
    trig['webhook'] = hook
    return trig


def list_webhooks(state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_webhooks(state_dir)
    items = list(state.get('webhooks') or [])
    return {'ok': True, 'items': items, 'count': len(items)}


def _filter_match(filters: dict[str, Any], payload: dict[str, Any]) -> bool:
    for key, expected in (filters or {}).items():
        if payload.get(key) != expected:
            return False
    return True


def emit_event(event: str, payload: Dict[str, Any] | None = None, *, state_dir: str | Path | None = None, source: str = 'event') -> Dict[str, Any]:
    payload = dict(payload or {})
    triggers = _load_triggers(state_dir)
    matched = []
    for trig in triggers.get('triggers') or []:
        if not trig.get('enabled', True):
            continue
        if str(trig.get('event')) != str(event):
            continue
        if not _filter_match(dict(trig.get('filters') or {}), payload):
            continue
        q = enqueue_job(trig, payload, source=source, state_dir=state_dir)
        trig['last_event'] = {'event': event, 'at': _now_iso(), 'payload': payload}
        trig['run_count'] = int(trig.get('run_count') or 0) + 1
        matched.append(q['item'])
    p = _save_triggers(triggers, state_dir)
    return {'ok': True, 'event': event, 'matched': len(matched), 'items': matched, 'path': str(p)}


def receive_webhook(name: str, payload: Dict[str, Any] | None = None, *, token: str | None = None, state_dir: str | Path | None = None) -> Dict[str, Any]:
    hooks = _load_webhooks(state_dir)
    hook = next((h for h in hooks.get('webhooks') or [] if h.get('name') == name), None)
    if not hook:
        return {'ok': False, 'error': f'webhook not found: {name}'}
    if token and str(hook.get('token')) != str(token):
        return {'ok': False, 'error': 'invalid webhook token'}
    return emit_event(str(hook.get('event')), payload, state_dir=state_dir, source='webhook')
