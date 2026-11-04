"""The Python prelude every transpiled program runs on top of."""

from __future__ import annotations


_MELLOW_BUILTINS_SRC = """\
import math as _math, random as _rand, sys as _sys, time as _time

# ── stdlib shims ──────────────────────────────────────────────
def _fmt(v):
    if v is True: return "true"
    if v is False: return "false"
    if v is None: return "none"
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15: return str(int(v))
    if isinstance(v, list): return "[" + ", ".join(_fmt(x) for x in v) + "]"
    if isinstance(v, dict): return "{" + ", ".join(f"{_fmt(k)}: {_fmt(v2)}" for k, v2 in v.items()) + "}"
    return str(v)

def show(*args): print(*(_fmt(a) for a in args))
def _mellow_len(x): return len(x) if hasattr(x, '__len__') else 0
def list_push(lst, item): lst.append(item); return lst
def list_pop(lst): return lst.pop() if lst else None
def list_len(lst): return len(lst) if lst else 0
def list_has(lst, item): return item in lst if lst else False
def list_map(lst, fn): return [fn(x) for x in lst]
def list_filter(lst, fn): return [x for x in lst if fn(x)]
def list_reduce(lst, fn, init=None):
    acc = init if init is not None else (lst[0] if lst else None)
    st = 0 if init is not None else 1
    for x in lst[st:]: acc = fn(acc, x)
    return acc
def list_sort(lst, *a, **kw): import copy; r = copy.copy(lst); r.sort(); return r
def list_reverse(lst): return list(reversed(lst)) if lst else []
def list_slice(lst, s, e=None): return lst[s:e]
def list_find(lst, fn): return next((x for x in lst if fn(x)), None)
def list_count(lst, fn): return sum(1 for x in lst if fn(x))
def list_flat(lst): return [x for sub in lst for x in (sub if isinstance(sub, list) else [sub])]
def map_keys(d): return list(d.keys()) if d else []
def map_values(d): return list(d.values()) if d else []
def map_has(d, k): return k in d if d else False
def map_set(d, k, v): d[k] = v; return d
def map_get(d, k, dflt=None): return d.get(k, dflt) if d else dflt
def map_del(d, k): d.pop(k, None); return d
def str_split(s, sep=None): return s.split(sep) if sep else s.split()
def str_join(sep, lst): return sep.join(str(x) for x in lst)
def str_upper(s): return s.upper()
def str_lower(s): return s.lower()
def str_trim(s): return s.strip()
def str_starts(s, p): return s.startswith(p)
def str_ends(s, p): return s.endswith(p)
def str_contains(s, p): return p in s
def str_replace(s, old, new): return s.replace(old, new)
def str_find(s, p): return s.find(p)
def str_repeat(s, n): return s * int(n)
def str_pad_left(s, n, c=' '): return s.rjust(int(n), c)
def str_pad_right(s, n, c=' '): return s.ljust(int(n), c)
def str_format(fmt, *args): return fmt.format(*args)
def to_int(x): return int(float(x)) if x is not None else 0
def to_float(x): return float(x) if x is not None else 0.0
def to_str(x): return _fmt(x)
def to_bool(x): return bool(x)
def _pow(a, b): r = float(a)**float(b); return int(r) if r == int(r) else r
def abs_val(x): return abs(x)
def floor_val(x): return int(_math.floor(x))
def ceil_val(x): return int(_math.ceil(x))
def round_val(x, d=0): return round(float(x), int(d))
def sqrt_val(x): return _math.sqrt(x)
def log_val(x, b=None): return _math.log(x) if b is None else _math.log(x, b)
def sin_val(x): return _math.sin(x)
def cos_val(x): return _math.cos(x)
def tan_val(x): return _math.tan(x)
def min_val(*a): return min(*a) if len(a) > 1 else min(a[0])
def max_val(*a): return max(*a) if len(a) > 1 else max(a[0])
def clamp_val(v, lo, hi): return max(lo, min(hi, v))
def sign(x): return (1 if x > 0 else -1) if x != 0 else 0
def fmod(a, b): return _math.fmod(a, b)
def is_number(x): return isinstance(x, (int, float)) and not isinstance(x, bool)
def is_string(x): return isinstance(x, str)
def is_bool(x): return isinstance(x, bool)
def is_list(x): return isinstance(x, list)
def is_map(x): return isinstance(x, dict)
def is_none(x): return x is None
def type_of(x):
    if isinstance(x, bool): return "bool"
    if isinstance(x, int) or isinstance(x, float): return "number"
    if isinstance(x, str): return "string"
    if isinstance(x, list): return "list"
    if isinstance(x, dict): return "map"
    return "none"
def enumerate_mellow(lst): return list(enumerate(lst))
def zip_mellow(*lsts): return [list(t) for t in zip(*lsts)]
def range_mellow(s, e=None, st=1):
    if e is None: return list(range(int(s)))
    return list(range(int(s), int(e), int(st)))
def assert_mellow(cond, msg="assertion failed"):
    if not cond: raise RuntimeError(msg)
def assert_eq(a, b): assert_mellow(a == b, f"assert_eq: {_fmt(a)} != {_fmt(b)}")
def assert_ne(a, b): assert_mellow(a != b, f"assert_ne: {_fmt(a)} == {_fmt(b)}")
def random_int(lo, hi): return _rand.randint(int(lo), int(hi))
def random_float(): return _rand.random()
def random_choice(lst): return _rand.choice(lst) if lst else None
def shuffle_list(lst): import copy; r = copy.copy(lst); _rand.shuffle(r); return r
PI = _math.pi
TAU = _math.tau
E = _math.e
"""
