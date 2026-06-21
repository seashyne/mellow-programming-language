
# frinds/parser.py (v2.2)
from __future__ import annotations
import re
from typing import List, Tuple, Optional
from .ast import *
from .lexer import lex_expr, Token
from .error_core import MellowLangRuntimeError

class ParseError(MellowLangRuntimeError):
    """Syntax/parse error with position.

    Backwards-compatible: existing code may raise ParseError("... line 5 ...").
    We infer line/col best-effort.
    """
    DEFAULT_FILENAME: str = "<script>"

    def __init__(self, message: str, *, filename: str | None = None, line: int | None = None, col: int | None = None):
        fn = filename or ParseError.DEFAULT_FILENAME
        ln = line
        cl = col
        if ln is None:
            import re as _re
            m = _re.search(r"\bline\s+(\d+)\b", message)
            if m:
                try:
                    ln = int(m.group(1))
                except Exception:
                    ln = None
        if cl is None:
            cl = 1
        super().__init__('SYNTAX', message, ln, filename=fn, col=cl)


# ---------------- Expression Parser (Pratt) ----------------

PRECEDENCE = {
    "or": 1,
    "and": 2,
    "==": 3, "!=": 3, ">": 3, "<": 3, ">=": 3, "<=": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5, "%": 5,
    "**": 6,   # highest binary precedence (right-associative via bp+1)
}

class ExprParser:
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
                        expr_node = parse_expr(expr_src,
                                               filename=self._filename,
                                               line=self._line)
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

def parse_expr(expr_src: str, *, filename: str | None = None, line: int = 1, base_col: int = 1) -> Expr:
    return ExprParser(expr_src, filename=filename, line=line, base_col=base_col).parse()

# ---------------- Statement Parser (Indentation blocks) ----------------



def _strip_inline_comment(line: str) -> str:
    """Strip // and # comments while respecting string literals."""
    in_str = False
    esc = False
    i = 0
    while i < len(line) - 1:
        ch = line[i]
        if esc:
            esc = False
            i += 1
            continue
        if ch == "\\":
            esc = True
            i += 1
            continue
        if ch == '"':
            in_str = not in_str
            i += 1
            continue
        if not in_str and ch == '#':
            return line[:i].rstrip()
        if not in_str and line[i:i+2] == '//':
            return line[:i].rstrip()
        i += 1
    return line


def _expr_col(raw_line_no_comment: str, expr_src: str, fallback_col: int) -> int:
    """Best-effort 1-based column of expr_src in a raw source line."""
    try:
        idx = raw_line_no_comment.find(expr_src)
        if idx >= 0:
            return idx + 1
    except Exception:
        pass
    return int(fallback_col or 1)

def _indent_level(line: str) -> int:
    count = 0
    for ch in line:
        if ch == ' ':
            count += 1
        elif ch == '\t':
            count += 4
        else:
            break
    return count

def _balance_delta(s: str) -> int:
    # counts (),[],{} balance ignoring strings
    depth = 0
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
    return depth

def _collect_multiline_expr(lines: List[str], i: int, expr_src: str) -> Tuple[str, int]:
    # If expr has unbalanced brackets/braces/parens, consume following lines until balanced.
    bal = _balance_delta(expr_src)
    if bal <= 0:
        return expr_src, i + 1
    parts = [expr_src.strip()]
    j = i + 1
    while j < len(lines) and bal > 0:
        raw = lines[j]
        if not raw.strip() or raw.strip().startswith(("#","//")):
            j += 1
            continue
        chunk = _strip_inline_comment(raw.strip())
        if not chunk:
            j += 1
            continue
        parts.append(chunk)
        bal += _balance_delta(chunk)
        j += 1
    if bal != 0:
        raise ParseError(f"Unclosed literal/expression starting at line {i+1}")
    return " ".join(parts), j


def _split_top_level_commas(s: str) -> List[str]:
    """Split by commas not inside strings/brackets/parens."""
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    in_str = False
    esc = False
    for ch in s:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == '\\':
            buf.append(ch)
            esc = True
            continue
        if ch == '"':
            buf.append(ch)
            in_str = not in_str
            continue
        if in_str:
            buf.append(ch)
            continue
        if ch in "([{":
            depth += 1
            buf.append(ch)
            continue
        if ch in ")]}":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(ch)
    last = "".join(buf).strip()
    if last:
        parts.append(last)
    return parts


def _split_top_level_assign(s: str) -> Optional[Tuple[str, str]]:
    """Split 'lhs = rhs' on the first '=' that is not inside strings/brackets/parens.
    Returns (lhs, rhs) or None.
    Rejects comparison operators like '==', '>=', '<=', '!='.
    """
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "([{":
            depth += 1
            continue
        if ch in ")]}":
            depth = max(0, depth - 1)
            continue
        if ch == '=' and depth == 0:
            # reject ==, >=, <=, !=
            prev = s[i-1] if i-1 >= 0 else ''
            nxt  = s[i+1] if i+1 < len(s) else ''
            if prev in ('=', '!', '>', '<') or nxt == '=':
                continue
            lhs = s[:i].strip()
            rhs = s[i+1:].strip()
            if lhs and rhs:
                return lhs, rhs
            return None
    return None


def _rewrite_modern_aliases(lines: list[str]) -> list[str]:
    """Line-level sugar (v1.0.7):
    - while <cond>:   -> loop (<cond>):
    - for <vars> in <expr>: -> loop <vars> in <expr>:
    - let/var -> keep
    - def/fn/function -> skill
    - print( ... ) statement keyword is handled by compiler/host (kept as call).
    """
    out=[]
    for line in lines:
        raw=line
        s=line.lstrip()
        indent=line[:len(line)-len(s)]
        # keep comments and empty
        if not s or s.startswith("#") or s.startswith("//"):
            out.append(raw); continue
        # let/var
        for kw in ("let ", "var "):
            if s.startswith(kw):
                out.append(indent + "keep " + s[len(kw):])
                break
        else:
            # def/fn/function
            for kw in ("def ", "fn ", "function "):
                if s.startswith(kw):
                    out.append(indent + "skill " + s[len(kw):])
                    break
            else:
                # while
                if s.startswith("while ") and s.rstrip().endswith(":"):
                    cond=s[len("while "):].rstrip()
                    cond=cond[:-1].rstrip()  # remove :
                    out.append(indent + "loop (" + cond + "):")
                # for ... in ...
                elif s.startswith("for ") and s.rstrip().endswith(":") and " in " in s:
                    body=s[len("for "):].rstrip()
                    body=body[:-1].rstrip()
                    out.append(indent + "loop " + body + ":")
                else:
                    out.append(raw)
    return out

def parse_program(lines: List[str], filename: str | None = None) -> Program:
    filename = filename or '<script>'
    ParseError.DEFAULT_FILENAME = filename
    clean = [ln.rstrip("\n") for ln in lines]
    clean = _rewrite_modern_aliases(clean)
    body, _ = _parse_block(clean, 0, 0, filename)
    return Program(body)


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

def _parse_block(lines: List[str], start: int, base_indent: int, filename: str | None = None) -> Tuple[List[Stmt], int]:
    stmts: List[Stmt] = []
    def _push(stmt: Stmt):
        setattr(stmt, "_line", i + 1)
        setattr(stmt, "_col", ind + 1)
        stmts.append(stmt)

    i = start
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.strip().startswith(("#","//")):
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

        # Aliases: while/for (Lua/Python-like)

        # do ... end (Lua-like explicit scope block)
        if line == "do" or line == "do:":
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
            j = _consume_end(lines, j, base_indent)
            _push(DoBlock(body))
            i = j
            continue

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
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
            j = _consume_end(lines, j, base_indent)
            _push(LoopForRange(var_name, parse_expr(start_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, start_src, ind+1)), parse_expr(end_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, end_src, ind+1)), (parse_expr(step_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, step_src, ind+1)) if step_src else None), body))
            i = j
            continue

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
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
            _push(SkillDef(name, params, body, defaults=defaults))
            i = j
            continue

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
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
            _push(OnDef(event_name, params, body))
            i = j
            continue

        # try/catch/finally
        if line == "try:":
            try_body, j = _parse_block(lines, i+1, base_indent+4, filename)
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

                    catch_body, j2 = _parse_block(lines, i+1, base_indent+4, filename)
                    i = j2
                    continue

                if sline == "finally:":
                    finally_body, j2 = _parse_block(lines, i+1, base_indent+4, filename)
                    i = j2
                    continue

                break

            _push(TryStmt(try_body, catch_name, catch_body, finally_body))
            continue

                # repeat-until (Lua-like)
        if line == "repeat:":
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
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
            continue

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
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
            j = _consume_end(lines, j, base_indent)
            _push(LoopCount(parse_expr(limit_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, limit_src, ind+1)), body))
            i = j
            continue

# break/continue
        if line == "break":
            _push(BreakStmt())
            i += 1
            continue
        if line == "continue":
            _push(ContinueStmt())
            i += 1
            continue

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
            block, j = _parse_block(lines, i+1, base_indent+4, filename)
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
                    b2, j2 = _parse_block(lines, i+1, base_indent+4, filename)
                    branches.append((parse_expr(c2, filename=filename, line=i+1, base_col=_expr_col(raw_nc, c2, ind+1)), b2))
                    i = j2
                    continue
                if s.startswith("else:"):
                    else_block, j2 = _parse_block(lines, i+1, base_indent+4, filename)
                    i = j2
                    break
                break

            _push(IfGroup(branches, else_block))
            continue

        # loop foreach
        if line.startswith("loop ") and " in " in line and line.endswith(":"):
            head = line[len("loop "):-1]
            var_part, expr_src = head.split(" in ", 1)
            names = [x.strip() for x in var_part.split(",") if x.strip()]
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
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
            continue

        # v1.4.9: FIX - "loop N times:" → proper LoopCount (was infinite loop bug)
        if line.startswith("loop") and (line.rstrip().endswith("times:") or " times:" in line):
            rest = line[len("loop"):].strip()
            if rest.endswith("times:"):
                limit_src = rest[:-len("times:")].strip()
                body, j = _parse_block(lines, i+1, base_indent+4, filename)
                j = _consume_end(lines, j, base_indent)
                _push(LoopCount(parse_expr(limit_src, filename=filename, line=i+1), body))
                i = j
                continue

        # loop while
        if line.startswith("loop"):
            cond_src = _extract_cond(line, "loop", i)
            body, j = _parse_block(lines, i+1, base_indent+4, filename)
            j = _consume_end(lines, j, base_indent)
            _push(LoopWhile(parse_expr(cond_src, filename=filename, line=i+1, base_col=_expr_col(raw_nc, cond_src, ind+1)), body))
            i = j
            continue

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
            continue

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
            continue

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
            continue

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
            continue
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
            continue

        # precision
        if line.startswith("precision"):
            arg = _extract_cond(line, "precision", i)
            _push(PrecisionStmt(parse_expr(arg, filename=filename, line=i+1, base_col=_expr_col(raw_nc, arg, ind+1))))
            i += 1
            continue

        # stop
        if line == "stop":
            _push(StopStmt())
            i += 1
            continue

        # wait
        if line.startswith("wait"):
            arg = _extract_cond(line, "wait", i)
            _push(WaitStmt(parse_expr(arg, filename=filename, line=i+1, base_col=_expr_col(raw_nc, arg, ind+1))))
            i += 1
            continue

        # put
        if line.startswith("put "):
            rest = line[len("put "):]
            if " into " not in rest:
                raise ParseError(f"put requires 'into' at line {i+1}")
            item_src, list_name = rest.split(" into ", 1)
            _push(PutStmt(parse_expr(item_src.strip()), list_name.strip()))
            i += 1
            continue

        # save/load
        if line.startswith("save ") and " into " in line:
            rest = line[len("save "):]
            a, b = rest.split(" into ", 1)
            _push(SaveStmt(parse_expr(a.strip()), parse_expr(b.strip())))
            i += 1
            continue

        if line.startswith("load ") and " into " in line:
            rest = line[len("load "):]
            a, b = rest.split(" into ", 1)
            _push(LoadStmt(parse_expr(a.strip()), b.strip()))
            i += 1
            continue

        # return
        if line.startswith("return"):
            rest = line[len("return"):].strip()
            _push(ReturnStmt(parse_expr(rest, filename=filename, line=i+1, base_col=_expr_col(raw_nc, rest, ind+1)) if rest else None))
            i += 1
            continue

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
                    continue
                elif paren_pos2 < 0:
                    # get math.pi  (no args, property access)
                    func_name = after_dot.strip()
                    _push(GetModuleStmt(mod_name, func_name, []))
                    i += 1
                    continue

        # expression statement (e.g. function call)
        try:
            _push(ExprStmt(parse_expr(line, filename=filename, line=i+1, base_col=_expr_col(raw_nc, line, ind+1))))
            i += 1
            continue
        except ParseError:
            pass

        raise ParseError(f"Unknown statement at line {i+1}: {line}")

    return stmts, i

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
