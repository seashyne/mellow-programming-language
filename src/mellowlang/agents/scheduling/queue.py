"""Queue items: building one from a trigger, submitting it directly, and reading a single item, a
   named queue, or the dead letter back."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict

from .paths import _append_jsonl, _now_iso, _queue_log_path
from .state import _load_dead_letter, _load_queue, _save_queue
from .backoff import _normalize_backoff


def _queue_item_from_trigger(trigger: Dict[str, Any], payload: Dict[str, Any] | None = None, *, source: str = 'event', queue_name: str = 'main') -> Dict[str, Any]:
    return {
        'id': uuid.uuid4().hex[:12],
        'trigger_id': trigger.get('id'),
        'name': trigger.get('name'),
        'event': trigger.get('event'),
        'kind': trigger.get('kind', 'run'),
        'task': trigger.get('task'),
        'package': trigger.get('package'),
        'model': trigger.get('model', 'rule-based'),
        'memory': trigger.get('memory', '.mellow/agent_memory.jsonl'),
        'obs': trigger.get('obs', '.mellow/agent_observability.jsonl'),
        'rag_file': trigger.get('rag_file'),
        'retries': int(trigger.get('retries') or 0),
        'timeout_ms': trigger.get('timeout_ms'),
        'parallel': bool(trigger.get('parallel')),
        'sandbox': bool(trigger.get('sandbox')),
        'allow_caps': list(trigger.get('allow_caps') or []),
        'secrets': list(trigger.get('secrets') or []),
        'payload': dict(payload or {}),
        'source': source,
        'queue': queue_name,
        'status': 'queued',
        'queued_at': _now_iso(),
        'available_at': _now_iso(),
        'started_at': None,
        'finished_at': None,
        'result': None,
        'attempts': 0,
        'max_attempts': max(1, int(trigger.get('retries') or 0) + 1),
        'last_error': None,
        'backoff': _normalize_backoff(trigger.get('backoff')),
    }


def enqueue_job(trigger: Dict[str, Any], payload: Dict[str, Any] | None = None, *, source: str = 'event', state_dir: str | Path | None = None, queue_name: str = 'main') -> Dict[str, Any]:
    state = _load_queue(state_dir)
    item = _queue_item_from_trigger(trigger, payload, source=source, queue_name=queue_name)
    state['items'].append(item)
    p = _save_queue(state, state_dir)
    _append_jsonl(_queue_log_path(state_dir), {'ts': _now_iso(), 'event': 'enqueue', 'queue': queue_name, 'item': {'id': item['id'], 'name': item['name'], 'event': item['event']}})
    return {'ok': True, 'item': item, 'path': str(p)}


def submit_job(task: str, *, name: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, backoff: Dict[str, Any] | None = None, payload: Dict[str, Any] | None = None, state_dir: str | Path | None = None, queue_name: str = 'main') -> Dict[str, Any]:
    trigger = {
        'id': uuid.uuid4().hex[:10],
        'name': name or f'job-{uuid.uuid4().hex[:6]}',
        'event': 'job.submit',
        'kind': kind,
        'task': task,
        'package': package,
        'model': model,
        'memory': memory,
        'obs': obs,
        'rag_file': rag_file,
        'retries': int(retries or 0),
        'timeout_ms': timeout_ms,
        'parallel': bool(parallel),
        'sandbox': bool(sandbox),
        'allow_caps': list(allow_caps or []),
        'secrets': list(secrets or []),
        'backoff': _normalize_backoff(backoff),
    }
    return enqueue_job(trigger, payload or {}, source='http-job', state_dir=state_dir, queue_name=queue_name)


def get_queue_item(item_id: str, *, state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_queue(state_dir)
    items = list(state.get('items') or [])
    for item in items:
        if str(item.get('id')) == str(item_id):
            return {'ok': True, 'item': item}
    dlq = _load_dead_letter(state_dir)
    for item in dlq.get('items') or []:
        if str(item.get('id')) == str(item_id):
            return {'ok': True, 'item': item, 'dead_letter': True}
    return {'ok': False, 'error': f'queue item not found: {item_id}'}


def list_queue(state_dir: str | Path | None = None, *, queue_name: str | None = None) -> Dict[str, Any]:
    state = _load_queue(state_dir)
    items = list(state.get('items') or [])
    if queue_name:
        items = [i for i in items if str(i.get('queue') or 'main') == queue_name]
    queued = [i for i in items if i.get('status') == 'queued']
    done = [i for i in items if i.get('status') == 'done']
    retry = [i for i in items if i.get('status') == 'retry']
    running = [i for i in items if i.get('status') == 'running']
    dlq = list((_load_dead_letter(state_dir).get('items') or [])) if queue_name in (None, 'dead-letter') else []
    return {'ok': True, 'items': items, 'count': len(items), 'queued': len(queued), 'done': len(done), 'retry': len(retry), 'running': len(running), 'dead_letter': len(dlq)}


def list_dead_letter(state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_dead_letter(state_dir)
    items = list(state.get('items') or [])
    return {'ok': True, 'items': items, 'count': len(items)}
