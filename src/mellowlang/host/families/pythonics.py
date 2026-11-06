"""Mellow host syscall family: pythonics."""

from __future__ import annotations

from ..base import HostFunction, HostRegistry


def register_pythonics_functions(h: HostRegistry) -> None:
    """Register the pythonics syscalls on a fresh host registry."""
    # ----- v1.4.9: General Programming Additions -----

    # enumerate: returns [[0,v0],[1,v1],...]
    def _enumerate(a):
        lst = a[0] if a else []
        if not isinstance(lst, (list, str)):
            return []
        return [[i, v] for i, v in enumerate(lst)]
    h.register(HostFunction('std.list.enumerate', _enumerate, cost=2, min_args=1, max_args=1))

    # zip: zip two or more lists into list of pairs
    def _zip(a):
        if len(a) < 2:
            return []
        return [[row[i] for row in a] for i in range(min(len(r) for r in a))]
    h.register(HostFunction('std.list.zip', _zip, cost=2, min_args=2, max_args=10))

    # map_fn: map(fn_ref, list) → [fn(x) for x in list]  — fn_ref is a ("__func__", name) tuple
    # Handled specially in VM's SYSCALL dispatch (needs func_table access)
    h.register(HostFunction('std.list.map_fn', lambda a: a, cost=1, min_args=2, max_args=2))  # stub, VM intercepts

    # filter_fn: filter(fn_ref, list)
    h.register(HostFunction('std.list.filter_fn', lambda a: a, cost=1, min_args=2, max_args=2))  # stub

    # sorted: sorted(list, reverse=False)
    def _sorted(a):
        lst = list(a[0]) if isinstance(a[0], list) else []
        rev = bool(a[1]) if len(a) > 1 else False
        try: return sorted(lst, reverse=rev)
        except: return lst
    h.register(HostFunction('std.list.sorted', _sorted, cost=2, min_args=1, max_args=2))

    # reversed: reversed(list)
    def _reversed(a):
        lst = list(a[0]) if isinstance(a[0], list) else []
        return lst[::-1]
    h.register(HostFunction('std.list.reversed', _reversed, cost=2, min_args=1, max_args=1))

    # any/all
    def _mellow_any(a):
        lst = a[0] if isinstance(a[0], list) else []
        return any(bool(x) for x in lst)
    def _mellow_all(a):
        lst = a[0] if isinstance(a[0], list) else []
        return all(bool(x) for x in lst)
    h.register(HostFunction('std.list.any', _mellow_any, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.list.all', _mellow_all, cost=1, min_args=1, max_args=1))

    # sum
    def _sum(a):
        lst = a[0] if isinstance(a[0], list) else []
        try: return sum(float(x) if isinstance(x, float) else int(x) for x in lst)
        except: return 0
    h.register(HostFunction('std.math.sum', _sum, cost=2, min_args=1, max_args=1))

    # type conversions
    def _to_int(a): 
        try: return int(float(a[0])) if a else 0
        except: return 0
    def _to_float(a):
        try: return float(a[0]) if a else 0.0
        except: return 0.0
    def _to_str(a):
        v = a[0] if a else None
        if v is None: return "none"
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, float) and v == int(v): return str(int(v))
        return str(v)
    def _to_bool(a):
        v = a[0] if a else None
        if isinstance(v, bool): return v
        if isinstance(v, (int, float)): return v != 0
        if isinstance(v, str): return v.lower() not in ('', '0', 'false', 'none')
        return v is not None
    def _to_list(a):
        v = a[0] if a else None
        if isinstance(v, list): return v
        if isinstance(v, str): return list(v)
        if isinstance(v, dict): return list(v.keys())
        return [v] if v is not None else []

    h.register(HostFunction('std.type.to_int', _to_int, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_float', _to_float, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_str', _to_str, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_bool', _to_bool, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.type.to_list', _to_list, cost=1, min_args=1, max_args=1))

    # chr/ord
    h.register(HostFunction('std.string.chr', lambda a: chr(int(a[0])) if a else '', cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.string.ord', lambda a: ord(str(a[0])[0]) if a and str(a[0]) else 0, cost=1, min_args=1, max_args=1))

    # list extend helpers for spread builds
    def _list_extend(a):
        base = list(a[0]) if isinstance(a[0], list) else []
        ext = a[1] if len(a) > 1 else []
        if isinstance(ext, (list, str)):
            return base + list(ext)
        return base
    def _list_append_to_top(a):
        base = list(a[0]) if isinstance(a[0], list) else []
        item = a[1] if len(a) > 1 else None
        return base + [item]
    h.register(HostFunction('std.list._extend', _list_extend, cost=2, min_args=2, max_args=2))
    h.register(HostFunction('std.list._append_to_top', _list_append_to_top, cost=1, min_args=2, max_args=2))
