"""Per-pass modules behind mellowlang.compiler.optimizer."""

from __future__ import annotations

from .ir_data import (
    BasicBlock,
    ControlFlowGraph,
    DefUseInfo,
    DominatorTree,
    OptimizationSummary,
    PhiNode,
    SSAProgram,
    _CONST_TOP,
    _StackValue,
)
from .graph import ControlFlowMixin
from .folding import ConstantFoldingMixin
from .dataflow import DataflowMixin
from .rewrite import BlockRewriteMixin
from .gvn import GlobalValueNumberingMixin
from .sccp import SccpMixin
from .loops import LoopInvariantMotionMixin
from .cleanup import CleanupMixin
from .exprs import ExpressionMixin
from .optimizer import IROptimizer


__all__ = [
    "BasicBlock",
    "BlockRewriteMixin",
    "CleanupMixin",
    "ConstantFoldingMixin",
    "ControlFlowGraph",
    "ControlFlowMixin",
    "DataflowMixin",
    "DefUseInfo",
    "DominatorTree",
    "ExpressionMixin",
    "GlobalValueNumberingMixin",
    "IROptimizer",
    "LoopInvariantMotionMixin",
    "OptimizationSummary",
    "PhiNode",
    "SSAProgram",
    "SccpMixin",
    "_CONST_TOP",
    "_StackValue",
]
