# mellowlang/parsing/expression_postfix.py

"""Trailing call, member and index forms: f(x), a.b(y), xs[i], xs[a:b]."""

from __future__ import annotations

from typing import List, Optional
from ..ast import Call, CallValExpr, Expr, GetModuleExpr, Index, Literal, SliceExpr, Var


class ExpressionPostfixMixin:
    """Provides ExprParser._parse_postfix."""

    def _parse_postfix(self, expr: Expr) -> Expr:
        while True:
            t = self.peek()
            if t.value == "(" and isinstance(expr, Var):
                self.advance()
                args: List[Expr] = []
                kwargs: List[tuple[str, Expr]] = []
                if self.peek().value != ")":
                    while True:
                        t0 = self.peek()
                        if t0.type in ("IDENT", "KW"):
                            name_tok = t0
                            if self.i + 1 < len(self.tokens) and self.tokens[self.i + 1].value == "=":
                                self.advance()
                                self.advance()
                                val = self._parse_bp(0)
                                kwargs.append((str(name_tok.value), val))
                            else:
                                args.append(self._parse_bp(0))
                        else:
                            args.append(self._parse_bp(0))
                        if self.match_val(")"):
                            break
                        self.expect_val(",")
                else:
                    self.advance()
                expr = Call(expr.name, args, kwargs=kwargs)
                continue
            # v1.4.9: call-via-expression: fns[0](args), (skill(x): x*2)(3), etc.
            if t.value == "(" and not isinstance(expr, Var):
                self.advance()
                call_args2: List[Expr] = []
                if self.peek().value != ")": 
                    while True:
                        call_args2.append(self._parse_bp(0))
                        if self.match_val(")"):
                            break
                        self.expect_val(",")
                else:
                    self.advance()
                expr = CallValExpr(expr, call_args2)
                continue
            # v1.4.9: dot-call for imported modules: mylib.func(args)
            if t.value == "." and isinstance(expr, Var):
                self.advance()
                attr_tok = self.peek()
                attr_name = attr_tok.value
                self.advance()
                if self.peek().value == "(":
                    self.advance()
                    args2: List[Expr] = []
                    if self.peek().value != ")":
                        while True:
                            args2.append(self._parse_bp(0))
                            if self.match_val(")"):
                                break
                            self.expect_val(",")
                    else:
                        self.advance()
                    # module.func(args) → use qualified call name
                    expr = Call(f"{expr.name}.{attr_name}", args2)
                else:
                    expr = GetModuleExpr(expr.name, attr_name, [])
                continue
            if t.value == "[":
                self.advance()
                # v1.4.9: slice support xs[start:stop] or xs[start:stop:step]
                start_e: Optional[Expr] = None
                stop_e: Optional[Expr] = None
                step_e: Optional[Expr] = None
                is_slice = False
                if self.peek().value != "]":
                    if self.peek().value != ":":
                        start_e = self._parse_bp(0)
                    if self.peek().value == ":":
                        is_slice = True
                        self.advance()
                        if self.peek().value not in ("]", ":"):
                            stop_e = self._parse_bp(0)
                        if self.peek().value == ":":
                            self.advance()
                            if self.peek().value != "]":
                                step_e = self._parse_bp(0)
                self.expect_val("]")
                if is_slice:
                    expr = SliceExpr(expr, start_e, stop_e, step_e)
                else:
                    idx_val = start_e if start_e is not None else Literal(0)
                    expr = Index(expr, idx_val)
                continue
            break
        return expr
