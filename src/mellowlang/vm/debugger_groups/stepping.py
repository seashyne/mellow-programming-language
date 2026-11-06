"""The execution side of debugging: the trace/step hook, resume modes and the
runtime pause decision."""

from __future__ import annotations


class SteppingMixin:
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
