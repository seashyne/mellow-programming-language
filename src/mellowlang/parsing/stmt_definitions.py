# mellowlang/parsing/stmt_definitions.py

"""Statement run for skill definitions and on() handlers."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from ..ast import OnDef, SkillDef, Stmt
from .errors import ParseError
from .line_text import _split_top_level_commas
from .expressions import parse_expr


class DefinitionMixin:
    """skill/def/fn/function headers and on(event, params) handlers."""

    def _run_definitions(self, line: str, i: int) -> Tuple[str, Optional[int]]:
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

        # skill / def / fn / function
        if line.startswith("skill ") or line.startswith("def ") or line.startswith("fn ") or line.startswith("function "):
            if line.startswith("skill "):
                header = line[len("skill "):]
            elif line.startswith("def "):
                header = line[len("def "):]
            elif line.startswith("fn "):
                header = line[len("fn "):]
            else:
                header = line[len("function "):]

            if not header.endswith(":"):
                raise ParseError(f"Skill header must end with ':' at line {i+1}")
            header = header[:-1].strip()
            if "(" not in header or not header.endswith(")"):
                raise ParseError(f"Skill header must be like def name(a,b): at line {i+1}")
            name = header[:header.find("(")].strip()
            params_str = header[header.find("(")+1:-1].strip()
            # v1.4.9: parse default args: skill foo(x, y=5, z="hi"):
            params = []
            defaults = {}
            if params_str:
                for p_raw in _split_top_level_commas(params_str):
                    p = p_raw.strip()
                    if "=" in p:
                        pname, pdefault = p.split("=", 1)
                        pname = pname.strip()
                        params.append(pname)
                        defaults[pname] = parse_expr(pdefault.strip(), filename=filename, line=i+1)
                    else:
                        params.append(p)
            body, j = self.sub_block(i+1, base_indent+4)
            _push(SkillDef(name, params, body, defaults=defaults))
            i = j
            return line, i

        # on(event, params...):
        if line.startswith("on(") and line.endswith("):"):
            inside = line[len("on("):-2].strip()
            # split by commas not inside quotes
            parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', inside)
            parts = [p.strip() for p in parts if p.strip()]
            if not parts:
                raise ParseError(f"on(...) requires event name at line {i+1}")
            ev_raw = parts[0]
            if not (ev_raw.startswith('"') and ev_raw.endswith('"')):
                raise ParseError(f"on(...) event must be a string literal at line {i+1}")
            event_name = ev_raw[1:-1]
            params = []
            for p in parts[1:]:
                if not p.isidentifier():
                    raise ParseError(f"on(...) param must be identifier at line {i+1}: {p}")
                params.append(p)
            body, j = self.sub_block(i+1, base_indent+4)
            _push(OnDef(event_name, params, body))
            i = j
            return line, i

        return line, None
