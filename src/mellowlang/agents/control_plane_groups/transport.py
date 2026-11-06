"""The HTTP side: whether a control plane is remote, how its URLs are
built, and how one JSON call is made."""

from __future__ import annotations

import json
from typing import Any, Dict
from urllib import parse, request, error


def _is_remote_control_plane(url: str | None) -> bool:
    raw = str(url or '').strip().lower()
    return raw.startswith('http://') or raw.startswith('https://')


def _request_json(method: str, url: str, payload: Dict[str, Any] | None = None, token: str | None = None) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = request.Request(url, data=data, method=method.upper())
    req.add_header('Accept', 'application/json')
    if payload is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body) if body else {'ok': True}
    except error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {'error': body or str(e)}
        parsed.setdefault('ok', False)
        parsed.setdefault('status', e.code)
        return parsed
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _remote_url(base: str, path: str, **query: Any) -> str:
    base = base.rstrip('/')
    url = base + path
    clean = {k: v for k, v in query.items() if v is not None}
    if clean:
        url += '?' + parse.urlencode(clean)
    return url
