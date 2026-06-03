from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mellowlang.package_manager import init_package, publish_remote, install_remote, login_with_token, set_registry, search_remote


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_public_registry_token_publish_and_install(tmp_path: Path):
    port = _free_port()
    data_dir = tmp_path / "registry-data"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["MELLOW_BOOTSTRAP_TOKEN"] = "unit-test-token"
    proc = subprocess.Popen(
        [sys.executable, "-m", "mellowlang.registry.server", "--host", "127.0.0.1", "--port", str(port), "--data-dir", str(data_dir)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                import urllib.request
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        registry = f"http://127.0.0.1:{port}"
        set_registry(registry)
        auth = login_with_token("unit-test-token", registry=registry)
        assert auth.get("ok") is True

        pkg_dir = tmp_path / "dialoguekit"
        init_package(pkg_dir, name="dialoguekit")
        published = publish_remote(pkg_dir, registry=registry)
        assert published.get("ok") is True

        found = search_remote("dialogue", registry=registry)
        assert found.get("count", 0) >= 1

        installed = install_remote("dialoguekit", registry=registry)
        assert installed.get("name") == "dialoguekit"
        assert Path(installed["installed_to"]).exists()
    finally:
        proc.terminate()
        proc.wait(timeout=5)
