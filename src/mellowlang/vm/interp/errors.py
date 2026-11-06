"""Position lookup, trace building and the runtime/sandbox raise helpers."""

from __future__ import annotations

from ...error_core import MellowLangRuntimeError


class ErrorMixin:
        # Unsupported opcodes in _step: silently ignored (SYSCALL, TRY, etc.)
        # These are handled by the full run() loop only.

# ---------------- Run ----------------

    def _pos(self):
        """Return (line, col) for current pc if available."""
        line = None
        col = None
        if self._line_map and 0 <= self.pc < len(self._line_map):
            ln = int(self._line_map[self.pc] or 0)
            line = ln if ln > 0 else None
        if self._col_map and 0 <= self.pc < len(self._col_map):
            c = int(self._col_map[self.pc] or 1)
            col = c if c > 0 else 1
        return line, col

    def _build_trace(self, line: int | None, col: int | None):
        trace = []
        # frame_stack contains call frames (function/event)
        for fr in self.frame_stack:
            trace.append(dict(fr))
        # add current context frame
        cur_name = trace[-1]["name"] if trace else "<main>"
        trace.append({
            "name": cur_name,
            "filename": self.filename,
            "line": line,
            "col": col,
        })
        return trace

    def _raise_runtime(self, message: str):
        line, col = self._pos()
        raise MellowLangRuntimeError('RUNTIME', message, line, filename=self.filename, col=col, trace=self._build_trace(line, col))

    def _raise_sandbox(self, message: str):
        line, col = self._pos()
        raise MellowLangRuntimeError('SANDBOX', message, line, filename=self.filename, col=col, trace=self._build_trace(line, col))

    def _handle_exception(self, e: Exception):
        # if inside try: jump to catch/finally
        if self._try_stack:
            frame = self._try_stack.pop()
            # restore stack length
            self.stack = self.stack[:frame.get('stack_len', len(self.stack))]
            # bind error name if provided
            err_name = frame.get('err_name')
            if err_name:
                self.variables[-1][err_name] = str(e)
            # jump to catch_pc (or finally_pc)
            self.pc = int(frame.get('catch_pc', self.pc))
            return True
        # otherwise raise pretty runtime error
        self._raise_runtime(str(e))
        return False
