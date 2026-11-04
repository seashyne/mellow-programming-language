"""The serving surface: playground, serve, marketplace and deploy."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
import json

from ...common import _cli_line, _json_print
from .deps import (
    serve_playground, build_static_playground, load_agent_package, search_agent_local,
    search_agent_remote, load_deployment_manifest, write_deployment_bundle, register_deployment,
    sync_deployment,
)
from .support import _make_agent_runtime, _resolve_agent_package_ref, _run_agent_package

def _cmd_playground(host: str, port: int, build_only: bool, out: str, json_out: bool) -> int:
    target = build_static_playground(out)
    payload = {
        "ok": True,
        "path": str(target.resolve()),
        "url": None if build_only else f"http://{host}:{port}/",
        "served": not build_only,
        "host": host,
        "port": int(port),
    }
    if build_only:
        if json_out:
            _json_print(payload)
        else:
            _cli_line(f"Playground assets written to {target}", kind="ok")
        return 0

    server = serve_playground(host=host, port=port)
    if json_out:
        _json_print(payload)
        return 0
    _cli_line(f"Mellow Playground serving at {payload['url']}", kind='ok')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0

def _cmd_agent_playground(out: str, serve: bool, port: int, json_out: bool) -> int:
    build_only = not bool(serve)
    return _cmd_playground("127.0.0.1", port, build_only, str(Path(out).parent), json_out)

def _cmd_agent_serve(package: str | None, host: str, port: int, json_out: bool, deployment_manifest: str | None = None) -> int:
    manifest = load_deployment_manifest(deployment_manifest) if deployment_manifest else None
    effective_host = str((manifest or {}).get('runtime', {}).get('host', host))
    effective_port = int((manifest or {}).get('runtime', {}).get('port', port))
    effective_package = package
    if manifest and not effective_package:
        candidate = (Path(deployment_manifest).parent / 'package').resolve()
        if candidate.exists():
            effective_package = str(candidate)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            health_path = str((manifest or {}).get('runtime', {}).get('healthcheck', 'GET /health')).split(' ', 1)[-1]
            if self.path == health_path:
                body = json.dumps({'ok': True, 'provider': (manifest or {}).get('runtime', {}).get('provider', 'local-http')}).encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404); self.end_headers()

        def do_POST(self):
            run_path = str((manifest or {}).get('runtime', {}).get('entrypoint', 'POST /run')).split(' ', 1)[-1]
            if self.path != run_path:
                self.send_response(404); self.end_headers(); return
            length = int(self.headers.get('Content-Length', '0') or '0')
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw.decode('utf-8'))
            except Exception:
                data = {}
            task = str(data.get('task', 'demo task'))
            if effective_package:
                payload = {'ok': _run_agent_package(effective_package, task, json_out=True) == 0, 'task': task, 'deployment_manifest': deployment_manifest}
            else:
                runtime = _make_agent_runtime('rule-based', '.mellow/agent_memory.jsonl', '.mellow/agent_observability.jsonl')
                res = runtime.run(task)
                payload = {'ok': True, 'task': task, 'answer': res.answer, 'deployment_manifest': deployment_manifest}
            body = json.dumps(payload).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    if json_out:
        _json_print({'ok': True, 'host': effective_host, 'port': effective_port, 'package': effective_package, 'deployment_manifest': deployment_manifest})
        return 0
    _cli_line(f'Hosted agent server listening on http://{effective_host}:{effective_port}', kind='ok')
    server = ThreadingHTTPServer((effective_host, effective_port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0

def _cmd_agent_marketplace(query: str, online: bool, registry: str | None, json_out: bool) -> int:
    res = search_agent_remote(query, registry=registry) if online else search_agent_local(query)
    payload = {'ok': True, 'query': query, 'items': list(res.get('items') or []), 'source': 'remote' if online else 'local'}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Marketplace results ({payload['source']})", kind='ok')
        for item in payload['items']:
            print(f"- {item.get('name')}@{item.get('version', '?')} :: model={item.get('model', 'rule-based')} tags={','.join(item.get('tags') or [])}")
    return 0

def _cmd_agent_deploy(ref: str, out: str, json_out: bool, public_url: str | None = None, host: str | None = None, port: int | None = None, target: str | None = None, control_plane: str | None = None) -> int:
    pkg_root = _resolve_agent_package_ref(ref)
    pkg = load_agent_package(pkg_root)
    out_dir = Path(out) / pkg.name.replace('.', '_')
    bundle = write_deployment_bundle(pkg_root, out_dir, public_url=public_url, host=host, port=port, target=target, control_plane=control_plane)
    reg = sync_deployment(bundle['manifest'], out_dir, control_plane=control_plane, manifest_path=bundle['manifest_path']) if control_plane else register_deployment(bundle['manifest'], out_dir, manifest_path=bundle['manifest_path'])
    payload = {'ok': True, 'out_dir': str(out_dir.resolve()), 'manifest': bundle['manifest'], 'manifest_path': bundle['manifest_path'], 'start_script': bundle['start_script'], 'adapters': bundle.get('adapters', {}), 'deployment': reg.get('deployment'), 'revision': reg.get('revision'), 'remote': reg.get('remote', False)}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Deployment bundle written to {out_dir}", kind='ok')
        print(f"Manifest        : {bundle['manifest_path']}")
        print(f"Start script    : {bundle['start_script']}")
        print(f"Target          : {bundle['manifest']['runtime']['provider']}")
        if bundle.get('adapters'):
            print(f"Adapters        : {json.dumps(bundle['adapters'], ensure_ascii=False)}")
        if reg.get('deployment'):
            print(f"Deployment ID   : {reg['deployment']['id']}")
        if reg.get('revision'):
            print(f"Revision        : {reg['revision']['revision']}")
        if reg.get('remote'):
            print('Control plane   : remote sync completed')
    return 0
