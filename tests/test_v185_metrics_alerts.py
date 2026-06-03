import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mellowlang.agents.packages import init_agent_package
from mellowlang.agents.deployment import write_deployment_bundle
from mellowlang.agents.control_plane import sync_deployment, record_deployment_metrics, get_autoscaling_signals, set_alert_rules, evaluate_alerts


def test_local_metrics_autoscaling_and_alerts(tmp_path: Path):
    pkg_dir = tmp_path / "agent"
    init_agent_package(pkg_dir, name="metrics.agent")
    out = tmp_path / "deploy"
    res = write_deployment_bundle(pkg_dir, out, target="docker")
    sync_deployment(res["manifest"], out, control_plane=None, state_dir=tmp_path / "cp", manifest_path=res["manifest_path"], revision_notes="first")
    rules = [{"name": "cpu-high", "metric": "cpu", "op": ">=", "threshold": 80, "window": 1, "level": "warn"}]
    configured = set_alert_rules("metrics.agent", rules, state_dir=tmp_path / "cp")
    assert configured["ok"] is True
    rec = record_deployment_metrics("metrics.agent", {"cpu": 91, "memory": 72, "rps": 140, "p95_ms": 950, "error_rate": 0.01, "replicas": 2, "queued_requests": 140}, state_dir=tmp_path / "cp")
    assert rec["ok"] is True
    assert rec["autoscaling"]["action"] == "scale-out"
    assert rec["alerts"]["status"] == "firing"
    signals = get_autoscaling_signals("metrics.agent", state_dir=tmp_path / "cp")
    assert signals["autoscaling"]["desired_replicas"] >= 3
    alerts = evaluate_alerts("metrics.agent", state_dir=tmp_path / "cp")
    assert alerts["alerts"]["count"] >= 1


def test_remote_metrics_alerts_endpoints(tmp_path: Path):
    pkg_dir = tmp_path / "agent2"
    init_agent_package(pkg_dir, name="remote.metrics.agent")
    out = tmp_path / "deploy2"
    res = write_deployment_bundle(pkg_dir, out, target="vercel")

    state = {"items": {}, "metrics": {}, "rules": {}}

    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            if self.path == "/deployments/sync":
                manifest = payload["manifest"]
                dep_id = manifest["package"]["name"] + "-" + manifest["runtime"]["provider"]
                dep = state["items"].setdefault(dep_id, {"id": dep_id, "package": manifest["package"], "provider": manifest["runtime"]["provider"], "status": "synced", "current_revision": 1, "latest_revision": 1, "bundle_dir": payload["bundle_dir"]})
                self._json(200, {"ok": True, "deployment": dep, "revision": {"revision": 1}, "remote": True})
                return
            if self.path == "/deployments/metrics":
                dep = state["items"][payload["ref"]]
                state["metrics"][payload["ref"]] = payload["metrics"]
                self._json(200, {"ok": True, "deployment": dep, "metrics": payload["metrics"], "autoscaling": {"action": "scale-out", "desired_replicas": 3}, "alerts": {"status": "ok", "count": 0}, "remote": True})
                return
            if self.path == "/deployments/alert-rules":
                dep = state["items"][payload["ref"]]
                state["rules"][payload["ref"]] = payload["rules"]
                self._json(200, {"ok": True, "deployment": dep, "rules": payload["rules"], "alerts": {"status": "ok", "count": 0}, "remote": True})
                return
            self._json(404, {"ok": False})

        def do_GET(self):
            if self.path.startswith("/deployments/autoscaling"):
                ref = self.path.split("ref=", 1)[1]
                dep = state["items"][ref]
                self._json(200, {"ok": True, "deployment": dep, "autoscaling": {"action": "scale-out", "desired_replicas": 3}, "remote": True})
                return
            if self.path.startswith("/deployments/alerts"):
                ref = self.path.split("ref=", 1)[1]
                dep = state["items"][ref]
                self._json(200, {"ok": True, "deployment": dep, "alerts": {"status": "ok", "count": 0}, "rules": state["rules"].get(ref, []), "remote": True})
                return
            self._json(404, {"ok": False})

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        synced = sync_deployment(res["manifest"], out, control_plane=base, manifest_path=res["manifest_path"])
        dep_id = synced["deployment"]["id"]
        metrics = record_deployment_metrics(dep_id, {"cpu": 85, "replicas": 2}, control_plane=base)
        assert metrics["autoscaling"]["desired_replicas"] == 3
        rules = set_alert_rules(dep_id, [{"name": "cpu-high", "metric": "cpu", "op": ">=", "threshold": 80}], control_plane=base)
        assert rules["ok"] is True
        signals = get_autoscaling_signals(dep_id, control_plane=base)
        assert signals["autoscaling"]["action"] == "scale-out"
        alerts = evaluate_alerts(dep_id, control_plane=base)
        assert alerts["alerts"]["status"] == "ok"
    finally:
        server.shutdown()
        thread.join(timeout=2)
