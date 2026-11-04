"""Where the scheduler keeps its files and how a value becomes a timestamp: the state root, one
   path per store, the JSON and JSONL read/write primitives."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


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
