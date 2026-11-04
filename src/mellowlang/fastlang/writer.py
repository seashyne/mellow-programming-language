"""The indentation and temporary-name helpers every emitter writes through."""

from __future__ import annotations


class WriterMixin:
    # ── Helpers ───────────────────────────────────────────────────────

    def _w(self, line: str = ""):
        self._out.write("    " * self._indent + line + "\n")

    def _w_raw(self, text: str):
        self._out.write(text)

    def _new_tmp(self) -> str:
        self._tmp_counter += 1
        return f"__tmp{self._tmp_counter}"

