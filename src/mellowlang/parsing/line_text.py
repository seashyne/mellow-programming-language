# mellowlang/parsing/line_text.py

"""Line-level text helpers: comment stripping, indentation, bracket balance and top-level splits."""

from __future__ import annotations

from typing import List, Optional, Tuple
from .errors import ParseError


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
