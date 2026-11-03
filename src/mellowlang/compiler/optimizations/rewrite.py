"""The block rewriter that applies a dataflow environment."""

from __future__ import annotations

from typing import Any, Dict, List

from ...ir import IRInstruction

from .ir_data import _CONST_TOP, _StackValue


class BlockRewriteMixin:
    """The block rewriter that applies a dataflow environment."""

    def _rewrite_block(self, instructions: List[IRInstruction], env: Dict[str, Any]) -> tuple[List[IRInstruction], int, int, int, int]:
        out: List[IRInstruction] = []
        stack: List[_StackValue] = []
        cp_count = 0
        lvn_count = 0
        branch_count = 0
        jump_count = 0
        value_of_var: Dict[str, Any] = {k: self._const_expr(v) if v is not _CONST_TOP else None for k, v in env.items()}
        expr_to_var: Dict[Any, str] = {}
        for name, expr in value_of_var.items():
            if expr is not None:
                expr_to_var[expr] = name

        for ins in instructions:
            op = ins.op
            if op == "LABEL":
                out.append(ins)
                continue

            if op == "PUSH":
                out.append(ins)
                stack.append(_StackValue(const=ins.args[0], expr=self._const_expr(ins.args[0]), start=len(out) - 1))
                continue

            if op == "LOAD":
                var_name = str(ins.args[0])
                known = env.get(var_name, _CONST_TOP)
                if known is not _CONST_TOP:
                    out.append(IRInstruction("PUSH", (known,), line=ins.line, col=ins.col))
                    stack.append(_StackValue(const=known, expr=self._const_expr(known), start=len(out) - 1))
                    cp_count += 1
                else:
                    out.append(ins)
                    expr = value_of_var.get(var_name) or ("var", var_name)
                    stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=len(out) - 1))
                continue

            if op in self.BINARY_OPS:
                right = stack.pop() if stack else _StackValue()
                left = stack.pop() if stack else _StackValue()
                out.append(ins)
                start = min(v.start for v in (left, right) if v.start >= 0) if (left.start >= 0 or right.start >= 0) else len(out) - 1
                if left.const is not _CONST_TOP and right.const is not _CONST_TOP:
                    ok, value = self._eval_binary(left.const, right.const, ins)
                    if ok:
                        out[start:] = [IRInstruction("PUSH", (value,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=value, expr=self._const_expr(value), start=start))
                        cp_count += 1
                        continue
                expr = self._expr_for_binary(op, left.expr, right.expr, ins)
                existing_var = expr_to_var.get(expr)
                if existing_var and value_of_var.get(existing_var) == expr:
                    out[start:] = [IRInstruction("LOAD", (existing_var,), line=ins.line, col=ins.col)]
                    stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                    lvn_count += 1
                    continue
                stack.append(_StackValue(const=_CONST_TOP, expr=expr, start=start))
                continue

            if op in self.UNARY_OPS:
                value = stack.pop() if stack else _StackValue()
                out.append(ins)
                start = value.start if value.start >= 0 else len(out) - 1
                if value.const is not _CONST_TOP:
                    ok, result = self._eval_unary(value.const, ins)
                    if ok:
                        out[start:] = [IRInstruction("PUSH", (result,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=result, expr=self._const_expr(result), start=start))
                        cp_count += 1
                        continue
                stack.append(_StackValue(const=_CONST_TOP, expr=(op, value.expr), start=start))
                continue

            if op in self.STORE_OPS:
                value = stack.pop() if stack else _StackValue()
                out.append(ins)
                var_name = str(ins.args[0])
                env[var_name] = value.const
                value_of_var[var_name] = value.expr
                if value.expr is not None:
                    expr_to_var[value.expr] = var_name
                self._invalidate_var_aliases(expr_to_var, value_of_var, var_name)
                continue

            if op == "POP":
                if stack:
                    stack.pop()
                out.append(ins)
                continue

            if op == "JUMP_IF_FALSE":
                cond = stack.pop() if stack else _StackValue()
                if cond.const is not _CONST_TOP:
                    out[cond.start:] = []
                    if bool(cond.const):
                        branch_count += 1
                        continue
                    out.append(IRInstruction("JUMP", ins.args, line=ins.line, col=ins.col))
                    branch_count += 1
                    jump_count += 1
                    continue
                out.append(ins)
                continue

            if op == "JUMP":
                out.append(ins)
                continue

            if op == "CALL":
                argc = int(ins.args[1]) if len(ins.args) > 1 else 0
                for _ in range(argc):
                    if stack:
                        stack.pop()
                out.append(ins)
                stack.append(_StackValue(const=_CONST_TOP, expr=("call",) + tuple(ins.args), start=len(out) - 1))
                continue

            # SYSCALL keeps its name on the stack, then argc arguments.
            if op == "SYSCALL":
                argc = int(ins.args[0]) if ins.args else 0
                for _ in range(argc + 1):
                    if stack:
                        stack.pop()
                out.append(ins)
                stack.append(_StackValue(const=_CONST_TOP, expr=("syscall",) + tuple(ins.args), start=len(out) - 1))
                continue

            if op == "LEN":
                value = stack.pop() if stack else _StackValue()
                out.append(ins)
                start = value.start if value.start >= 0 else len(out) - 1
                if value.const is not _CONST_TOP:
                    try:
                        result = len(value.const)
                        out[start:] = [IRInstruction("PUSH", (result,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=result, expr=self._const_expr(result), start=start))
                        cp_count += 1
                        continue
                    except Exception:
                        pass
                stack.append(_StackValue(const=_CONST_TOP, expr=("len", value.expr), start=start))
                continue

            if op == "GETITEM":
                idx = stack.pop() if stack else _StackValue()
                obj = stack.pop() if stack else _StackValue()
                out.append(ins)
                starts = [v.start for v in (obj, idx) if v.start >= 0]
                start = min(starts) if starts else len(out) - 1
                if obj.const is not _CONST_TOP and idx.const is not _CONST_TOP:
                    try:
                        result = obj.const[idx.const]
                        out[start:] = [IRInstruction("PUSH", (result,), line=ins.line, col=ins.col)]
                        stack.append(_StackValue(const=result, expr=self._const_expr(result), start=start))
                        cp_count += 1
                        continue
                    except Exception:
                        pass
                stack.append(_StackValue(const=_CONST_TOP, expr=("getitem", obj.expr, idx.expr), start=start))
                continue

            if op == "LOAD_F":
                out.append(ins)
                var_name = str(ins.args[0])
                env[var_name] = _CONST_TOP
                value_of_var[var_name] = None
                self._invalidate_var_aliases(expr_to_var, value_of_var, var_name)
                continue

            # Any op this pass does not model may leave a value of its own on
            # the stack, so nothing above STORE may be treated as a constant.
            out.append(ins)
            stack.clear()
        return out, cp_count, lvn_count, branch_count, jump_count

    def _kill_exprs_touching_var(self, exprs: Dict[Any, str], var_name: str) -> None:
        stale = [expr for expr in exprs if var_name in self._vars_in_expr(expr) or expr == ("var", var_name)]
        for expr in stale:
            exprs.pop(expr, None)

    def _invalidate_var_aliases(self, expr_to_var: Dict[Any, str], value_of_var: Dict[str, Any], var_name: str) -> None:
        stale = [expr for expr, name in expr_to_var.items() if name == var_name and value_of_var.get(var_name) != expr]
        for expr in stale:
            expr_to_var.pop(expr, None)
        expr = value_of_var.get(var_name)
        if expr is not None:
            expr_to_var[expr] = var_name
