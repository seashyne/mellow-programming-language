"""The lowering machine: instruction list, label and temp counters, loop stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ...ast import Program
from ...ir import IRFunction, IRInstruction, IRProgram


@dataclass
class _LoopCtx:
    break_label: str
    continue_label: str


class LoweringDriverMixin:
    def __init__(self, filename: str | None = None):
        self.filename = filename
        self.instructions: List[IRInstruction] = []
        self.functions: Dict[str, IRFunction] = {}
        self.events: Dict[str, IRFunction] = {}
        self._label_id = 0
        self._temp_id = 0
        self._loop_stack: List[_LoopCtx] = []
        self._current_position = (0, 1)

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
        line = int(getattr(node, "_line", 0) or 0)
        col = int(getattr(node, "_col", 1) or 1)
        return (line, col) if line > 0 else self._current_position

    def new_label(self, prefix: str) -> str:
        self._label_id += 1
        return f"{prefix}_{self._label_id}"

    def new_temp(self, prefix: str = "__tmp") -> str:
        self._temp_id += 1
        return f"{prefix}_{self._temp_id}"
