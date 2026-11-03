# mellowlang/parsing/stmt_control.py

"""Statement runs for try/repeat/break and the check chain."""

from __future__ import annotations

from typing import List, Optional, Tuple
from ..ast import BreakStmt, ContinueStmt, Expr, IfGroup, LoopCount, RepeatUntil, Stmt, TryStmt
from .errors import ParseError
from .line_text import _expr_col, _indent_level, _strip_inline_comment
from .expressions import parse_expr
from .block_core import _consume_end, _extract_cond


class ExceptionHandlerMixin:
    """try/catch/finally, repeat/until, loop count, break and continue."""

    def _run_exceptions(self, line: str, i: int) -> Tuple[str, Optional[int]]:
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

        # try/catch/finally
        if line == "try:":
            try_body, j = self.sub_block(i+1, base_indent+4)
            i = j
            catch_name = None
            catch_body = None
            finally_body = None

            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip() or nxt.strip().startswith(("#","//")):
                    i += 1
                    continue
                if _indent_level(nxt) != base_indent:
                    break
                sline = _strip_inline_comment(nxt.strip())
                if not sline:
                    i += 1
                    continue

                if sline.startswith("catch") and sline.endswith(":"):
                    head = sline[:-1].strip()  # remove ':'
                    parts = head.split()
                    if len(parts) == 1:
                        catch_name = "err"
                    elif len(parts) == 2:
                        catch_name = parts[1]
                        if not catch_name.isidentifier():
                            raise ParseError(f"catch name must be identifier at line {i+1}: {sline}")
                    else:
                        raise ParseError(f"Invalid catch header at line {i+1}: {sline}")

                    catch_body, j2 = self.sub_block(i+1, base_indent+4)
                    i = j2
                    continue

                if sline == "finally:":
                    finally_body, j2 = self.sub_block(i+1, base_indent+4)
                    i = j2
                    continue

                break

            _push(TryStmt(try_body, catch_name, catch_body, finally_body))
            return line, i

                # repeat-until (Lua-like)
        if line == "repeat:":
            body, j = self.sub_block(i+1, base_indent+4)
            i = j
            # expect 'until <cond>' at same indent
            while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith(("#","//"))):
                i += 1
            if i >= len(lines) or _indent_level(lines[i]) != base_indent:
                raise ParseError(f"repeat: must be followed by 'until <cond>' at line {i+1 if i < len(lines) else len(lines)}")
            until_line = _strip_inline_comment(lines[i].strip())
            if not until_line.startswith("until"):
                raise ParseError(f"repeat: must be followed by 'until <cond>' at line {i+1}: {lines[i].strip()}")
            cond_src = _extract_cond(until_line, "until", i)
            _push(RepeatUntil(body, parse_expr(cond_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, cond_src, ind+1))))
            i += 1
            return line, i

        # loop count < limit:  (sandbox-friendly counter loop)
        if line.startswith("loop count") and line.endswith(":"):
            # accept: loop count < expr:
            head = line[len("loop "):-1].strip()  # 'count < expr'
            if "<" not in head:
                raise ParseError(f"loop count requires '<' at line {i+1}: {line}")
            left, right = head.split("<", 1)
            if left.strip() != "count":
                raise ParseError(f"loop count syntax is: loop count < N:  at line {i+1}")
            limit_src = right.strip()
            body, j = self.sub_block(i+1, base_indent+4)
            j = _consume_end(lines, j, base_indent)
            _push(LoopCount(parse_expr(limit_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, limit_src, ind+1)), body))
            i = j
            return line, i

# break/continue
        if line == "break":
            _push(BreakStmt())
            i += 1
            return line, i
        if line == "continue":
            _push(ContinueStmt())
            i += 1
            return line, i

        return line, None


class ConditionalMixin:
    """the if/elif/else alias and the check/also/else chain."""

    def _run_conditionals(self, line: str, i: int) -> Tuple[str, Optional[int]]:
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

        # check/also/else chain

        # if/elif/else alias (Python/Lua-like) -> check/also/else
        # if/elif/else alias (Python/Lua-like) -> check/also/else
        # Support: if cond:    elif cond:    else:
        if line.startswith("if") and (line.startswith("if ") or line.startswith("if(")):
            line = "check" + line[len("if"):]
        # elif alias is handled inside the chain below ("elif" treated like "also")

        if line.startswith("check"):
            branches: List[Tuple[Expr, List[Stmt]]] = []
            else_block: Optional[List[Stmt]] = None

            cond_src = _extract_cond(line, "check", i)
            block, j = self.sub_block(i+1, base_indent+4)
            branches.append((parse_expr(cond_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, cond_src, ind+1)), block))
            i = j

            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip() or nxt.strip().startswith(("#","//")):
                    i += 1
                    continue
                if _indent_level(nxt) != base_indent:
                    break
                s = nxt.strip()
                if s.startswith("also") or s.startswith("elif"):
                    c2 = _extract_cond(s, "also" if s.startswith("also") else "elif", i)
                    b2, j2 = self.sub_block(i+1, base_indent+4)
                    branches.append((parse_expr(c2, filename=filename, line=i+1, base_col=_expr_col(raw_nc, c2, ind+1)), b2))
                    i = j2
                    continue
                if s.startswith("else:"):
                    else_block, j2 = self.sub_block(i+1, base_indent+4)
                    i = j2
                    break
                break

            _push(IfGroup(branches, else_block))
            return line, i

        return line, None
