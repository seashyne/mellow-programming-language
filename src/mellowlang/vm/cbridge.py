# mellowlang/vm/cbridge.py  — v1.4.8
# C VM bridge with full Python fallback for all opcodes.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

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

    In v2.0.3 this helper makes fallback explicit instead of silently dropping
    into the Python VM. Callers can require native execution and fail fast when
    the loaded extension or runtime path cannot satisfy the request.
    """
    ext = _load_ext()
    native_available = ext is not None
    if ext is not None:
        try:
            result = ext.run(
                bytecode=bytecode,
                host=host,
                config=config,
                func_table=func_table,
                event_table=event_table,
            )
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
                if require_native or not allow_fallback:
                    raise
        except Exception as e:
            if require_native or not allow_fallback:
                raise NativeExecutionRequiredError(f'native-c-execution-failed: {e}') from e

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
        "notes": "Prebuilt extension exposes native execution only until rebuilt with newer debug hooks.",
        "requires_python_fallback_for_debugger": True,
        "native_parity_level": "execution-first",
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
