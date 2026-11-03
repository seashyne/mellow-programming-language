# mellowlang/parsing/expressions.py

"""The Pratt expression parser: precedence table, driver and prefix forms."""

from __future__ import annotations

from ..ast import BinaryOp, Expr, GetModuleExpr, Literal, UnaryOp, Var
from ..lexer import Token, lex_expr
from .errors import ParseError
from .expression_postfix import ExpressionPostfixMixin
from .expression_atoms import ExpressionAtomMixin


PRECEDENCE = {
    "or": 1,
    "and": 2,
    "==": 3, "!=": 3, ">": 3, "<": 3, ">=": 3, "<=": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5, "%": 5,
    "**": 6,   # highest binary precedence (right-associative via bp+1)
}


class ExprParser(ExpressionPostfixMixin, ExpressionAtomMixin):
    """Recursive-descent over the token stream from mellowlang.lexer."""

    def __init__(self, src: str, *, filename: str | None = None, line: int = 1, base_col: int = 1):
        self.src = src
        self._filename = filename or ParseError.DEFAULT_FILENAME
        self._line = int(line or 1)
        self._base_col = int(base_col or 1)
        self.tokens = lex_expr(src, line=self._line, base_col=self._base_col)
        self.i = 0

    def peek(self) -> Token:
        return self.tokens[self.i]

    def advance(self) -> Token:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def match_val(self, *vals: str) -> bool:
        t = self.peek()
        if t.value in vals:
            self.advance()
            return True
        if t.type == "KW" and t.value.lower() in vals:
            self.advance()
            return True
        return False

    def expect_val(self, val: str):
        if not self.match_val(val):
            t = self.peek()
            raise ParseError(f"Expected '{val}' in expression: {self.src}", filename=self._filename, line=self._line, col=getattr(t,'col',1))

    def parse(self) -> Expr:
        return self._parse_bp(0)

    def _parse_bp(self, min_bp: int) -> Expr:
        lhs = self._parse_prefix()
        while True:
            t = self.peek()
            op = None
            if t.type == "KW" and t.value.lower() in ("and", "or"):
                op = t.value.lower()
            elif t.value in PRECEDENCE:
                op = t.value
            elif t.type == "OP" and t.value in PRECEDENCE:   # e.g. **
                op = t.value
            if op is None:
                break
            bp = PRECEDENCE[op]
            if bp < min_bp:
                break
            self.advance()
            rhs = self._parse_bp(bp + 1)
            lhs = BinaryOp(op, lhs, rhs)
        return lhs

    def _parse_prefix(self) -> Expr:
        t = self.peek()

        if t.type == "KW" and t.value.lower() == "not":
            self.advance()
            return UnaryOp("not", self._parse_bp(6))
        if t.value == "-":
            self.advance()
            return UnaryOp("-", self._parse_bp(6))

        if t.type == "NUMBER":
            self.advance()
            s = t.value
            return Literal(float(s) if "." in s else int(s))
        if t.type == "STRING":
            self.advance()
            return Literal(t.value)
        # v1.4.5: f-string interpolation
        if t.type == "FSTRING":
            self.advance()
            return self._parse_fstring(t.value)
        if t.type == "KW":
            low = t.value.lower()
            if low in ("true", "false"):
                self.advance()
                return Literal(low == "true")
            if low in ("none", "null"):
                self.advance()
                return Literal(None)
            # v1.4.9: inline lambda — skill(x, y=0): expr
            # Only trigger if followed by ( ... ) : pattern (not a plain fn call)
            if low in ("skill", "fn", "lambda", "def", "function"):
                # Lookahead: self.i points to 'skill' keyword itself
                # We need self.i+1 == '(' and after the closing ')' is ':'
                saved_i = self.i
                try:
                    if self.i + 1 < len(self.tokens) and self.tokens[self.i + 1].value == "(":
                        depth, j = 1, self.i + 2  # start inside the '('
                        while j < len(self.tokens) and depth > 0:
                            if self.tokens[j].value == "(": depth += 1
                            elif self.tokens[j].value == ")": depth -= 1
                            j += 1
                        # j is now the index AFTER the closing ')'
                        if j < len(self.tokens) and self.tokens[j].value == ":":
                            return self._parse_lambda()  # it IS a lambda
                except Exception:
                    pass
                self.i = saved_i
                # Fall through — treat as a regular variable name
            # v1.4.8: get/call as expression
            if low in ("get", "call"):
                self.advance()
                # expect IDENT.IDENT(args)
                mod_tok = self.peek()
                if mod_tok.type in ("IDENT", "KW"):
                    mod_name = mod_tok.value
                    self.advance()
                    if self.peek().value == ".":
                        self.advance()
                        func_tok = self.peek()
                        if func_tok.type in ("IDENT", "KW"):
                            func_name = func_tok.value
                            self.advance()
                            args = []
                            if self.peek().value == "(":
                                self.advance()
                                if self.peek().value != ")":
                                    while True:
                                        args.append(self._parse_bp(0))
                                        if self.match_val(")"):
                                            break
                                        self.expect_val(",")
                                else:
                                    self.advance()
                            return GetModuleExpr(mod_name, func_name, args)

        if t.value == "(":
            self.advance()
            inner = self._parse_bp(0)
            self.expect_val(")")
            return self._parse_postfix(inner)

        if t.value == "[":
            expr = self._parse_list()
            return self._parse_postfix(expr)

        if t.value == "{":
            expr = self._parse_map()
            return self._parse_postfix(expr)

        if t.type in ("IDENT", "KW"):
            name = t.value
            self.advance()
            expr: Expr = Var(name)
            return self._parse_postfix(expr)

        t = self.peek()
        raise ParseError(f"Unexpected token in expression: {t.type}:{t.value} in '{self.src}'", filename=self._filename, line=self._line, col=getattr(t,'col',1))


def parse_expr(expr_src: str, *, filename: str | None = None, line: int = 1, base_col: int = 1) -> Expr:
    return ExprParser(expr_src, filename=filename, line=line, base_col=base_col).parse()
