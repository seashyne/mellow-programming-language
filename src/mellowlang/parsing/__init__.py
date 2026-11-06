"""Grammar layers behind mellowlang.parser.

parser.py stays the import path every consumer already uses; this package holds
the implementation: ParseError, the line helpers, the Pratt expression parser
and the indentation-based statement driver with one statement run per mixin.
"""

from __future__ import annotations

from .block_core import BLOCK_RUNS, BlockParserBase, _consume_end, _extract_cond
from .blocks import BlockParser, _parse_block, parse_program
from .errors import ParseError
from .expression_atoms import ExpressionAtomMixin
from .expression_postfix import ExpressionPostfixMixin
from .expressions import PRECEDENCE, ExprParser, parse_expr
from .line_text import (
    _balance_delta,
    _collect_multiline_expr,
    _expr_col,
    _indent_level,
    _rewrite_modern_aliases,
    _split_top_level_assign,
    _split_top_level_commas,
    _strip_inline_comment,
)

__all__ = [
    "BLOCK_RUNS",
    "BlockParser",
    "BlockParserBase",
    "ExprParser",
    "ParseError",
    "PRECEDENCE",
    "parse_expr",
    "parse_program",
]
