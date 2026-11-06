"""The indentation-based statement driver.

_parse_block used to be one 560-line function holding every statement form.
Its chain is now a contiguous list of run methods declared by the stmt_*
mixins; BLOCK_RUNS below fixes their order, which is the order the original
if-chain tested them. Each run returns the (possibly rewritten) line plus the
index it consumed, or None when the line is not its own.
"""

from __future__ import annotations

from typing import List, Tuple

from ..ast import ExprStmt, Stmt
from .errors import ParseError
from .expressions import parse_expr
from .line_text import _expr_col, _indent_level, _strip_inline_comment

BLOCK_RUNS: Tuple[str, ...] = (
    "_run_scope_loops",
    "_run_definitions",
    "_run_exceptions",
    "_run_conditionals",
    "_run_loop_forms",
    "_run_bindings",
    "_run_output",
    "_run_utility",
    "_run_module_calls",
)


class BlockParserBase:
    """State the statement runs read: the lines, the block indent, the cursor.

    Subclasses mix in the statement runs (see BLOCK_RUNS) and nothing else.
    """

    BLOCK_RUNS = BLOCK_RUNS

    def __init__(self, lines: List[str], start: int, base_indent: int,
                 filename: str | None = None):
        self.lines = lines
        self.base_indent = base_indent
        self.filename = filename
        self.stmts: List[Stmt] = []
        self.i = start
        self.ind = base_indent
        self.raw_nc = ""

    def sub_block(self, start: int, base_indent: int) -> Tuple[List[Stmt], int]:
        """Parse a nested block with the same mixin set (the old _parse_block call)."""
        return type(self)(self.lines, start, base_indent, self.filename).parse()

    def parse(self) -> Tuple[List[Stmt], int]:
        lines = self.lines
        base_indent = self.base_indent
        filename = self.filename
        stmts = self.stmts
        i = self.i
        while i < len(lines):
            raw = lines[i]
            if not raw.strip() or raw.strip().startswith(("#", "//")):
                i += 1
                continue

            ind = _indent_level(raw)
            if ind < base_indent:
                break
            if ind > base_indent:
                raise ParseError(f"Unexpected indent at line {i+1}: {raw}")

            raw_nc = _strip_inline_comment(raw.rstrip("\n"))
            line = _strip_inline_comment(raw.strip())
            if not line:
                i += 1
                continue

            # block terminator (Lua-style)
            if line == "end":
                if base_indent == 0:
                    raise ParseError(f"Unexpected 'end' at top-level (line {i+1})")
                i += 1
                break

            def _push(stmt: Stmt):
                setattr(stmt, "_line", i + 1)
                setattr(stmt, "_col", ind + 1)
                stmts.append(stmt)

            self.ind, self.raw_nc = ind, raw_nc
            consumed = False
            for run in self.BLOCK_RUNS:
                line, next_i = getattr(self, run)(line, i)
                if next_i is not None:
                    i = next_i
                    consumed = True
                    break
            if consumed:
                continue

            # expression statement (e.g. function call)
            try:
                _push(ExprStmt(parse_expr(line, filename=filename, line=i+1, base_col=_expr_col(raw_nc, line, ind+1))))
                i += 1
                continue
            except ParseError:
                pass

            raise ParseError(f"Unknown statement at line {i+1}: {line}")

        self.i = i
        return stmts, i


def _consume_end(lines: List[str], i: int, base_indent: int) -> int:
    """Optionally consume a standalone 'end' line at the given base indent.
    This allows Lua-style block termination while keeping indentation-based blocks (Python-style).
    """
    j = i
    while j < len(lines):
        raw = lines[j]
        if not raw.strip() or raw.strip().startswith(("#","//")):
            j += 1
            continue
        if _indent_level(raw) != base_indent:
            return i
        line = _strip_inline_comment(raw.strip())
        if line == "end":
            return j + 1
        return i
    return i

def _extract_cond(line: str, kw: str, line_no: int) -> str:
    """Extract condition for check/also/loop/if/elif.
    Supports forms:
      kw(expr)
      kw expr:
      kw(expr):
    """
    s = line.strip()
    # remove trailing ':' if present
    if s.endswith(':'):
        s = s[:-1].rstrip()
    # parenthesized
    start = s.find('(')
    end = s.rfind(')')
    if start != -1 and end != -1 and end > start:
        return s[start+1:end].strip()
    # space form: kw <cond>
    prefix = kw + ' '
    if s.startswith(prefix):
        return s[len(prefix):].strip()
    raise ParseError(f"Expected {kw}(...) or {kw} <cond>: at line {line_no+1}: {line}")
