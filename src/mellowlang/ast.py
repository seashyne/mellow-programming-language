# frinds/ast.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

# --------- Program / Statements ---------

@dataclass
class Program:
    body: List["Stmt"]


class Stmt: ...


# ----- Simple statements -----

@dataclass
class KeepStmt(Stmt):
    name: str
    expr: "Expr"


@dataclass
class KeepMultiStmt(Stmt):
    """Multi-assign keep: keep a, b = expr1, expr2"""
    names: List[str]
    exprs: List["Expr"]


@dataclass
class AssignStmt(Stmt):
    """General assignment: a = expr or a,b = expr1,expr2 (parallel)."""
    names: List[str]
    exprs: List["Expr"]


@dataclass
class ExprStmt(Stmt):
    """Standalone expression statement (e.g. list_push(items, x))."""
    expr: "Expr"


@dataclass
class ShowStmt(Stmt):
    # Support multi-value printing: print(a, b, c)
    # This keeps the statement form (print/show) game-friendly.
    exprs: List["Expr"]


@dataclass
class PrecisionStmt(Stmt):
    expr: "Expr"


@dataclass
class StopStmt(Stmt):
    pass


@dataclass
class WaitStmt(Stmt):
    expr: "Expr"


@dataclass
class SaveStmt(Stmt):
    value_expr: "Expr"
    filename_expr: "Expr"


@dataclass
class LoadStmt(Stmt):
    filename_expr: "Expr"
    var_name: str


@dataclass
class PutStmt(Stmt):
    item_expr: "Expr"
    list_name: str


@dataclass
class ReturnStmt(Stmt):
    expr: Optional["Expr"]


@dataclass
class BreakStmt(Stmt):
    pass


@dataclass
class ContinueStmt(Stmt):
    pass


@dataclass
class TryStmt(Stmt):
    try_body: List["Stmt"]
    catch_name: Optional[str]
    catch_body: Optional[List["Stmt"]]
    finally_body: Optional[List["Stmt"]]


# ----- Definitions -----

@dataclass
class SkillDef(Stmt):
    name: str
    params: List[str]
    body: List["Stmt"]
    defaults: "dict" = field(default_factory=dict)  # param_name -> Expr (v1.4.9)


@dataclass
class IfGroup(Stmt):
    branches: List[Tuple["Expr", List["Stmt"]]]
    else_block: Optional[List["Stmt"]]


@dataclass
class LoopWhile(Stmt):
    cond: "Expr"
    body: List["Stmt"]


@dataclass
class LoopForEach(Stmt):
    var_name: str          # single var name, OR comma-separated for unpacking "i, v"
    var_names: List[str]   # parsed list of names (v1.4.9)
    iterable: "Expr"
    body: List["Stmt"]


@dataclass
class LoopForMap(Stmt):
    key_name: str
    value_name: str
    iterable: "Expr"   # must be map/dict at runtime
    body: List["Stmt"]


@dataclass
class DoBlock(Stmt):
    """Lua-style do ... end scope (syntax sugar for an explicit block)."""
    body: List["Stmt"]


@dataclass
class LoopForRange(Stmt):
    var_name: str
    start: "Expr"
    end: "Expr"
    step: Optional["Expr"]  # None => friendly default step
    body: List["Stmt"]


@dataclass
class RepeatUntil(Stmt):
    body: List["Stmt"]
    cond: "Expr"


@dataclass
class LoopCount(Stmt):
    limit: "Expr"   # loop count < limit
    body: List["Stmt"]


@dataclass
class OnDef(Stmt):
    event: str
    params: List[str]
    body: List["Stmt"]


# --------- Expressions ---------

class Expr: ...


@dataclass
class Literal(Expr):
    value: Any


@dataclass
class Var(Expr):
    name: str


@dataclass
class UnaryOp(Expr):
    op: str
    expr: Expr


@dataclass
class BinaryOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class Call(Expr):
    name: str
    args: List[Expr]
    # v1.2.2+: named arguments are supported in call syntax, e.g.
    #   file_write("a.txt", "hi", mode="w")
    # To avoid breaking the bytecode format, kwargs are
    # compiled as a trailing map argument.
    kwargs: List[Tuple[str, Expr]] = field(default_factory=list)


@dataclass
class Index(Expr):
    target: Expr
    index: Expr


@dataclass
class ListLiteral(Expr):
    items: List[Expr]


@dataclass
class MapLiteral(Expr):
    pairs: List[Tuple[Expr, Expr]]


# v1.4.5: F-string interpolation
@dataclass
class FStringExpr(Expr):
    """F-string: a template string with {expr} placeholders.

    template: raw string with {name} markers
    parts: list of ('literal', str) | ('expr', Expr) tuples
    """
    template: str
    parts: List[Any]  # list of ('literal', str) | ('expr', Expr)


# v1.4.8: Module system — get/call
@dataclass
class GetModuleStmt(Stmt):
    """
    get module.function(args...)
    Resolves module.function through MODULE_ALLOWLIST and calls it.
    The result is discarded (use as expression via GetModuleExpr for assignment).
    """
    module: str      # e.g. "math"
    function: str    # e.g. "sqrt"
    args: List[Expr] = field(default_factory=list)
    var_name: str = ""   # if non-empty, store result in var_name


@dataclass
class GetModuleExpr(Expr):
    """
    Used when `get` appears in expression context or with assignment:
      let x = get math.sqrt(25)
      keep y = call ai.chat("hello")
    """
    module: str
    function: str
    args: List[Expr] = field(default_factory=list)


@dataclass
class CallValExpr(Expr):
    """v1.4.9: Call an expression value — e.g. fns[0](5) or (skill(x): x*2)(3)"""
    callee: "Expr"
    args: List["Expr"] = field(default_factory=list)


# v1.4.9: First-class functions / lambda
@dataclass
class LambdaExpr(Expr):
    """Anonymous function: skill(x, y): expr  or  fn(x) => x * 2"""
    params: List[str]
    defaults: "dict"      # param_name -> Expr (for default values)
    body: List[Stmt]      # for multi-line; or single ReturnStmt for inline


# v1.4.9: List comprehension
@dataclass
class ListCompExpr(Expr):
    """[expr for var in iterable if cond]"""
    expr: Expr
    var_name: str
    iterable: Expr
    condition: Optional[Expr] = None


# v1.4.9: Spread expression
@dataclass
class SpreadExpr(Expr):
    """*xs inside a list literal: [1, *xs, 2]"""
    expr: Expr


# v1.4.9: Slice expression
@dataclass
class SliceExpr(Expr):
    """target[start:stop] or target[start:stop:step]"""
    target: Expr
    start: Optional[Expr]
    stop: Optional[Expr]
    step: Optional[Expr] = None


# v1.4.9: Import statement
@dataclass
class ImportStmt(Stmt):
    """import "path/to/module.mellow" as alias"""
    path: str        # file path string
    alias: str       # namespace name


# v1.4.9: Update SkillDef to support default params and variadic
@dataclass
class SkillDefV2(Stmt):
    """Extended skill definition with default args and *args support."""
    name: str
    params: List[str]
    defaults: "dict"   # param_name -> Expr
    body: List[Stmt]
    variadic: bool = False   # True if last param is *args style
