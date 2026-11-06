"""Arithmetic, comparison and the boolean operators."""

from __future__ import annotations

from ...constants import Op
from .actions import _STEP


class MathMixin:
    def _exec_arithmetic(self, op, instr) -> object:
        """ADD, SUB, MUL, DIV."""
        if op == Op.ADD:
            b = self.stack.pop(); a = self.stack.pop()
            if isinstance(a, str) or isinstance(b, str):
                out = self.format_value(a) + self.format_value(b)
                self._enforce_value_limits(out)
                self.stack.append(out)
            else:
                self.stack.append(a + b)
            return _STEP
        if op == Op.SUB:
            b = self.stack.pop(); a = self.stack.pop()
            self.stack.append(a - b)
            return _STEP
        if op == Op.MUL:
            b = self.stack.pop(); a = self.stack.pop()
            self.stack.append(a * b)
            return _STEP
        if op == Op.DIV:
            b = self.stack.pop(); a = self.stack.pop()
            # raise on division by zero (catchable by try/catch)
            if b == 0:
                raise ZeroDivisionError('division by zero')
            self.stack.append(a / b)
            return _STEP
        raise AssertionError("_exec_arithmetic received " + repr(op))

    def _exec_comparisons(self, op, instr) -> object:
        """COMPARE and the boolean operators."""
        if op == Op.COMPARE:
            cmp_op = instr[1] if len(instr) > 1 else '=='
            b = self.stack.pop(); a = self.stack.pop()
            num_ok = True
            try:
                af = float(a); bf = float(b)
            except:
                num_ok = False
            if num_ok:
                if cmp_op == '==': res = (af == bf)
                elif cmp_op == '!=': res = (af != bf)
                elif cmp_op == '>': res = (af > bf)
                elif cmp_op == '<': res = (af < bf)
                elif cmp_op == '>=': res = (af >= bf)
                elif cmp_op == '<=': res = (af <= bf)
                else: res = False
            else:
                if cmp_op == '==': res = (a == b)
                elif cmp_op == '!=': res = (a != b)
                else: res = False
            self.stack.append(res)
            return _STEP
        if op == Op.BOOL_AND:
            b = self.stack.pop(); a = self.stack.pop()
            self.stack.append(self._truthy(a) and self._truthy(b))
            return _STEP
        if op == Op.BOOL_OR:
            b = self.stack.pop(); a = self.stack.pop()
            self.stack.append(self._truthy(a) or self._truthy(b))
            return _STEP
        if op == Op.BOOL_NOT:
            a = self.stack.pop()
            self.stack.append(not self._truthy(a))
            return _STEP
        raise AssertionError("_exec_comparisons received " + repr(op))

    def _exec_mod_pow(self, op, instr) -> object:
        """MOD and POW_OP."""
        if op == Op.MOD:
            b = self.stack.pop(); a = self.stack.pop()
            try:
                self.stack.append(int(a) % int(b) if isinstance(a, int) and isinstance(b, int) else float(a) % float(b))
            except Exception:
                self.stack.append(None)
            return _STEP
        if op == Op.POW_OP:
            b = self.stack.pop(); a = self.stack.pop()
            try:
                result = float(a) ** float(b)
                self.stack.append(int(result) if result == int(result) else result)
            except Exception:
                self.stack.append(None)
            return _STEP
        raise AssertionError("_exec_mod_pow received " + repr(op))
