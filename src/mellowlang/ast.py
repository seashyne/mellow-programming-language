"""The MellowLang syntax tree: one record type per node, and nothing else.

The node definitions live in `mellowlang/ast_nodes/`: `base.py` holds the three
containers, `statements.py` and `expressions.py` the node families, and neither
node module imports the other. This module keeps the import path
`mellowlang.ast` that the parser, the compiler, the VM and the tests already use,
including `from .ast import *`, so every node type is re-exported by name.
"""

from __future__ import annotations

# re-exported so `from mellowlang.ast import *` keeps handing these out too
from dataclasses import dataclass, field  # noqa: F401
from typing import Any, List, Optional, Tuple  # noqa: F401

from .ast_nodes.base import (
    Program,
    Stmt,
    Expr,
)

from .ast_nodes.statements import (
    KeepStmt,
    KeepMultiStmt,
    AssignStmt,
    ExprStmt,
    ShowStmt,
    PrecisionStmt,
    StopStmt,
    WaitStmt,
    SaveStmt,
    LoadStmt,
    PutStmt,
    ReturnStmt,
    BreakStmt,
    ContinueStmt,
    TryStmt,
    SkillDef,
    IfGroup,
    LoopWhile,
    LoopForEach,
    LoopForMap,
    DoBlock,
    LoopForRange,
    RepeatUntil,
    LoopCount,
    OnDef,
    GetModuleStmt,
    ImportStmt,
    SkillDefV2,
)

from .ast_nodes.expressions import (
    Literal,
    Var,
    UnaryOp,
    BinaryOp,
    Call,
    Index,
    ListLiteral,
    MapLiteral,
    FStringExpr,
    GetModuleExpr,
    CallValExpr,
    LambdaExpr,
    ListCompExpr,
    SpreadExpr,
    SliceExpr,
)
