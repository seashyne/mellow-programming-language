"""Frame control: try frames, jumps and skill returns."""

from __future__ import annotations

from ...constants import Op
from .actions import _HALT, _NEXT, _STEP


class ControlMixin:
    def _exec_try_frames(self, op, instr) -> object:
        """HALT/STOP, the try frames and the finally bookkeeping."""
        if op in (Op.HALT, Op.STOP):
            self._halted = True
            return _HALT
        if op == Op.TRY:
            catch_pc = int(instr[1])
            finally_pc = int(instr[2])
            err_name = instr[3] if len(instr) > 3 else None
            self._try_stack.append({
                'catch_pc': catch_pc,
                'finally_pc': finally_pc,
                'err_name': err_name,
                'stack_len': len(self.stack),
            })
            return _STEP
        if op == Op.ENDTRY:
            if self._try_stack:
                self._try_stack.pop()
            return _STEP
        raise AssertionError("_exec_try_frames received " + repr(op))

    def _exec_jumps(self, op, instr) -> object:
        """JUMP and JIF."""
        if op == Op.JUMP:
            self.pc = instr[1]
            return _NEXT
        if op == Op.JIF:
            cond = self.stack.pop() if self.stack else False
            if not self._truthy(cond):
                self.pc = instr[1]
                return _NEXT
            return _STEP
        raise AssertionError("_exec_jumps received " + repr(op))

    def _exec_skill_return(self, op, instr) -> object:
        """RETURN and ARG."""
        if op == Op.RETURN:
            res = self.stack.pop() if self.stack else None
            if self.variables:
                self.variables.pop()
            self.pc = self.call_stack.pop() if self.call_stack else len(self.bytecode)
            if self.frame_stack:
                self.frame_stack.pop()
            self.stack.append(res)
            return _NEXT
        if op == Op.ARG:
            self.variables[-1][instr[1]] = self.stack.pop() if self.stack else None
            return _STEP
        raise AssertionError("_exec_skill_return received " + repr(op))
