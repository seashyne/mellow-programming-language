# mellowlang/lexer.py
# v1.4.5: Added FSTRING token type for f"..." / f'...' interpolated strings
from __future__ import annotations
from dataclasses import dataclass
from typing import List

@dataclass
class Token:
    type: str
    value: str
    pos: int          # 0-based position within the lexed string
    line: int = 1     # 1-based line in source file (best-effort)
    col: int = 1      # 1-based column in source file (best-effort)

# NOTE:
# - Lexer works on a single line / expression string.
# - The caller can provide (line, base_col) so tokens can carry precise line:col.

KEYWORDS = {
    # language keywords
    "keep","show","precision","check","also","else","loop","skill","return",
    "stop","wait","save","load","into","put","in","and","or","not","true","false","none","null",
    "try","catch","finally","repeat","until","break","continue","import","on","do",
    # modern aliases (recommended)
    "let","var","def","fn","function","print","input","if","elif","while","for",
    # v1.4.8: module system
    "get","call",
}

TWO_CHAR = {"==","!=",">=","<=","**"}
SINGLE = set("()+-*/=,:[]{}<>%&|^~!")

def lex_expr(src: str, *, line: int = 1, base_col: int = 1) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    n = len(src)

    def _tok(tt: str, val: str, start: int):
        tokens.append(Token(tt, val, start, line=line, col=base_col + start))

    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
            continue

        # v1.4.5: f-string detection: f"..." or f'...'
        if ch in ('f', 'F') and i + 1 < n and src[i + 1] in ('"', "'"):
            start = i
            i += 1  # skip 'f'
            quote = src[i]
            i += 1  # skip opening quote
            buf = []
            while i < n:
                if src[i] == '\\' and i + 1 < n:
                    esc = src[i + 1]
                    i += 2
                    if esc == 'n': buf.append('\n')
                    elif esc == 't': buf.append('\t')
                    elif esc == 'r': buf.append('\r')
                    elif esc == '\\': buf.append('\\')
                    elif esc in ('"', "'"): buf.append(esc)
                    else: buf.append(esc)
                    continue
                if src[i] == quote:
                    i += 1
                    break
                buf.append(src[i])
                i += 1
            # Store raw template string (with {}) as FSTRING token
            _tok("FSTRING", "".join(buf), start)
            continue

        # normal string literal: "..." or '...'
        if ch in ('"', "'"):
            start = i
            quote = ch
            i += 1
            buf = []
            while i < n:
                if src[i] == '\\' and i + 1 < n:
                    i += 1
                    esc = src[i]
                    i += 1

                    if esc == 'n':
                        buf.append('\n')
                        continue
                    if esc == 'r':
                        buf.append('\r')
                        continue
                    if esc == 't':
                        buf.append('\t')
                        continue
                    if esc == '\\':
                        buf.append('\\')
                        continue
                    if esc == '"':
                        buf.append('"')
                        continue
                    if esc == "'":
                        buf.append("'")
                        continue
                    if esc == 'u':
                        # Unicode escape: \uXXXX
                        if i + 3 < n:
                            hex4 = src[i:i+4]
                            if all(c in '0123456789abcdefABCDEF' for c in hex4):
                                buf.append(chr(int(hex4, 16)))
                                i += 4
                                continue
                        # invalid \u escape -> keep literal 'u'
                        buf.append('u')
                        continue

                    # Unknown escape: keep the escaped char (drop the backslash)
                    buf.append(esc)
                    continue

                if src[i] == quote:
                    i += 1
                    break
                buf.append(src[i])
                i += 1
            _tok("STRING", "".join(buf), start)
            continue

        # number (int/float)
        if ch.isdigit() or (ch == '.' and i+1 < n and src[i+1].isdigit()):
            start = i
            has_dot = False
            while i < n and (src[i].isdigit() or src[i] == '.'):
                if src[i] == '.':
                    if has_dot:
                        break
                    has_dot = True
                i += 1
            _tok("NUMBER", src[start:i], start)
            continue

        # identifier / keyword
        if ch.isalpha() or ch == '_':
            start = i
            i += 1
            while i < n and (src[i].isalnum() or src[i] == '_'):
                i += 1
            text = src[start:i]
            ttype = "KW" if text.lower() in KEYWORDS else "IDENT"
            _tok(ttype, text, start)
            continue

        # operators
        if i+1 < n and src[i:i+2] in TWO_CHAR:
            _tok("OP", src[i:i+2], i)
            i += 2
            continue

        if ch in SINGLE:
            _tok("SYMBOL", ch, i)
            i += 1
            continue

        # unknown char
        _tok("SYMBOL", ch, i)
        i += 1

    tokens.append(Token("EOF", "", n, line=line, col=base_col + n))
    return tokens
