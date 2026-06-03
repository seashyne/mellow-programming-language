from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + ENV.get("PYTHONPATH", "")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-m", "mellowlang.cli.main", *args], cwd=cwd or ROOT, env=env or ENV, capture_output=True, text=True, timeout=60)


def test_online_registry_publish_search_install():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        port = _free_port()
        env = ENV.copy()
        env["MELLOW_CONFIG_DIR"] = str(td / "cfg")
        server = subprocess.Popen([sys.executable, "-m", "mellowlang.registry.server", "--host", "127.0.0.1", "--port", str(port), "--data-dir", str(td / "registry")], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(1.2)
            assert _run("pkg", "registry", f"http://127.0.0.1:{port}", env=env).returncode == 0
            login = _run("pkg", "login", "--username", "admin", "--password", "admin", env=env)
            assert login.returncode == 0, login.stderr + login.stdout
            pkgdir = td / "physics2d"
            assert _run("pkg", "init", str(pkgdir), "--name", "physics2d", env=env).returncode == 0
            publish = _run("pkg", "publish", str(pkgdir), "--online", env=env)
            assert publish.returncode == 0, publish.stderr + publish.stdout
            search = _run("pkg", "search", "physics", env=env)
            assert search.returncode == 0
            assert "physics2d" in search.stdout
            install = _run("pkg", "install", "physics2d", "--online", env=env)
            assert install.returncode == 0, install.stderr + install.stdout
            man = json.loads((ROOT / "mellow_packages" / "installed" / "physics2d" / "current" / "manifest.json").read_text(encoding="utf-8"))
            assert man["name"] == "physics2d"
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()
            import shutil
            shutil.rmtree(ROOT / "mellow_packages", ignore_errors=True)
