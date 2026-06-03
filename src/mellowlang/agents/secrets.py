from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List

SECRET_FILE = Path.home() / '.mellow' / 'agent_secrets.json'


def _ensure_parent() -> None:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)


def _normalize_scopes(scopes: Iterable[str] | None = None) -> List[str]:
    seen = []
    for item in scopes or []:
        value = str(item).strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def load_secret_records() -> Dict[str, Dict[str, object]]:
    if not SECRET_FILE.exists():
        return {}
    try:
        data = json.loads(SECRET_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}
    out: Dict[str, Dict[str, object]] = {}
    if not isinstance(data, dict):
        return out
    for key, value in data.items():
        name = str(key)
        if isinstance(value, str):
            out[name] = {'value': value, 'scopes': ['*']}
        elif isinstance(value, dict):
            out[name] = {
                'value': str(value.get('value', '')),
                'scopes': _normalize_scopes(value.get('scopes') or ['*']),
                'description': str(value.get('description', '')),
            }
    return out


def load_secrets() -> Dict[str, str]:
    return {name: str(meta.get('value', '')) for name, meta in load_secret_records().items()}


def save_secret_records(data: Dict[str, Dict[str, object]]) -> None:
    _ensure_parent()
    payload = {}
    for name, meta in sorted(data.items()):
        payload[str(name)] = {
            'value': str(meta.get('value', '')),
            'scopes': _normalize_scopes(meta.get('scopes') or ['*']),
            'description': str(meta.get('description', '')),
        }
    SECRET_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def save_secrets(data: Dict[str, str]) -> None:
    save_secret_records({name: {'value': value, 'scopes': ['*']} for name, value in data.items()})


def set_secret(name: str, value: str, *, scopes: Iterable[str] | None = None, description: str | None = None) -> None:
    data = load_secret_records()
    data[str(name)] = {
        'value': str(value),
        'scopes': _normalize_scopes(scopes or ['*']),
        'description': str(description or ''),
    }
    save_secret_records(data)


def remove_secret(name: str) -> bool:
    data = load_secret_records()
    existed = str(name) in data
    data.pop(str(name), None)
    save_secret_records(data)
    return existed


def list_secrets() -> List[dict]:
    out = []
    for name, meta in sorted(load_secret_records().items()):
        value = str(meta.get('value', ''))
        masked = value[:2] + '***' + value[-2:] if len(value) >= 6 else '***'
        out.append({
            'name': name,
            'masked': masked,
            'length': len(value),
            'scopes': list(meta.get('scopes') or ['*']),
            'description': str(meta.get('description', '')),
        })
    return out


def _secret_scope_allowed(record_scopes: Iterable[str], requested_scope: str | None = None) -> bool:
    scopes = set(_normalize_scopes(record_scopes))
    if not scopes or '*' in scopes:
        return True
    if not requested_scope:
        return True
    req = str(requested_scope).strip()
    if req in scopes:
        return True
    # hierarchical allowance: tool.search.docs matches tool.search.*
    parts = req.split('.')
    for i in range(len(parts), 0, -1):
        candidate = '.'.join(parts[:i]) + '.*'
        if candidate in scopes:
            return True
    return False


def resolve_secret_env(name: str, *, scope: str | None = None) -> str | None:
    if name in os.environ:
        return os.environ[name]
    record = load_secret_records().get(name)
    if not record:
        return None
    if not _secret_scope_allowed(record.get('scopes') or ['*'], scope):
        return None
    return str(record.get('value', ''))


def export_selected(names: list[str] | None = None, *, scope: str | None = None) -> Dict[str, str]:
    if not names:
        return {}
    out: Dict[str, str] = {}
    for name in names:
        val = resolve_secret_env(str(name), scope=scope)
        if val is not None:
            out[str(name)] = val
    return out
