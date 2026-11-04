"""Inspecting a frozen frame: typed values, scopes, stacks, frames and the
expression evaluator the watch list is read through."""

from __future__ import annotations

from typing import Any

from ...constants import Op


class InspectionMixin:
    def _instr_name(self, op: int) -> str:
        try:
            for name, value in vars(Op).items():
                if not name.startswith('_') and value == op:
                    return str(name)
        except Exception:
            pass
        return f'OP_{op}'


    def _current_frame_depth(self) -> int:
        return len(self.call_stack)


    def _typed_value(self, value: Any) -> dict:
        t = type(value).__name__
        size = None
        try:
            size = len(value)  # type: ignore[arg-type]
        except Exception:
            size = None
        return {
            'type': t,
            'repr': repr(value),
            'value': value,
            'size': size,
        }


    def _typed_scope(self, scope: dict[str, Any]) -> dict[str, dict]:
        return {str(k): self._typed_value(v) for k, v in dict(scope or {}).items()}


    def _typed_stack(self) -> list[dict]:
        return [
            {
                'index': idx,
                **self._typed_value(value),
            }
            for idx, value in enumerate(list(self.stack))
        ]


    def _eval_debug_expr(self, expr: str):
        expr = str(expr or '').strip()
        if not expr:
            return None
        env = {}
        for scope in self.variables:
            env.update(scope)
        env.update(self._keep_values or {})
        env.update({
            'stack_depth': len(self.stack),
            'frame_depth': self._current_frame_depth(),
            'pc': int(self.pc),
        })
        safe_globals = {'__builtins__': {}}
        try:
            return eval(expr, safe_globals, env)
        except Exception as e:
            return f'<error: {e}>'


    def _debug_watch_expr_values(self) -> dict[str, Any]:
        return {expr: self._eval_debug_expr(expr) for expr in self._dbg_watch_exprs}


    def _typed_frames(self) -> list[dict]:
        frames = []
        raw_frames = list(self.frame_stack or [])
        for idx, frame in enumerate(raw_frames):
            frame_name = '<frame>'
            frame_file = self.filename
            frame_line = 0
            if isinstance(frame, dict):
                frame_name = str(frame.get('name', frame_name))
                frame_file = str(frame.get('filename', frame_file))
                try:
                    frame_line = int(frame.get('line', 0) or 0)
                except Exception:
                    frame_line = 0
            frames.append({
                'index': idx,
                'name': frame_name,
                'filename': frame_file,
                'line': frame_line,
                'locals': self._typed_scope(self.variables[idx + 1] if idx + 1 < len(self.variables) else {}),
            })
        if not frames:
            frames.append({
                'index': 0,
                'name': '<main>',
                'filename': self.filename,
                'line': int(self._pos()[0] or 0),
                'locals': self._typed_scope(self.variables[-1] if self.variables else {}),
            })
        return frames
