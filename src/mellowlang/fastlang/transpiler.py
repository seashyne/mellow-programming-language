"""The class the CLI imports, assembled from the three mixins."""

from __future__ import annotations

import io
from ..parser import parse_program
from .builtins import _MELLOW_BUILTINS_SRC
from .expressions import ExpressionMixin
from .statements import StatementMixin
from .writer import WriterMixin


class PyTranspiler(WriterMixin, StatementMixin, ExpressionMixin):
    """
    v1.4.9: MellowLang → Python source transpiler.

    Usage::
        tp = PyTranspiler()
        py_src = tp.transpile(source_lines)
        exec(compile(py_src, '<mellow>', 'exec'), {})
    """

    def __init__(self):
        self._indent = 0
        self._out = io.StringIO()
        self._lambda_counter = 0
        self._tmp_counter = 0

    # ── Public API ────────────────────────────────────────────────────

    def transpile(self, lines: list[str], *, filename: str | None = None) -> str:
        prog = parse_program(lines, filename=filename)
        self._out = io.StringIO()
        self._indent = 0
        # Write builtins preamble
        self._out.write(_MELLOW_BUILTINS_SRC)
        self._out.write("\n# ── Transpiled MellowLang ────────────────────────────────────────\n")
        for stmt in prog.body:
            self._stmt(stmt)
        return self._out.getvalue()
