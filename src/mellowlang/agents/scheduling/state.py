"""One load/save pair per store on disk - jobs, triggers, queue, dead letter, webhooks, server
   state and the job API state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .paths import (
    _dead_letter_path,
    _job_api_path,
    _jobs_path,
    _load_json,
    _queue_path,
    _save_json,
    _server_path,
    _triggers_path,
    _webhooks_path,
)


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
