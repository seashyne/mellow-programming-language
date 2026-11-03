# frinds/parser.py (v2.2)
# The grammar lives in mellowlang/parsing/: ParseError, the line helpers, the
# Pratt expression parser and the indentation-based statement driver, with the
# statement chain cut into one run per stmt_* mixin. This module keeps the flat
# import path every consumer already uses.
"""Facade over mellowlang.parsing."""

from __future__ import annotations

from .ast import *  # noqa: F401,F403 - parser.py has always re-exported the node types
from .parsing import (
    BlockParser,
    ExprParser,
    ParseError,
    PRECEDENCE,
    _balance_delta,
    _collect_multiline_expr,
    _consume_end,
    _expr_col,
    _extract_cond,
    _indent_level,
    _parse_block,
    _rewrite_modern_aliases,
    _split_top_level_assign,
    _split_top_level_commas,
    _strip_inline_comment,
    parse_expr,
    parse_program,
)

__all__ = [
    "ExprParser",
    "PRECEDENCE",
    "ParseError",
    "parse_expr",
    "parse_program",
]
