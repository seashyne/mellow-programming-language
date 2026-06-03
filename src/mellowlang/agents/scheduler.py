from __future__ import annotations

import json
import math
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import parse_qs, urlparse

SCHEDULER_HOME = Path('.mellow/scheduler')


def _root(base: str | Path | None = None) -> Path:
    root = Path(base) if base else SCHEDULER_HOME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _jobs_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'jobs.json'


def _runner_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'runner.json'


def _triggers_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'triggers.json'


def _queue_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'queue.json'


def _queue_log_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'queue_log.jsonl'


def _dead_letter_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'dead_letter.json'


def _webhooks_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'webhooks.json'


def _server_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'webhook_server.json'


def _job_api_path(base: str | Path | None = None) -> Path:
    return _root(base) / 'job_api.json'


def _now_iso(dt: datetime | None = None) -> str:
    value = dt or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value)
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        return datetime.fromisoformat(raw).astimezone(timezone.utc)
    except Exception:
        return None


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(payload, ensure_ascii=False) + '\n')


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                merged = dict(default)
                merged.update(data)
                return merged
        except Exception:
            pass
    return dict(default)


def _save_json(path: Path, state: Dict[str, Any]) -> Path:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def _load_jobs(base: str | Path | None = None) -> Dict[str, Any]:
    return _load_json(_jobs_path(base), {'jobs': []})


def _save_jobs(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    return _save_json(_jobs_path(base), state)


def _load_triggers(base: str | Path | None = None) -> Dict[str, Any]:
    return _load_json(_triggers_path(base), {'triggers': []})


def _save_triggers(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    return _save_json(_triggers_path(base), state)


def _load_queue(base: str | Path | None = None) -> Dict[str, Any]:
    return _load_json(_queue_path(base), {'items': []})


def _save_queue(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    return _save_json(_queue_path(base), state)


def _load_dead_letter(base: str | Path | None = None) -> Dict[str, Any]:
    return _load_json(_dead_letter_path(base), {'items': []})


def _save_dead_letter(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    return _save_json(_dead_letter_path(base), state)


def _load_webhooks(base: str | Path | None = None) -> Dict[str, Any]:
    return _load_json(_webhooks_path(base), {'webhooks': []})


def _save_webhooks(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    return _save_json(_webhooks_path(base), state)


def _load_server_state(base: str | Path | None = None) -> Dict[str, Any]:
    return _load_json(_server_path(base), {'running': False})


def _save_server_state(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    return _save_json(_server_path(base), state)


def _load_job_api_state(base: str | Path | None = None) -> Dict[str, Any]:
    return _load_json(_job_api_path(base), {'running': False})


def _save_job_api_state(state: Dict[str, Any], base: str | Path | None = None) -> Path:
    return _save_json(_job_api_path(base), state)


def _parse_field(field: str, value: int) -> bool:
    field = str(field).strip()
    if field == '*':
        return True
    if field.startswith('*/'):
        try:
            step = int(field[2:])
            return step > 0 and value % step == 0
        except Exception:
            return False
    parts = [x.strip() for x in field.split(',') if x.strip()]
    for part in parts:
        if '-' in part:
            try:
                a, b = [int(x) for x in part.split('-', 1)]
                if a <= value <= b:
                    return True
            except Exception:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except Exception:
                continue
    return False


def cron_matches(expr: str, dt: datetime | None = None) -> bool:
    now = (dt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expr = str(expr or '').strip().lower()
    aliases = {'@hourly': '0 * * * *', '@daily': '0 0 * * *', '@weekly': '0 0 * * 0'}
    expr = aliases.get(expr, expr)
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f'invalid cron expression: {expr}')
    minute, hour, dom, month, dow = fields
    py_dow = (now.weekday() + 1) % 7
    return (
        _parse_field(minute, now.minute)
        and _parse_field(hour, now.hour)
        and _parse_field(dom, now.day)
        and _parse_field(month, now.month)
        and _parse_field(dow, py_dow)
    )


def next_run(expr: str, from_dt: datetime | None = None, *, max_minutes: int = 60 * 24 * 31) -> str:
    start = (from_dt or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    probe = start + timedelta(minutes=1)
    for _ in range(max_minutes):
        if cron_matches(expr, probe):
            return _now_iso(probe)
        probe += timedelta(minutes=1)
    raise ValueError(f'could not find next run for cron: {expr}')


def _normalize_backoff(backoff: Dict[str, Any] | None = None) -> Dict[str, Any]:
    raw = dict(backoff or {})
    strategy = str(raw.get('strategy') or 'fixed').lower()
    if strategy not in {'fixed', 'exponential', 'jitter'}:
        strategy = 'fixed'
    initial = max(0, int(raw.get('initial_delay_ms') or 0))
    max_delay = max(initial, int(raw.get('max_delay_ms') or initial or 0))
    jitter_pct = max(0.0, min(1.0, float(raw.get('jitter_pct') or 0.15)))
    return {
        'strategy': strategy,
        'initial_delay_ms': initial,
        'max_delay_ms': max_delay,
        'jitter_pct': jitter_pct,
    }


def _compute_backoff_delay_ms(backoff: Dict[str, Any], attempt: int) -> int:
    policy = _normalize_backoff(backoff)
    base = int(policy.get('initial_delay_ms') or 0)
    if base <= 0:
        return 0
    strategy = str(policy.get('strategy') or 'fixed')
    if strategy == 'fixed':
        delay = base
    else:
        exp = max(0, int(attempt) - 1)
        delay = base * int(math.pow(2, exp))
        delay = min(delay, int(policy.get('max_delay_ms') or delay))
        if strategy == 'jitter':
            jitter_pct = float(policy.get('jitter_pct') or 0.15)
            low = max(0, int(delay * (1.0 - jitter_pct)))
            high = max(low, int(delay * (1.0 + jitter_pct)))
            delay = random.randint(low, high)
    return int(delay)


def add_job(name: str, schedule: str, task: str, *, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, backoff: Dict[str, Any] | None = None, state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_jobs(state_dir)
    record = {
        'id': uuid.uuid4().hex[:10],
        'name': name,
        'kind': kind,
        'schedule': schedule,
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
        'enabled': True,
        'created_at': _now_iso(),
        'next_run': next_run(schedule),
        'last_run': None,
        'last_result': None,
        'run_count': 0,
    }
    state['jobs'].append(record)
    p = _save_jobs(state, state_dir)
    return {'ok': True, 'job': record, 'path': str(p)}


def list_jobs(state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_jobs(state_dir)
    items = list(state.get('jobs') or [])
    return {'ok': True, 'items': items, 'count': len(items)}


def add_trigger(name: str, event: str, task: str, *, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, filters: dict[str, Any] | None = None, backoff: Dict[str, Any] | None = None, state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_triggers(state_dir)
    record = {
        'id': uuid.uuid4().hex[:10],
        'name': name,
        'event': event,
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
        'filters': dict(filters or {}),
        'enabled': True,
        'created_at': _now_iso(),
        'last_event': None,
        'run_count': 0,
        'source': 'event',
    }
    state['triggers'].append(record)
    p = _save_triggers(state, state_dir)
    return {'ok': True, 'trigger': record, 'path': str(p)}


def list_triggers(state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_triggers(state_dir)
    items = list(state.get('triggers') or [])
    return {'ok': True, 'items': items, 'count': len(items)}


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


def _should_run(job: Dict[str, Any], now: datetime) -> bool:
    if not job.get('enabled', True):
        return False
    try:
        if not cron_matches(str(job.get('schedule') or '* * * * *'), now):
            return False
    except Exception:
        return False
    last_run = str(job.get('last_run') or '')
    return last_run[:16] != _now_iso(now)[:16]


def run_due_jobs(*, state_dir: str | Path | None = None, now: datetime | None = None, callback: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None) -> Dict[str, Any]:
    state = _load_jobs(state_dir)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    ran: List[Dict[str, Any]] = []
    due: List[Dict[str, Any]] = []
    for job in state.get('jobs') or []:
        if _should_run(job, current):
            due.append(job)
            result = callback(job) if callback else {'ok': True, 'answer': f"scheduled run for {job['task']}"}
            job['last_run'] = _now_iso(current)
            job['next_run'] = next_run(str(job.get('schedule')), current)
            job['last_result'] = result
            job['run_count'] = int(job.get('run_count') or 0) + 1
            ran.append({'id': job['id'], 'name': job['name'], 'result': result})
    p = _save_jobs(state, state_dir)
    return {'ok': True, 'count': len(ran), 'due': len(due), 'items': ran, 'path': str(p)}


def _move_to_dead_letter(item: Dict[str, Any], *, state_dir: str | Path | None = None, reason: str | None = None) -> None:
    dlq = _load_dead_letter(state_dir)
    item = dict(item)
    item['status'] = 'dead-letter'
    item['dead_lettered_at'] = _now_iso()
    if reason:
        item['last_error'] = reason
    dlq['items'].append(item)
    _save_dead_letter(dlq, state_dir)
    _append_jsonl(_queue_log_path(state_dir), {'ts': _now_iso(), 'event': 'dead-letter', 'item': {'id': item['id'], 'name': item['name']}, 'reason': item.get('last_error')})


def retry_queue_item(item_id: str, *, state_dir: str | Path | None = None) -> Dict[str, Any]:
    dlq = _load_dead_letter(state_dir)
    queue = _load_queue(state_dir)
    for idx, item in enumerate(dlq.get('items') or []):
        if str(item.get('id')) == str(item_id):
            revived = dict(item)
            revived['status'] = 'queued'
            revived['queue'] = 'main'
            revived['started_at'] = None
            revived['finished_at'] = None
            revived['result'] = None
            revived['available_at'] = _now_iso()
            queue['items'].append(revived)
            del dlq['items'][idx]
            _save_dead_letter(dlq, state_dir)
            _save_queue(queue, state_dir)
            _append_jsonl(_queue_log_path(state_dir), {'ts': _now_iso(), 'event': 'requeue-dead-letter', 'item': {'id': revived['id'], 'name': revived['name']}})
            return {'ok': True, 'item': revived}
    return {'ok': False, 'error': f'queue item not found in dead-letter queue: {item_id}'}


def _is_available(item: Dict[str, Any], now: datetime) -> bool:
    available = _parse_iso(str(item.get('available_at') or ''))
    return available is None or available <= now


def _process_queue_item(item: Dict[str, Any], callback: Callable[[Dict[str, Any]], Dict[str, Any]] | None, state_dir: str | Path | None = None) -> Dict[str, Any]:
    item['status'] = 'running'
    item['started_at'] = _now_iso()
    item['attempts'] = int(item.get('attempts') or 0) + 1
    _append_jsonl(_queue_log_path(state_dir), {'ts': _now_iso(), 'event': 'start', 'item': {'id': item['id'], 'name': item['name']}, 'attempt': item['attempts']})
    try:
        result = callback(item) if callback else {'ok': True, 'answer': f"queued run for {item['task']}"}
        if isinstance(result, dict) and result.get('ok') is False:
            raise RuntimeError(str(result.get('error') or 'job failed'))
        item['result'] = result
        item['status'] = 'done'
        item['finished_at'] = _now_iso()
        item['last_error'] = None
        _append_jsonl(_queue_log_path(state_dir), {'ts': _now_iso(), 'event': 'done', 'item': {'id': item['id'], 'name': item['name']}})
        return {'id': item['id'], 'name': item['name'], 'result': result, 'status': item['status']}
    except Exception as e:
        item['last_error'] = str(e)
        item['finished_at'] = _now_iso()
        if int(item.get('attempts') or 0) >= int(item.get('max_attempts') or 1):
            _move_to_dead_letter(item, state_dir=state_dir, reason=str(e))
            item['status'] = 'dead-letter'
        else:
            item['status'] = 'retry'
            delay_ms = _compute_backoff_delay_ms(dict(item.get('backoff') or {}), int(item.get('attempts') or 1))
            item['available_at'] = _now_iso(datetime.now(timezone.utc) + timedelta(milliseconds=delay_ms))
            item['next_retry_delay_ms'] = delay_ms
        _append_jsonl(_queue_log_path(state_dir), {'ts': _now_iso(), 'event': item['status'], 'item': {'id': item['id'], 'name': item['name']}, 'error': str(e), 'available_at': item.get('available_at')})
        return {'id': item['id'], 'name': item['name'], 'error': str(e), 'status': item['status'], 'available_at': item.get('available_at')}


def drain_queue(*, state_dir: str | Path | None = None, limit: int | None = None, callback: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None, workers: int = 1) -> Dict[str, Any]:
    state = _load_queue(state_dir)
    now = datetime.now(timezone.utc)
    items = list(state.get('items') or [])
    candidates = [i for i in items if i.get('status') in {'queued', 'retry'} and _is_available(i, now)]
    max_items = None if limit is None else max(0, int(limit))
    if max_items is not None:
        candidates = candidates[:max_items]
    workers = max(1, int(workers or 1))
    processed: list[dict[str, Any]] = []
    if workers == 1 or len(candidates) <= 1:
        for item in candidates:
            processed.append(_process_queue_item(item, callback, state_dir))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_process_queue_item, item, callback, state_dir): item for item in candidates}
            for fut in as_completed(futs):
                processed.append(fut.result())
    state['items'] = [i for i in state.get('items') or [] if i.get('status') != 'dead-letter']
    p = _save_queue(state, state_dir)
    return {'ok': True, 'count': len(processed), 'items': processed, 'path': str(p), 'workers': workers}


def write_runner_status(status: Dict[str, Any], base: str | Path | None = None) -> str:
    p = _runner_path(base)
    p.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return str(p)


def read_runner_status(base: str | Path | None = None) -> Dict[str, Any]:
    p = _runner_path(base)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {'running': False, 'iterations': 0, 'executed_jobs': 0, 'queue_mode': False, 'workers': 1}


def run_background_runner(*, state_dir: str | Path | None = None, interval_s: float = 1.0, iterations: int = 1, callback: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None, queue_backed: bool = False, queue_limit: int | None = None, workers: int = 1) -> Dict[str, Any]:
    started = _now_iso()
    status = {'ok': True, 'running': True, 'started_at': started, 'last_tick': None, 'iterations': 0, 'executed_jobs': 0, 'queue_mode': bool(queue_backed), 'workers': max(1, int(workers or 1))}
    write_runner_status(status, state_dir)
    total = 0
    try:
        loops = max(1, int(iterations or 1))
        for idx in range(loops):
            tick = drain_queue(state_dir=state_dir, callback=callback, limit=queue_limit, workers=workers) if queue_backed else run_due_jobs(state_dir=state_dir, callback=callback)
            total += int(tick.get('count') or 0)
            status.update({'running': True, 'last_tick': _now_iso(), 'iterations': idx + 1, 'executed_jobs': total})
            write_runner_status(status, state_dir)
            if idx + 1 < loops:
                time.sleep(max(0.0, float(interval_s or 0)))
    finally:
        status.update({'running': False, 'stopped_at': _now_iso(), 'executed_jobs': total})
        write_runner_status(status, state_dir)
    return status


def read_queue_log(*, state_dir: str | Path | None = None, limit: int = 50) -> Dict[str, Any]:
    path = _queue_log_path(state_dir)
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    limit = max(1, int(limit or 50))
    rows = rows[-limit:]
    return {'ok': True, 'items': rows, 'count': len(rows), 'path': str(path)}


def queue_stats(*, state_dir: str | Path | None = None) -> Dict[str, Any]:
    data = list_queue(state_dir)
    return {
        'ok': True,
        'queued': int(data.get('queued') or 0),
        'running': int(data.get('running') or 0),
        'retry': int(data.get('retry') or 0),
        'done': int(data.get('done') or 0),
        'dead_letter': int(data.get('dead_letter') or 0),
        'count': int(data.get('count') or 0),
    }


def _read_request_payload(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get('Content-Length') or 0)
    raw = handler.rfile.read(length) if length > 0 else b''
    try:
        payload = json.loads(raw.decode('utf-8')) if raw else {}
        if not isinstance(payload, dict):
            payload = {'body': payload}
    except Exception:
        payload = {'raw': raw.decode('utf-8', errors='replace')}
    return payload


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def start_webhook_server(*, host: str = '127.0.0.1', port: int = 8788, state_dir: str | Path | None = None, token_header: str = 'X-Mellow-Webhook-Token', run_once: bool = False, enable_job_api: bool = True) -> Dict[str, Any]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split('/') if p]
            if len(parts) == 2 and parts[0] == 'webhooks':
                name = parts[1]
                qs = parse_qs(parsed.query)
                token = self.headers.get(token_header) or (qs.get('token') or [None])[0]
                payload = _read_request_payload(self)
                res = receive_webhook(name, payload, token=token, state_dir=state_dir)
                _json_response(self, 200 if res.get('ok') else 400, res)
                if run_once:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if enable_job_api and len(parts) == 1 and parts[0] == 'jobs':
                payload = _read_request_payload(self)
                backoff = payload.get('backoff') if isinstance(payload.get('backoff'), dict) else None
                res = submit_job(
                    str(payload.get('task') or ''),
                    name=payload.get('name'),
                    kind=str(payload.get('kind') or 'run'),
                    package=payload.get('package'),
                    model=str(payload.get('model') or 'rule-based'),
                    memory=str(payload.get('memory') or '.mellow/agent_memory.jsonl'),
                    obs=str(payload.get('obs') or '.mellow/agent_observability.jsonl'),
                    rag_file=payload.get('rag_file'),
                    retries=int(payload.get('retries') or 1),
                    timeout_ms=payload.get('timeout_ms'),
                    parallel=bool(payload.get('parallel')),
                    sandbox=bool(payload.get('sandbox')),
                    allow_caps=list(payload.get('allow_caps') or []),
                    secrets=list(payload.get('secrets') or []),
                    backoff=backoff,
                    payload=payload.get('payload') if isinstance(payload.get('payload'), dict) else {},
                    state_dir=state_dir,
                )
                _json_response(self, 201 if res.get('ok') else 400, res)
                if run_once:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            _json_response(self, 404, {'ok': False, 'error': 'not found'})

        def do_GET(self):
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split('/') if p]
            if enable_job_api and len(parts) == 1 and parts[0] == 'jobs':
                data = list_queue(state_dir)
                _json_response(self, 200, data)
                return
            if enable_job_api and len(parts) == 2 and parts[0] == 'jobs':
                data = get_queue_item(parts[1], state_dir=state_dir)
                _json_response(self, 200 if data.get('ok') else 404, data)
                return
            if len(parts) == 1 and parts[0] == 'health':
                _json_response(self, 200, {'ok': True, 'service': 'mellow-agent-http', 'ts': _now_iso()})
                return
            _json_response(self, 404, {'ok': False, 'error': 'not found'})

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((host, int(port)), Handler)
    info = {
        'ok': True,
        'running': True,
        'host': host,
        'port': int(port),
        'url': f'http://{host}:{int(port)}',
        'token_header': token_header,
        'job_api': bool(enable_job_api),
        'started_at': _now_iso(),
    }
    _save_server_state(info, state_dir)
    _save_job_api_state(info, state_dir)
    try:
        server.serve_forever()
    finally:
        info.update({'running': False, 'stopped_at': _now_iso()})
        _save_server_state(info, state_dir)
        _save_job_api_state(info, state_dir)
    return info


def read_webhook_server_status(*, state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_server_state(state_dir)
    state.setdefault('ok', True)
    return state


def read_job_api_status(*, state_dir: str | Path | None = None) -> Dict[str, Any]:
    state = _load_job_api_state(state_dir)
    state.setdefault('ok', True)
    return state
