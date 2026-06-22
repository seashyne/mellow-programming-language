from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mellowlang.package_manager import author_profile_remote, init_package, package_info_remote, package_signature_remote, publish_remote, install_remote, login_with_token, set_registry, search_remote

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_public_registry_token_publish_and_install(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MELLOW_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    port = _free_port()
    data_dir = tmp_path / "registry-data"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
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
        init_package(pkg_dir, name="dialoguekit", author="Mellow Maker")
        manifest = pkg_dir / "mellow.pkg.json"
        import json
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["keywords"] = ["dialogue", "npc"]
        data["badges"] = ["official"]
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        toml = pkg_dir / "mellow.toml"
        toml_text = toml.read_text(encoding="utf-8")
        toml_text = toml_text.replace('keywords = ["mellow", "package"]', 'keywords = ["dialogue", "npc"]')
        toml.write_text(toml_text.replace("\n[dependencies]", '\nbadges = ["official"]\n[dependencies]'), encoding="utf-8")
        published = publish_remote(pkg_dir, registry=registry)
        assert published.get("ok") is True
        assert published.get("creator") == "Mellow Maker"

        found = search_remote("dialogue", registry=registry)
        assert found.get("count", 0) >= 1
        row = next(item for item in found.get("items", []) if item.get("name") == "dialoguekit")
        assert row.get("creator") == "Mellow Maker"
        assert "official" in row.get("badges", [])
        assert row.get("downloads") == 0

        profile = author_profile_remote("Mellow Maker", registry=registry)
        assert profile.get("ok") is True
        assert any(item.get("name") == "dialoguekit" for item in profile.get("items", []))

        info = package_info_remote("dialoguekit", registry=registry)
        assert info.get("ok") is True
        assert info.get("latest") == "0.1.0"
        assert info.get("versions") == ["0.1.0"]
        assert info.get("entry") == "src/main.mellow"
        assert info.get("creator") == "Mellow Maker"
        assert info.get("keywords") == ["dialogue", "npc"]

        signature = package_signature_remote("dialoguekit", registry=registry)
        assert signature.get("ok") is True
        assert signature.get("verified") is True
        assert signature.get("sha256")

        installed = install_remote("dialoguekit", registry=registry)
        assert installed.get("name") == "dialoguekit"
        assert installed.get("creator") == "Mellow Maker"
        assert Path(installed["installed_to"]).exists()

        found_after = search_remote("dialogue", registry=registry)
        row_after = next(item for item in found_after.get("items", []) if item.get("name") == "dialoguekit")
        assert row_after.get("downloads") == 1

        import urllib.request
        with urllib.request.urlopen(f"{registry}/packages?q=dialogue", timeout=2) as resp:
            html = resp.read().decode("utf-8")
        assert "Mellow Registry" in html
        assert "dialoguekit" in html
    finally:
        proc.terminate()
        proc.wait(timeout=5)
