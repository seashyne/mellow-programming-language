"""The AST walk itself: expression and statement dispatch, scope pushes
and the unused-declaration sweep."""

from __future__ import annotations

from typing import List

from ..ast import (
    KeepStmt, KeepMultiStmt, AssignStmt, ExprStmt,
    ShowStmt, PrecisionStmt, StopStmt, WaitStmt,
    SaveStmt, LoadStmt, PutStmt, ReturnStmt,
    BreakStmt, ContinueStmt, TryStmt,
    SkillDef, OnDef,
    IfGroup, LoopWhile, LoopForEach, LoopForMap,
    LoopForRange, RepeatUntil, LoopCount, DoBlock,
    Var, Call, BinaryOp, UnaryOp, Literal,
    Index, ListLiteral, MapLiteral, FStringExpr,
    CallValExpr, LambdaExpr, ListCompExpr, SpreadExpr, SliceExpr,
    GetModuleExpr, GetModuleStmt, ImportStmt,
)

from .issues import _BUILTINS, LintIssue, _Scope


class _Linter:
    def __init__(self):
        self.issues: List[LintIssue] = []
        self._scope = _Scope()
        for b in _BUILTINS:
            self._scope.declare(b)
            self._scope.mark_used(b)

    def _warn(self, kind, msg, line=None):
        self.issues.append(LintIssue(kind, msg, line))

    def _push(self, fn_name=None):
        self._scope = _Scope(parent=self._scope, fn_name=fn_name)
        return self._scope

    def _pop(self):
        popped = self._scope
        self._scope = self._scope.parent
        return popped

    def _declare(self, name, line=None, param=False, loop_var=False):
        if (name in self._scope.vars
                and not self._scope.vars[name].param
                and not self._scope.vars[name].loop_var
                and self._scope.vars[name].line is not None):
            self._warn("SHADOW",
                f"'{name}' shadows earlier declaration at line {self._scope.vars[name].line}", line)
        self._scope.declare(name, line=line, param=param, loop_var=loop_var)

    def _use(self, name, line=None):
        if name in _BUILTINS: return
        if not self._scope.is_declared(name):
            self._warn("UNDEFINED", f"'{name}' used before declaration", line)
        else:
            self._scope.mark_used(name)

    def _flush_unused(self, scope):
        for name, info in scope.unused():
            self._warn("UNUSED", f"'{name}' is declared but never used", info.line)

    def _expr(self, e):
        if e is None: return
        if isinstance(e, Var):
            self._use(e.name)
        elif isinstance(e, (Literal,)):
            pass
        elif isinstance(e, BinaryOp):
            self._expr(e.left); self._expr(e.right)
        elif isinstance(e, UnaryOp):
            self._expr(e.expr)
        elif isinstance(e, Call):
            self._use(e.name)
            for a in e.args: self._expr(a)
            for _, v in (e.kwargs or []): self._expr(v)
        elif isinstance(e, Index):
            self._expr(e.target); self._expr(e.index)
        elif isinstance(e, ListLiteral):
            for i in e.items: self._expr(i)
        elif isinstance(e, MapLiteral):
            for k, v in e.pairs: self._expr(k); self._expr(v)
        elif isinstance(e, FStringExpr):
            for kind, val in e.parts:
                if kind == "expr": self._expr(val)
        elif isinstance(e, CallValExpr):
            self._expr(e.callee)
            for a in e.args: self._expr(a)
        elif isinstance(e, LambdaExpr):
            self._push(fn_name="<lambda>")
            for p in e.params:
                self._scope.declare(p, param=True)
                self._scope.mark_used(p)
            for default in e.defaults.values(): self._expr(default)
            self._stmts(e.body)
            self._flush_unused(self._pop())
        elif isinstance(e, ListCompExpr):
            self._expr(e.iterable)
            self._push()
            self._scope.declare(e.var_name, loop_var=True)
            self._scope.mark_used(e.var_name)
            self._expr(e.expr)
            self._expr(e.condition)
            self._flush_unused(self._pop())
        elif isinstance(e, SpreadExpr):
            self._expr(e.expr)
        elif isinstance(e, SliceExpr):
            self._expr(e.target)
            self._expr(e.start)
            self._expr(e.stop)
            self._expr(e.step)
        elif isinstance(e, GetModuleExpr):
            for a in e.args: self._expr(a)

    def _stmts(self, stmts):
        for s in stmts: self._stmt(s)

    def _stmt(self, s):
        if isinstance(s, KeepStmt):
            self._expr(s.expr)
            self._declare(s.name, getattr(s, "line", None))
        elif isinstance(s, KeepMultiStmt):
            for e in s.exprs: self._expr(e)
            for n in s.names: self._declare(n)
        elif isinstance(s, AssignStmt):
            for e in s.exprs: self._expr(e)
            for n in s.names:
                if not self._scope.is_declared(n): self._declare(n)
                else: self._scope.mark_used(n)
        elif isinstance(s, ExprStmt):
            self._expr(s.expr)
        elif isinstance(s, ImportStmt):
            self._declare(s.alias)
            self._scope.mark_used(s.alias)
        elif isinstance(s, GetModuleStmt):
            for e in s.args: self._expr(e)
        elif isinstance(s, ShowStmt):
            for e in s.exprs: self._expr(e)
        elif isinstance(s, (PrecisionStmt, WaitStmt)):
            self._expr(s.expr)
        elif isinstance(s, SaveStmt):
            self._expr(s.value_expr); self._expr(s.filename_expr)
        elif isinstance(s, LoadStmt):
            self._expr(s.filename_expr); self._declare(s.var_name)
        elif isinstance(s, PutStmt):
            self._expr(s.item_expr); self._use(s.list_name)
        elif isinstance(s, ReturnStmt):
            self._expr(s.expr)
        elif isinstance(s, (StopStmt, BreakStmt, ContinueStmt)):
            pass
        elif isinstance(s, TryStmt):
            self._push(); self._stmts(s.try_body); self._flush_unused(self._pop())
            if s.catch_body is not None:
                self._push()
                if s.catch_name: self._scope.declare(s.catch_name, param=True); self._scope.mark_used(s.catch_name)
                self._stmts(s.catch_body); self._flush_unused(self._pop())
            if s.finally_body:
                self._push(); self._stmts(s.finally_body); self._flush_unused(self._pop())
        elif isinstance(s, SkillDef):
            self._declare(s.name); self._scope.mark_used(s.name)
            self._push(fn_name=s.name)
            for p in s.params: self._scope.declare(p, param=True); self._scope.mark_used(p)
            self._stmts(s.body); self._flush_unused(self._pop())
        elif isinstance(s, OnDef):
            self._declare(s.event); self._scope.mark_used(s.event)
            self._push(fn_name=f"on:{s.event}")
            for p in s.params: self._scope.declare(p, param=True); self._scope.mark_used(p)
            self._stmts(s.body); self._flush_unused(self._pop())
        elif isinstance(s, IfGroup):
            for cond, block in s.branches:
                self._expr(cond); self._push(); self._stmts(block); self._flush_unused(self._pop())
            if s.else_block:
                self._push(); self._stmts(s.else_block); self._flush_unused(self._pop())
        elif isinstance(s, LoopWhile):
            self._expr(s.cond); self._push(); self._stmts(s.body); self._flush_unused(self._pop())
        elif isinstance(s, LoopForRange):
            self._expr(s.start); self._expr(s.end)
            if s.step: self._expr(s.step)
            self._push(); self._scope.declare(s.var_name, loop_var=True); self._scope.mark_used(s.var_name)
            self._stmts(s.body); self._flush_unused(self._pop())
        elif isinstance(s, LoopForEach):
            self._expr(s.iterable)
            self._push()
            for name in s.var_names:
                self._scope.declare(name, loop_var=True)
                self._scope.mark_used(name)
            self._stmts(s.body); self._flush_unused(self._pop())
        elif isinstance(s, LoopForMap):
            self._expr(s.iterable)
            self._push()
            self._scope.declare(s.key_name, loop_var=True); self._scope.mark_used(s.key_name)
            self._scope.declare(s.value_name, loop_var=True); self._scope.mark_used(s.value_name)
            self._stmts(s.body); self._flush_unused(self._pop())
        elif isinstance(s, (RepeatUntil,)):
            self._push(); self._stmts(s.body); self._flush_unused(self._pop()); self._expr(s.cond)
        elif isinstance(s, LoopCount):
            self._expr(s.limit); self._push(); self._stmts(s.body); self._flush_unused(self._pop())
        elif isinstance(s, DoBlock):
            self._push(); self._stmts(s.body); self._flush_unused(self._pop())

    def run(self, program):
        for s in program.body:
            if isinstance(s, SkillDef):
                self._scope.declare(s.name); self._scope.mark_used(s.name)
            elif isinstance(s, OnDef):
                self._scope.declare(s.event); self._scope.mark_used(s.event)
        self._stmts(program.body)
        self._flush_unused(self._scope)
