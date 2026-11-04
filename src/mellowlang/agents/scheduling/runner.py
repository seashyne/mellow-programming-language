"""The scheduler loop: which jobs are due, running them through a callback, and the background
   runner that writes its status file."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from .paths import _now_iso, _runner_path
from .state import _load_jobs, _save_jobs
from .cron import cron_matches, next_run
from .drain import drain_queue


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
