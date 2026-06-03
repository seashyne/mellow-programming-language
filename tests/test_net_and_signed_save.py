import base64
import io
import json
import sys
import contextlib
import textwrap
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

# Allow running tests without installing the package
sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from mellowlang.compiler.compiler import Compiler
from mellowlang.vm.vm import MellowVM, RunConfig


@pytest.fixture()
def ws_echo_server():
    import websockets

    async def echo(websocket):
        async for message in websocket:
            await websocket.send(message)

    stop_evt = asyncio.Event()

    async def runner(host, port, ready_evt, out):
        async with websockets.serve(echo, host, port) as server:
            out.append(server.sockets[0].getsockname()[1])
            ready_evt.set()
            await stop_evt.wait()

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    port_box = []
    t = threading.Thread(
        target=lambda: (asyncio.set_event_loop(loop), loop.run_until_complete(runner("127.0.0.1", 0, ready, port_box))),
        daemon=True,
    )
    t.start()
    assert ready.wait(5)
    port = port_box[0]
    try:
        yield f"ws://127.0.0.1:{port}/"
    finally:
        loop.call_soon_threadsafe(stop_evt.set)
        import time as _time
        _time.sleep(0.05)
        loop.call_soon_threadsafe(loop.stop)


def run_source(src: str, *, cfg: RunConfig):
    src = textwrap.dedent(src).lstrip("\n")
    prog = Compiler().compile(src, filename="<test>")
    vm = MellowVM()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        vm.run(prog, config=cfg)
    return buf.getvalue()


class _SignerHandler(BaseHTTPRequestHandler):
    priv = None

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        hhex = obj.get("hash_sha256")
        if not isinstance(hhex, str) or len(hhex) != 64:
            self.send_response(400)
            self.end_headers()
            return
        sig = _SignerHandler.priv.sign(bytes.fromhex(hhex))
        out = json.dumps({"signature_b64": base64.b64encode(sig).decode("ascii")}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, fmt, *args):
        # silence
        return


@pytest.fixture()
def signer_server():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    _SignerHandler.priv = priv

    httpd = HTTPServer(("127.0.0.1", 0), _SignerHandler)
    host, port = httpd.server_address
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{host}:{port}/sign", base64.b64encode(pub).decode("ascii")
    finally:
        httpd.shutdown()


def test_signed_save_roundtrip(signer_server, tmp_path: Path):
    url, pub_b64 = signer_server
    # Use unique app_id to avoid cross-test collisions in OS save dir
    app_id = f"test.game.{tmp_path.name}"
    cfg = RunConfig(
        allow_save=True,
        allow_net=True,
        net_http_allow=url.rsplit("/", 1)[0] + "/",
        storage_dir=str(tmp_path),
    )
    out = run_source(
        f'''
        save_init("{app_id}")
        save_set("a", 1)
        save_set("b", "ok")
        save_commit_signed("slot1", "{url}", "{pub_b64}")

        save_clear()
        let ok = save_load_signed("slot1", "{pub_b64}")
        print(ok)
        print(save_get("b", "no"))
        ''',
        cfg=cfg,
    )
    assert "True" in out
    assert "ok" in out


def test_http_post_basic(signer_server, tmp_path: Path):
    url, _pub_b64 = signer_server
    base = url.rsplit("/", 1)[0] + "/"
    cfg = RunConfig(
        allow_net=True,
        net_http_allow=base,
        net_timeout_s=5.0,
        storage_dir=str(tmp_path),
    )
    out = run_source(
        f'''
        # build map via json.decode (literal map syntax is not guaranteed)
        import "json" as json
        let r = net_http_post("{url}", call(json["decode"], "{{\\"hash_sha256\\":\\"{'0'*64}\\"}}"))
        print(r)
        ''',
        cfg=cfg,
    )
    assert "signature_b64" in out


def test_websocket_echo(ws_echo_server, tmp_path: Path):
    url = ws_echo_server
    cfg = RunConfig(
        allow_net=True,
        net_ws_allow=url,
        net_max_bytes=1024,
        storage_dir=str(tmp_path),
    )
    out = run_source(
        f'''
        let cid = net_ws_connect("{url}")
        net_ws_send(cid, "ping")
        let msg = net_ws_recv(cid, 2.0)
        print(msg)
        net_ws_close(cid)
        ''',
        cfg=cfg,
    )
    assert "ping" in out
