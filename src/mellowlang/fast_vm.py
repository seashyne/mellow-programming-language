"""
MellowLang v1.4.9 — FastVM: compile-to-Python-bytecode engine.

Strategy: Walk the AST and generate a Python source string for each program,
then compile it with Python's built-in `compile()` and exec() it.
Generated Python calls are native CPython function calls, so the overhead is
just Python itself — no interpreter loop, no step-counting, no dict lookups
per opcode.

Expected speedup over the Python interpreter:
  - Tight loops:       ~15-30x
  - Recursion (fib):   ~20-40x
  - Mixed programs:    ~10-20x

Limitations (addressed by falling back to Python VM):
  - Replay / deterministic mode needs Python VM
  - Sandbox step-limit enforcement uses Python VM
  - Some advanced opcodes (WAIT, ASK) delegate to the Python VM
"""
from __future__ import annotations
import io
import sys
import types
import contextlib
from typing import Any

from .ast import (
    Program, Stmt, Expr,
    KeepStmt, KeepMultiStmt, AssignStmt, ExprStmt, ShowStmt,
    PrecisionStmt, StopStmt, ReturnStmt, BreakStmt, ContinueStmt,
    SkillDef, IfGroup, LoopWhile, LoopForEach, LoopForMap, LoopForRange,
    LoopCount, RepeatUntil, DoBlock, TryStmt, OnDef,
    ImportStmt, GetModuleStmt, WaitStmt,
    Literal, Var, UnaryOp, BinaryOp, Call, Index, ListLiteral, MapLiteral,
    FStringExpr, GetModuleExpr,
    LambdaExpr, ListCompExpr, SliceExpr, SpreadExpr,
)
from .parser import parse_program


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_name(s: str) -> str:
    """Convert a MellowLang identifier (possibly containing '.' or '-') to a
    valid Python identifier for generated code."""
    return "_ml_" + s.replace(".", "__dot__").replace("-", "__dash__")


def _indent(lines: list[str], n: int = 1) -> list[str]:
    pad = "    " * n
    return [pad + l for l in lines]


# ─── Code Generator ───────────────────────────────────────────────────────────

class _Gen:
    """Generates Python source from a MellowLang AST."""

    def __init__(self, host_registry):
        self._host = host_registry
        self._tmp = 0
        self._funcs: list[str] = []   # top-level function definitions
        self._output: list[str] = []  # main body

    def _new_tmp(self, prefix: str = "_t") -> str:
        self._tmp += 1
        return f"{prefix}{self._tmp}"

    # ── Entry point ──────────────────────────────────────────────────────────

    def generate(self, prog: Program) -> str:
        """Return complete Python source for the program."""
        self._funcs = []
        self._output = []

        # Collect skill definitions first (needed for forward references)
        for stmt in prog.body:
            if isinstance(stmt, SkillDef):
                self._gen_skill(stmt)

        # Generate main body
        main_lines = []
        for stmt in prog.body:
            if isinstance(stmt, SkillDef):
                continue  # already emitted
            main_lines.extend(self._gen_stmt(stmt))

        # Assemble full source
        parts = [
            "# MellowLang v1.4.9 — generated Python code",
            "import math as _math",
            "",
            # Runtime helpers
            self._runtime_helpers(),
            "",
            # Skill function definitions
            "\n".join(self._funcs),
            "",
            # Main body wrapped in a function (for local-variable speed)
            "def _mellow_main(_ctx):",
        ]
        if main_lines:
            parts.extend(_indent(main_lines))
        else:
            parts.append("    pass")
        parts.append("")
        parts.append("_mellow_main(_ctx)")

        return "\n".join(parts)

    # ── Runtime helpers emitted once ─────────────────────────────────────────

    def _runtime_helpers(self) -> str:
        return """\
def _mellow_truthy(v):
    if v is None or v is False: return False
    if v == 0: return False
    return True

def _mellow_add(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return _mellow_tostr(a) + _mellow_tostr(b)
    return a + b

def _mellow_tostr(v):
    if v is None: return "none"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, float) and v == int(v): return str(int(v))
    return str(v)

def _mellow_fmt_list(lst):
    return "[" + ", ".join(_mellow_repr(x) for x in lst) + "]"

def _mellow_repr(v):
    if v is None: return "none"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, str): return repr(v)
    if isinstance(v, list): return _mellow_fmt_list(v)
    if isinstance(v, float) and v == int(v): return str(int(v))
    return str(v)

def _mellow_print(v, prec=None):
    if isinstance(v, list):
        print(_mellow_fmt_list(v))
    elif isinstance(v, bool):
        print("true" if v else "false")
    elif isinstance(v, float) and v == int(v):
        print(int(v))
    else:
        print(v if v is not None else "none")

class _MellowStop(Exception): pass
class _MellowBreak(Exception): pass
class _MellowContinue(Exception): pass

def _mellow_getitem(target, idx):
    try:
        if isinstance(target, list):
            i = int(idx)
            if i < 0: i = len(target) + i
            return target[i] if 0 <= i < len(target) else None
        if isinstance(target, dict):
            return target.get(idx)
        if isinstance(target, str):
            i = int(idx)
            if i < 0: i = len(target) + i
            return target[i] if 0 <= i < len(target) else ''
        return None
    except Exception:
        return None

def _mellow_slice(target, start, stop):
    try:
        return target[start:stop]
    except Exception:
        return None if isinstance(target, list) else ''
"""

    # ── Skill definitions ────────────────────────────────────────────────────

    def _gen_skill(self, s: SkillDef, prefix: str = "") -> None:
        """Generate a Python function for a SkillDef."""
        fn_name = _safe_name((prefix + s.name) if prefix else s.name)
        # Build parameter list
        params = ["_ctx"]
        for p in s.params:
            params.append(_safe_name(p))

        lines = [f"def {fn_name}({', '.join(params)}):"]
        body_lines = []

        # Default arg checks
        defaults = getattr(s, "defaults", {}) or {}
        for p in s.params:
            if p in defaults:
                pn = _safe_name(p)
                defval = self._gen_expr(defaults[p])
                body_lines.append(f"if {pn} is None: {pn} = {defval}")

        # Body
        for stmt in s.body:
            body_lines.extend(self._gen_stmt(stmt))

        # Implicit return None
        body_lines.append("return None")

        if not body_lines:
            body_lines = ["pass"]

        lines.extend(_indent(body_lines))
        self._funcs.append("\n".join(lines))

    # ── Statement generation ─────────────────────────────────────────────────

    def _gen_stmt(self, s: Stmt) -> list[str]:
        if isinstance(s, KeepStmt):
            return [f"{_safe_name(s.name)} = {self._gen_expr(s.expr)}"]
        if isinstance(s, KeepMultiStmt):
            vals = ", ".join(self._gen_expr(e) for e in s.exprs)
            names = ", ".join(_safe_name(n) for n in s.names)
            return [f"{names} = {vals}"]
        if isinstance(s, AssignStmt):
            if len(s.names) == 1 and len(s.exprs) == 1:
                return [f"{_safe_name(s.names[0])} = {self._gen_expr(s.exprs[0])}"]
            vals = ", ".join(self._gen_expr(e) for e in s.exprs)
            names = ", ".join(_safe_name(n) for n in s.names)
            return [f"{names} = {vals}"]
        if isinstance(s, ExprStmt):
            return [self._gen_expr(s.expr)]
        if isinstance(s, ShowStmt):
            if len(s.exprs) == 1:
                return [f"_mellow_print({self._gen_expr(s.exprs[0])})"]
            vals = ", ".join(self._gen_expr(e) for e in s.exprs)
            return [f"print(' '.join(_mellow_tostr(v) for v in [{vals}]))"]
        if isinstance(s, ReturnStmt):
            if s.expr is None:
                return ["return None"]
            return [f"return {self._gen_expr(s.expr)}"]
        if isinstance(s, BreakStmt):
            return ["break"]
        if isinstance(s, ContinueStmt):
            return ["continue"]
        if isinstance(s, StopStmt):
            return ["raise _MellowStop()"]
        if isinstance(s, PrecisionStmt):
            return [f"_ctx._precision = {self._gen_expr(s.expr)}"]
        if isinstance(s, IfGroup):
            return self._gen_if(s)
        if isinstance(s, LoopWhile):
            return self._gen_loop_while(s)
        if isinstance(s, LoopCount):
            return self._gen_loop_count(s)
        if isinstance(s, LoopForEach):
            return self._gen_loop_foreach(s)
        if isinstance(s, LoopForRange):
            return self._gen_loop_range(s)
        if isinstance(s, LoopForMap):
            return self._gen_loop_formap(s)
        if isinstance(s, RepeatUntil):
            return self._gen_repeat_until(s)
        if isinstance(s, DoBlock):
            lines = []
            for st in s.body:
                lines.extend(self._gen_stmt(st))
            return lines
        if isinstance(s, TryStmt):
            return self._gen_try(s)
        if isinstance(s, SkillDef):
            # Nested function — emit inline as closure
            fn_name = _safe_name(s.name)
            inner_params = ["_ctx"] + [_safe_name(p) for p in s.params]
            lines = [f"def {fn_name}({', '.join(inner_params)}):"]
            defaults = getattr(s, "defaults", {}) or {}
            body_lines = []
            for p in s.params:
                if p in defaults:
                    pn = _safe_name(p)
                    body_lines.append(f"if {pn} is None: {pn} = {self._gen_expr(defaults[p])}")
            for st in s.body:
                body_lines.extend(self._gen_stmt(st))
            body_lines.append("return None")
            lines.extend(_indent(body_lines))
            return lines
        if isinstance(s, ImportStmt):
            return self._gen_import(s)
        if isinstance(s, GetModuleStmt):
            call_e = GetModuleExpr(s.module, s.function, s.args)
            if s.var_name:
                return [f"{_safe_name(s.var_name)} = {self._gen_expr(call_e)}"]
            return [self._gen_expr(call_e)]
        if isinstance(s, WaitStmt):
            return [f"_ctx._syscall('std.time.sleep', [{self._gen_expr(s.expr)}])"]
        # Fallback — skip unknown
        return [f"# UNHANDLED stmt: {type(s).__name__}"]

    def _gen_if(self, s: IfGroup) -> list[str]:
        lines = []
        for i, (cond_expr, body) in enumerate(s.branches):
            kw = "if" if i == 0 else "elif"
            lines.append(f"{kw} _mellow_truthy({self._gen_expr(cond_expr)}):")
            body_lines = []
            for st in body:
                body_lines.extend(self._gen_stmt(st))
            if not body_lines:
                body_lines = ["pass"]
            lines.extend(_indent(body_lines))
        if s.else_block is not None:
            lines.append("else:")
            else_lines = []
            for st in s.else_block:
                else_lines.extend(self._gen_stmt(st))
            if not else_lines:
                else_lines = ["pass"]
            lines.extend(_indent(else_lines))
        return lines

    def _gen_loop_while(self, s: LoopWhile) -> list[str]:
        lines = [f"while _mellow_truthy({self._gen_expr(s.cond)}):"]
        body = []
        for st in s.body:
            body.extend(self._gen_stmt(st))
        if not body:
            body = ["pass"]
        lines.extend(_indent(body))
        return lines

    def _gen_loop_count(self, s: LoopCount) -> list[str]:
        tmp = self._new_tmp("_cnt")
        lines = [
            f"for {tmp} in range(int({self._gen_expr(s.limit)})):",
        ]
        body = []
        for st in s.body:
            body.extend(self._gen_stmt(st))
        if not body:
            body = ["pass"]
        lines.extend(_indent(body))
        return lines

    def _gen_loop_foreach(self, s: LoopForEach) -> list[str]:
        iterable = self._gen_expr(s.iterable)
        var_names = getattr(s, "var_names", [s.var_name])
        if len(var_names) > 1:
            loop_var = "(" + ", ".join(_safe_name(v) for v in var_names) + ")"
        else:
            loop_var = _safe_name(var_names[0])
        lines = [f"for {loop_var} in (_mellow_iter({iterable})):"]
        body = []
        for st in s.body:
            body.extend(self._gen_stmt(st))
        if not body:
            body = ["pass"]
        lines.extend(_indent(body))
        return lines

    def _gen_loop_range(self, s: LoopForRange) -> list[str]:
        var = _safe_name(s.var_name)
        start = self._gen_expr(s.start)
        end = self._gen_expr(s.end)
        step = self._gen_expr(s.step) if s.step else "1"
        lines = [f"for {var} in range(int({start}), int({end}) + 1, int({step})):"]
        body = []
        for st in s.body:
            body.extend(self._gen_stmt(st))
        if not body:
            body = ["pass"]
        lines.extend(_indent(body))
        return lines

    def _gen_loop_formap(self, s: LoopForMap) -> list[str]:
        tmp_map = self._new_tmp("_map")
        k = _safe_name(s.key_name)
        v = _safe_name(s.value_name)
        lines = [
            f"{tmp_map} = {self._gen_expr(s.iterable)}",
            f"for {k} in (list({tmp_map}.keys()) if isinstance({tmp_map}, dict) else []):",
            f"    {v} = {tmp_map}.get({k})",
        ]
        body = []
        for st in s.body:
            body.extend(self._gen_stmt(st))
        if not body:
            body = ["pass"]
        lines.extend(_indent(body, 1))
        return lines

    def _gen_repeat_until(self, s: RepeatUntil) -> list[str]:
        lines = ["while True:"]
        body = []
        for st in s.body:
            body.extend(self._gen_stmt(st))
        body.append(f"if _mellow_truthy({self._gen_expr(s.cond)}): break")
        lines.extend(_indent(body))
        return lines

    def _gen_try(self, s: TryStmt) -> list[str]:
        lines = ["try:"]
        try_body = []
        for st in s.try_body:
            try_body.extend(self._gen_stmt(st))
        if not try_body:
            try_body = ["pass"]
        lines.extend(_indent(try_body))

        if s.catch_body is not None:
            err_name = _safe_name(s.catch_name) if s.catch_name else "_err"
            lines.append(f"except Exception as {err_name}:")
            catch_body = []
            for st in (s.catch_body or []):
                catch_body.extend(self._gen_stmt(st))
            if not catch_body:
                catch_body = ["pass"]
            lines.extend(_indent(catch_body))
        if s.finally_body is not None:
            lines.append("finally:")
            fin_body = []
            for st in (s.finally_body or []):
                fin_body.extend(self._gen_stmt(st))
            if not fin_body:
                fin_body = ["pass"]
            lines.extend(_indent(fin_body))
        return lines

    def _gen_import(self, s: ImportStmt) -> list[str]:
        """Generate import as: call _ctx._import(path, alias) at runtime."""
        alias = _safe_name(s.alias)
        return [f"{alias} = _ctx._import_module({repr(s.path)}, {repr(s.alias)})"]

    # ── Expression generation ────────────────────────────────────────────────

    def _gen_expr(self, e: Expr) -> str:
        if isinstance(e, Literal):
            return repr(e.value)
        if isinstance(e, Var):
            return _safe_name(e.name)
        if isinstance(e, UnaryOp):
            inner = self._gen_expr(e.expr)
            if e.op == "not":
                return f"(not _mellow_truthy({inner}))"
            if e.op == "-":
                return f"(-({inner}))"
            return inner
        if isinstance(e, BinaryOp):
            l = self._gen_expr(e.left)
            r = self._gen_expr(e.right)
            op = e.op
            if op == "+":  return f"_mellow_add({l}, {r})"
            if op == "-":  return f"(({l}) - ({r}))"
            if op == "*":  return f"(({l}) * ({r}))"
            if op == "/":  return f"_mellow_div({l}, {r})"
            if op == "%":  return f"(int({l}) % int({r}))"
            if op == "**": return f"(({l}) ** ({r}))"
            if op == "==": return f"(({l}) == ({r}))"
            if op == "!=": return f"(({l}) != ({r}))"
            if op == ">":  return f"(({l}) > ({r}))"
            if op == "<":  return f"(({l}) < ({r}))"
            if op == ">=": return f"(({l}) >= ({r}))"
            if op == "<=": return f"(({l}) <= ({r}))"
            if op == "and": return f"(_mellow_truthy({l}) and _mellow_truthy({r}))"
            if op == "or":  return f"(_mellow_truthy({l}) or _mellow_truthy({r}))"
            return f"({l} {op} {r})"
        if isinstance(e, Call):
            return self._gen_call(e)
        if isinstance(e, Index):
            return f"_mellow_getitem({self._gen_expr(e.target)}, {self._gen_expr(e.index)})"
        if isinstance(e, SliceExpr):
            t = self._gen_expr(e.target)
            start = self._gen_expr(e.start) if e.start else "None"
            stop  = self._gen_expr(e.stop)  if e.stop  else "None"
            return f"_mellow_slice({t}, {start}, {stop})"
        if isinstance(e, ListLiteral):
            has_spread = any(isinstance(i, SpreadExpr) for i in e.items)
            if has_spread:
                parts = []
                for item in e.items:
                    if isinstance(item, SpreadExpr):
                        parts.append(f"*({self._gen_expr(item.expr)})")
                    else:
                        parts.append(self._gen_expr(item))
                return f"[{', '.join(parts)}]"
            return "[" + ", ".join(self._gen_expr(i) for i in e.items) + "]"
        if isinstance(e, MapLiteral):
            pairs = ", ".join(
                f"{self._gen_expr(k)}: {self._gen_expr(v)}"
                for k, v in e.pairs
            )
            return "{" + pairs + "}"
        if isinstance(e, FStringExpr):
            parts = []
            for kind, val in e.parts:
                if kind == "literal":
                    parts.append(repr(val))
                else:
                    parts.append(f"_mellow_tostr({self._gen_expr(val)})")
            if not parts:
                return '""'
            return " + ".join(parts)
        if isinstance(e, ListCompExpr):
            cond_part = f" if _mellow_truthy({self._gen_expr(e.condition)})" if e.condition else ""
            return f"[{self._gen_expr(e.expr)} for {_safe_name(e.var_name)} in _mellow_iter({self._gen_expr(e.iterable)}){cond_part}]"
        if isinstance(e, LambdaExpr):
            # Generate as inline lambda or nested function
            tmp_name = self._new_tmp("_lam")
            params = ["_ctx"] + [_safe_name(p) for p in e.params]
            sk = SkillDef(tmp_name, e.params, e.body, defaults=getattr(e, "defaults", {}))
            # emit as nested definition
            self._gen_skill_inline(sk, tmp_name)
            return tmp_name
        if isinstance(e, SpreadExpr):
            return f"*({self._gen_expr(e.expr)})"
        if isinstance(e, GetModuleExpr):
            if not e.args:
                return _safe_name(f"{e.module}.{e.function}")
            # Module method call
            return f"_ctx._syscall('std.{e.module}.{e.function}', [{', '.join(self._gen_expr(a) for a in e.args)}])"
        return "None  # unknown expr"

    def _gen_skill_inline(self, s: SkillDef, fn_name: str) -> None:
        """Emit a skill as a top-level Python function (for lambda use)."""
        params = ["_ctx"] + [_safe_name(p) for p in s.params]
        lines = [f"def {fn_name}({', '.join(params)}):"]
        body_lines = []
        defaults = getattr(s, "defaults", {}) or {}
        for p in s.params:
            if p in defaults:
                pn = _safe_name(p)
                body_lines.append(f"if {pn} is None: {pn} = {self._gen_expr(defaults[p])}")
        for st in s.body:
            body_lines.extend(self._gen_stmt(st))
        body_lines.append("return None")
        lines.extend(_indent(body_lines))
        self._funcs.append("\n".join(lines))

    def _gen_call(self, e: Call) -> str:
        name = e.name
        args = list(e.args)

        # Built-in functions that map directly to Python / stdlib
        DIRECT = {
            "len": lambda: f"len({', '.join(self._gen_expr(a) for a in args)})",
            "range": lambda: f"list(range({', '.join(self._gen_expr(a) for a in args)}))",
            "abs":   lambda: f"abs({self._gen_expr(args[0])})" if args else "0",
            "min":   lambda: f"min({', '.join(self._gen_expr(a) for a in args)})",
            "max":   lambda: f"max({', '.join(self._gen_expr(a) for a in args)})",
            "floor": lambda: f"int(_math.floor({self._gen_expr(args[0])}))" if args else "0",
            "ceil":  lambda: f"int(_math.ceil({self._gen_expr(args[0])}))" if args else "0",
            "round": lambda: f"round({', '.join(self._gen_expr(a) for a in args)})",
            "sqrt":  lambda: f"_math.sqrt({self._gen_expr(args[0])})" if args else "0",
            "pow":   lambda: f"({self._gen_expr(args[0])} ** {self._gen_expr(args[1])})" if len(args)>=2 else "0",
            "int":   lambda: f"(int(float({self._gen_expr(args[0])})) if {self._gen_expr(args[0])} is not None else 0)" if args else "0",
            "float": lambda: f"(float({self._gen_expr(args[0])}) if {self._gen_expr(args[0])} is not None else 0.0)" if args else "0.0",
            "str":   lambda: f"_mellow_tostr({self._gen_expr(args[0])})" if args else '""',
            "bool":  lambda: f"bool({self._gen_expr(args[0])})" if args else "False",
            "list":  lambda: f"(list({self._gen_expr(args[0])}) if {self._gen_expr(args[0])} is not None else [])" if args else "[]",
            "sum":   lambda: f"sum({self._gen_expr(args[0])})" if args else "0",
            "sorted":lambda: f"sorted({self._gen_expr(args[0])}{', reverse=True' if len(args)>1 else ''})" if args else "[]",
            "reversed":lambda: f"list(reversed({self._gen_expr(args[0])}))" if args else "[]",
            "any":   lambda: f"any(bool(x) for x in ({self._gen_expr(args[0])}))" if args else "False",
            "all":   lambda: f"all(bool(x) for x in ({self._gen_expr(args[0])}))" if args else "True",
            "enumerate": lambda: f"list(enumerate({self._gen_expr(args[0])}))" if args else "[]",
            "zip":   lambda: f"[list(t) for t in zip({', '.join(self._gen_expr(a) for a in args)})]",
            "chr":   lambda: f"chr(int({self._gen_expr(args[0])}))" if args else "''",
            "ord":   lambda: f"ord(str({self._gen_expr(args[0])})[0])" if args else "0",
            "type_of": lambda: f"type({self._gen_expr(args[0])}).__name__" if args else "'none'",
            "is_number": lambda: f"isinstance({self._gen_expr(args[0])}, (int, float))" if args else "False",
            "is_string": lambda: f"isinstance({self._gen_expr(args[0])}, str)" if args else "False",
            "is_list":   lambda: f"isinstance({self._gen_expr(args[0])}, list)" if args else "False",
            "is_map":    lambda: f"isinstance({self._gen_expr(args[0])}, dict)" if args else "False",
            "is_none":   lambda: f"({self._gen_expr(args[0])} is None)" if args else "True",
            "print":  lambda: f"_mellow_print({', '.join(self._gen_expr(a) for a in args)})" if args else "_mellow_print(None)",
            "sin": lambda: f"_math.sin({self._gen_expr(args[0])})" if args else "0",
            "cos": lambda: f"_math.cos({self._gen_expr(args[0])})" if args else "0",
            "tan": lambda: f"_math.tan({self._gen_expr(args[0])})" if args else "0",
            "atan2": lambda: f"_math.atan2({self._gen_expr(args[0])}, {self._gen_expr(args[1])})" if len(args)>=2 else "0",
        }

        if name in DIRECT:
            return DIRECT[name]()

        # list_* functions
        LIST_FN = {
            "list_push": lambda: f"({self._gen_expr(args[0])}.append({self._gen_expr(args[1])}) or {self._gen_expr(args[0])})" if len(args)>=2 else "[]",
            "list_pop":  lambda: f"({self._gen_expr(args[0])}.pop() if {self._gen_expr(args[0])} else None)" if args else "None",
            "list_len":  lambda: f"len({self._gen_expr(args[0])})" if args else "0",
            "list_sort": lambda: f"(sorted({self._gen_expr(args[0])}))" if args else "[]",
            "list_has":  lambda: f"({self._gen_expr(args[1])} in {self._gen_expr(args[0])})" if len(args)>=2 else "False",
            "list_reverse": lambda: f"list(reversed({self._gen_expr(args[0])}))" if args else "[]",
            "list_slice": lambda: f"({self._gen_expr(args[0])}[int({self._gen_expr(args[1])}):{('int('+self._gen_expr(args[2])+')') if len(args)>2 else ''}])" if args else "[]",
            "list_insert": lambda: f"(_mellow_list_insert({self._gen_expr(args[0])}, {self._gen_expr(args[1])}, {self._gen_expr(args[2])}) if len(args)>=3 else None)",
            "list_remove": lambda: f"(_mellow_list_remove({self._gen_expr(args[0])}, {self._gen_expr(args[1])}) if len(args)>=2 else None)",
            "list_filter": lambda: f"_ctx._syscall('std.list.filter', [{', '.join(self._gen_expr(a) for a in args)}])",
            "list_map":    lambda: f"_ctx._syscall('std.list.map', [{', '.join(self._gen_expr(a) for a in args)}])",
            "list_count":  lambda: f"len({self._gen_expr(args[0])})" if args else "0",
            "list_find":   lambda: f"_ctx._syscall('std.list.find', [{', '.join(self._gen_expr(a) for a in args)}])",
            "list_reduce": lambda: f"_ctx._syscall('std.list.reduce', [{', '.join(self._gen_expr(a) for a in args)}])",
        }
        if name in LIST_FN:
            return LIST_FN[name]()

        # map_* functions
        MAP_FN = {
            "map_get":    lambda: f"({self._gen_expr(args[0])}.get({self._gen_expr(args[1])}, {self._gen_expr(args[2]) if len(args)>2 else 'None'}))",
            "map_set":    lambda: f"_mellow_map_set({self._gen_expr(args[0])}, {self._gen_expr(args[1])}, {self._gen_expr(args[2])})" if len(args)>=3 else "{}",
            "map_keys":   lambda: f"list({self._gen_expr(args[0])}.keys())" if args else "[]",
            "map_values": lambda: f"list({self._gen_expr(args[0])}.values())" if args else "[]",
            "map_has":    lambda: f"({self._gen_expr(args[1])} in {self._gen_expr(args[0])})" if len(args)>=2 else "False",
        }
        if name in MAP_FN:
            return MAP_FN[name]()

        # str_* / string_*
        STR_FN = {
            "str_len":       lambda: f"len(str({self._gen_expr(args[0])}))" if args else "0",
            "str_upper":     lambda: f"str({self._gen_expr(args[0])}).upper()" if args else "''",
            "str_lower":     lambda: f"str({self._gen_expr(args[0])}).lower()" if args else "''",
            "str_trim":      lambda: f"str({self._gen_expr(args[0])}).strip()" if args else "''",
            "str_split":     lambda: f"str({self._gen_expr(args[0])}).split({self._gen_expr(args[1]) if len(args)>1 else 'None'})" if args else "[]",
            "str_join":      lambda: f"str({self._gen_expr(args[0]) if args else repr(' ')}).join({self._gen_expr(args[1]) if len(args)>1 else '[]'})",
            "str_replace":   lambda: f"str({self._gen_expr(args[0])}).replace({self._gen_expr(args[1])}, {self._gen_expr(args[2])})" if len(args)>=3 else "''",
            "str_find":      lambda: f"str({self._gen_expr(args[0])}).find({self._gen_expr(args[1])})" if len(args)>=2 else "-1",
            "str_contains":  lambda: f"({self._gen_expr(args[1])} in str({self._gen_expr(args[0])}))" if len(args)>=2 else "False",
            "str_starts_with":lambda: f"str({self._gen_expr(args[0])}).startswith({self._gen_expr(args[1])})" if len(args)>=2 else "False",
            "str_ends_with": lambda: f"str({self._gen_expr(args[0])}).endswith({self._gen_expr(args[1])})" if len(args)>=2 else "False",
            "str_repeat":    lambda: f"str({self._gen_expr(args[0])}) * int({self._gen_expr(args[1])})" if len(args)>=2 else "''",
            "string_len":    lambda: f"len(str({self._gen_expr(args[0])}))" if args else "0",
            "string_lower":  lambda: f"str({self._gen_expr(args[0])}).lower()" if args else "''",
            "string_upper":  lambda: f"str({self._gen_expr(args[0])}).upper()" if args else "''",
        }
        if name in STR_FN:
            return STR_FN[name]()

        # math helpers
        MATH_FN = {
            "clamp": lambda: f"max({self._gen_expr(args[1])}, min({self._gen_expr(args[2])}, {self._gen_expr(args[0])}))" if len(args)>=3 else "0",
            "lerp":  lambda: f"({self._gen_expr(args[0])} + ({self._gen_expr(args[1])} - {self._gen_expr(args[0])}) * {self._gen_expr(args[2])})" if len(args)>=3 else "0",
            "sign":  lambda: f"(1 if ({self._gen_expr(args[0])}) > 0 else (-1 if ({self._gen_expr(args[0])}) < 0 else 0))" if args else "0",
            "fmod":  lambda: f"_math.fmod({self._gen_expr(args[0])}, {self._gen_expr(args[1])})" if len(args)>=2 else "0",
            "deg_to_rad": lambda: f"(_math.radians({self._gen_expr(args[0])}))" if args else "0",
            "rad_to_deg": lambda: f"(_math.degrees({self._gen_expr(args[0])}))" if args else "0",
        }
        if name in MATH_FN:
            return MATH_FN[name]()

        # map/filter as higher-order with first-class functions
        if name in ("map", "filter", "reduce"):
            fn_arg = self._gen_expr(args[0]) if args else "None"
            lst_arg = self._gen_expr(args[1]) if len(args)>1 else "[]"
            if name == "map":
                return f"[{fn_arg}(_ctx, x) for x in {lst_arg}]"
            if name == "filter":
                return f"[x for x in {lst_arg} if _mellow_truthy({fn_arg}(_ctx, x))]"
            # reduce — fallback to syscall
            return f"_ctx._syscall('std.list.reduce', [{fn_arg}, {lst_arg}])"

        # random
        if name in ("rand", "rand_float", "random_float"):
            return "_ctx._rng.random()"
        if name in ("randi", "rand_int", "random_int", "random") and args:
            a0 = self._gen_expr(args[0])
            a1 = self._gen_expr(args[1]) if len(args)>1 else "1"
            return f"_ctx._rng.randint(int({a0}), int({a1}))"

        # seed/global_seed
        if name == "seed" and args:
            return f"(_ctx._rng.seed(int({self._gen_expr(args[0])})) or None)"
        if name == "global_seed" and args:
            return f"(_ctx._rng.seed(int({self._gen_expr(args[0])})) or None)"

        # time
        if name == "time_now":
            return "_ctx._syscall('std.time.now', [])"
        if name == "time_ms":
            return "_ctx._syscall('std.time.ms', [])"

        # assert
        if name == "assert" and args:
            return f"(_ctx._syscall('std.assert.check', [{', '.join(self._gen_expr(a) for a in args)}]))"

        # json
        if name in ("json_encode", "json_decode"):
            _jop = name.split("_")[1]
            _jargs = ", ".join(self._gen_expr(a) for a in args)
            return f"_ctx._syscall('std.json.{_jop}', [{_jargs}])"

        # emit event
        if name == "emit":
            return f"_ctx._syscall('std.event.emit', [{', '.join(self._gen_expr(a) for a in args)}])"

        # Named dot-call (module method): utils.square(4)
        if "." in name:
            fn_ref = _safe_name(name)
            arg_strs = ["_ctx"] + [self._gen_expr(a) for a in args]
            return f"{fn_ref}({', '.join(arg_strs)})"

        # User-defined skill call
        fn_ref = _safe_name(name)
        arg_strs = ["_ctx"] + [self._gen_expr(a) for a in args]
        # Also support first-class fn: if name might be a variable holding a func
        # We always emit a call; if fn_ref is a Python function it will work.
        return f"{fn_ref}({', '.join(arg_strs)})"


# ─── Context object passed to all generated functions ─────────────────────────

class _MellowCtx:
    """Runtime context: holds host registry, RNG, and precision."""

    def __init__(self, host, filename: str | None = None):
        import random as _random
        self._host = host
        self._precision = None
        self._rng = _random.Random(12345)
        self._filename = filename

    def _syscall(self, name: str, args: list) -> Any:
        """Dispatch a stdlib syscall through the host registry."""
        try:
            fn = self._host.get(name)
            if fn:
                return fn.call(args)
        except Exception as e:
            raise RuntimeError(f"syscall {name}: {e}") from e
        return None

    def _import_module(self, path: str, alias: str) -> "types.SimpleNamespace":
        """Import a .mellow file and return a namespace object."""
        import os
        original_path = path
        if path.startswith("pkg:"):
            try:
                from .package_manager import resolve_import_entry
                resolved = resolve_import_entry(path[4:], os.path.dirname(self._filename or "") or ".")
                if not resolved:
                    raise RuntimeError(f"package import not installed: {path[4:]}")
                path = resolved
            except Exception as e:
                raise RuntimeError(f"import '{original_path}': {e}") from e
        base_dir = os.path.dirname(self._filename or "") or "."
        full_path = os.path.join(base_dir, path)
        if not os.path.exists(full_path):
            full_path = path
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                src = f.read()
        except OSError as e:
            raise RuntimeError(f"import '{original_path}': {e}") from e

        # Compile and run the module in a new FastVM
        fvm = FastVM(self._host)
        ns = fvm.run_module(src, filename=full_path)
        return ns


# ─── FastVM public API ────────────────────────────────────────────────────────

# Extra Python runtime helpers emitted at exec() scope
_EXEC_HELPERS = """\
def _mellow_div(a, b):
    if b == 0: raise ZeroDivisionError('division by zero')
    r = a / b
    return int(r) if r == int(r) else r

def _mellow_map_set(d, k, v):
    d = d if isinstance(d, dict) else {}
    d[k] = v
    return d

def _mellow_list_insert(lst, idx, val):
    lst.insert(int(idx), val)
    return lst

def _mellow_list_remove(lst, val):
    try: lst.remove(val)
    except: pass
    return lst

def _mellow_iter(obj):
    if isinstance(obj, list): return obj
    if isinstance(obj, dict): return list(obj.keys())
    if isinstance(obj, str): return list(obj)
    try: return list(obj)
    except: return []
"""


class FastVM:
    """
    MellowLang v1.4.9 compile-to-Python engine.

    Usage:
        fvm = FastVM(host_registry)
        result = fvm.run(source_code, filename='script.mellow')
    """

    def __init__(self, host):
        self._host = host

    def run(self, source: str, *, filename: str | None = None) -> Any:
        """Compile and run MellowLang source. Returns stdout as string."""
        prog = parse_program(source.splitlines(), filename=filename)
        gen = _Gen(self._host)
        py_src = gen.generate(prog)

        ctx = _MellowCtx(self._host, filename=filename)
        buf = io.StringIO()

        globs = {"_ctx": ctx}
        exec(compile(_EXEC_HELPERS, "<mellow_helpers>", "exec"), globs)

        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(py_src, filename or "<mellow>", "exec"), globs)
        except _MellowStop:
            pass  # normal program stop

        return buf.getvalue()

    def run_module(self, source: str, *, filename: str | None = None):
        """Run a module file and return its exported namespace (SimpleNamespace)."""
        prog = parse_program(source.splitlines(), filename=filename)
        gen = _Gen(self._host)
        py_src = gen.generate(prog)

        ctx = _MellowCtx(self._host, filename=filename)
        globs = {"_ctx": ctx}
        exec(compile(_EXEC_HELPERS, "<mellow_helpers>", "exec"), globs)

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(py_src, filename or "<mellow_module>", "exec"), globs)
        except _MellowStop:
            pass

        # Collect exports: all _ml_* variables → namespace
        ns = types.SimpleNamespace()
        for k, v in globs.items():
            if k.startswith("_ml_") and not k.startswith("_ml___"):
                attr = k[4:].replace("__dot__", ".").replace("__dash__", "-")
                setattr(ns, attr, v)
        return ns

    def get_source(self, source: str, *, filename: str | None = None) -> str:
        """Return generated Python source for debugging."""
        prog = parse_program(source.splitlines(), filename=filename)
        gen = _Gen(self._host)
        return gen.generate(prog)
