# mellowlang/parsing/stmt_bindings.py

"""Statement run for keep, import and assignment."""

from __future__ import annotations

from typing import Optional, Tuple
from ..ast import AssignStmt, Call, ImportStmt, KeepMultiStmt, KeepStmt, Literal, Stmt
from .errors import ParseError
from .line_text import _collect_multiline_expr, _expr_col, _split_top_level_assign, _split_top_level_commas
from .expressions import parse_expr


class BindingMixin:
    """keep/let/var, import/use/need and general assignment."""

    def _run_bindings(self, line: str, i: int) -> Tuple[str, Optional[int]]:
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

        # keep / let / var
        if line.startswith("keep ") or line.startswith("let ") or line.startswith("var "):
            # normalize keyword length
            if line.startswith("keep "):
                rest = line[len("keep "):]
            elif line.startswith("let "):
                rest = line[len("let "):]
            else:
                rest = line[len("var "):]

            if "=" not in rest:
                raise ParseError(f"variable declaration requires '=' at line {i+1}")
            left, expr_src = rest.split("=", 1)
            names = [x.strip() for x in left.split(",") if x.strip()]
            expr_full, next_i = _collect_multiline_expr(lines, i, expr_src.strip())
            expr_parts = _split_top_level_commas(expr_full)
            if len(names) == 1:
                _push(KeepStmt(names[0], parse_expr(expr_full, filename=filename, line=i+1, base_col=_expr_col(raw_nc, expr_full, ind+1))))
            else:
                if len(expr_parts) != len(names):
                    raise ParseError(
                        f"keep multi-assign expects {len(names)} values, got {len(expr_parts)} at line {i+1}"
                    )
                _push(KeepMultiStmt(names, [parse_expr(p, filename=filename, line=i+1, base_col=_expr_col(raw_nc, p, ind+1)) for p in expr_parts]))
            i = next_i
            return line, i

        # import/use/need sugar
        #   import math as math
        #   use core-ai as ai
        #   need "core-ai" as ai
        if line.startswith("import ") or line.startswith("use ") or line.startswith("need "):
            keyword = "import" if line.startswith("import ") else ("use" if line.startswith("use ") else "need")
            rest = line[len(keyword) + 1:].strip()
            if " as " not in rest:
                raise ParseError(f"{keyword} requires 'as' at line {i+1}")
            mod_src, alias = rest.split(" as ", 1)
            mod_src = mod_src.strip()
            alias = alias.strip()
            if not alias.isidentifier():
                raise ParseError(f"{keyword} alias must be identifier at line {i+1}: {alias}")
            if (mod_src.startswith('"') and mod_src.endswith('"')) or (mod_src.startswith("'") and mod_src.endswith("'")):
                raw_value = mod_src[1:-1]
                if raw_value.endswith('.mellow'):
                    _push(ImportStmt(raw_value, alias))
                else:
                    package_path = raw_value if raw_value.startswith("pkg:") else f"pkg:{raw_value}"
                    _push(ImportStmt(package_path, alias))
            else:
                if any(ch in mod_src for ch in ('-', '/', '@')):
                    _push(ImportStmt(f"pkg:{mod_src}", alias))
                else:
                    mod_expr = Literal(mod_src)
                    _push(AssignStmt([alias], [Call("get", [mod_expr])]))
            i += 1
            return line, i

        # general assignment (parallel multi-assign)
        #   a = expr
        #   a, b = expr1, expr2
        split = _split_top_level_assign(line)
        if split is not None:
            left, rhs_src = split
            names = [x.strip() for x in left.split(",") if x.strip()]
            if not names:
                raise ParseError(f"assignment requires at least one name at line {i+1}")
            for nm in names:
                if not nm.isidentifier():
                    raise ParseError(f"assignment target must be identifier at line {i+1}: {nm}")
            rhs_full, next_i = _collect_multiline_expr(lines, i, rhs_src)
            rhs_parts = _split_top_level_commas(rhs_full)
            if len(rhs_parts) != len(names):
                raise ParseError(
                    f"multi-assign expects {len(names)} values, got {len(rhs_parts)} at line {i+1}"
                )
            _push(AssignStmt(names, [parse_expr(p, filename=filename, line=i+1, base_col=_expr_col(raw_nc, p, ind+1)) for p in rhs_parts]))
            i = next_i
            return line, i

        return line, None
