"""mellowlang/lint.py (v1.4.7)

Linter ฉลาดขึ้น — วิเคราะห์ AST จริง:
  - ตัวแปรที่ประกาศแต่ไม่ได้ใช้ (UNUSED)
  - ตัวแปรที่ใช้โดยไม่ประกาศ (UNDEFINED)
  - Shadow ตัวแปรใน scope ซ้อน (SHADOW)
  - Style: tabs, trailing spaces
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from .parser import parse_program, ParseError
from .ast import (
    Program, Stmt, Expr,
    KeepStmt, KeepMultiStmt, AssignStmt, ExprStmt,
    ShowStmt, PrecisionStmt, StopStmt, WaitStmt,
    SaveStmt, LoadStmt, PutStmt, ReturnStmt,
    BreakStmt, ContinueStmt, TryStmt,
    SkillDef, OnDef,
    IfGroup, LoopWhile, LoopForEach, LoopForMap,
    LoopForRange, RepeatUntil, LoopCount, DoBlock,
    Var, Call, BinaryOp, UnaryOp, Literal,
    Index, ListLiteral, MapLiteral, FStringExpr,
)


@dataclass
class LintIssue:
    kind: str
    message: str
    line: Optional[int] = None
    col: Optional[int] = None


_BUILTINS: Set[str] = {
    "print","show","input","ask","len","range","wait","stop","precision",
    "call","get","lib","true","false","none","null",
    "abs","min","max","floor","ceil","round","sqrt","pow","sin","cos","tan",
    "atan2","clamp","lerp","pi","log","sign","deg_to_rad","rad_to_deg",
    "distance","angle_between","fmod",
    "random","randi","rand","rand_int","rand_float","random_int","random_float",
    "global_seed","seed",
    "is_number","is_string","is_bool","is_list","is_map","is_none","type_of",
    "assert","assert_eq","assert_ne",
    "vec","vec2","vec3","vector",
    "vec_add","vec_sub","vec_mul","vec_dot","vec_len","vec_norm",
    "vec_dist","vec_lerp","vec_limit","vec_dim","vec_axis","vec_with",
    "list_push","list_pop","list_insert","list_remove","list_has","list_sort","list_len",
    "list_map","list_filter","list_find","list_slice","list_reverse","list_reduce","list_count",
    "map_get","map_set","map_keys","map_values","map_has",
    "str_len","str_lower","str_upper","str_trim","str_replace",
    "str_find","str_split","str_join","str_format",
    "string_len","string_lower","string_upper",
    "str_starts_with","str_ends_with","str_pad_left","str_pad_right","str_repeat","str_contains",
    "json_encode","json_decode",
    "save_data","load_data","mkdir",
    "file_read","file_write","file_append","file_exists","file_delete",
    "save_init","save_set","save_get","save_commit","save_load",
    "save_list","save_delete","save_clear",
    "save_commit_signed","save_load_signed",
    "net_http_get","net_http_post",
    "net_ws_connect","net_ws_send","net_ws_recv","net_ws_close","net_ws_state",
    "astar","neighbors4","neighbors8","tween",
    "ease_linear","ease_in_quad","ease_out_quad","ease_in_out_quad",
    "ease_in_cubic","ease_out_cubic","ease_in_out_cubic",
    "ease_in_back","ease_out_back","ease_out_bounce","ease_out_elastic",
    "ai_seek","ai_flee","ai_arrive","ai_wander","ai_patrol",
    "ai_in_range","ai_in_sight","ai_nearest","ai_filter_range",
    "ai_decide","ai_utility","ai_bt","ai_fsm",
    "time_now","time_unix","time_ms",
    "emit",
}


@dataclass
class _VarInfo:
    line: Optional[int]
    used: bool = False
    param: bool = False
    loop_var: bool = False


class _Scope:
    def __init__(self, parent=None, fn_name=None):
        self.parent = parent
        self.fn_name = fn_name
        self.vars: Dict[str, _VarInfo] = {}

    def declare(self, name, line=None, param=False, loop_var=False):
        self.vars[name] = _VarInfo(line=line, param=param, loop_var=loop_var)

    def mark_used(self, name):
        if name in self.vars:
            self.vars[name].used = True
            return True
        if self.parent:
            return self.parent.mark_used(name)
        return False

    def is_declared(self, name):
        if name in self.vars: return True
        if self.parent: return self.parent.is_declared(name)
        return False

    def unused(self):
        return [
            (n, i) for n, i in self.vars.items()
            if not i.used and not i.param and not i.loop_var
            and not n.startswith("_")
        ]


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
            self._push(); self._scope.declare(s.var_name, loop_var=True); self._scope.mark_used(s.var_name)
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


def lint_source(src: str) -> List[LintIssue]:
    issues: List[LintIssue] = []
    lines = src.splitlines()
    try:
        program = parse_program(lines)
    except ParseError as e:
        issues.append(LintIssue("SYNTAX", str(e)))
        return issues

    for i, ln in enumerate(lines, start=1):
        if "\t" in ln:
            issues.append(LintIssue("STYLE", "tab character found; use spaces", i))
        if ln.rstrip("\n") != ln.rstrip("\n").rstrip(" "):
            issues.append(LintIssue("STYLE", "trailing spaces", i))

    try:
        linter = _Linter()
        linter.run(program)
        issues.extend(linter.issues)
    except Exception:
        pass

    issues.sort(key=lambda x: (x.line or 0, x.kind))
    return issues


def format_source(src: str) -> str:
    out_lines: List[str] = []
    blank_run = 0
    for ln in src.splitlines():
        ln = ln.replace("\t", "    ").rstrip()
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out_lines.append("")
            continue
        blank_run = 0
        out_lines.append(ln)
    return "\n".join(out_lines) + ("\n" if src.endswith("\n") else "")
