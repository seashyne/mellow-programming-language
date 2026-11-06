"""The native C VM bridge: capability reporting, the storage guards and the

bytecode runners. The host adapter and the native vocabulary live in
`mellowlang/vm/cbridge_groups/`; the capability reporters and the runners stay
here because `_load_ext` is patched on this module, so their globals must be
this module."""

from __future__ import annotations

from typing import Any, Dict

from ..native_vm import native_vm_status
from .cbridge_groups.host import NativeHostAdapter
from .cbridge_groups.native import (CVMUnsupportedOpcode,
                                    NativeExecutionRequiredError,
                                    NativeRunResult, _load_ext)
from .cbridge_groups.storage import (_lock_native_storage_dir,
                                     _storage_path_unsafe,
                                     _validate_native_storage_bytecode)


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
        "source_span_parity": bool(ext is not None),
        "notes": "Native C execution covers the stable language core and source spans plus money, data, and ledger stdlib services; debugger, event, and replay hooks still route through Python.",
        "requires_python_fallback_for_debugger": True,
        "native_stdlib_parity": bool(ext is not None),
        "native_data_transforms": False,
        "native_ledger_bridge": bool(ext is not None),
        "native_parity_level": "core-complete+money+data+ledger",
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
        native_config = _lock_native_storage_dir(config)
        adapter = NativeHostAdapter(host, native_config)
        try:
            _validate_native_storage_bytecode(bytecode, config)
            run_kwargs = {
                'bytecode': bytecode,
                'config': native_config,
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
            if getattr(e, "pc", None) is not None:
                raise
            if require_native or not allow_fallback:
                raise NativeExecutionRequiredError(f'native-c-execution-failed: {e}') from e
        finally:
            adapter.close()

    if require_native and not native_available:
        raise NativeExecutionRequiredError('native-c-extension-unavailable')

    if not allow_fallback:
        raise NativeExecutionRequiredError('python-fallback-disabled')

    from .python_vm import MellowLangVM

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
