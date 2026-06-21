from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..ast import (
    AssignStmt,
    BinaryOp,
    BreakStmt,
    Call,
    ContinueStmt,
    DoBlock,
    Expr,
    ExprStmt,
    FStringExpr,
    GetModuleExpr,
    GetModuleStmt,
    IfGroup,
    Index,
    KeepMultiStmt,
    KeepStmt,
    ListLiteral,
    Literal,
    LoadStmt,
    LoopCount,
    LoopForEach,
    LoopForRange,
    LoopWhile,
    MapLiteral,
    OnDef,
    PrecisionStmt,
    Program,
    PutStmt,
    ReturnStmt,
    SaveStmt,
    ShowStmt,
    SkillDef,
    SkillDefV2,
    SpreadExpr,
    StopStmt,
    Stmt,
    UnaryOp,
    Var,
    WaitStmt,
)
from ..ir import IRFunction, IRInstruction, IRProgram
from ..host.runtime import MODULE_ALLOWLIST


STDLIB_CALLS = {
    "len": "std.len",
    "money": "std.money.of",
    "money.of": "std.money.of",
    "money_of": "std.money.of",
    "money.add": "std.money.add",
    "money_add": "std.money.add",
    "money.sub": "std.money.sub",
    "money_sub": "std.money.sub",
    "money.mul": "std.money.mul",
    "money_mul": "std.money.mul",
    "money.div": "std.money.div",
    "money_div": "std.money.div",
    "money.quantize": "std.money.quantize",
    "money_quantize": "std.money.quantize",
    "money.format": "std.money.format",
    "money_format": "std.money.format",
    "money.amount": "std.money.amount",
    "money_amount": "std.money.amount",
    "money.currency": "std.money.currency",
    "money_currency": "std.money.currency",
    "money.eq": "std.money.eq",
    "money_eq": "std.money.eq",
    "money.lt": "std.money.lt",
    "money_lt": "std.money.lt",
    "money.gt": "std.money.gt",
    "money_gt": "std.money.gt",
    "data.open_jsonl": "std.data.open_jsonl",
    "data_open_jsonl": "std.data.open_jsonl",
    "data.open_csv": "std.data.open_csv",
    "data_open_csv": "std.data.open_csv",
    "data.next": "std.data.next",
    "data_next": "std.data.next",
    "data.close": "std.data.close",
    "data_close": "std.data.close",
    "data.cancel": "std.data.cancel",
    "data_cancel": "std.data.cancel",
    "data.info": "std.data.info",
    "data_info": "std.data.info",
    "data.project": "std.data.project",
    "data_project": "std.data.project",
    "data.where": "std.data.where",
    "data_where": "std.data.where",
    "data.sum": "std.data.sum",
    "data_sum": "std.data.sum",
    "data.sqlite_open": "std.data.sqlite_open",
    "data_sqlite_open": "std.data.sqlite_open",
    "data.sqlite_close": "std.data.sqlite_close",
    "data_sqlite_close": "std.data.sqlite_close",
    "data.sqlite_query": "std.data.sqlite_query",
    "data_sqlite_query": "std.data.sqlite_query",
    "data.sqlite_execute": "std.data.sqlite_execute",
    "data_sqlite_execute": "std.data.sqlite_execute",
    "ledger.create": "std.ledger.create",
    "ledger_create": "std.ledger.create",
    "ledger.post": "std.ledger.post",
    "ledger_post": "std.ledger.post",
    "ledger.verify": "std.ledger.verify",
    "ledger_verify": "std.ledger.verify",
    "ledger.balance": "std.ledger.balance",
    "ledger_balance": "std.ledger.balance",
    "ledger.entries": "std.ledger.entries",
    "ledger_entries": "std.ledger.entries",
}


class UnsupportedLoweringError(RuntimeError):
    pass


def _module_syscall(module: str, function: str) -> str:
    mod = str(module).lower()
    func = str(function).lower()
    if mod in MODULE_ALLOWLIST and func in MODULE_ALLOWLIST[mod]:
        return MODULE_ALLOWLIST[mod][func]
    return f"std.{mod}.{func}"


@dataclass
class _LoopCtx:
    break_label: str
    continue_label: str


class IRLowerer:
    def __init__(self, filename: str | None = None):
        self.filename = filename
        self.instructions: List[IRInstruction] = []
        self.functions: Dict[str, IRFunction] = {}
        self.events: Dict[str, IRFunction] = {}
        self._label_id = 0
        self._temp_id = 0
        self._loop_stack: List[_LoopCtx] = []

    def lower(self, program: Program) -> IRProgram:
        for stmt in program.body:
            self._stmt(stmt)
        self.emit("HALT")
        return IRProgram(
            instructions=self.instructions,
            functions=self.functions,
            events=self.events,
            filename=self.filename,
        )

    def emit(self, op: str, *args: Any, line: int = 0, col: int = 1):
        self.instructions.append(IRInstruction(op=op, args=tuple(args), line=int(line or 0), col=int(col or 1)))

    def pos(self, node: Any) -> tuple[int, int]:
        return int(getattr(node, "_line", 0) or 0), int(getattr(node, "_col", 1) or 1)

    def new_label(self, prefix: str) -> str:
        self._label_id += 1
        return f"{prefix}_{self._label_id}"

    def new_temp(self, prefix: str = "__tmp") -> str:
        self._temp_id += 1
        return f"{prefix}_{self._temp_id}"

    def _stmt(self, stmt: Stmt):
        line, col = self.pos(stmt)
        if isinstance(stmt, KeepStmt):
            self._expr(stmt.expr)
            self.emit("STORE_KEEP", stmt.name, line=line, col=col)
        elif isinstance(stmt, KeepMultiStmt):
            for expr in stmt.exprs:
                self._expr(expr)
            for name in reversed(stmt.names):
                self.emit("STORE_KEEP", name, line=line, col=col)
        elif isinstance(stmt, AssignStmt):
            for expr in stmt.exprs:
                self._expr(expr)
            for name in reversed(stmt.names):
                self.emit("STORE_AUTO", name, line=line, col=col)
        elif isinstance(stmt, ExprStmt):
            self._expr(stmt.expr)
            self.emit("POP", line=line, col=col)
        elif isinstance(stmt, ShowStmt):
            for expr in stmt.exprs:
                self._expr(expr)
            self.emit("PRINTN" if len(stmt.exprs) > 1 else "PRINT", len(stmt.exprs), line=line, col=col)
        elif isinstance(stmt, PrecisionStmt):
            self._expr(stmt.expr)
            self.emit("SHOW_PREC", line=line, col=col)
        elif isinstance(stmt, StopStmt):
            self.emit("STOP", line=line, col=col)
        elif isinstance(stmt, WaitStmt):
            self._expr(stmt.expr)
            self.emit("WAIT", line=line, col=col)
        elif isinstance(stmt, SaveStmt):
            self._expr(stmt.filename_expr)
            self._expr(stmt.value_expr)
            self.emit("SAVE_VAL", line=line, col=col)
        elif isinstance(stmt, LoadStmt):
            self._expr(stmt.filename_expr)
            self.emit("LOAD_F", stmt.var_name, line=line, col=col)
        elif isinstance(stmt, PutStmt):
            self._expr(stmt.item_expr)
            self.emit("LOAD", stmt.list_name, line=line, col=col)
            self.emit("LIST_PUT", line=line, col=col)
        elif isinstance(stmt, ReturnStmt):
            if stmt.expr is None:
                self.emit("PUSH", None, line=line, col=col)
            else:
                self._expr(stmt.expr)
            self.emit("RETURN", line=line, col=col)
        elif isinstance(stmt, IfGroup):
            end_label = self.new_label("if_end")
            for idx, (cond, body) in enumerate(stmt.branches):
                next_label = self.new_label(f"if_next_{idx}")
                self._expr(cond)
                self.emit("JUMP_IF_FALSE", next_label, line=line, col=col)
                for s in body:
                    self._stmt(s)
                self.emit("JUMP", end_label, line=line, col=col)
                self.emit("LABEL", next_label, line=line, col=col)
            if stmt.else_block:
                for s in stmt.else_block:
                    self._stmt(s)
            self.emit("LABEL", end_label, line=line, col=col)
        elif isinstance(stmt, LoopWhile):
            start = self.new_label("while_start")
            end = self.new_label("while_end")
            self.emit("LABEL", start, line=line, col=col)
            self._expr(stmt.cond)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=start))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("JUMP", start, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, LoopCount):
            counter = self.new_temp("count")
            start = self.new_label("count_start")
            end = self.new_label("count_end")
            self.emit("PUSH", 0, line=line, col=col)
            self.emit("STORE", counter, line=line, col=col)
            self.emit("LABEL", start, line=line, col=col)
            self.emit("LOAD", counter, line=line, col=col)
            self._expr(stmt.limit)
            self.emit("COMPARE", "<", line=line, col=col)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=start))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("LOAD", counter, line=line, col=col)
            self.emit("PUSH", 1, line=line, col=col)
            self.emit("ADD", line=line, col=col)
            self.emit("STORE", counter, line=line, col=col)
            self.emit("JUMP", start, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, LoopForRange):
            start_tmp = self.new_temp("range_start")
            end_tmp = self.new_temp("range_end")
            step_tmp = self.new_temp("range_step")
            loop = self.new_label("for_range")
            end = self.new_label("for_range_end")
            self._expr(stmt.start)
            self.emit("STORE", start_tmp, line=line, col=col)
            self._expr(stmt.end)
            self.emit("STORE", end_tmp, line=line, col=col)
            if stmt.step is None:
                self.emit("PUSH", 1, line=line, col=col)
            else:
                self._expr(stmt.step)
            self.emit("STORE", step_tmp, line=line, col=col)
            self.emit("LOAD", start_tmp, line=line, col=col)
            self.emit("STORE", stmt.var_name, line=line, col=col)
            self.emit("LABEL", loop, line=line, col=col)
            self.emit("LOAD", stmt.var_name, line=line, col=col)
            self.emit("LOAD", end_tmp, line=line, col=col)
            self.emit("COMPARE", "<", line=line, col=col)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=loop))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("LOAD", stmt.var_name, line=line, col=col)
            self.emit("LOAD", step_tmp, line=line, col=col)
            self.emit("ADD", line=line, col=col)
            self.emit("STORE", stmt.var_name, line=line, col=col)
            self.emit("JUMP", loop, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, LoopForEach):
            items_tmp = self.new_temp("foreach_items")
            len_tmp = self.new_temp("foreach_len")
            idx_tmp = self.new_temp("foreach_idx")
            loop = self.new_label("foreach")
            end = self.new_label("foreach_end")
            self._expr(stmt.iterable)
            self.emit("STORE", items_tmp, line=line, col=col)
            self.emit("LOAD", items_tmp, line=line, col=col)
            self.emit("LEN", line=line, col=col)
            self.emit("STORE", len_tmp, line=line, col=col)
            self.emit("PUSH", 0, line=line, col=col)
            self.emit("STORE", idx_tmp, line=line, col=col)
            self.emit("LABEL", loop, line=line, col=col)
            self.emit("LOAD", idx_tmp, line=line, col=col)
            self.emit("LOAD", len_tmp, line=line, col=col)
            self.emit("COMPARE", "<", line=line, col=col)
            self.emit("JUMP_IF_FALSE", end, line=line, col=col)
            self.emit("LOAD", items_tmp, line=line, col=col)
            self.emit("LOAD", idx_tmp, line=line, col=col)
            self.emit("GETITEM", line=line, col=col)
            if len(stmt.var_names) == 1:
                self.emit("STORE", stmt.var_names[0], line=line, col=col)
            else:
                raise UnsupportedLoweringError("foreach unpacking is not yet supported in IR pipeline")
            self._loop_stack.append(_LoopCtx(break_label=end, continue_label=loop))
            for s in stmt.body:
                self._stmt(s)
            self._loop_stack.pop()
            self.emit("LOAD", idx_tmp, line=line, col=col)
            self.emit("PUSH", 1, line=line, col=col)
            self.emit("ADD", line=line, col=col)
            self.emit("STORE", idx_tmp, line=line, col=col)
            self.emit("JUMP", loop, line=line, col=col)
            self.emit("LABEL", end, line=line, col=col)
        elif isinstance(stmt, DoBlock):
            for s in stmt.body:
                self._stmt(s)
        elif isinstance(stmt, BreakStmt):
            if not self._loop_stack:
                raise UnsupportedLoweringError("break used outside loop")
            self.emit("JUMP", self._loop_stack[-1].break_label, line=line, col=col)
        elif isinstance(stmt, ContinueStmt):
            if not self._loop_stack:
                raise UnsupportedLoweringError("continue used outside loop")
            self.emit("JUMP", self._loop_stack[-1].continue_label, line=line, col=col)
        elif isinstance(stmt, SkillDef):
            skip = self.new_label(f"after_skill_{stmt.name}")
            entry = self.new_label(f"skill_{stmt.name}")
            self.emit("JUMP", skip, line=line, col=col)
            self.emit("LABEL", entry, line=line, col=col)
            for param in stmt.params:
                self.emit("ARG", param, line=line, col=col)
            for s in stmt.body:
                self._stmt(s)
            self.emit("PUSH", None, line=line, col=col)
            self.emit("RETURN", line=line, col=col)
            self.emit("LABEL", skip, line=line, col=col)
            self.functions[stmt.name] = IRFunction(name=stmt.name, entry_label=entry, params=list(stmt.params), kind="skill")
        elif isinstance(stmt, SkillDefV2):
            raise UnsupportedLoweringError("SkillDefV2/default args are not yet lowered in IR pipeline")
        elif isinstance(stmt, OnDef):
            skip = self.new_label(f"after_on_{stmt.event}")
            entry = self.new_label(f"on_{stmt.event}")
            self.emit("JUMP", skip, line=line, col=col)
            self.emit("LABEL", entry, line=line, col=col)
            for param in stmt.params:
                self.emit("ARG", param, line=line, col=col)
            for s in stmt.body:
                self._stmt(s)
            self.emit("PUSH", None, line=line, col=col)
            self.emit("RETURN", line=line, col=col)
            self.emit("LABEL", skip, line=line, col=col)
            self.events[stmt.event] = IRFunction(name=stmt.event, entry_label=entry, params=list(stmt.params), kind="event")
        elif isinstance(stmt, GetModuleStmt):
            self.emit("PUSH", _module_syscall(stmt.module, stmt.function), line=line, col=col)
            for arg in stmt.args:
                self._expr(arg)
            self.emit("SYSCALL", len(stmt.args), line=line, col=col)
            if stmt.var_name:
                self.emit("STORE_AUTO", stmt.var_name, line=line, col=col)
            else:
                self.emit("POP", line=line, col=col)
        else:
            raise UnsupportedLoweringError(f"AST node not supported by IR pipeline: {type(stmt).__name__}")

    def _expr(self, expr: Expr):
        line, col = self.pos(expr)
        if isinstance(expr, Literal):
            self.emit("PUSH", expr.value, line=line, col=col)
        elif isinstance(expr, Var):
            self.emit("LOAD", expr.name, line=line, col=col)
        elif isinstance(expr, UnaryOp):
            self._expr(expr.expr)
            if expr.op == "not":
                self.emit("BOOL_NOT", line=line, col=col)
            elif expr.op == "-":
                self.emit("PUSH", -1, line=line, col=col)
                self.emit("MUL", line=line, col=col)
            else:
                raise UnsupportedLoweringError(f"unsupported unary operator: {expr.op}")
        elif isinstance(expr, BinaryOp):
            self._expr(expr.left)
            self._expr(expr.right)
            op_map = {
                "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD", "**": "POW_OP",
                "and": "BOOL_AND", "or": "BOOL_OR",
                "==": ("COMPARE", "=="), "!=": ("COMPARE", "!="), ">": ("COMPARE", ">"),
                "<": ("COMPARE", "<"), ">=": ("COMPARE", ">="), "<=": ("COMPARE", "<="),
            }
            chosen = op_map.get(expr.op)
            if chosen is None:
                raise UnsupportedLoweringError(f"unsupported binary operator: {expr.op}")
            if isinstance(chosen, tuple):
                self.emit(chosen[0], chosen[1], line=line, col=col)
            else:
                self.emit(chosen, line=line, col=col)
        elif isinstance(expr, Call):
            syscall_name = STDLIB_CALLS.get(str(expr.name).lower())
            if syscall_name:
                if expr.kwargs:
                    raise UnsupportedLoweringError("named arguments are not yet lowered in IR pipeline")
                self.emit("PUSH", syscall_name, line=line, col=col)
                for arg in expr.args:
                    self._expr(arg)
                self.emit("SYSCALL", len(expr.args), line=line, col=col)
                return
            for arg in expr.args:
                self._expr(arg)
            if expr.kwargs:
                raise UnsupportedLoweringError("named arguments are not yet lowered in IR pipeline")
            self.emit("CALL", expr.name, len(expr.args), line=line, col=col)
        elif isinstance(expr, GetModuleExpr):
            self.emit("PUSH", _module_syscall(expr.module, expr.function), line=line, col=col)
            for arg in expr.args:
                self._expr(arg)
            self.emit("SYSCALL", len(expr.args), line=line, col=col)
        elif isinstance(expr, Index):
            self._expr(expr.target)
            self._expr(expr.index)
            self.emit("GETITEM", line=line, col=col)
        elif isinstance(expr, ListLiteral):
            for item in expr.items:
                if isinstance(item, SpreadExpr):
                    raise UnsupportedLoweringError("spread in list literals is not yet lowered in IR pipeline")
                self._expr(item)
            self.emit("BUILD_LIST", len(expr.items), line=line, col=col)
        elif isinstance(expr, MapLiteral):
            for k, v in expr.pairs:
                self._expr(k)
                self._expr(v)
            self.emit("BUILD_MAP", len(expr.pairs), line=line, col=col)
        elif isinstance(expr, FStringExpr):
            parts: list[Expr] = []
            for kind, value in expr.parts:
                if kind == "literal":
                    parts.append(Literal(value))
                elif kind == "expr":
                    parts.append(value)
                else:
                    raise UnsupportedLoweringError("unknown f-string part")
            if not parts:
                self.emit("PUSH", "", line=line, col=col)
                return
            self._expr(parts[0])
            for part in parts[1:]:
                self._expr(part)
                self.emit("ADD", line=line, col=col)
        else:
            raise UnsupportedLoweringError(f"Expr node not supported by IR pipeline: {type(expr).__name__}")
