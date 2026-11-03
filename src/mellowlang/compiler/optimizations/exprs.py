"""Shared expression evaluation and value-number predicates."""

from __future__ import annotations

from typing import Any, Dict, Set

from ...ir import IRInstruction

from .ir_data import DominatorTree


class ExpressionMixin:
    """Shared expression evaluation and value-number predicates."""

    def _expr_safe_to_reuse(self, expr: Any, write_blocks_by_var: Dict[str, Set[str]], dom: DominatorTree, current_label: str) -> bool:
        touched = self._vars_in_expr(expr)
        for var in touched:
            if current_label in write_blocks_by_var.get(var, set()):
                return False
            for block in write_blocks_by_var.get(var, set()):
                if block != current_label and current_label in dom.natural_loops and block in dom.natural_loops.get(current_label, []):
                    return False
        return True

    def _vars_in_expr(self, expr: Any) -> Set[str]:
        out: Set[str] = set()
        if isinstance(expr, tuple):
            if len(expr) >= 2 and expr[0] == "var":
                out.add(str(expr[1]))
            for item in expr[1:]:
                out.update(self._vars_in_expr(item))
        return out

    def _const_expr(self, value: Any) -> tuple[str, Any]:
        return ("const", value)

    def _expr_for_binary(self, op: str, left: Any, right: Any, ins: IRInstruction) -> Any:
        if op == "COMPARE":
            return (op, str(ins.args[0]), left, right)
        if op in {"ADD", "MUL", "BOOL_AND", "BOOL_OR"}:
            a, b = (left, right) if repr(left) <= repr(right) else (right, left)
            return (op, a, b)
        return (op, left, right)

    def _eval_binary(self, left: Any, right: Any, ins: IRInstruction) -> tuple[bool, Any]:
        try:
            if ins.op == "ADD":
                return True, left + right
            if ins.op == "SUB":
                return True, left - right
            if ins.op == "MUL":
                return True, left * right
            if ins.op == "DIV":
                return (False, None) if right == 0 else (True, left / right)
            if ins.op == "MOD":
                return (False, None) if right == 0 else (True, left % right)
            if ins.op == "POW_OP":
                return True, left ** right
            if ins.op == "BOOL_AND":
                return True, bool(left) and bool(right)
            if ins.op == "BOOL_OR":
                return True, bool(left) or bool(right)
            if ins.op == "COMPARE":
                op = str(ins.args[0])
                table = {
                    "==": left == right,
                    "!=": left != right,
                    "<": left < right,
                    "<=": left <= right,
                    ">": left > right,
                    ">=": left >= right,
                }
                if op in table:
                    return True, table[op]
        except Exception:
            return False, None
        return False, None

    def _eval_unary(self, value: Any, ins: IRInstruction) -> tuple[bool, Any]:
        try:
            if ins.op == "BOOL_NOT":
                return True, not bool(value)
        except Exception:
            return False, None
        return False, None
