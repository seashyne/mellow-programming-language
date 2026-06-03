# MellowLang v1.4.9 — Compile-to-Python Fast Path
# Transpiles MellowLang AST → Python source, then exec() for ~10-50x speedup
# vs bytecode VM for compute-intensive scripts.
from __future__ import annotations
import io
import sys
import math
import random
from typing import Any, Optional
from .ast import *
from .parser import parse_program, ParseError


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


class PyTranspiler:
    """
    v1.4.9: MellowLang → Python source transpiler.

    Usage::
        tp = PyTranspiler()
        py_src = tp.transpile(source_lines)
        exec(compile(py_src, '<mellow>', 'exec'), {})
    """

    def __init__(self):
        self._indent = 0
        self._out = io.StringIO()
        self._lambda_counter = 0
        self._tmp_counter = 0

    # ── Public API ────────────────────────────────────────────────────

    def transpile(self, lines: list[str], *, filename: str | None = None) -> str:
        prog = parse_program(lines, filename=filename)
        self._out = io.StringIO()
        self._indent = 0
        # Write builtins preamble
        self._out.write(_MELLOW_BUILTINS_SRC)
        self._out.write("\n# ── Transpiled MellowLang ────────────────────────────────────────\n")
        for stmt in prog.body:
            self._stmt(stmt)
        return self._out.getvalue()

    # ── Helpers ───────────────────────────────────────────────────────

    def _w(self, line: str = ""):
        self._out.write("    " * self._indent + line + "\n")

    def _w_raw(self, text: str):
        self._out.write(text)

    def _new_tmp(self) -> str:
        self._tmp_counter += 1
        return f"__tmp{self._tmp_counter}"

    # ── Statement compilation ─────────────────────────────────────────

    def _stmt(self, s: Stmt):
        if isinstance(s, KeepStmt):
            self._w(f"{_py_name(s.name)} = {self._expr(s.expr)}")

        elif isinstance(s, KeepMultiStmt):
            lhs = ", ".join(_py_name(n) for n in s.names)
            rhs = ", ".join(self._expr(e) for e in s.exprs)
            self._w(f"{lhs} = {rhs}")

        elif isinstance(s, AssignStmt):
            lhs = ", ".join(_py_name(n) for n in s.names)
            rhs = ", ".join(self._expr(e) for e in s.exprs)
            self._w(f"{lhs} = {rhs}")

        elif isinstance(s, ExprStmt):
            self._w(self._expr(s.expr))

        elif isinstance(s, ShowStmt):
            args = ", ".join(self._expr(e) for e in s.exprs)
            self._w(f"show({args})")

        elif isinstance(s, ReturnStmt):
            if s.expr is None:
                self._w("return None")
            else:
                self._w(f"return {self._expr(s.expr)}")

        elif isinstance(s, BreakStmt):
            self._w("break")

        elif isinstance(s, ContinueStmt):
            self._w("continue")

        elif isinstance(s, StopStmt):
            self._w("import sys as _sys_stop; _sys_stop.exit(0)")

        elif isinstance(s, SkillDef):
            self._skill_def(s)

        elif isinstance(s, IfGroup):
            for i, (cond, body) in enumerate(s.branches):
                kw = "if" if i == 0 else "elif"
                self._w(f"{kw} {self._expr(cond)}:")
                self._indent += 1
                for st in body: self._stmt(st)
                if not body: self._w("pass")
                self._indent -= 1
            if s.else_block is not None:
                self._w("else:")
                self._indent += 1
                for st in s.else_block: self._stmt(st)
                if not s.else_block: self._w("pass")
                self._indent -= 1

        elif isinstance(s, LoopWhile):
            self._w(f"while {self._expr(s.cond)}:")
            self._indent += 1
            for st in s.body: self._stmt(st)
            if not s.body: self._w("pass")
            self._indent -= 1

        elif isinstance(s, LoopCount):
            tmp = self._new_tmp()
            lim = self._new_tmp()
            self._w(f"{lim} = {self._expr(s.limit)}")
            self._w(f"for {tmp} in range(int({lim})):")
            self._indent += 1
            self._w(f"count = {tmp}")
            for st in s.body: self._stmt(st)
            if not s.body: self._w("pass")
            self._indent -= 1

        elif isinstance(s, LoopForEach):
            self._w(f"for {_py_name(s.var_name)} in ({self._expr(s.iterable)} or []):")
            self._indent += 1
            for st in s.body: self._stmt(st)
            if not s.body: self._w("pass")
            self._indent -= 1

        elif isinstance(s, LoopForMap):
            it = self._expr(s.iterable)
            self._w(f"for {_py_name(s.key_name)}, {_py_name(s.value_name)} in (({it}) or {{}}).items():")
            self._indent += 1
            for st in s.body: self._stmt(st)
            if not s.body: self._w("pass")
            self._indent -= 1

        elif isinstance(s, LoopForRange):
            v = _py_name(s.var_name)
            start = self._expr(s.start)
            end = self._expr(s.end)
            step = self._expr(s.step) if s.step else "1"
            self._w(f"for {v} in range(int({start}), int({end}) + 1, int({step})):")
            self._indent += 1
            for st in s.body: self._stmt(st)
            if not s.body: self._w("pass")
            self._indent -= 1

        elif isinstance(s, RepeatUntil):
            self._w("while True:")
            self._indent += 1
            for st in s.body: self._stmt(st)
            self._w(f"if {self._expr(s.cond)}: break")
            self._indent -= 1

        elif isinstance(s, TryStmt):
            self._w("try:")
            self._indent += 1
            for st in s.try_body: self._stmt(st)
            if not s.try_body: self._w("pass")
            self._indent -= 1
            if s.catch_body is not None:
                err_name = _py_name(s.catch_name) if s.catch_name else "__err"
                self._w(f"except Exception as {err_name}:")
                self._indent += 1
                # expose error as string
                self._w(f"{err_name} = str({err_name})")
                for st in s.catch_body: self._stmt(st)
                if not s.catch_body: self._w("pass")
                self._indent -= 1
            if s.finally_body is not None:
                self._w("finally:")
                self._indent += 1
                for st in s.finally_body: self._stmt(st)
                if not s.finally_body: self._w("pass")
                self._indent -= 1

        elif isinstance(s, DoBlock):
            for st in s.body: self._stmt(st)

        elif isinstance(s, PutStmt):
            self._w(f"{_py_name(s.list_name)}.append({self._expr(s.item_expr)})")

        elif isinstance(s, SaveStmt):
            pass  # storage: no-op in fast path

        elif isinstance(s, LoadStmt):
            self._w(f"{_py_name(s.var_name)} = None")

        elif isinstance(s, PrecisionStmt):
            pass  # precision: no-op in fast path

        elif isinstance(s, WaitStmt):
            self._w(f"_time.sleep({self._expr(s.expr)} / 1000.0)")

        elif isinstance(s, ImportStmt):
            self._import_stmt(s)

        elif isinstance(s, OnDef):
            # Event handlers compiled as regular functions
            self._w(f"def {_py_name(s.event)}({', '.join(_py_name(p) for p in s.params)}):")
            self._indent += 1
            for st in s.body: self._stmt(st)
            if not s.body: self._w("pass")
            self._indent -= 1

        elif isinstance(s, GetModuleStmt):
            # get module.func(args) → _mellow_module_call(...)
            args_src = ", ".join(self._expr(a) for a in s.args)
            call = f"_mod_{s.module}_{s.function}({args_src})"
            if s.var_name:
                self._w(f"{_py_name(s.var_name)} = {call}")
            else:
                self._w(call)

        else:
            # Unknown stmt: emit a comment
            self._w(f"# (unsupported stmt: {type(s).__name__})")

    def _skill_def(self, s: SkillDef):
        # Build param list with defaults
        defaults = getattr(s, 'defaults', {}) or {}
        params_str = []
        for p in s.params:
            if p.startswith("*"):
                params_str.append(f"*{_py_name(p[1:])}")
            elif p in defaults:
                dv = self._expr(defaults[p])
                params_str.append(f"{_py_name(p)}={dv}")
            else:
                params_str.append(_py_name(p))
        self._w(f"def {_py_name(s.name)}({', '.join(params_str)}):")
        self._indent += 1
        for st in s.body: self._stmt(st)
        if not s.body: self._w("pass")
        self._indent -= 1

    def _import_stmt(self, s: ImportStmt):
        """Transpile import: parse module, collect skill defs as Python functions."""
        import os
        path = s.path
        alias = s.alias
        self._w(f"# import {path!r} as {alias}")
        # We'll load the file and transpile it inline in an exec block
        self._w(f"__import_path_{alias} = {path!r}")
        self._w(f"if str(__import_path_{alias}).startswith('pkg:'): from mellowlang.package_manager import resolve_import_entry as _mellow_resolve_import_{alias}; __import_path_{alias} = _mellow_resolve_import_{alias}(str(__import_path_{alias})[4:]) or __import_path_{alias}")
        self._w(f"if True:  # import {alias}")
        self._indent += 1
        self._w(f"import os as _os_import_{alias}")
        self._w(f"_import_src = open(__import_path_{alias}, encoding='utf-8').read()")
        self._w(f"from mellowlang.fast_compiler import PyTranspiler as _PyTP_{alias}")
        self._w(f"_tp_{alias} = _PyTP_{alias}()")
        self._w(f"_py_{alias} = _tp_{alias}.transpile(_import_src.splitlines())")
        self._w(f"_mod_{alias}_ns = {{}}")
        self._w(f"exec(compile(_py_{alias}, __import_path_{alias}, 'exec'), _mod_{alias}_ns)")
        # Create a namespace proxy object
        self._w(f"class _{alias}_proxy:")
        self._indent += 1
        self._w(f"def __getattr__(self, name): return _mod_{alias}_ns[name]")
        self._indent -= 1
        self._w(f"{_py_name(alias)} = _{alias}_proxy()")
        self._indent -= 1

    # ── Expression compilation ─────────────────────────────────────────

    def _expr(self, e: Expr) -> str:
        if isinstance(e, Literal):
            v = e.value
            if v is None: return "None"
            if v is True: return "True"
            if v is False: return "False"
            if isinstance(v, str): return repr(v)
            return str(v)

        elif isinstance(e, Var):
            name = e.name
            # Remap common builtins
            _remaps = {
                'true': 'True', 'false': 'False', 'none': 'None', 'null': 'None',
                'len': '_mellow_len', 'abs': 'abs_val', 'floor': 'floor_val',
                'ceil': 'ceil_val', 'round': 'round_val', 'sqrt': 'sqrt_val',
                'log': 'log_val', 'sin': 'sin_val', 'cos': 'cos_val', 'tan': 'tan_val',
                'min': 'min_val', 'max': 'max_val', 'clamp': 'clamp_val',
                'int': 'to_int', 'float': 'to_float', 'str': 'to_str', 'bool': 'to_bool',
                'random_int': 'random_int', 'random_float': 'random_float',
                'enumerate': 'enumerate_mellow', 'zip': 'zip_mellow',
                'range': 'range_mellow',
            }
            return _remaps.get(name, _py_name(name))

        elif isinstance(e, UnaryOp):
            operand = self._expr(e.expr)
            if e.op == '-': return f"(-{operand})"
            if e.op in ('not', '!'): return f"(not {operand})"
            return f"({e.op}{operand})"

        elif isinstance(e, BinaryOp):
            left = self._expr(e.left)
            right = self._expr(e.right)
            op_map = {
                '+': '+', '-': '-', '*': '*', '/': '/',
                '%': '%', '**': '**',
                '==': '==', '!=': '!=', '<': '<', '>': '>',
                '<=': '<=', '>=': '>=',
                'and': 'and', 'or': 'or',
            }
            py_op = op_map.get(e.op, e.op)
            if e.op == '/':
                # Mellow division: integer result if exact
                return f"(lambda _a, _b: int(_a/_b) if _b != 0 and int(_a/_b) == _a/_b else (_a/_b if _b != 0 else 0))({left}, {right})"
            return f"({left} {py_op} {right})"

        elif isinstance(e, Call):
            return self._call_expr(e)

        elif isinstance(e, Index):
            return f"({self._expr(e.target)})[{self._expr(e.index)}]"

        elif isinstance(e, SliceExpr):
            target = self._expr(e.target)
            start = self._expr(e.start) if e.start else ""
            stop = self._expr(e.stop) if e.stop else ""
            step = f":{self._expr(e.step)}" if e.step else ""
            return f"({target})[{start}:{stop}{step}]"

        elif isinstance(e, ListLiteral):
            items = []
            for item in e.items:
                if isinstance(item, SpreadExpr):
                    items.append(f"*({self._expr(item.expr)})")
                else:
                    items.append(self._expr(item))
            return f"[{', '.join(items)}]"

        elif isinstance(e, MapLiteral):
            pairs = ", ".join(f"{self._expr(k)}: {self._expr(v)}" for k, v in e.pairs)
            return "{" + pairs + "}"

        elif isinstance(e, FStringExpr):
            parts = []
            for kind, val in e.parts:
                if kind == 'literal':
                    parts.append(repr(str(val)))
                else:
                    parts.append(f"_fmt({self._expr(val)})")
            if not parts: return "''"
            return " + ".join(parts)

        elif isinstance(e, LambdaExpr):
            # Build params with defaults
            defaults = getattr(e, 'defaults', {}) or {}
            params_parts = []
            for p in e.params:
                if p.startswith("*"):
                    params_parts.append(f"*{_py_name(p[1:])}")
                elif p in defaults:
                    params_parts.append(f"{_py_name(p)}={self._expr(defaults[p])}")
                else:
                    params_parts.append(_py_name(p))
            params_str = ", ".join(params_parts)

            if len(e.body) == 1 and isinstance(e.body[0], ReturnStmt) and e.body[0].expr is not None:
                body_src = self._expr(e.body[0].expr)
                return f"(lambda {params_str}: {body_src})"
            else:
                # Multi-statement: emit as nested def and return reference
                fn_name = f"__lam_{self._tmp_counter}"
                self._tmp_counter += 1
                self._w(f"def {fn_name}({params_str}):")
                self._indent += 1
                for st in e.body: self._stmt(st)
                if not e.body: self._w("pass")
                self._indent -= 1
                return fn_name

        elif isinstance(e, CallValExpr):
            # v1.4.9: call expression value: fns[0](args)
            callee = self._expr(e.callee)
            args = [self._expr(a) for a in e.args]
            return f"({callee})({', '.join(args)})"
        elif isinstance(e, ListCompExpr):
            expr_src = self._expr(e.expr)
            var = _py_name(e.var_name)
            it = self._expr(e.iterable)
            if e.condition:
                cond = self._expr(e.condition)
                return f"[{expr_src} for {var} in ({it} or []) if {cond}]"
            return f"[{expr_src} for {var} in ({it} or [])]"

        elif isinstance(e, GetModuleExpr):
            args_src = ", ".join(self._expr(a) for a in e.args)
            return f"_mod_{e.module}_{e.function}({args_src})"

        else:
            return f"None  # unsupported expr: {type(e).__name__}"

    def _call_expr(self, e: Call) -> str:
        # Map Mellow standard library calls to Python equivalents
        _name_map = {
            'show': 'show',
            'len': '_mellow_len',
            'list_push': 'list_push',
            'list_pop': 'list_pop',
            'list_len': 'list_len',
            'list_has': 'list_has',
            'list_map': 'list_map',
            'list_filter': 'list_filter',
            'list_reduce': 'list_reduce',
            'list_sort': 'list_sort',
            'list_reverse': 'list_reverse',
            'list_slice': 'list_slice',
            'list_find': 'list_find',
            'list_count': 'list_count',
            'list_flat': 'list_flat',
            'map_keys': 'map_keys',
            'map_values': 'map_values',
            'map_has': 'map_has',
            'map_set': 'map_set',
            'map_get': 'map_get',
            'map_del': 'map_del',
            'str_split': 'str_split',
            'str_join': 'str_join',
            'str_upper': 'str_upper',
            'str_lower': 'str_lower',
            'str_trim': 'str_trim',
            'str_starts': 'str_starts',
            'str_ends': 'str_ends',
            'str_contains': 'str_contains',
            'str_replace': 'str_replace',
            'str_find': 'str_find',
            'to_int': 'to_int',
            'to_float': 'to_float',
            'to_str': 'to_str',
            'to_bool': 'to_bool',
            'abs': 'abs_val',
            'floor': 'floor_val',
            'ceil': 'ceil_val',
            'round': 'round_val',
            'sqrt': 'sqrt_val',
            'sin': 'sin_val',
            'cos': 'cos_val',
            'tan': 'tan_val',
            'log': 'log_val',
            'min': 'min_val',
            'max': 'max_val',
            'clamp': 'clamp_val',
            'sign': 'sign',
            'fmod': 'fmod',
            'random_int': 'random_int',
            'random_float': 'random_float',
            'random_choice': 'random_choice',
            'shuffle': 'shuffle_list',
            'assert': 'assert_mellow',
            'assert_eq': 'assert_eq',
            'assert_ne': 'assert_ne',
            'is_number': 'is_number',
            'is_string': 'is_string',
            'is_bool': 'is_bool',
            'is_list': 'is_list',
            'is_map': 'is_map',
            'is_none': 'is_none',
            'type_of': 'type_of',
            'enumerate': 'enumerate_mellow',
            'zip': 'zip_mellow',
            'range': 'range_mellow',
        }
        name_raw = e.name
        # Handle dotted module calls: mylib.func(args) → keep as mylib.func
        if '.' in name_raw:
            parts = name_raw.split('.', 1)
            py_mod = _py_name(parts[0])
            py_func = parts[1]
            args = [self._expr(a) for a in e.args]
            if e.kwargs:
                kw_str = ", ".join(f"{k}={self._expr(v)}" for k, v in e.kwargs)
                args.append(kw_str)
            return f"{py_mod}.{py_func}({', '.join(args)})"

        name = _name_map.get(name_raw, _py_name(name_raw))
        args = [self._expr(a) for a in e.args]
        if e.kwargs:
            kw_str = ", ".join(f"{k}={self._expr(v)}" for k, v in e.kwargs)
            args.append(kw_str)
        return f"{name}({', '.join(args)})"


def _py_name(name: str) -> str:
    """Convert Mellow identifier to safe Python identifier."""
    # Avoid Python keywords
    _kw = {'for', 'while', 'if', 'else', 'elif', 'def', 'class', 'return',
           'import', 'from', 'as', 'try', 'except', 'finally', 'raise',
           'pass', 'break', 'continue', 'and', 'or', 'not', 'in', 'is',
           'None', 'True', 'False', 'lambda', 'with', 'yield', 'global',
           'nonlocal', 'del', 'assert', 'print', 'exec', 'eval'}
    if name in _kw:
        return f"_{name}_"
    return name.replace('-', '_').replace('.', '_')


# ── Public fast-run API ────────────────────────────────────────────────

class FastRunner:
    """
    Run MellowLang source using compile-to-Python-bytecode fast path.
    ~10-50x faster than bytecode VM for compute-heavy scripts.
    """

    def __init__(self, *, capture_output: bool = False):
        self.capture_output = capture_output
        self._last_py_src: str | None = None

    def run(self, source: str | list[str], *, filename: str | None = None) -> dict:
        """Compile and run MellowLang source. Returns {output, result, py_src}."""
        import io as _io, sys as _sys

        if isinstance(source, str):
            lines = source.splitlines()
        else:
            lines = list(source)

        tp = PyTranspiler()
        py_src = tp.transpile(lines, filename=filename)
        self._last_py_src = py_src

        namespace: dict = {}
        buf = _io.StringIO()

        if self.capture_output:
            old_stdout = _sys.stdout
            _sys.stdout = buf

        try:
            code_obj = compile(py_src, filename or '<mellow>', 'exec')
            exec(code_obj, namespace)
            result = None
        except SystemExit:
            result = None
        except Exception as e:
            if self.capture_output:
                _sys.stdout = old_stdout
            raise
        finally:
            if self.capture_output:
                try:
                    _sys.stdout = old_stdout
                except Exception:
                    pass

        return {
            'output': buf.getvalue() if self.capture_output else None,
            'result': result,
            'py_src': py_src,
        }
