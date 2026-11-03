# mellowlang/compiler/optimizer.py
# The optimizer implementation lives in compiler/optimizations/: one mixin
# per pass section plus the shared IR value types. This module keeps the
# import path that compiler.py and compiler/__init__.py already use.
"""Facade over mellowlang.compiler.optimizations."""

from __future__ import annotations

from .optimizations import (
    BasicBlock,
    ControlFlowGraph,
    DefUseInfo,
    DominatorTree,
    IROptimizer,
    OptimizationSummary,
    PhiNode,
    SSAProgram,
    _CONST_TOP,
    _StackValue,
)


__all__ = [
    "BasicBlock",
    "ControlFlowGraph",
    "DefUseInfo",
    "DominatorTree",
    "IROptimizer",
    "OptimizationSummary",
    "PhiNode",
    "SSAProgram",
    "_CONST_TOP",
    "_StackValue",
]
