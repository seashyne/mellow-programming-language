"""Transpile, compile and exec in one call, with the output captured."""

from __future__ import annotations

from .transpiler import PyTranspiler


# ── Public fast-run API ────────────────────────────────────────────────

class FastRunner:
    """
    Run MellowLang source using compile-to-Python-bytecode fast path.
    ~10-50x faster than bytecode VM for compute-heavy scripts.
    """

    def __init__(self, *, capture_output: bool = False):
        self.capture_output = capture_output
        self._last_py_src: str | None = None

    def run(self, source: str | list[str], *, filename: str | None = None) -> dict:
        """Compile and run MellowLang source. Returns {output, result, py_src}."""
        import io as _io, sys as _sys

        if isinstance(source, str):
            lines = source.splitlines()
        else:
            lines = list(source)

        tp = PyTranspiler()
        py_src = tp.transpile(lines, filename=filename)
        self._last_py_src = py_src

        namespace: dict = {}
        buf = _io.StringIO()

        if self.capture_output:
            old_stdout = _sys.stdout
            _sys.stdout = buf

        try:
            code_obj = compile(py_src, filename or '<mellow>', 'exec')
            exec(code_obj, namespace)
            result = None
        except SystemExit:
            result = None
        except Exception as e:
            if self.capture_output:
                _sys.stdout = old_stdout
            raise
        finally:
            if self.capture_output:
                try:
                    _sys.stdout = old_stdout
                except Exception:
                    pass

        return {
            'output': buf.getvalue() if self.capture_output else None,
            'result': result,
            'py_src': py_src,
        }
