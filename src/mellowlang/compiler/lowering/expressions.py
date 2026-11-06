"""One expression node in, one run of IR instructions out."""

from __future__ import annotations

from ...ast import (
    BinaryOp,
    Call,
    Expr,
    FStringExpr,
    GetModuleExpr,
    Index,
    ListLiteral,
    Literal,
    MapLiteral,
    SpreadExpr,
    UnaryOp,
    Var,
)

from .errors import UnsupportedLoweringError
from .syscalls import _bind_call_arguments, _module_syscall
from .tables import STDLIB_CALLS


class ExpressionMixin:
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
                call_args = (_bind_call_arguments(syscall_name, expr.args, expr.kwargs)
                             if expr.kwargs else list(expr.args))
                self.emit("PUSH", syscall_name, line=line, col=col)
                for arg in call_args:
                    self._expr(arg)
                self.emit("SYSCALL", len(call_args), line=line, col=col)
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
