"""The hosted surface: request parsing, JSON responses, the webhook and job API server, and the two
   status readers beside it."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from .paths import _now_iso
from .state import (
    _load_job_api_state,
    _load_server_state,
    _save_job_api_state,
    _save_server_state,
)
from .webhooks import receive_webhook
from .queue import get_queue_item, list_queue, submit_job


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
