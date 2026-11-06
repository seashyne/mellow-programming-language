"""Queue draining: claiming an item, moving a failed one to the dead letter, retrying it, running a
   queue with workers, and reading the log and the stats."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict

from .paths import (
    _append_jsonl,
    _now_iso,
    _parse_iso,
    _queue_log_path,
)
from .state import (
    _load_dead_letter,
    _load_queue,
    _save_dead_letter,
    _save_queue,
)
from .backoff import _compute_backoff_delay_ms
from .queue import list_queue


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
