"""Mellow host syscall family: list functional."""

from __future__ import annotations

from ..base import HostFunction, HostRegistry
from .support import is_list as _is_list


def register_list_functional_functions(h: HostRegistry) -> None:
    """Register the list functional syscalls on a fresh host registry."""
    # ==========================================================
    # v1.4.7: List functional helpers
    # ==========================================================

    def _list_map(args):
        """list_map(list, fn_name) -> list ใหม่ที่ผ่าน fn แต่ละ element"""
        lst = args[0]; _is_list(lst)
        fn_name = str(args[1])
        # fn_name ต้องเป็น registered syscall
        return [h.call(fn_name, [item]) for item in lst]
    h.register(HostFunction('std.list.map', _list_map, cost=3, min_args=2, max_args=2))

    def _list_filter(args):
        """list_filter(list, fn_name) -> list เฉพาะ element ที่ fn return truthy"""
        lst = args[0]; _is_list(lst)
        fn_name = str(args[1])
        return [item for item in lst if h.call(fn_name, [item])]
    h.register(HostFunction('std.list.filter', _list_filter, cost=3, min_args=2, max_args=2))

    def _list_find(args):
        """list_find(list, value) -> index หรือ -1"""
        lst = args[0]; _is_list(lst)
        val = args[1]
        try:
            return lst.index(val)
        except ValueError:
            return -1
    h.register(HostFunction('std.list.find', _list_find, cost=1, min_args=2, max_args=2))

    def _list_slice(args):
        """list_slice(list, start, end?) -> sub-list"""
        lst = args[0]; _is_list(lst)
        start = int(args[1])
        end = int(args[2]) if len(args) >= 3 else len(lst)
        return lst[start:end]
    h.register(HostFunction('std.list.slice', _list_slice, cost=1, min_args=2, max_args=3))

    def _list_reverse(args):
        lst = args[0]; _is_list(lst)
        return list(reversed(lst))
    h.register(HostFunction('std.list.reverse', _list_reverse, cost=1, min_args=1, max_args=1))

    def _list_reduce(args):
        """list_reduce(list, fn_name, initial) -> accumulated value"""
        lst = args[0]; _is_list(lst)
        fn_name = str(args[1])
        acc = args[2] if len(args) >= 3 else (lst[0] if lst else None)
        start = 0 if len(args) >= 3 else 1
        for item in lst[start:]:
            acc = h.call(fn_name, [acc, item])
        return acc
    h.register(HostFunction('std.list.reduce', _list_reduce, cost=3, min_args=2, max_args=3))

    def _list_count(args):
        """list_count(list, value) -> count ของ value ใน list"""
        lst = args[0]; _is_list(lst)
        val = args[1]
        return lst.count(val)
    h.register(HostFunction('std.list.count', _list_count, cost=1, min_args=2, max_args=2))
