"""mellowlang.compiler

Stable public compiler API (v1.0.3+).

- Compiler: facade used by CLI/tooling (stable contract)
- LegacyCompiler: previous bytecode compiler (kept for internal/back-compat)
"""

from __future__ import annotations

from .compiler.compiler import Compiler, CompiledProgram
from .compiler.legacy import Compiler as LegacyCompiler

__all__ = ["Compiler", "CompiledProgram", "LegacyCompiler"]
