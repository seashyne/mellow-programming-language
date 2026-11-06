"""Mellow host syscall family: basic."""

from __future__ import annotations

from ..base import HostFunction, HostRegistry
from .support import is_dict as _is_dict, is_list as _is_list


def register_basic_functions(h: HostRegistry) -> None:
    """Register the basic syscalls on a fresh host registry."""
    # Example: clamp(number, lo, hi)

    # ----- stdlib (allowlist) -----
    import json as _json
    import math as _math
    from decimal import Decimal as _Decimal, InvalidOperation as _InvalidDecimal, ROUND_HALF_UP as _ROUND_HALF_UP

    h.register(HostFunction(
        name='std.list.push',
        handler=lambda a: (a[0].append(a[1]) or a[0]) if (_is_list(a[0]) is None) else a[0],
        cost=1,
        min_args=2,
        max_args=2
    ))
    h.register(HostFunction(
        name='std.list.pop',
        handler=lambda a: (a[0].pop() if (_is_list(a[0]) is None) and a[0] else None),
        cost=1,
        min_args=1,
        max_args=1
    ))
    h.register(HostFunction(
        name='std.list.len',
        handler=lambda a: len(a[0]) if (_is_list(a[0]) is None) else 0,
        cost=1,
        min_args=1,
        max_args=1
    ))

    def _map_get(args):
        m, k = args[0], args[1]
        _is_dict(m)
        if len(args) == 3:
            return m.get(k, args[2])
        return m.get(k)
    h.register(HostFunction('std.map.get', _map_get, cost=1, min_args=2, max_args=3))

    def _map_set(args):
        m, k, v = args[0], args[1], args[2]
        _is_dict(m)
        m[k] = v
        return m
    h.register(HostFunction('std.map.set', _map_set, cost=1, min_args=3, max_args=3))

    def _map_keys(args):
        m=args[0]
        _is_dict(m)
        return list(m.keys())
    h.register(HostFunction('std.map.keys', _map_keys, cost=1, min_args=1, max_args=1))

    h.register(HostFunction('std.string.len', lambda a: len(str(a[0])) if a else 0, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.len', lambda a: len(a[0]) if isinstance(a[0], (list,dict)) else len(str(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.lower', lambda a: str(a[0]).lower(), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.upper', lambda a: str(a[0]).upper(), cost=1, min_args=1, max_args=1))

    # v1.4.5: std.string.tostr — convert any value to string (used by f-string compiler)
    def _tostr(a):
        if not a: return ""
        v = a[0]
        if v is None: return "none"
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, float) and v == int(v): return str(int(v))
        return str(v)
    h.register(HostFunction('std.string.tostr', _tostr, cost=1, min_args=1, max_args=1))

    # --- std.string extras ---
    h.register(HostFunction('std.string.trim', lambda a: str(a[0]).strip(), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.replace', lambda a: str(a[0]).replace(str(a[1]), str(a[2])), cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.string.find', lambda a: str(a[0]).find(str(a[1])), cost=1, min_args=2, max_args=2))
