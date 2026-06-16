# mellowlang/vm/cbridge.py
# C VM bridge with explicit fallback and native stdlib host delegation.
from __future__ import annotations

from dataclasses import dataclass
import os
import sqlite3
import time
from typing import Any, Dict, Optional

from ..data_core import DataCoreError, DataStreamManager
from ..constants import Op
from ..native_vm import native_vm_status

class CVMUnsupportedOpcode(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeRunResult:
    result: Any
    engine: str
    used_fallback: bool
    detail: str
    native_available: bool


class NativeExecutionRequiredError(RuntimeError):
    pass


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


def _storage_path_unsafe(value: Any) -> bool:
    raw = ("" if value is None else str(value)).strip().strip('"').strip("'").replace("\\", "/")
    if not raw or raw == ".":
        return False
    if os.path.isabs(raw):
        return True
    parts = [part for part in raw.split("/") if part]
    return any(part == ".." for part in parts)


def _validate_native_storage_bytecode(bytecode: list[tuple], config: Dict[str, Any]) -> None:
    if not bool(config.get("allow_storage", True)):
        return
    stack: list[Any] = []
    for instr in bytecode:
        if not instr:
            continue
        op = instr[0]
        if op == Op.PUSH:
            stack.append(instr[1] if len(instr) > 1 else None)
        elif op == Op.BUILD_MAP:
            count = int(instr[1] if len(instr) > 1 else 0)
            for _ in range(max(0, count) * 2):
                if stack:
                    stack.pop()
            stack.append({"<map>": True})
        elif op == Op.SAVE_VAL:
            stack.pop() if stack else None
            filename = stack.pop() if stack else None
            if _storage_path_unsafe(filename):
                raise RuntimeError("SANDBOX: invalid storage path (path traversal blocked)")
        elif op in {Op.SAVE, Op.LOAD_F}:
            filename = stack.pop() if stack else None
            if _storage_path_unsafe(filename):
                raise RuntimeError("SANDBOX: invalid storage path (path traversal blocked)")
        else:
            stack.clear()


def _load_ext():
    """Try to load the native C extension. Returns None if unavailable."""
    try:
        from .. import _mellowvm  # type: ignore
        return _mellowvm
    except Exception:
        return None


def run_bytecode(
    *,
    bytecode: list[tuple],
    host: Any,
    config: Dict[str, Any],
    func_table: Any = None,
    event_table: Any = None,
    allow_fallback: bool = True,
    require_native: bool = False,
) -> Any:
    return run_bytecode_ex(
        bytecode=bytecode,
        host=host,
        config=config,
        func_table=func_table,
        event_table=event_table,
        allow_fallback=allow_fallback,
        require_native=require_native,
    ).result


def run_bytecode_ex(
    *,
    bytecode: list[tuple],
    host: Any,
    config: Dict[str, Any],
    func_table: Any = None,
    event_table: Any = None,
    allow_fallback: bool = True,
    require_native: bool = False,
) -> NativeRunResult:
    """Run bytecode through the native C VM when possible.

    In v2.4.0 this helper makes fallback explicit instead of silently dropping
    into the Python VM. Callers can require native execution and fail fast when
    the loaded extension or runtime path cannot satisfy the request.
    """
    ext = _load_ext()
    native_available = ext is not None
    if ext is not None:
        adapter = NativeHostAdapter(host, config)
        try:
            _validate_native_storage_bytecode(bytecode, config)
            run_kwargs = {
                'bytecode': bytecode,
                'config': config,
                'func_table': func_table,
                'event_table': event_table,
                'host': adapter,
            }
            result = ext.run(**run_kwargs)
            return NativeRunResult(
                result=result,
                engine='c',
                used_fallback=False,
                detail='native-c',
                native_available=True,
            )
        except RuntimeError as e:
            msg = str(e)
            if msg.startswith('CVM_UNSUPPORTED_OPCODE:'):
                if require_native or not allow_fallback:
                    raise NativeExecutionRequiredError(msg) from e
            else:
                raise
        except Exception as e:
            if require_native or not allow_fallback:
                raise NativeExecutionRequiredError(f'native-c-execution-failed: {e}') from e
        finally:
            adapter.close()

    if require_native and not native_available:
        raise NativeExecutionRequiredError('native-c-extension-unavailable')

    if not allow_fallback:
        raise NativeExecutionRequiredError('python-fallback-disabled')

    from .legacy import MellowLangVM

    vm = MellowLangVM(
        bytecode,
        func_table=func_table,
        event_table=event_table,
        config=config,
        host=host,
    )
    return NativeRunResult(
        result=vm.run(),
        engine='py',
        used_fallback=True,
        detail='python-fallback',
        native_available=native_available,
    )


def c_vm_available() -> bool:
    """Returns True if the native C extension is compiled and loadable."""
    return _load_ext() is not None


def c_vm_capabilities() -> Dict[str, Any]:
    """Return native C VM capability metadata when available.

    This is intentionally conservative. Newer source builds may expose a
    `capabilities()` function directly from the extension; otherwise we return a
    compatibility matrix that callers can rely on without crashing.
    """
    ext = _load_ext()
    status = native_vm_status()
    base: Dict[str, Any] = {
        "available": bool(ext is not None),
        "native_vm": status,
        "native_execution": bool(ext is not None),
        "conditional_breakpoints": False,
        "watch_expressions": False,
        "typed_frame_snapshots": False,
        "source_span_parity": False,
        "notes": "Native C execution covers the stable language core plus money, data, and ledger stdlib services; debugger, event, and replay hooks still route through Python.",
        "requires_python_fallback_for_debugger": True,
        "native_stdlib_parity": bool(ext is not None),
        "native_data_transforms": False,
        "native_ledger_bridge": bool(ext is not None),
        "native_parity_level": "stable-core+money+data+ledger",
    }
    if ext is None:
        return base
    fn = getattr(ext, 'capabilities', None)
    if callable(fn):
        try:
            payload = fn()
            if isinstance(payload, dict):
                merged = dict(base)
                merged.update(payload)
                return merged
        except Exception:
            pass
    return base


def c_vm_debug_supported() -> bool:
    caps = c_vm_capabilities()
    return bool(caps.get('conditional_breakpoints')) and bool(caps.get('watch_expressions')) and bool(caps.get('typed_frame_snapshots'))
