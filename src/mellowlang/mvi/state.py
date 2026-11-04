"""The accumulators one lowering pass shares, so the pass reads as a sequence of steps instead
   of one function holding twenty-one locals in its frame."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..compiler.compiler import CompiledProgram
from .format import FunctionEntry, ModuleEntry


@dataclass
class Lowering:
    """The accumulators one lowering pass shares. Each field is a local the monolithic pass
       kept in its frame, under the same name, so a step that used to reach up now reaches
       the same word on `state`."""

    compiled: CompiledProgram
    bytecode: list[Any]
    spans_src: list[dict[str, Any]]
    func_table: dict[str, Any]

    const_pool: list[dict[str, Any]] = field(default_factory=list)
    const_index: dict[str, int] = field(default_factory=dict)
    code: list[tuple[int, int, int, int]] = field(default_factory=list)
    spans: list[tuple[int, int, int, int]] = field(default_factory=list)
    globals_map: dict[str, int] = field(default_factory=dict)
    _func_locals: dict[str, dict[str, int]] = field(default_factory=dict)   # func_name → {var: slot}
    _func_ranges: list[tuple[int, int, str]] = field(default_factory=list)  # (start_pc, end_pc, func_name)
    # Determine current function scope during lowering
    _current_func: str | None = None
    _current_func_end: int = -1
    func_const_slots: dict[str, int] = field(default_factory=dict)
    functions: list[FunctionEntry] = field(default_factory=list)
    modules: list[ModuleEntry] = field(default_factory=list)
    # Track pending syscall name pushed before SYSCALL opcode
    _pending_syscall_name: str | None = None
    # v2.3.4: two-pass JUMP target fix
    # src_pc → image instruction index (after skipped ARGs are removed)
    _src_to_img: dict[int, int] = field(default_factory=dict)
    # (image_instr_index, field) pairs that hold a src_pc jump target to patch
    _jump_patches: list[tuple[int, str]] = field(default_factory=list)  # (img_idx, 'a')


    def slot_for(self, name: str, src_pc: int = -1) -> int:
        """The slot a name occupies in the scope the lowering is currently in; a name this function
           has not declared is a global, and gets the next global slot."""
        # If inside a function, use function-local slot
        if self._current_func and name in self._func_locals.get(self._current_func, {}):
            return self._func_locals[self._current_func][name]
        # Global scope
        if name not in self.globals_map:
            self.globals_map[name] = len(self.globals_map)
        return self.globals_map[name]


    def enter_scope(self, pc: int) -> None:
        """Switch the current function when the program counter crosses a boundary, so the next
           name resolves against the frame that owns it."""
        # Track function scope transitions
        for (fstart, fend, fname) in self._func_ranges:
            if pc == fstart:
                self._current_func = fname
                self._current_func_end = fend
                break
            if pc >= fend and self._current_func == fname:
                self._current_func = None
                self._current_func_end = -1
