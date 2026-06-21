from __future__ import annotations

from typing import Any

from ..constants import Op


class DebuggerMixin:
    # ---------------- Sandbox helpers ----------------
    def _parse_break_lines(self, spec: str) -> set[int]:
        out: set[int] = set()
        spec = (spec or "").strip()
        if not spec:
            return out
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    lo = int(a.strip()); hi = int(b.strip())
                except Exception:
                    continue
                if hi < lo:
                    lo, hi = hi, lo
                for n in range(lo, hi + 1):
                    out.add(n)
            else:
                try:
                    out.add(int(part))
                except Exception:
                    continue
        return out

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

    def _debug_hook(self) -> bool:
        """Return False to stop execution."""
        if not (self._dbg_trace or self._dbg_step or self._dbg_break):
            return True
        line, col = self._pos()
        src_line = ""
        if self.source_lines and line and 1 <= int(line) <= len(self.source_lines):
            src_line = self.source_lines[int(line) - 1].rstrip("\n")

        hit_break = bool(line and int(line) in self._dbg_break)
        should_print = self._dbg_trace or hit_break or self._dbg_step
        if should_print:
            watch = self._debug_dump_watch()
            loc = f"{self.filename or '<script>'}:{line}:{col}" if line else (self.filename or "<script>")
            if watch:
                print(f"[trace] {loc} | {src_line}   # {watch}")
            else:
                print(f"[trace] {loc} | {src_line}")

        if self._dbg_step or hit_break:
            if not self._dbg_interactive:
                # non-interactive: stop at first breakpoint; step just prints.
                if hit_break:
                    self._dbg_last_stop = {
                        'reason': 'breakpoint',
                        'line': int(line or 0),
                        'col': int(col or 1),
                        'source': src_line,
                        'watch': self._debug_dump_watch(),
                    }
                    self._dbg_last_stop = {
                        'reason': 'quit',
                        'line': int(line or 0),
                        'col': int(col or 1),
                        'source': src_line,
                        'watch': self._debug_dump_watch(),
                    }
                    return False
                return True

            # interactive prompt
            while True:
                try:
                    cmd = input("mellowdbg (n=next, c=cont, p <var>, s=stack, q=quit)> ").strip()
                except EOFError:
                    return True
                if cmd in ("", "n", "next"):
                    self._dbg_last_stop = {
                        'reason': 'step',
                        'line': int(line or 0),
                        'col': int(col or 1),
                        'source': src_line,
                        'watch': self._debug_dump_watch(),
                    }
                    return True
                if cmd in ("c", "cont", "continue"):
                    self._dbg_step = False
                    return True
                if cmd.startswith("p "):
                    var = cmd[2:].strip()
                    if var:
                        try:
                            val = self._load_var(var)
                            print(f"{var} = {val}")
                        except Exception as e:
                            print(f"(error) {e}")
                    continue
                if cmd in ("s", "stack"):
                    print(self.stack)
                    continue
                if cmd in ("q", "quit", "exit"):
                    return False
                print("unknown command")


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

    def debug_resume(self, mode: str = 'continue'):
        mode = str(mode or 'continue').strip().lower()
        self._dbg_paused = False
        self._dbg_last_stop = None
        self._dbg_runtime_enabled = True
        if mode in ('continue', 'cont'):
            self._dbg_step_plan = None
            self._dbg_skip_pause_once = False
        elif mode in ('step_into', 'into', 'step'):
            self._dbg_step_plan = 'into'
            self._dbg_step_depth = self._current_frame_depth()
            self._dbg_skip_pause_once = True
        elif mode in ('step_over', 'over'):
            self._dbg_step_plan = 'over'
            self._dbg_step_depth = self._current_frame_depth()
            self._dbg_skip_pause_once = True
        elif mode in ('step_out', 'out'):
            self._dbg_step_plan = 'out'
            self._dbg_step_depth = self._current_frame_depth()
            self._dbg_skip_pause_once = True
        else:
            self._dbg_step_plan = None
            self._dbg_skip_pause_once = False

    def _maybe_pause_runtime_debugger(self) -> bool:
        if not self._dbg_runtime_enabled:
            return True
        if self._dbg_skip_pause_once:
            self._dbg_skip_pause_once = False
            self._dbg_started = True
            return True
        instr = self.bytecode[self.pc] if 0 <= self.pc < len(self.bytecode) else None
        op_name = self._instr_name(instr[0]) if instr else 'HALT'
        line, _ = self._pos()
        depth = self._current_frame_depth()
        reason = None
        if not self._dbg_started and self._dbg_pause_on_start:
            reason = 'entry'
        elif self._dbg_step_plan == 'into':
            reason = 'step_into'
        elif self._dbg_step_plan == 'over' and depth <= self._dbg_step_depth:
            reason = 'step_over'
        elif self._dbg_step_plan == 'out' and depth < self._dbg_step_depth:
            reason = 'step_out'
        elif self.pc in self._dbg_break_instrs:
            reason = 'instruction_breakpoint'
        elif op_name in self._dbg_break_opcodes:
            reason = 'opcode_breakpoint'
        elif line and int(line) in self._dbg_break:
            reason = 'breakpoint'
        else:
            for expr in self._dbg_break_when:
                value = self._eval_debug_expr(expr)
                if value is True:
                    reason = 'conditional_breakpoint'
                    break
        if reason:
            self._dbg_step_plan = None
            self._dbg_paused = True
            self._debug_snapshot(reason=reason)
            self._dbg_started = True
            return False
        self._dbg_started = True
        return True

    def run_until_pause(self):
        result = self.run()
        return {
            'paused': bool(self._dbg_paused),
            'finished': bool(self._halted or self.pc >= len(self.bytecode)),
            'result': result,
            'stop': self._dbg_last_stop,
        }
