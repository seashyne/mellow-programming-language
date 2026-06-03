import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mellowlang.agents.packages import init_agent_package
from mellowlang.agents.deployment import write_deployment_bundle
from mellowlang.agents.control_plane import sync_deployment, rollout_revision, update_traffic_split, rollback_deployment, run_health_check, get_deployment_status


def test_local_canary_traffic_health_and_rollback(tmp_path: Path):
    pkg_dir = tmp_path / "agent"
    init_agent_package(pkg_dir, name="health.agent")
    out = tmp_path / "deploy"
    res = write_deployment_bundle(pkg_dir, out, target="docker")
    sync_deployment(res["manifest"], out, control_plane=None, state_dir=tmp_path / "cp", manifest_path=res["manifest_path"], revision_notes="first")
    sync_deployment(res["manifest"], out, control_plane=None, state_dir=tmp_path / "cp", manifest_path=res["manifest_path"], revision_notes="second")
    rolled = rollout_revision("health.agent", 2, state_dir=tmp_path / "cp", canary_percent=20)
    assert rolled["ok"] is True
    assert rolled["deployment"]["status"] == "canary"
    assert rolled["deployment"]["traffic_split"]["canary"] == 20
    traffic = update_traffic_split("health.agent", 70, 30, state_dir=tmp_path / "cp")
    assert traffic["traffic_split"] == {"stable": 70, "canary": 30}
    health = run_health_check("health.agent", state_dir=tmp_path / "cp")
    assert health["health"]["status"] == "healthy"
    rolled_back = rollback_deployment("health.agent", state_dir=tmp_path / "cp", revision=1)
    assert rolled_back["deployment"]["current_revision"] == 1
    assert rolled_back["deployment"]["status"] == "rolled-back"
    status = get_deployment_status("health.agent", state_dir=tmp_path / "cp")
    assert status["deployment"]["traffic_split"] == {"stable": 100, "canary": 0}


def test_remote_health_traffic_and_rollback(tmp_path: Path):
    pkg_dir = tmp_path / 'agent2'
    init_agent_package(pkg_dir, name='remote.health.agent')
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
                revision = {'revision': len(revs) + 1, 'status': 'synced'}
                revs.append(revision)
                dep = state['items'].setdefault(dep_id, {'id': dep_id, 'package': manifest['package'], 'provider': manifest['runtime']['provider'], 'status': 'synced', 'current_revision': 1, 'latest_revision': 1, 'bundle_dir': payload['bundle_dir'], 'traffic_split': {'stable': 100, 'canary': 0}})
                dep['latest_revision'] = revision['revision']
                self._json(200, {'ok': True, 'deployment': dep, 'revision': revision, 'remote': True})
                return
            if self.path == '/deployments/rollout':
                dep = state['items'][payload['ref']]
                dep['status'] = 'canary' if payload.get('canary_percent') else 'rolled-out'
                dep['traffic_split'] = {'stable': 100 - int(payload.get('canary_percent') or 0), 'canary': int(payload.get('canary_percent') or 0)} if payload.get('canary_percent') else {'stable': 100, 'canary': 0}
                self._json(200, {'ok': True, 'deployment': dep, 'revision': {'revision': int(payload['revision'])}, 'remote': True})
                return
            if self.path == '/deployments/traffic':
                dep = state['items'][payload['ref']]
                dep['traffic_split'] = payload['traffic_split']
                self._json(200, {'ok': True, 'deployment': dep, 'traffic_split': payload['traffic_split'], 'remote': True})
                return
            if self.path == '/deployments/rollback':
                dep = state['items'][payload['ref']]
                dep['current_revision'] = int(payload.get('revision') or 1)
                dep['status'] = 'rolled-back'
                dep['traffic_split'] = {'stable': 100, 'canary': 0}
                self._json(200, {'ok': True, 'deployment': dep, 'revision': {'revision': dep['current_revision']}, 'remote': True})
                return
            self._json(404, {'ok': False})

        def do_GET(self):
            if self.path.startswith('/deployments/health'):
                ref = self.path.split('ref=', 1)[1]
                dep = state['items'][ref]
                self._json(200, {'ok': True, 'deployment': dep, 'health': {'status': 'healthy'}, 'remote': True})
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
        dep_id = synced['deployment']['id']
        rolled = rollout_revision(dep_id, 1, control_plane=base, canary_percent=10)
        assert rolled['deployment']['traffic_split']['canary'] == 10
        traffic = update_traffic_split(dep_id, 60, 40, control_plane=base)
        assert traffic['traffic_split'] == {'stable': 60, 'canary': 40}
        health = run_health_check(dep_id, control_plane=base)
        assert health['health']['status'] == 'healthy'
        back = rollback_deployment(dep_id, control_plane=base, revision=1)
        assert back['deployment']['status'] == 'rolled-back'
    finally:
        server.shutdown()
        thread.join(timeout=2)
