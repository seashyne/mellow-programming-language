# mellowlang/parsing/errors.py

"""ParseError: the syntax error type the parser and CLI both report."""

from __future__ import annotations

from ..error_core import MellowLangRuntimeError


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
