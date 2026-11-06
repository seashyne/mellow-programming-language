"""Mellow host syscall family: modules."""

from __future__ import annotations

from typing import Any, Dict, List
from ..base import MODULE_ALLOWLIST, HostFunction, HostRegistry


def register_modules_functions(h: HostRegistry) -> None:
    """Register the modules syscalls on a fresh host registry."""
    # ---------------- Module get/import helper ----------------
    # get("math") -> {"abs": "std.math.abs", ...}
    # Allows dynamic call(module["abs"], x) while still enforcing an allowlist.
    _module_cache: Dict[str, Dict[str, str]] = {}
    _MODULE_ALLOWLIST = MODULE_ALLOWLIST

    def _sys_get(args: List[Any]):
        name = str(args[0]) if args else ""
        name = name.strip().lower()
        if name not in _MODULE_ALLOWLIST:
            raise RuntimeError(f"sys.get: module not allowed: {name}")
        if name in _module_cache:
            return _module_cache[name]
        mod = dict(_MODULE_ALLOWLIST[name])
        _module_cache[name] = mod
        return mod

    h.register(HostFunction('sys.get', _sys_get, cost=1, min_args=1, max_args=1))
