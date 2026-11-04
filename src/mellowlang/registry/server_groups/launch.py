"""Bind a store to a threading HTTP server and serve it, or parse the CLI
arguments that do."""

from __future__ import annotations

import argparse
import os
from http.server import ThreadingHTTPServer

from .handler import Handler
from .store import RegistryStore


def run_registry_server(host: str = "127.0.0.1", port: int = 8089, data_dir: str | None = None):
    store = RegistryStore(data_dir or os.environ.get("MELLOW_REGISTRY_DATA", "mellow_registry_data"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.store = store  # type: ignore[attr-defined]
    print(f"Mellow Registry running on http://{host}:{port}")
    print(f"Data dir: {store.data_dir}")
    print("Default login: admin / admin")
    print("Bootstrap publish token:", os.environ.get("MELLOW_BOOTSTRAP_TOKEN", "dev-publish-token"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down registry...")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mellow package registry server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8089)
    ap.add_argument("--data-dir", default=os.environ.get("MELLOW_REGISTRY_DATA", "mellow_registry_data"))
    ns = ap.parse_args(argv)
    run_registry_server(ns.host, ns.port, ns.data_dir)
    return 0
