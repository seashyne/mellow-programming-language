# mellowlang/parsing/stmt_loops.py

"""Statement runs for do/end scopes and every loop form."""

from __future__ import annotations

from typing import Optional, Tuple
from ..ast import DoBlock, LoopCount, LoopForEach, LoopForRange, LoopWhile, Stmt
from .errors import ParseError
from .line_text import _expr_col, _split_top_level_commas
from .expressions import parse_expr
from .block_core import _consume_end, _extract_cond


class LoopHeadMixin:
    """do/end scopes, Lua-style numeric for, and the while/for-in aliases."""

    def _run_scope_loops(self, line: str, i: int) -> Tuple[str, Optional[int]]:
        lines = self.lines
        base_indent = self.base_indent
        filename = self.filename
        ind = self.ind
        raw_nc = self.raw_nc
        stmts = self.stmts

        def _push(stmt: Stmt):
            setattr(stmt, "_line", i + 1)
            setattr(stmt, "_col", ind + 1)
            stmts.append(stmt)

        # Aliases: while/for (Lua/Python-like)

        # do ... end (Lua-like explicit scope block)
        if line == "do" or line == "do:":
            body, j = self.sub_block(i+1, base_indent+4)
            j = _consume_end(lines, j, base_indent)
            _push(DoBlock(body))
            i = j
            return line, i

        # Numeric for (Lua-like): for i = a, b, step do  ... end
        # Friendly forms:
        #   for i = end do              -> start=1, end=end, step=1
        #   for i = start, end do       -> step defaults (+1 or -1 based on start/end)
        #   for i = start, end, step do
        if line.startswith("for") and (line.startswith("for ") or line.startswith("for(")) and "=" in line and " in " not in line:
            # allow optional trailing ':' or ' do'
            head = line
            if head.endswith(" do"):
                head = head[:-3].rstrip()
            if not (head.endswith(":") or line.endswith(" do") or head.endswith("do")):
                # allow without ':'/do if user wrote 'for i=1,3' then next indented block
                pass
            if head.endswith(":"):
                head2 = head[:-1].strip()
            else:
                head2 = head.strip()
            # strip leading 'for'
            head2 = head2[len("for"):].strip()
            # parse 'i = exprs'
            if "=" not in head2:
                raise ParseError(f"Invalid numeric for syntax at line {i+1}: {line}")
            var_part, expr_part = head2.split("=", 1)
            var_name = var_part.strip()
            if not var_name.isidentifier():
                raise ParseError(f"for-loop variable must be identifier at line {i+1}: {var_name}")
            exprs = _split_top_level_commas(expr_part.strip())
            if len(exprs) == 0:
                raise ParseError(f"for-loop requires range at line {i+1}: {line}")
            if len(exprs) == 1:
                start_src = "1"
                end_src = exprs[0]
                step_src = None
            elif len(exprs) == 2:
                start_src, end_src = exprs
                step_src = None
            elif len(exprs) == 3:
                start_src, end_src, step_src = exprs
            else:
                raise ParseError(f"for-loop supports 1-3 range expressions at line {i+1}: {line}")
            body, j = self.sub_block(i+1, base_indent+4)
            j = _consume_end(lines, j, base_indent)
            _push(LoopForRange(var_name, parse_expr(start_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, start_src, ind+1)), parse_expr(end_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, end_src, ind+1)), (parse_expr(step_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, step_src, ind+1)) if step_src else None), body))
            i = j
            return line, i

        if line.startswith("while") and (line.startswith("while ") or line.startswith("while(")):
            wl = line
            if wl.endswith(" do"):
                wl = wl[:-3].rstrip() + ":"
            line = "loop" + wl[len("while"):]

        if line.startswith("for ") and " in " in line:
            fl = line
            if fl.endswith(" do"):
                fl = fl[:-3].rstrip() + ":"
            if fl.endswith(":"):
                line = "loop " + fl[len("for "):]

        return line, None


class LoopFormMixin:
    """loop ... in ..., loop N times: and loop <cond>."""

    def _run_loop_forms(self, line: str, i: int) -> Tuple[str, Optional[int]]:
        lines = self.lines
        base_indent = self.base_indent
        filename = self.filename
        ind = self.ind
        raw_nc = self.raw_nc
        stmts = self.stmts

        def _push(stmt: Stmt):
            setattr(stmt, "_line", i + 1)
            setattr(stmt, "_col", ind + 1)
            stmts.append(stmt)

        # loop foreach
        if line.startswith("loop ") and " in " in line and line.endswith(":"):
            head = line[len("loop "):-1]
            var_part, expr_src = head.split(" in ", 1)
            names = [x.strip() for x in var_part.split(",") if x.strip()]
            body, j = self.sub_block(i+1, base_indent+4)
            j = _consume_end(lines, j, base_indent)
            if len(names) == 1:
                _push(LoopForEach(names[0], [names[0]], parse_expr(expr_src.strip(), filename=filename, line=i+1), body))
            elif len(names) == 2:
                # v1.4.9: if iterable looks like a plain dict access, use LoopForMap; else tuple unpack
                expr_stripped = expr_src.strip()
                _push(LoopForEach(names[0] + "," + names[1], names, parse_expr(expr_stripped, filename=filename, line=i+1), body))
            else:
                raise ParseError(f"loop ... in ... supports 1 or 2 vars (got {len(names)}) at line {i+1}")
            i = j
            return line, i

        # v1.4.9: FIX - "loop N times:" → proper LoopCount (was infinite loop bug)
        if line.startswith("loop") and (line.rstrip().endswith("times:") or " times:" in line):
            rest = line[len("loop"):].strip()
            if rest.endswith("times:"):
                limit_src = rest[:-len("times:")].strip()
                body, j = self.sub_block(i+1, base_indent+4)
                j = _consume_end(lines, j, base_indent)
                _push(LoopCount(parse_expr(limit_src, filename=filename, line=i+1), body))
                i = j
                return line, i

        # loop while
        if line.startswith("loop"):
            cond_src = _extract_cond(line, "loop", i)
            body, j = self.sub_block(i+1, base_indent+4)
            j = _consume_end(lines, j, base_indent)
            _push(LoopWhile(parse_expr(cond_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, cond_src, ind+1)), body))
            i = j
            return line, i

        return line, None
