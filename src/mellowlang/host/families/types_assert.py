"""Mellow host syscall family: types assert."""

from __future__ import annotations

import json as _json
from ..base import HostFunction, HostRegistry
from .support import is_dict as _is_dict


def register_types_assert_functions(h: HostRegistry) -> None:
    """Register the types assert syscalls on a fresh host registry."""
    # ==========================================================
    # v1.4.7: Type checking
    # ==========================================================
    h.register(HostFunction('std.type.is_number',
        lambda a: isinstance(a[0], (int, float)) and not isinstance(a[0], bool),
        cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_string',
        lambda a: isinstance(a[0], str), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_bool',
        lambda a: isinstance(a[0], bool), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_list',
        lambda a: isinstance(a[0], list), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_map',
        lambda a: isinstance(a[0], dict), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.is_none',
        lambda a: a[0] is None, cost=1, min_args=1, max_args=1))

    def _type_of(args):
        v = args[0]
        if isinstance(v, bool): return "bool"
        if isinstance(v, (int, float)): return "number"
        if isinstance(v, str): return "string"
        if isinstance(v, list): return "list"
        if isinstance(v, dict): return "map"
        if v is None: return "none"
        return "unknown"
    h.register(HostFunction('std.type.of', _type_of, cost=1, min_args=1, max_args=1))

    # ==========================================================
    # v1.4.7: assert
    # ==========================================================
    def _assert(args):
        cond = args[0]
        msg = str(args[1]) if len(args) >= 2 else "assertion failed"
        if not cond:
            raise RuntimeError(f"AssertionError: {msg}")
        return True
    h.register(HostFunction('std.assert.check', _assert, cost=1, min_args=1, max_args=2))

    def _assert_eq(args):
        a, b = args[0], args[1]
        msg = str(args[2]) if len(args) >= 3 else f"expected {b!r}, got {a!r}"
        if a != b:
            raise RuntimeError(f"AssertionError: {msg}")
        return True
    h.register(HostFunction('std.assert.eq', _assert_eq, cost=1, min_args=2, max_args=3))

    def _assert_ne(args):
        a, b = args[0], args[1]
        msg = str(args[2]) if len(args) >= 3 else f"expected {a!r} != {b!r}"
        if a == b:
            raise RuntimeError(f"AssertionError: {msg}")
        return True
    h.register(HostFunction('std.assert.ne', _assert_ne, cost=1, min_args=2, max_args=3))

    # ==========================================================
    # v1.4.7: Event System
    # ==========================================================
    # emit() — fire event โดย VM จัดการ dispatch ใน vm/python_vm.py
    # register ที่นี่แค่เป็น placeholder สำหรับ static analysis
    # การทำงานจริงถูก intercept ใน VM loop ก่อนถึง host
    h.register(HostFunction('std.event.emit', lambda a: None, cost=1, min_args=1, max_args=99))

    # --- std.map extras ---
    def _map_values(args):
        m=args[0]; _is_dict(m); return list(m.values())
    h.register(HostFunction('std.map.values', _map_values, cost=1, min_args=1, max_args=1))
    def _map_has(args):
        m,k=args[0],args[1]; _is_dict(m); return k in m
    h.register(HostFunction('std.map.has', _map_has, cost=1, min_args=2, max_args=2))

    h.register(HostFunction('std.json.encode', lambda a: _json.dumps(a[0], ensure_ascii=False), cost=2, min_args=1, max_args=1))
    h.register(HostFunction('std.json.decode', lambda a: _json.loads(str(a[0])), cost=2, min_args=1, max_args=1))
