"""Every expression node: literals, operators, calls, containers and the
v1.4.9 first-class function, comprehension and slice forms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .base import Expr, Stmt


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
