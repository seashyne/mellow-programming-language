from __future__ import annotations

"""mellowlang.net_core

Minimal, safe networking primitives used by Mellow built-ins.

Design goals:
  - Always-online friendly (HTTP + WebSocket)
  - Sandboxable (host/VM enforces allowlists, payload limits, rate limits)
  - Synchronous API at VM boundary (internally uses asyncio threads)

Notes:
  - TLS / certificate validation is handled by Python's stdlib/SSL.
  - Deterministic replay of networking is handled at a higher layer by recording
    incoming/outgoing messages (optional tooling).
"""

import asyncio
import base64
import importlib
import json
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _load_websockets() -> Any:
    try:
        return importlib.import_module("websockets")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "NET_WS_DEPENDENCY_MISSING: install WebSocket support with "
            "`pip install mellowlang[net]`"
        ) from exc


def http_post_json(url: str, payload: Dict[str, Any], *, timeout_s: float = 10.0, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(str(k), str(v))
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        raise RuntimeError("NET_HTTP_BAD_JSON: server response is not valid json")
    if not isinstance(obj, dict):
        raise RuntimeError("NET_HTTP_BAD_JSON: server response must be a json object")
    return obj


def http_get_json(url: str, *, timeout_s: float = 10.0, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(str(k), str(v))
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        raise RuntimeError("NET_HTTP_BAD_JSON: server response is not valid json")
    if not isinstance(obj, dict):
        raise RuntimeError("NET_HTTP_BAD_JSON: server response must be a json object")
    return obj


@dataclass
class WSState:
    url: str
    connected: bool = False
    last_error: Optional[str] = None


class WebSocketManager:
    """Threaded asyncio websocket manager.

    VM sees a synchronous, handle-based API.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_id = 1
        self._states: Dict[int, WSState] = {}
        self._queues: Dict[int, "asyncio.Queue[bytes]"] = {}
        self._send_queues: Dict[int, "asyncio.Queue[bytes]"] = {}

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="mellow-ws", daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def connect(self, url: str, *, headers: Optional[Dict[str, str]] = None) -> int:
        with self._lock:
            hid = self._next_id
            self._next_id += 1
            self._states[hid] = WSState(url=url, connected=False)
        q_in: "asyncio.Queue[bytes]" = asyncio.Queue()
        q_out: "asyncio.Queue[bytes]" = asyncio.Queue()
        self._queues[hid] = q_in
        self._send_queues[hid] = q_out

        fut = asyncio.run_coroutine_threadsafe(self._ws_task(hid, url, headers=headers), self._loop)
        # Ensure task is started
        fut.add_done_callback(lambda f: None)
        return hid

    async def _ws_task(self, hid: int, url: str, *, headers: Optional[Dict[str, str]] = None) -> None:
        try:
            websockets = _load_websockets()
            async with websockets.connect(url, extra_headers=headers) as ws:
                with self._lock:
                    st = self._states.get(hid)
                    if st:
                        st.connected = True
                        st.last_error = None

                async def reader() -> None:
                    try:
                        async for msg in ws:
                            if isinstance(msg, str):
                                msg_b = msg.encode("utf-8")
                            else:
                                msg_b = bytes(msg)
                            await self._queues[hid].put(msg_b)
                    except Exception as e:
                        with self._lock:
                            st = self._states.get(hid)
                            if st:
                                st.connected = False
                                st.last_error = f"{type(e).__name__}: {e}"

                async def writer() -> None:
                    try:
                        while True:
                            data = await self._send_queues[hid].get()
                            if data is None:  # type: ignore
                                return
                            await ws.send(data)
                    except Exception as e:
                        with self._lock:
                            st = self._states.get(hid)
                            if st:
                                st.connected = False
                                st.last_error = f"{type(e).__name__}: {e}"

                await asyncio.gather(reader(), writer())
        except Exception as e:
            with self._lock:
                st = self._states.get(hid)
                if st:
                    st.connected = False
                    st.last_error = f"{type(e).__name__}: {e}"

    def send(self, hid: int, data: bytes) -> bool:
        if hid not in self._send_queues:
            return False
        asyncio.run_coroutine_threadsafe(self._send_queues[hid].put(bytes(data)), self._loop)
        return True

    def recv(self, hid: int, *, timeout_s: float = 0.0) -> Optional[bytes]:
        if hid not in self._queues:
            return None
        # Poll synchronously
        deadline = time.time() + max(0.0, timeout_s)
        while True:
            try:
                return self._queues[hid].get_nowait()
            except asyncio.QueueEmpty:
                if timeout_s <= 0.0 or time.time() >= deadline:
                    return None
                time.sleep(0.01)

    def close(self, hid: int) -> bool:
        if hid not in self._send_queues:
            return False
        # Signal writer to stop
        asyncio.run_coroutine_threadsafe(self._send_queues[hid].put(None), self._loop)  # type: ignore
        with self._lock:
            st = self._states.get(hid)
            if st:
                st.connected = False
        return True

    def state(self, hid: int) -> Dict[str, Any]:
        with self._lock:
            st = self._states.get(hid)
            if not st:
                return {"ok": False, "error": "unknown connection"}
            return {"ok": True, "url": st.url, "connected": bool(st.connected), "error": st.last_error}


_WS_MANAGER: Optional[WebSocketManager] = None


def ws_manager() -> WebSocketManager:
    global _WS_MANAGER
    if _WS_MANAGER is None:
        _WS_MANAGER = WebSocketManager()
    return _WS_MANAGER


def b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64_decode(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))
