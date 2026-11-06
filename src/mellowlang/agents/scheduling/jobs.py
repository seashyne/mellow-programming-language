"""Scheduled jobs and event triggers: the two definitions that carry a task, their
   model/memory/sandbox options, and the listing that reads them back."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict

from .paths import _now_iso
from .state import (
    _load_jobs,
    _load_triggers,
    _save_jobs,
    _save_triggers,
)
from .cron import next_run
from .backoff import _normalize_backoff


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
