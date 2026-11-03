# mellowlang/parsing/stmt_output.py

"""Statement runs for output and the small utility keywords."""

from __future__ import annotations

from typing import Optional, Tuple
from ..ast import Call, ExprStmt, Literal, LoadStmt, PrecisionStmt, PutStmt, ReturnStmt, SaveStmt, ShowStmt, Stmt, StopStmt, WaitStmt
from .errors import ParseError
from .line_text import _expr_col, _split_top_level_commas
from .expressions import parse_expr
from .block_core import _extract_cond


class OutputMixin:
    """println, write, print and show."""

    def _run_output(self, line: str, i: int) -> Tuple[str, Optional[int]]:
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

        # println (explicit newline output; function-style and statement-style)
        if line.startswith("println"):
            arg_str = line[len("println"):].strip()
            if arg_str.startswith("(") and arg_str.endswith(")"):
                arg_str = arg_str[1:-1].strip()
            parts = _split_top_level_commas(arg_str) if arg_str else [""]
            exprs = [parse_expr(p.strip(), filename=filename, line=i+1, base_col=_expr_col(raw_nc, p, ind+1)) for p in parts if p.strip()]
            if not exprs:
                exprs = [Literal(None)]
            _push(ShowStmt(exprs))
            i += 1
            return line, i

        # write (no trailing newline)
        if line.startswith("write"):
            arg_str = line[len("write"):].strip()
            if arg_str.startswith("(") and arg_str.endswith(")"):
                arg_str = arg_str[1:-1].strip()
            args = [
                parse_expr(p.strip(), filename=filename, line=i+1, base_col=_expr_col(raw_nc, p, ind+1))
                for p in (_split_top_level_commas(arg_str) if arg_str else [])
                if p.strip()
            ]
            _push(ExprStmt(Call("write", args)))
            i += 1
            return line, i

        # show
        # print (alias of show)
        # v1.2.5: support multi-value printing like Python: print(a, b, c)
        # Also supports print a, b, c (without parentheses).
        if line.startswith("print"):
            # strip 'print' keyword; handle print(a,b) and print a,b
            arg_str = line[len("print"):].strip()
            if arg_str.startswith("(") and arg_str.endswith(")"):
                arg_str = arg_str[1:-1].strip()
            parts = _split_top_level_commas(arg_str) if arg_str else [""]
            exprs = [parse_expr(p.strip(), filename=filename, line=i+1, base_col=_expr_col(raw_nc, p, ind+1)) for p in parts if p.strip()]
            if not exprs:
                exprs = [Literal(None)]
            _push(ShowStmt(exprs))
            i += 1
            return line, i
        if line.startswith("show"):
            # v1.4.9 FIX: strip 'show' directly – don't use _extract_cond (it strips fn(5) incorrectly)
            arg_str = line[len("show"):].strip()
            if arg_str.startswith("(") and arg_str.endswith(")"):
                inner = arg_str[1:-1].strip()
                if inner:
                    arg_str = inner
            parts = _split_top_level_commas(arg_str) if arg_str else []
            exprs = [parse_expr(p.strip(), filename=filename, line=i+1, base_col=_expr_col(raw_nc, p, ind+1)) for p in parts if p.strip()]
            if not exprs:
                exprs = [Literal(None)]
            _push(ShowStmt(exprs))
            i += 1
            return line, i

        return line, None


class UtilityMixin:
    """precision, stop, wait, put, save, load and return."""

    def _run_utility(self, line: str, i: int) -> Tuple[str, Optional[int]]:
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

        # precision
        if line.startswith("precision"):
            arg = _extract_cond(line, "precision", i)
            _push(PrecisionStmt(parse_expr(arg, filename=filename, line=i+1, base_col=_expr_col(raw_nc, arg, ind+1))))
            i += 1
            return line, i

        # stop
        if line == "stop":
            _push(StopStmt())
            i += 1
            return line, i

        # wait
        if line.startswith("wait"):
            arg = _extract_cond(line, "wait", i)
            _push(WaitStmt(parse_expr(arg, filename=filename, line=i+1, base_col=_expr_col(raw_nc, arg, ind+1))))
            i += 1
            return line, i

        # put
        if line.startswith("put "):
            rest = line[len("put "):]
            if " into " not in rest:
                raise ParseError(f"put requires 'into' at line {i+1}")
            item_src, list_name = rest.split(" into ", 1)
            _push(PutStmt(parse_expr(item_src.strip()), list_name.strip()))
            i += 1
            return line, i

        # save/load
        if line.startswith("save ") and " into " in line:
            rest = line[len("save "):]
            a, b = rest.split(" into ", 1)
            _push(SaveStmt(parse_expr(a.strip()), parse_expr(b.strip())))
            i += 1
            return line, i

        if line.startswith("load ") and " into " in line:
            rest = line[len("load "):]
            a, b = rest.split(" into ", 1)
            _push(LoadStmt(parse_expr(a.strip()), b.strip()))
            i += 1
            return line, i

        # return
        if line.startswith("return"):
            rest = line[len("return"):].strip()
            _push(ReturnStmt(parse_expr(rest, filename=filename, line=i+1, base_col=_expr_col(raw_nc, rest, ind+1)) if rest else None))
            i += 1
            return line, i

        return line, None
