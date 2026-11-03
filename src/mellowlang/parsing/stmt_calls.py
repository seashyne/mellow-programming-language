# mellowlang/parsing/stmt_calls.py

"""Statement run for get/call module.function(...)."""

from __future__ import annotations

from typing import Optional, Tuple
from ..ast import GetModuleStmt, Stmt
from .line_text import _collect_multiline_expr, _expr_col, _split_top_level_commas
from .expressions import parse_expr


class ModuleCallMixin:
    """get/call module.function(...) as a statement."""

    def _run_module_calls(self, line: str, i: int) -> Tuple[str, Optional[int]]:
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

        # v1.4.8: get/call module system
        # Syntax: get module.func(args...)  OR  call module.func(args...)
        # Also: keep x = get module.func(args...)  already handled via expression
        if line.startswith(("get ", "call ")) and "." in line:
            kw = "get" if line.startswith("get ") else "call"
            rest = line[len(kw):].strip()
            # rest = "module.func(args...)"
            dot_pos = rest.find(".")
            paren_pos = rest.find("(")
            if dot_pos > 0 and (paren_pos < 0 or dot_pos < paren_pos):
                mod_name = rest[:dot_pos].strip()
                after_dot = rest[dot_pos+1:]
                paren_pos2 = after_dot.find("(")
                if paren_pos2 >= 0:
                    func_name = after_dot[:paren_pos2].strip()
                    # Collect multi-line expression: everything from "func_name(..." onwards
                    call_src = after_dot[paren_pos2:]  # starts with "("
                    full_call, next_i = _collect_multiline_expr(lines, i, call_src)
                    # full_call is balanced: "(args...)" possibly multi-line joined
                    inner = full_call.strip()
                    if inner.startswith("(") and inner.endswith(")"):
                        args_str = inner[1:inner.rfind(")")].strip()
                    else:
                        args_str = ""
                    if args_str:
                        raw_args = _split_top_level_commas(args_str)
                        arg_exprs = [parse_expr(a, filename=filename, line=i+1, base_col=_expr_col(raw_nc, a, ind+1)) for a in raw_args]
                    else:
                        arg_exprs = []
                    _push(GetModuleStmt(mod_name, func_name, arg_exprs))
                    i = next_i
                    return line, i
                elif paren_pos2 < 0:
                    # get math.pi  (no args, property access)
                    func_name = after_dot.strip()
                    _push(GetModuleStmt(mod_name, func_name, []))
                    i += 1
                    return line, i

        return line, None
