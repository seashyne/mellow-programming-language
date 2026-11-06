"""Mellow host syscall family: text list."""

from __future__ import annotations

from ..base import HostFunction, HostRegistry
from .support import is_list as _is_list


def register_text_list_functions(h: HostRegistry) -> None:
    """Register the text list syscalls on a fresh host registry."""
    def _str_split(args):
        s = str(args[0])
        sep = None if len(args) < 2 else str(args[1])
        return s.split(sep) if sep is not None else s.split()
    h.register(HostFunction('std.string.split', _str_split, cost=2, min_args=1, max_args=2))
    def _str_join(args):
        arr = args[0]
        if not isinstance(arr, list):
            raise RuntimeError('std.string.join: expected list')
        sep = '' if len(args) < 2 else str(args[1])
        return sep.join(str(x) for x in arr)
    h.register(HostFunction('std.string.join', _str_join, cost=2, min_args=1, max_args=2))

    # --- std.list extras ---
    def _list_insert(args):
        lst, idx, val = args[0], int(args[1]), args[2]
        _is_list(lst)
        if idx < 0: idx = 0
        if idx > len(lst): idx = len(lst)
        lst.insert(idx, val)
        return lst
    h.register(HostFunction('std.list.insert', _list_insert, cost=1, min_args=3, max_args=3))
    def _list_remove(args):
        lst, val = args[0], args[1]
        _is_list(lst)
        try:
            lst.remove(val)
        except ValueError:
            pass
        return lst
    h.register(HostFunction('std.list.remove', _list_remove, cost=1, min_args=2, max_args=2))
    def _list_has(args):
        lst, val = args[0], args[1]
        _is_list(lst)
        return val in lst
    h.register(HostFunction('std.list.has', _list_has, cost=1, min_args=2, max_args=2))
    def _list_sort(args):
        lst = args[0]
        _is_list(lst)
        try:
            lst.sort()
        except Exception:
            # fallback: sort by string value
            lst.sort(key=lambda x: str(x))
        return lst
    h.register(HostFunction('std.list.sort', _list_sort, cost=2, min_args=1, max_args=1))

    # ==========================================================
    # v1.4.7: String helpers
    # ==========================================================
    h.register(HostFunction('std.string.starts_with',
        lambda a: str(a[0]).startswith(str(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.string.ends_with',
        lambda a: str(a[0]).endswith(str(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.string.contains',
        lambda a: str(a[1]) in str(a[0]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.string.repeat',
        lambda a: str(a[0]) * max(0, int(a[1])), cost=1, min_args=2, max_args=2))

    def _str_pad_left(args):
        s = str(args[0]); width = int(args[1])
        ch = str(args[2]) if len(args) >= 3 else " "
        return s.rjust(width, ch[0] if ch else " ")
    h.register(HostFunction('std.string.pad_left', _str_pad_left, cost=1, min_args=2, max_args=3))

    def _str_pad_right(args):
        s = str(args[0]); width = int(args[1])
        ch = str(args[2]) if len(args) >= 3 else " "
        return s.ljust(width, ch[0] if ch else " ")
    h.register(HostFunction('std.string.pad_right', _str_pad_right, cost=1, min_args=2, max_args=3))

    def _str_format(args):
        """str_format(template, val1, val2, ...) — ใช้ {} เป็น placeholder"""
        tmpl = str(args[0])
        vals = args[1:]
        try:
            return tmpl.format(*vals)
        except Exception:
            return tmpl
    h.register(HostFunction('std.string.format', _str_format, cost=1, min_args=1, max_args=99))
