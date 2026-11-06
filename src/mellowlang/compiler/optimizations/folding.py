"""Front-end constant folding over straight-line arithmetic."""

from __future__ import annotations

from typing import List

from ...ir import IRInstruction


class ConstantFoldingMixin:
    """Front-end constant folding over straight-line arithmetic."""

    def _constant_fold(self, instructions: List[IRInstruction]) -> tuple[List[IRInstruction], int]:
        out: List[IRInstruction] = []
        count = 0
        i = 0
        while i < len(instructions):
            if i + 2 < len(instructions):
                a, b, c = instructions[i], instructions[i + 1], instructions[i + 2]
                if a.op == "PUSH" and b.op == "PUSH" and c.op in self.BINARY_OPS:
                    ok, value = self._eval_binary(a.args[0], b.args[0], c)
                    if ok:
                        out.append(IRInstruction("PUSH", (value,), line=c.line, col=c.col))
                        count += 1
                        i += 3
                        continue
                if a.op == "PUSH" and b.op in self.UNARY_OPS:
                    ok, value = self._eval_unary(a.args[0], b)
                    if ok:
                        out.append(IRInstruction("PUSH", (value,), line=b.line, col=b.col))
                        count += 1
                        i += 2
                        continue
            out.append(instructions[i])
            i += 1
        return out, count
