"""The AST-to-IR lowering pipeline.

The machinery lives in `mellowlang/compiler/lowering/`, one module per concern;
this module keeps the import path `mellowlang.compiler.ir_lowering` that
`compiler.py` already uses, so no caller needs a second home."""

from __future__ import annotations

from .lowering.driver import _LoopCtx
from .lowering.errors import UnsupportedLoweringError
from .lowering.lowerer import IRLowerer
from .lowering.syscalls import _bind_call_arguments, _module_syscall
from .lowering.tables import STDLIB_CALLS, SYSCALL_ARGUMENTS
