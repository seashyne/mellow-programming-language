"""The per-run host bridge the native VM calls through: data streams, the
filesystem sandbox and the cancellation clock."""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict

from ...data_core import DataCoreError, DataStreamManager


class NativeHostAdapter:
    """Per-run host bridge for stateful stdlib services used by the C VM."""

    def __init__(self, host: Any, config: Dict[str, Any]) -> None:
        self._host = host
        self._config = config
        self._started = time.monotonic()
        self._data = DataStreamManager(
            resolve_read=lambda path: self._fs_resolve(path, op="read"),
            resolve_write=lambda path: self._fs_resolve(path, op="write"),
            check_cancelled=self._check_cancelled,
            max_batch_size=int(config.get("data_max_batch_size", 1_000)),
            max_open_streams=int(config.get("data_max_open_streams", 8)),
            max_record_bytes=int(config.get("data_max_record_bytes", 1_048_576)),
            max_query_rows=int(config.get("data_max_query_rows", 5_000)),
            allow_write=bool(config.get("allow_data_write", False)),
        )

    @staticmethod
    def _parse_allowlist(value: Any) -> list[str]:
        parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
        allowed: list[str] = []
        for part in parts:
            normalized = part.replace("\\", "/").strip()
            if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
                continue
            normalized = normalized.lstrip("./") or "."
            allowed.append(normalized)
        return allowed

    def _fs_resolve(self, path: Any, *, op: str) -> str:
        raw = ("" if path is None else str(path)).strip().strip('"').strip("'").replace("\\", "/").strip()
        raw = raw or "."
        project_mode = bool(self._config.get("project_mode", False))
        unsafe = bool(self._config.get("allow_unsafe_fs", False))

        if (raw == ".." or raw.startswith("../")) and (project_mode or not unsafe):
            raise RuntimeError('SANDBOX: fs: ".." traversal is blocked')
        if os.path.isabs(raw):
            if project_mode:
                raise RuntimeError("SANDBOX: fs: absolute paths are disabled in project mode")
            if not unsafe:
                raise RuntimeError("SANDBOX: fs: absolute paths are disabled by default (run with --unsafe-fs for dev)")
            return os.path.abspath(raw)

        if not project_mode:
            return os.path.abspath(os.path.join(os.getcwd(), raw))

        project_root = os.path.abspath(str(self._config.get("project_root") or os.getcwd()))
        full = os.path.abspath(os.path.join(project_root, raw))
        allow_key = "fs_read_allow" if op == "read" else "fs_write_allow"
        for allowed in self._parse_allowlist(self._config.get(allow_key)):
            base = project_root if allowed == "." else os.path.abspath(os.path.join(project_root, allowed))
            if full == base or full.startswith(base + os.sep):
                return full
        need = raw.split("/", 1)[0]
        suggestion = f"fs.{op}:./{need}" if need and need != "." else f"fs.{op}:."
        raise RuntimeError(
            f'SANDBOX: fs access denied ({op}): {raw}\n'
            f'Hint: add permission in mellow.json: "{suggestion}"'
        )

    def _check_cancelled(self) -> None:
        max_ms = self._config.get("max_ms")
        if max_ms is not None and (time.monotonic() - self._started) * 1000.0 > float(max_ms):
            raise RuntimeError("SANDBOX: Time limit exceeded")

    def has(self, name: str) -> bool:
        return name.startswith("std.data.") or bool(self._host.has(name))

    def get_cost(self, name: str) -> int:
        return 1 if name.startswith("std.data.") else int(self._host.get_cost(name))

    def call(self, name: str, args: list[Any]) -> Any:
        if not name.startswith("std.data."):
            return self._host.call(name, args)
        try:
            dispatch = {
                "std.data.open_jsonl": lambda: self._data.open_jsonl(args[0], args[1] if len(args) > 1 else 100),
                "std.data.open_csv": lambda: self._data.open_csv(args[0], args[1] if len(args) > 1 else 100),
                "std.data.next": lambda: self._data.next_batch(args[0]),
                "std.data.close": lambda: self._data.close(args[0]),
                "std.data.cancel": lambda: self._data.cancel(args[0]),
                "std.data.info": lambda: self._data.stream_info(args[0]),
                "std.data.project": lambda: self._data.project(args[0], args[1]),
                "std.data.where": lambda: self._data.where(args[0], args[1], args[2], args[3]),
                "std.data.sum": lambda: self._data.sum_field(args[0], args[1]),
                "std.data.sqlite_query": lambda: self._data.sqlite_query(
                    args[0], args[1], args[2] if len(args) > 2 else [], args[3] if len(args) > 3 else None
                ),
                "std.data.sqlite_execute": lambda: self._data.sqlite_execute(
                    args[0], args[1], args[2] if len(args) > 2 else []
                ),
                "std.data.sqlite_open": lambda: self._data.sqlite_open(
                    args[0] if args else ":memory:", args[1] if len(args) > 1 else False
                ),
                "std.data.sqlite_close": lambda: self._data.sqlite_close(args[0]),
            }
            handler = dispatch.get(name)
            if handler is None:
                raise RuntimeError(f"SANDBOX: syscall not allowed: {name}")
            return handler()
        except (DataCoreError, OSError, ValueError, sqlite3.Error) as exc:
            raise RuntimeError(f"RUNTIME: {exc}") from exc

    def close(self) -> None:
        self._data.close_all()
