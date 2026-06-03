from __future__ import annotations

from typing import Any

from ..compiler.bytecode_backend import BytecodeBackend
from ..ir import IRProgram
from .legacy import MellowLangVM


class IRVM:
    """Thin adapter that executes IR by lowering it into the existing bytecode VM.

    This keeps Mellow 2.0's AST -> IR -> VM pipeline real, while reusing the stable
    execution engine that already powers the runtime.
    """

    def __init__(self, *, host: Any = None, config: dict | None = None, filename: str | None = None, source_lines: list[str] | None = None):
        self.host = host
        self.config = config or {}
        self.filename = filename
        self.source_lines = source_lines or []

    def run(self, program: IRProgram) -> Any:
        bundle = BytecodeBackend().lower(program)
        vm = MellowLangVM(
            bundle.bytecode,
            func_table=bundle.func_table,
            event_table=bundle.event_table,
            config=self.config,
            host=self.host,
            filename=self.filename or program.filename,
            source_lines=self.source_lines,
            line_map=bundle.line_map,
            col_map=bundle.col_map,
        )
        return vm.run()
