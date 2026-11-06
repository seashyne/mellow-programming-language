"""Standalone C parity for the remote registry read path.

The native package client talks HTTP/1.1 to the same registry server the
Python CLI uses. These cases serve a real registry on localhost and assert the
C CLI reports the package rows the server published, with no Python involved
in the client itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mellowlang.registry.server_groups.handler import Handler
from mellowlang.registry.server_groups.store import RegistryStore


def _run(
    binary: Path, cwd: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), *args], capture_output=True, text=True, cwd=cwd, env=env, check=False
    )


def _env(tmp_path: Path, registry: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("MELLOW_REGISTRY_URL", "MELLOW_PUBLISH_TOKEN", "MELLOW_REGISTRY_TOKEN"):
        env.pop(key, None)
    env["MELLOW_CONFIG_DIR"] = str(tmp_path / "config")
    env["MELLOW_HTTP_TIMEOUT"] = "5"
    if registry:
        env["MELLOW_REGISTRY_URL"] = registry
    return env


@pytest.fixture()
def registry_url(tmp_path: Path) -> str:
    store = RegistryStore(tmp_path / "registry-data")
    token = next(iter(store.load_tokens()))
    manifest = {
        "name": "remote-demo",
        "version": "1.2.3",
        "entry": "src/main.mellow",
        "description": "Remote demo package",
        "authors": ["Remote Author"],
        "license": "MIT",
    }
    published = store.publish(token, manifest, b"PK\x03\x04remote-demo", None, "remote-demo-1.2.3.mpkg")
    assert published["ok"], published
    manifest["version"] = "1.3.0"
    published = store.publish(token, manifest, b"PK\x03\x04remote-demo-next", None, "remote-demo-1.3.0.mpkg")
    assert published["ok"], published

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.store = store  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_remote_search_reads_registry_rows(native_binary: Path, tmp_path: Path, registry_url: str) -> None:
    work = tmp_path / "work"
    work.mkdir()
    result = _run(native_binary, work, _env(tmp_path), "pkg", "search", "remote", "--registry", registry_url)
    assert result.returncode == 0, result.stderr
    assert "Found 1 package(s) for 'remote'" in result.stdout
    assert f"Registry: {registry_url}" in result.stdout
    assert "- remote-demo  latest=1.3.0  creator=Remote Author" in result.stdout
    assert "versions=1.2.3,1.3.0" in result.stdout
    assert "Remote demo package" in result.stdout


def test_remote_info_merges_latest_and_requested_version(
    native_binary: Path, tmp_path: Path, registry_url: str
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    env = _env(tmp_path, registry=registry_url)
    latest = _run(native_binary, work, env, "pkg", "info", "remote-demo")
    assert latest.returncode == 0, latest.stderr
    assert "name       : remote-demo" in latest.stdout
    assert "latest     : 1.3.0" in latest.stdout
    assert "versions   : 1.2.3, 1.3.0" in latest.stdout
    assert "creator    : Remote Author" in latest.stdout
    assert f"registry   : {registry_url}" in latest.stdout

    pinned = _run(native_binary, work, env, "pkg", "info", "remote-demo@1.2.3")
    assert pinned.returncode == 0, pinned.stderr
    assert "latest     : 1.2.3" in pinned.stdout


def test_local_registry_wins_before_the_remote_lookup(native_binary: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    (work / "localpkg" / "src").mkdir(parents=True)
    (work / "localpkg" / "mellow.toml").write_text(
        'name = "localpkg"\nversion = "0.1.0"\nauthors = ["Local Author"]\n', encoding="utf-8"
    )
    (work / "localpkg" / "src" / "main.mellow").write_text('print("local")\n', encoding="utf-8")
    env = _env(tmp_path)
    published = _run(native_binary, work, env, "pkg", "publish", "localpkg")
    assert published.returncode == 0, published.stderr

    unreachable = "http://127.0.0.1:1"
    info = _run(native_binary, work, env, "pkg", "info", "localpkg", "--registry", unreachable)
    assert info.returncode == 0, info.stderr
    assert "name       : localpkg" in info.stdout
    assert "creator    : Local Author" in info.stdout


def test_unreachable_registry_reports_an_error(native_binary: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    env = _env(tmp_path, registry="http://127.0.0.1:1")
    env["MELLOW_HTTP_TIMEOUT"] = "1"
    result = _run(native_binary, work, env, "pkg", "search", "anything")
    assert result.returncode != 0
    assert result.stderr.strip()


class _RedirectingHandler(BaseHTTPRequestHandler):
    """Redirect search to a chunked JSON body behind a decoy header."""

    protocol_version = "HTTP/1.1"
    body: bytes = b"{}"

    def log_message(self, *args: object) -> None:
        return

    def _send(self, status: int, extra: dict[str, str], body: bytes, chunked: bool) -> None:
        self.send_response(status)
        for key, value in extra.items():
            self.send_header(key, value)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if chunked:
            for start in range(0, len(body), 7):
                piece = body[start : start + 7]
                self.wfile.write(b"%x\r\n%s\r\n" % (len(piece), piece))
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.wfile.write(body)
        self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/v1/packages/search"):
            self._send(
                302,
                {"Content-Location": "/decoy", "Location": f"http://127.0.0.1:{self.server.server_address[1]}/real"},
                b"redirecting",
                chunked=False,
            )
            return
        if self.path == "/real":
            self._send(200, {"Content-Type": "application/json"}, self.body, chunked=True)
            return
        self._send(404, {"Content-Type": "text/plain"}, b"not found", chunked=False)


@pytest.fixture()
def redirecting_registry_url(tmp_path: Path) -> str:
    item = {
        "name": "redirect-demo",
        "latest": "9.9.9",
        "creator": "Redirect Author",
        "description": "Reached through a redirect",
        "versions": ["9.9.8", "9.9.9"],
    }
    _RedirectingHandler.body = json.dumps({"ok": True, "items": [item]}).encode("utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectingHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_redirect_and_chunked_response_are_parsed(
    native_binary: Path, tmp_path: Path, redirecting_registry_url: str
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    result = _run(native_binary, work, _env(tmp_path), "pkg", "search", "redirect",
                  "--registry", redirecting_registry_url)
    assert result.returncode == 0, result.stderr
    assert "Found 1 package(s) for 'redirect'" in result.stdout
    assert "- redirect-demo  latest=9.9.9  creator=Redirect Author" in result.stdout
    assert "versions=9.9.8,9.9.9" in result.stdout
    assert "Reached through a redirect" in result.stdout
