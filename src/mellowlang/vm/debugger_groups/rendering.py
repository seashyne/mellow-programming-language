"""Turning the machine's state into the stop snapshot and its source span,
plus the watch-line rendering the trace hook prints."""

from __future__ import annotations


class RenderingMixin:
    def _debug_dump_watch(self) -> str:
        if not self._dbg_watch:
            return ""
        pairs = []
        for name in self._dbg_watch:
            try:
                val = self._load_var(name)
            except Exception:
                val = None
            pairs.append(f"{name}={self.format_value(val)}")
        return ", ".join(pairs)


    def _source_span(self) -> dict:
        line, col = self._pos()
        end_line = int(line or 0)
        end_col = int(col or 1)
        hint = ''
        if 0 <= self.pc < len(self._span_map):
            raw = self._span_map[self.pc] or {}
            end_line = int(raw.get('end_line', end_line or 0) or 0)
            end_col = int(raw.get('end_col', end_col or 1) or 1)
            hint = str(raw.get('hint', '') or '')
        elif line and 1 <= int(line) <= len(self.source_lines):
            src = self.source_lines[int(line) - 1].rstrip('\n')
            end_col = max(int(col or 1), len(src) or int(col or 1))
            hint = src[max(0, int(col or 1)-1):end_col]
        return {
            'start_line': int(line or 0),
            'start_col': int(col or 1),
            'end_line': end_line,
            'end_col': end_col,
            'hint': hint,
        }


    def _debug_snapshot(self, *, reason: str, note: str | None = None) -> dict:
        line, col = self._pos()
        source = ""
        if self.source_lines and line and 1 <= int(line) <= len(self.source_lines):
            source = self.source_lines[int(line) - 1].rstrip("\n")
        instr = self.bytecode[self.pc] if 0 <= self.pc < len(self.bytecode) else None
        op_name = self._instr_name(instr[0]) if instr else 'HALT'
        operands = list(instr[1:]) if instr else []
        globals_scope = dict(self.variables[0]) if self.variables else {}
        locals_scope = dict(self.variables[-1]) if self.variables else {}
        stack_items = list(self.stack)
        frames = list(self.frame_stack)
        watch_expr_values = self._debug_watch_expr_values()
        snap = {
            'reason': reason,
            'note': note or '',
            'pc': int(self.pc),
            'line': int(line or 0),
            'col': int(col or 1),
            'source': source,
            'opcode': op_name,
            'operands': operands,
            'instruction': list(instr) if instr else [],
            'stack': stack_items,
            'typed_stack': self._typed_stack(),
            'stack_depth': len(stack_items),
            'locals': locals_scope,
            'typed_locals': self._typed_scope(locals_scope),
            'globals': globals_scope,
            'typed_globals': self._typed_scope(globals_scope),
            'frames': frames,
            'typed_frames': self._typed_frames(),
            'live_frame': frames[-1] if frames else {'name': '<main>', 'filename': self.filename},
            'frame_depth': self._current_frame_depth(),
            'watch': self._debug_dump_watch(),
            'watch_values': {name: self._load_var(name) for name in self._dbg_watch},
            'watch_expressions': watch_expr_values,
            'source_span': self._source_span(),
            'source_span_text': self._source_span().get('hint', ''),
            'halted': bool(self._halted),
            'finished': bool(self._halted or self.pc >= len(self.bytecode)),
            'bytecode_window': [
                {
                    'pc': i,
                    'instruction': list(self.bytecode[i]),
                    'opcode': self._instr_name(self.bytecode[i][0]),
                    'line': int(self._line_map[i]) + 1 if i < len(self._line_map) and self._line_map[i] is not None else 0,
                    'col': int(self._col_map[i]) if i < len(self._col_map) and self._col_map[i] is not None else 1,
                }
                for i in range(max(0, self.pc - 2), min(len(self.bytecode), self.pc + 3))
            ],
        }
        self._dbg_last_stop = snap
        self._dbg_history.append(snap)
        if len(self._dbg_history) > 512:
            self._dbg_history = self._dbg_history[-512:]
        return snap
