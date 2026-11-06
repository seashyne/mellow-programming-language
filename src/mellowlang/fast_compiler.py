# MellowLang v1.4.9 — Compile-to-Python Fast Path
# Transpiles MellowLang AST → Python source, then exec() for ~10-50x speedup
# vs bytecode VM for compute-intensive scripts.

"""The compile-to-Python fast path: `PyTranspiler` emits Python source and
   `FastRunner` compiles, runs and captures it.

The bodies live in `mellowlang/fastlang/`, one module per concern; this module
keeps the import path `mellowlang.fast_compiler` the CLI commands and the tests
already use, so no caller needs a second home."""

from __future__ import annotations

from .fastlang.builtins import _MELLOW_BUILTINS_SRC
from .fastlang.names import _py_name
from .fastlang.runner import FastRunner
from .fastlang.transpiler import PyTranspiler
