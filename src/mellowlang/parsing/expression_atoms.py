# mellowlang/parsing/expression_atoms.py

"""Composite and inline atoms: lambda, f-strings, list literals and maps."""

from __future__ import annotations

from typing import List, Tuple
from ..ast import Expr, FStringExpr, LambdaExpr, ListCompExpr, ListLiteral, Literal, MapLiteral, ReturnStmt, SpreadExpr
from .errors import ParseError


class ExpressionAtomMixin:
    """Provides ExprParser._parse_lambda, _parse_fstring, _parse_list and _parse_map."""

    def _parse_lambda(self) -> "LambdaExpr":
        """v1.4.9: Parse inline lambda: skill(x, y=0): expr"""
        self.advance()  # consume 'skill'/'fn'/'lambda'/'def'/'function'
        self.expect_val("(")
        params = []
        defaults = {}
        if self.peek().value != ")":
            while True:
                p_name = self.peek().value
                self.advance()
                if self.peek().value == "=":
                    self.advance()
                    defaults[p_name] = self._parse_bp(0)
                params.append(p_name)
                if self.match_val(")"):
                    break
                self.expect_val(",")
        else:
            self.advance()
        # Expect ':' then a single expression (inline body)
        self.expect_val(":")
        body_expr = self._parse_bp(0)
        return LambdaExpr(params, defaults, [ReturnStmt(body_expr)])

    def _parse_fstring(self, template: str) -> "FStringExpr":
        """v1.4.5: Parse f-string template into FStringExpr with literal/expr parts.

        Example: f"Hello {name}, you have {hp} HP"
          -> parts: [('literal', 'Hello '), ('expr', Var('name')),
                     ('literal', ', you have '), ('expr', Var('hp')),
                     ('literal', ' HP')]
        """
        parts = []
        buf = []
        i = 0
        n = len(template)
        while i < n:
            ch = template[i]
            if ch == '{':
                # Flush literal
                if buf:
                    parts.append(('literal', ''.join(buf)))
                    buf = []
                # Collect expression until matching '}'
                depth = 1
                i += 1
                expr_buf = []
                while i < n and depth > 0:
                    c = template[i]
                    if c == '{': depth += 1
                    elif c == '}': depth -= 1
                    if depth > 0:
                        expr_buf.append(c)
                    i += 1
                expr_src = ''.join(expr_buf).strip()
                if expr_src:
                    try:
                        expr_node = type(self)(expr_src,
                                               filename=self._filename,
                                               line=self._line).parse()
                    except Exception:
                        expr_node = Literal(expr_src)
                    parts.append(('expr', expr_node))
            elif ch == '}' and i + 1 < n and template[i + 1] == '}':
                # Escaped }}
                buf.append('}')
                i += 2
            else:
                buf.append(ch)
                i += 1
        if buf:
            parts.append(('literal', ''.join(buf)))
        return FStringExpr(template=template, parts=parts)

    def _parse_list(self) -> Expr:
        self.expect_val("[")
        items: List[Expr] = []
        if self.peek().value != "]":
            # Parse first item (could start list comp)
            # v1.4.9: spread support: *expr
            if self.peek().value == "*":
                self.advance()
                first = SpreadExpr(self._parse_bp(0))
            else:
                first = self._parse_bp(0)
            # v1.4.9: list comprehension check — [expr for var in iterable]
            if not isinstance(first, SpreadExpr) and \
               self.peek().type == "KW" and self.peek().value.lower() == "for":
                self.advance()  # 'for'
                var_tok = self.peek()
                var_name = var_tok.value
                self.advance()
                # expect 'in'
                if not (self.peek().type == "KW" and self.peek().value.lower() == "in"):
                    raise ParseError("Expected 'in' in list comprehension")
                self.advance()
                iterable = self._parse_bp(0)
                cond = None
                if self.peek().type == "KW" and self.peek().value.lower() == "if":
                    self.advance()
                    cond = self._parse_bp(0)
                self.expect_val("]")
                return ListCompExpr(first, var_name, iterable, cond)
            # Regular list
            items = [first]
            while self.peek().value == ",":
                self.advance()
                if self.peek().value == "]":
                    break
                if self.peek().value == "*":
                    self.advance()
                    items.append(SpreadExpr(self._parse_bp(0)))
                else:
                    items.append(self._parse_bp(0))
            self.expect_val("]")
        else:
            self.advance()
        return ListLiteral(items)

    def _parse_map(self) -> Expr:
        self.expect_val("{")
        pairs: List[Tuple[Expr, Expr]] = []
        if self.peek().value != "}":
            while True:
                key = self._parse_bp(0)
                self.expect_val(":")
                val = self._parse_bp(0)
                pairs.append((key, val))
                if self.match_val("}"):
                    break
                self.expect_val(",")
        else:
            self.advance()
        return MapLiteral(pairs)
