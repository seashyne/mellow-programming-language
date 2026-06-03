import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mellowlang.agents.packages import init_agent_package
from mellowlang.agents.deployment import write_deployment_bundle
from mellowlang.agents.control_plane import sync_deployment, list_revisions, rollout_revision, get_deployment_status


def test_local_revisions_and_rollout(tmp_path: Path):
    pkg_dir = tmp_path / 'agent'
    init_agent_package(pkg_dir, name='roll.agent')
    out = tmp_path / 'deploy'
    res = write_deployment_bundle(pkg_dir, out, target='docker')
    r1 = sync_deployment(res['manifest'], out, control_plane=None, state_dir=tmp_path / 'cp', manifest_path=res['manifest_path'], revision_notes='first')
    r2 = sync_deployment(res['manifest'], out, control_plane=None, state_dir=tmp_path / 'cp', manifest_path=res['manifest_path'], revision_notes='second')
    assert r2['revision']['revision'] == 2
    revs = list_revisions('roll.agent', state_dir=tmp_path / 'cp')
    assert revs['count'] == 2
    rolled = rollout_revision('roll.agent', 2, state_dir=tmp_path / 'cp')
    assert rolled['ok'] is True
    status = get_deployment_status('roll.agent', state_dir=tmp_path / 'cp')
    assert status['deployment']['current_revision'] == 2


def test_remote_sync_and_rollout(tmp_path: Path):
    pkg_dir = tmp_path / 'agent2'
    init_agent_package(pkg_dir, name='remote.agent')
    out = tmp_path / 'deploy2'
    res = write_deployment_bundle(pkg_dir, out, target='vercel')

    state = {'items': {}, 'revisions': {}}

    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, payload):
            body = json.dumps(payload).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get('Content-Length', '0') or '0')
            payload = json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            if self.path == '/deployments/sync':
                manifest = payload['manifest']
                dep_id = manifest['package']['name'] + '-' + manifest['runtime']['provider']
                revs = state['revisions'].setdefault(dep_id, [])
                revision = {'revision': len(revs)+1, 'status': 'synced'}
                revs.append(revision)
                dep = state['items'].setdefault(dep_id, {'id': dep_id, 'package': manifest['package'], 'provider': manifest['runtime']['provider'], 'status': 'synced', 'current_revision': 1, 'latest_revision': 1, 'bundle_dir': payload['bundle_dir']})
                dep['latest_revision'] = revision['revision']
                self._json(200, {'ok': True, 'deployment': dep, 'revision': revision, 'remote': True})
                return
            if self.path == '/deployments/rollout':
                dep = state['items'][payload['ref']]
                dep['current_revision'] = int(payload['revision'])
                dep['status'] = 'rolled-out'
                self._json(200, {'ok': True, 'deployment': dep, 'revision': {'revision': int(payload['revision'])}, 'remote': True})
                return
            self._json(404, {'ok': False})

        def do_GET(self):
            if self.path.startswith('/deployments/status'):
                ref = self.path.split('ref=',1)[1]
                dep = state['items'][ref]
                self._json(200, {'ok': True, 'deployment': dep, 'remote': True})
                return
            if self.path.startswith('/deployments/revisions'):
                ref = self.path.split('ref=',1)[1]
                revs = state['revisions'][ref]
                self._json(200, {'ok': True, 'items': revs, 'count': len(revs), 'current_revision': state['items'][ref]['current_revision'], 'remote': True})
                return
            self._json(404, {'ok': False})

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f'http://127.0.0.1:{server.server_port}'
        synced = sync_deployment(res['manifest'], out, control_plane=base, manifest_path=res['manifest_path'])
        assert synced['ok'] is True
        dep_id = synced['deployment']['id']
        revs = list_revisions(dep_id, control_plane=base)
        assert revs['count'] == 1
        rolled = rollout_revision(dep_id, 1, control_plane=base)
        assert rolled['deployment']['current_revision'] == 1
    finally:
        server.shutdown()
        thread.join(timeout=2)
