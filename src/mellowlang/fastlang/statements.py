"""One statement node in, one run of Python lines out."""

from __future__ import annotations

from ..ast import (
    AssignStmt,
    BreakStmt,
    ContinueStmt,
    DoBlock,
    ExprStmt,
    GetModuleStmt,
    IfGroup,
    ImportStmt,
    KeepMultiStmt,
    KeepStmt,
    LoadStmt,
    LoopCount,
    LoopForEach,
    LoopForMap,
    LoopForRange,
    LoopWhile,
    OnDef,
    PrecisionStmt,
    PutStmt,
    RepeatUntil,
    ReturnStmt,
    SaveStmt,
    ShowStmt,
    SkillDef,
    Stmt,
    StopStmt,
    TryStmt,
    WaitStmt,
)
from .names import _py_name


class StatementMixin:
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

