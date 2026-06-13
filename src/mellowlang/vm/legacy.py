
# frinds/vm.py (v2.2)
from __future__ import annotations
from typing import Any, List
from ..constants import Op
from ..host import HostRegistry, default_host
from ..replay import ReplayConfig, ReplayLog
from ..error_core import MellowLangRuntimeError
from ..range_core import MellowLangRange

class MellowLangVM:
    def __init__(self, bytecode, func_table=None, event_table=None, *, config=None, host: HostRegistry | None = None, replay: ReplayConfig | None = None, filename: str | None = None, source_lines: list[str] | None = None, line_map: list[int] | None = None, col_map: list[int] | None = None, end_line_map: list[int] | None = None, end_col_map: list[int] | None = None, span_map: list[dict] | None = None):
        self.bytecode = bytecode or []
        self.func_table = func_table or {}
        self.event_table = event_table or {}  # event_name -> meta

        self.stack: List[Any] = []
        self.call_stack: List[int] = []
        self.frame_stack: List[dict] = []  # function/event frames for trace
        self.variables = [{}]  # scope stack (0 = global)

        self.pc = 0
        self.precision = None

        # Debug info for pretty errors
        self.filename = filename
        self.source_lines = source_lines or []
        self._line_map = line_map or []
        self._col_map = col_map or []
        self._end_line_map = end_line_map or []
        self._end_col_map = end_col_map or []
        self._span_map = span_map or []
        self._try_stack: list[dict] = []  # stack of try frames

        self.config = {
            # Permissions
            "allow_ask": False,
            "allow_wait": True,
            "allow_storage": True,

            # Limits
            "max_steps": 200_000,
            "max_stack": 2_000,
            "max_string_len": 20_000,
            "max_list_len": 5_000,
            "max_map_keys": 2_000,

            # Budget for syscalls (anti-spam)
            "syscall_budget": 500,
        }
        if config:
            self.config.update(config)

        # ---------------- Project mode (v1.4.5 standard) ----------------
        # In project mode, storage is locked under <project_root>/<sandbox_root>.
        # Host filesystem operations via fs_* are deny-by-default unless allowlisted.
        import os as _os
        if bool(self.config.get('project_mode', False)):
            pr = self.config.get('project_root') or _os.getcwd()
            sr = self.config.get('sandbox_root') or 'saves'
            pr = _os.path.abspath(str(pr))
            sr = str(sr).strip().strip('"').strip("'").replace('\\', '/')
            if not sr:
                sr = 'saves'
            # Default storage dir is the sandbox root
            base = self.config.get('storage_dir')
            if base is None or str(base).strip() in ('', '.', 'mellow_saves', 'saves'):
                self.config['storage_dir'] = _os.path.join(pr, sr)
            else:
                # Treat provided storage_dir as a namespace under sandbox_root
                raw = str(base).strip().strip('"').strip("'")
                raw = raw.replace('\\', '/').lstrip('/')
                self.config['storage_dir'] = _os.path.join(pr, sr, raw)
            self.config['project_root'] = pr
            self.config['sandbox_root'] = sr

        self.host = host or default_host()
        self._steps = 0
        self._budget = int(self.config.get("syscall_budget", 500))

        # ---------------- Debugger (v1.2.0) ----------------
        import sys as _sys
        self._dbg_trace = bool(self.config.get("debug_trace", False))
        self._dbg_step = bool(self.config.get("debug_step", False))
        self._dbg_interactive = bool(self._dbg_step) and bool(_sys.stdin.isatty()) and bool(_sys.stdout.isatty())
        self._dbg_watch = [x.strip() for x in str(self.config.get("debug_watch", "")).split(",") if x.strip()]
        self._dbg_break = self._parse_break_lines(str(self.config.get("debug_break_lines", "")))
        self._dbg_break_instrs = self._parse_break_lines(str(self.config.get("debug_break_instrs", "")))
        self._dbg_break_opcodes = {x.strip().upper() for x in str(self.config.get("debug_break_opcodes", "")).split(",") if x.strip()}
        self._dbg_pause_on_start = bool(self.config.get("debug_pause_on_start", False))
        self._dbg_break_when = [x.strip() for x in str(self.config.get("debug_break_when", "")).split(";") if x.strip()]
        self._dbg_watch_exprs = [x.strip() for x in str(self.config.get("debug_watch_exprs", "")).split(";") if x.strip()]
        self._dbg_runtime_enabled = bool(self._dbg_trace or self._dbg_step or self._dbg_break or self._dbg_break_instrs or self._dbg_break_opcodes or self._dbg_pause_on_start or self._dbg_break_when or self._dbg_watch_exprs)
        self._dbg_skip_pause_once = False
        self._dbg_step_plan = None
        self._dbg_step_depth = 0
        self._dbg_started = False
        self._dbg_paused = False
        self._dbg_history = []
        self._dbg_last_stop = None
        self._halted = False
        self._last_result = None

        # AI decision timeline (v1.2.0)
        self._ai_trace = bool(self.config.get("ai_trace", False))
        self._ai_timeline_path = self.config.get("ai_timeline")
        self._ai_events: list[dict] = []

        # Deterministic RNG + Replay
        import random as _random
        import time as _time
        import hashlib as _hashlib

        self._replay = ReplayLog(replay or ReplayConfig())
        self._t0 = _time.monotonic()
        self._profile = bool(self.config.get('profile', False))
        self._opcounts = {}  # opcode -> count

        # Global base seed (optional): used to derive per-script seeds deterministically.
        # This keeps MellowLang identity: deterministic-by-default + sandboxed (no external entropy).
        self._global_seed = None
        if "global_seed" in self.config:
            try:
                self._global_seed = int(self.config.get("global_seed"))
            except Exception:
                self._global_seed = None
        else:
            # NOTE(v3.6.1): do not load global seed from disk implicitly
            self._global_seed = None

        def _derive_seed(base: int, name: str) -> int:
            payload = f"{int(base)}::{name}".encode("utf-8")
            digest = _hashlib.sha256(payload).digest()
            return int.from_bytes(digest[:8], "little", signed=False)

        if (replay or ReplayConfig()).mode == "replay":
            seed = int(self._replay.next_seed())
        else:
            if self._global_seed is not None:
                seed = _derive_seed(int(self._global_seed), str(self.filename or "<memory>"))
            else:
                seed = int(self.config.get("seed", 12345))
            self._replay.record_seed(seed)

        self.rng = _random.Random(seed)

        # ---------------- Persistent keep store ----------------
        # keep vars survive across runs by default (can be disabled via config)
        self._keep_dirty = False
        self._keep_enabled = bool(self.config.get("allow_storage", True)) and bool(self.config.get("keep_persistent", True))
        self._keep_values: dict[str, Any] = {}
        if self._keep_enabled:
            try:
                # isolate by filename (script) to avoid collisions
                key = (self.filename or "<memory>")
                data = self._load_json(f"__keep__{key}")
                if isinstance(data, dict):
                    self._keep_values = data
            except Exception:
                # keep is best-effort; never break sandbox on load
                self._keep_values = {}

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

    def _tick(self):
        self._steps += 1
        if self._steps > int(self.config.get("max_steps", 200_000)):
            self._raise_sandbox("Step limit exceeded")
        max_ms = self.config.get('max_ms', None)
        if max_ms is not None:
            import time as _time
            if (_time.monotonic() - self._t0) * 1000.0 > float(max_ms):
                self._raise_sandbox('Time limit exceeded')
        if len(self.stack) > int(self.config.get("max_stack", 2_000)):
            self._raise_sandbox("Stack limit exceeded")

    def _enforce_value_limits(self, v):
        ms = int(self.config.get("max_string_len", 20_000))
        ml = int(self.config.get("max_list_len", 5_000))
        mk = int(self.config.get("max_map_keys", 2_000))
        if isinstance(v, str) and len(v) > ms:
            self._raise_sandbox("String too large")
        if isinstance(v, list) and len(v) > ml:
            self._raise_sandbox("List too large")
        if isinstance(v, dict) and len(v) > mk:
            self._raise_sandbox("Map too large")

    # ---------------- Utilities ----------------
    def format_value(self, val):
        if isinstance(val, dict) and val.get("type") == "money":
            return f"{val.get('currency', 'USD')} {val.get('amount', '0.00')}"
        if isinstance(val, (float, int)):
            if self.precision is not None:
                try:
                    return f"{float(val):.{int(self.precision)}f}"
                except:
                    pass
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            return str(val)
        return str(val)

    def _load_var(self, name):
        for scope in reversed(self.variables):
            if name in scope:
                return scope[name]
        if self._keep_enabled and name in self._keep_values:
            return self._keep_values.get(name)
        return 0

    def _truthy(self, v) -> bool:
        return bool(v)

    # ---------------- Syscall ----------------
    def _syscall(self, name: str, args: list):
        if not isinstance(name, str):
            self._raise_sandbox("syscall name must be string")

        # --- v1.4.7: emit() — fire event to on-handler ---
        if name == "std.event.emit":
            event_name = str(args[0]) if len(args) >= 1 else ""
            event_args = list(args[1]) if len(args) >= 2 and isinstance(args[1], list) else args[1:]
            return self.emit(event_name, event_args)

        # --- Built-in AI helpers (v1.2.0) ---
        if name in ("std.ai.decide", "ai.decide"):
            label = str(args[0]) if len(args) >= 1 else ""
            reason = str(args[1]) if len(args) >= 2 else ""
            if self._ai_trace:
                line, col = self._pos()
                self._ai_events.append({
                    "t": int(self._steps),
                    "line": int(line) if line else None,
                    "col": int(col) if col else None,
                    "label": label,
                    "reason": reason,
                })
            return label

        if name == "std.ai.utility_choose":
            # args: list of {"score": number, "value": any}
            opts = args[0] if args else []
            if not isinstance(opts, list):
                self._raise_runtime("utility_choose expects list")
            best = None
            best_score = None
            for it in opts:
                if not isinstance(it, dict):
                    continue
                sc = it.get("score", 0)
                try:
                    scf = float(sc)
                except Exception:
                    scf = 0.0
                if best is None or scf > float(best_score):
                    best = it
                    best_score = scf
            return None if best is None else best.get("value")

        if name == "std.ai.bt_tick":
            tree = args[0] if len(args) >= 1 else None
            ctx = args[1] if len(args) >= 2 else {}
            return self._bt_tick(tree, ctx)

        if name == "std.ai.fsm_tick":
            fsm = args[0] if len(args) >= 1 else None
            ctx = args[1] if len(args) >= 2 else {}
            return self._fsm_tick(fsm, ctx)
        if not self.host.has(name):
            self._raise_sandbox(f"syscall not allowed: {name}")

        cost = int(self.host.get_cost(name))
        self._budget -= cost
        if self._budget < 0:
            self._raise_sandbox("syscall budget exceeded")

        # Replay mode: return recorded result without calling host
        if self._replay.cfg.mode == "replay":
            res = self._replay.next_syscall_result(name, args)
            self._enforce_value_limits(res)
            return res

        res = self.host.call(name, args)
        self._enforce_value_limits(res)
        self._replay.record_syscall(name, args, res)
        return res

    # ---------------- AI helpers (v1.2.0) ----------------
    def _bt_tick(self, node: Any, ctx: Any) -> str:
        """Behavior Tree tick.

        Node representation (dict):
          {"type": "selector"|"sequence"|"condition"|"action", ...}
        Condition/action nodes call host syscalls:
          {"type":"condition","sys":"game.sees_player","args":[...]}
          {"type":"action","sys":"game.move_to","args":[...]}

        Return status: "success"|"fail"|"running"
        """
        if node is None:
            return "fail"
        if not isinstance(node, dict):
            self._raise_runtime("bt_tick expects node map")
        t = str(node.get("type", ""))
        if t == "selector":
            children = node.get("children", [])
            if not isinstance(children, list):
                children = []
            for ch in children:
                st = self._bt_tick(ch, ctx)
                if st in ("success", "running"):
                    return st
            return "fail"
        if t == "sequence":
            children = node.get("children", [])
            if not isinstance(children, list):
                children = []
            for ch in children:
                st = self._bt_tick(ch, ctx)
                if st in ("fail", "running"):
                    return st
            return "success"
        if t == "condition":
            sysname = str(node.get("sys", ""))
            a = node.get("args", [])
            if not isinstance(a, list):
                a = [a]
            ok = self._syscall(sysname, a)
            return "success" if self._truthy(ok) else "fail"
        if t == "action":
            sysname = str(node.get("sys", ""))
            a = node.get("args", [])
            if not isinstance(a, list):
                a = [a]
            res = self._syscall(sysname, a)
            # allow host to return status string; otherwise treat truthy => success
            if isinstance(res, str) and res in ("success", "fail", "running"):
                return res
            return "success" if self._truthy(res) else "fail"
        return "fail"

    def _fsm_tick(self, fsm: Any, ctx: Any) -> Any:
        """Tiny FSM helper.

        fsm map:
          {"state":"idle", "on_tick": {"idle":"game.idle_tick", ...}}
        tick calls the current state's on_tick syscall, if present.
        """
        if fsm is None:
            self._raise_runtime("fsm_tick expects fsm map")
        if not isinstance(fsm, dict):
            self._raise_runtime("fsm_tick expects fsm map")
        state = str(fsm.get("state", ""))
        table = fsm.get("on_tick", {})
        if isinstance(table, dict) and state in table:
            sysname = str(table.get(state))
            if sysname:
                return self._syscall(sysname, [ctx] if ctx is not None else [])
        return None

    # ---------------- Storage helpers ----------------
    def _safe_path(self, filename: Any) -> str:
        import os
        base_dir = self.config.get("storage_dir", "mellow_saves")
        raw = str(filename).strip().strip('"').strip("'")
        raw = raw.replace('\\', '/').lstrip('/')
        if not raw or raw in ('.', '..'):
            raw = 'save.json'

        # Force .json extension for storage save/load
        if not raw.lower().endswith('.json'):
            raw = raw + '.json'

        # Join under base_dir and prevent traversal / absolute paths.
        # NOTE: Use absolute-path containment check so that base_dir="." works
        # (Python/Lua-style relative file paths).
        base_abs = os.path.abspath(base_dir)
        path = os.path.normpath(os.path.join(base_dir, raw))
        path_abs = os.path.abspath(path)
        if not (path_abs == base_abs or path_abs.startswith(base_abs + os.sep)):
            self._raise_sandbox("invalid storage path (path traversal blocked)")
        return path

    def _safe_fs_path(self, subpath: Any) -> tuple[str, str]:
        """Return (full_path, base_dir) for file operations under sandbox base dir.

        Unlike _safe_path (JSON storage), this does NOT force .json extension.
        """
        import os
        base_dir = self.config.get("storage_dir", "mellow_saves")
        raw = "" if subpath is None else str(subpath)
        raw = raw.strip().strip('"').strip("'")
        raw = raw.replace('\\', '/').lstrip('/')
        # empty/"." means base dir
        if raw in ('.', ''):
            raw = ''
        if raw == '..' or raw.startswith('../') or raw.startswith('..\\'):
            self._raise_sandbox("invalid file path (path traversal blocked)")

        base_abs = os.path.abspath(base_dir)
        full = os.path.normpath(os.path.join(base_dir, raw)) if raw else os.path.normpath(base_dir)
        full_abs = os.path.abspath(full)
        if not (full_abs == base_abs or full_abs.startswith(base_abs + os.sep)):
            self._raise_sandbox("invalid file path (path traversal blocked)")
        return full, os.path.normpath(base_dir)

    # ---------------- Host filesystem (project permissions) ----------------
    def _parse_allowlist(self, s: Any) -> list[str]:
        if s is None:
            return []
        txt = str(s)
        parts = [p.strip() for p in txt.split(',') if p.strip()]
        out: list[str] = []
        for p in parts:
            p = p.replace('\\', '/').strip()
            # Keep allowlist relative to project_root for portability
            if p.startswith('/') or (len(p) >= 2 and p[1] == ':'):
                # absolute allowlists are not portable; ignore in safe project mode
                continue
            # normalize
            p = p.lstrip('./')
            if p == '':
                p = '.'
            out.append(p)
        return out

    def _fs_resolve(self, path: Any, *, op: str) -> str:
        """Resolve a host filesystem path and enforce allowlist in project mode."""
        import os
        raw = '' if path is None else str(path)
        raw = raw.strip().strip('"').strip("'").replace('\\', '/').strip()
        if raw in ('', '.'):  # treat as project root (mainly for mkdir)
            raw = '.'

        project_mode = bool(self.config.get('project_mode', False))
        unsafe = bool(self.config.get('allow_unsafe_fs', False))

        # Disallow traversal by default
        if (raw == '..' or raw.startswith('../') or raw.startswith('..\\')) and (project_mode or not unsafe):
            self._raise_sandbox('fs: ".." traversal is blocked')

        # absolute paths: allowed only if unsafe_fs and not in project mode
        if os.path.isabs(raw):
            if project_mode:
                self._raise_sandbox('fs: absolute paths are disabled in project mode')
            if not unsafe:
                self._raise_sandbox('fs: absolute paths are disabled by default (run with --unsafe-fs for dev)')
            return os.path.abspath(raw)

        if project_mode:
            pr = os.path.abspath(str(self.config.get('project_root') or os.getcwd()))
            full = os.path.abspath(os.path.join(pr, raw))
            allow_key = 'fs_read_allow' if op == 'read' else 'fs_write_allow'
            allowed = self._parse_allowlist(self.config.get(allow_key))
            # deny-by-default
            ok = False
            for a in allowed:
                base = pr if a in ('.', '') else os.path.abspath(os.path.join(pr, a))
                if full == base or full.startswith(base + os.sep):
                    ok = True
                    break
            if not ok:
                # Provide a deterministic hint
                need = raw.split('/')[0] if '/' in raw else raw
                suggest = f"fs.{op}:./{need}" if need and need != '.' else f"fs.{op}:."
                self._raise_sandbox(
                    f"fs access denied ({op}): {raw}\nHint: add permission in mellow.json: \"{suggest}\""
                )
            return full

        # Dev mode: relative to CWD
        return os.path.abspath(os.path.join(os.getcwd(), raw))

    def _save_json(self, filename: Any, value: Any):
        if not self.config.get("allow_storage", True):
            self._raise_sandbox("storage is disabled")
        import json, os, tempfile
        path = self._safe_path(filename)

        # Base storage directory is NOT auto-created.
        base_dir = self.config.get("storage_dir", "mellow_saves")
        if not os.path.isdir(base_dir):
            # System base storage dir: created automatically on first use.
            os.makedirs(base_dir, exist_ok=True)

        # If user asked for subfolder, they must create it themselves.
        dirpath = os.path.dirname(path) or base_dir
        if os.path.normpath(dirpath) != os.path.normpath(base_dir) and not os.path.exists(dirpath):
            self._raise_runtime(f"Folder not found: {dirpath} (create it first)")

        # Atomic write: write temp then replace
        fd, tmp = tempfile.mkstemp(prefix=".mellow_", suffix=".tmp", dir=dirpath)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False)
            os.replace(tmp, path)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def _load_json(self, filename: Any):
        if not self.config.get("allow_storage", True):
            self._raise_sandbox("storage is disabled")
        import json, os
        path = self._safe_path(filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    
    # ---------------- Events ----------------
    def emit(self, event_name: str, args: list | None = None):
        """Trigger an event handler registered via on("event"):. Returns handler return value."""
        args = args or []
        if event_name not in self.event_table:
            return None
        meta = self.event_table[event_name]
        self._replay.record_emit(event_name, args)

        # Push args onto stack
        pcount = int(meta.get("param_count", 0))
        for a in args:
            self.stack.append(a)
        for _ in range(pcount - len(args)):
            self.stack.append(None)

        # Set up call frame — use len(bytecode) as sentinel return address
        # When RETURN pops this address, pc will be out-of-range → run() exits
        sentinel_pc = len(self.bytecode)
        self.call_stack.append(sentinel_pc)
        self.frame_stack.append({
            "name": f"event:{event_name}",
            "filename": self.filename,
            "line": None, "col": None
        })
        self.variables.append({})

        saved_pc = self.pc
        self.pc = int(meta["address"])
        self.run()  # runs until RETURN pops sentinel_pc → pc = sentinel_pc → loop exits

        result = self.stack.pop() if self.stack else None
        self.pc = saved_pc
        return result

# ---------------- Callable function helper ----------------

    def _call_fn(self, fn_name_or_ref, args: list):
        """v1.4.9: Call a user-defined function from inside the VM (e.g. for list_map).
        Accepts a string name or a ("__func__", name) tuple.
        Returns the function's return value.
        """
        # Resolve name
        if isinstance(fn_name_or_ref, tuple) and len(fn_name_or_ref) == 2 and fn_name_or_ref[0] == "__func__":
            fn_name = fn_name_or_ref[1]
        else:
            fn_name = str(fn_name_or_ref)

        if fn_name not in self.func_table:
            return None

        fn_meta = self.func_table[fn_name]
        pcount = int(fn_meta.get('param_count', 0))
        defaults = fn_meta.get('defaults', {})
        params = fn_meta.get('params', [])

        # Build a sub-VM with the same bytecode and func_table
        sub = MellowLangVM(
            self.bytecode,
            func_table=self.func_table,
            event_table=self.event_table,
            config=dict(self.config),
        )
        # Copy current global variables (read-only snapshot)
        sub.variables = [dict(self.variables[0])]  # global scope copy

        # Push args + defaults onto sub-VM stack
        for i, param in enumerate(params):
            if i < len(args):
                sub.stack.append(args[i])
            else:
                # Use default if available
                default_val = defaults.get(param, None)
                sub.stack.append(default_val)

        # Set up call frame: push None as sentinel return address
        sub.call_stack.append(None)
        sub.frame_stack.append({"name": fn_name, "filename": self.filename, "line": 0, "col": 0})
        sub.variables.append({})
        sub.pc = int(fn_meta['address'])

        # Run until RETURN with None return address (function top-level return)
        import sys as _sys
        from ..constants import Op as _Op
        _guard = int(self.config.get('max_steps', 200_000))
        while _guard > 0 and 0 <= sub.pc < len(sub.bytecode):
            _guard -= 1
            ci = sub.bytecode[sub.pc]
            if ci[0] in (_Op.HALT, _Op.STOP):
                break
            if ci[0] == _Op.RETURN:
                rv = sub.stack.pop() if sub.stack else None
                sub.variables.pop()
                if sub.frame_stack:
                    sub.frame_stack.pop()
                ra = sub.call_stack.pop() if sub.call_stack else None
                if ra is None:
                    return rv
                sub.pc = ra
                continue
            sub.pc += 1
            try:
                sub._step(ci)
            except Exception:
                pass  # silently ignore errors in sub-calls (safe sandbox)

        return None

    def _step(self, instr: tuple):
        """Execute a single instruction. Used by _call_fn."""
        from ..constants import Op as _Op
        op = instr[0]
        if op == _Op.PUSH:
            self.stack.append(instr[1])
        elif op == _Op.LOAD:
            _ln = instr[1]
            _lv = None; _found = False
            for _scope in reversed(self.variables):
                if _ln in _scope:
                    _lv = _scope[_ln]; _found = True; break
            if not _found:
                _lv = ("__func__", _ln) if _ln in self.func_table else 0
            self.stack.append(_lv)
        elif op == _Op.STORE or op == _Op.STORE_AUTO:
            self.variables[-1][instr[1]] = self.stack.pop() if self.stack else None
        elif op == _Op.ARG:
            self.variables[-1][instr[1]] = self.stack.pop() if self.stack else None
        elif op == _Op.ADD:
            b = self.stack.pop(); a = self.stack.pop()
            self.stack.append(a + b if not (isinstance(a, str) or isinstance(b, str)) else str(a) + str(b))
        elif op == _Op.SUB:
            b = self.stack.pop(); a = self.stack.pop(); self.stack.append(a - b)
        elif op == _Op.MUL:
            b = self.stack.pop(); a = self.stack.pop(); self.stack.append(a * b)
        elif op == _Op.DIV:
            b = self.stack.pop(); a = self.stack.pop()
            self.stack.append(a / b if b != 0 else 0)
        elif op == _Op.MOD:
            b = self.stack.pop(); a = self.stack.pop()
            self.stack.append(int(a) % int(b) if isinstance(a, int) and isinstance(b, int) else float(a) % float(b))
        elif op == _Op.POW_OP:
            b = self.stack.pop(); a = self.stack.pop()
            r = float(a) ** float(b); self.stack.append(int(r) if r == int(r) else r)
        elif op == _Op.COMPARE:
            b = self.stack.pop(); a = self.stack.pop(); oper = instr[1]
            cmp_map = {'==': a==b, '!=': a!=b, '<': a<b, '>': a>b, '<=': a<=b, '>=': a>=b}
            self.stack.append(cmp_map.get(oper, False))
        elif op == _Op.BOOL_AND:
            b = self.stack.pop(); a = self.stack.pop(); self.stack.append(self._truthy(a) and self._truthy(b))
        elif op == _Op.BOOL_OR:
            b = self.stack.pop(); a = self.stack.pop(); self.stack.append(self._truthy(a) or self._truthy(b))
        elif op == _Op.BOOL_NOT:
            self.stack.append(not self._truthy(self.stack.pop() if self.stack else None))
        elif op == _Op.JUMP:
            self.pc = int(instr[1]) - 1  # -1 because caller does pc+=1 after _step
        elif op == _Op.JIF:
            cond = self.stack.pop() if self.stack else None
            if not self._truthy(cond):
                self.pc = int(instr[1]) - 1
        elif op == _Op.CALL:
            fn = instr[1]; argc = int(instr[2]) if len(instr) > 2 else 0
            call_args = []
            for _ in range(argc):
                call_args.append(self.stack.pop() if self.stack else None)
            call_args.reverse()
            # Resolve variable-stored function refs
            fn_ref = self._load_var(fn)
            if isinstance(fn_ref, tuple) and len(fn_ref) == 2 and fn_ref[0] == "__func__":
                fn = fn_ref[1]
            if fn in self.func_table:
                result = self._call_fn(fn, call_args)
                self.stack.append(result)
            else:
                self.stack.append(None)
        elif op == _Op.SYSCALL:
            # Support syscalls in _step (for lambdas using string ops etc.)
            argc = int(instr[1]) if len(instr) > 1 else 0
            s_args = []
            for _ in range(argc):
                s_args.append(self.stack.pop() if self.stack else None)
            s_args.reverse()
            sc_name = self.stack.pop() if self.stack else ''
            try:
                result = self._syscall(str(sc_name), s_args)
                self.stack.append(result)
            except Exception:
                self.stack.append(None)
        elif op == _Op.GETITEM:
            idxv = self.stack.pop(); target = self.stack.pop()
            if isinstance(target, (list, str)):
                i2 = int(idxv)
                self.stack.append(target[i2] if -len(target) <= i2 < len(target) else None)
            elif isinstance(target, dict):
                self.stack.append(target.get(idxv, None))
            else:
                self.stack.append(None)
        elif op == _Op.BUILD_LIST:
            n = int(instr[1]); items = [self.stack.pop() for _ in range(n)]; items.reverse()
            self.stack.append(items)
        elif op == _Op.BUILD_MAP:
            n = int(instr[1]); d = {}
            for _ in range(n):
                v = self.stack.pop(); k = self.stack.pop(); d[str(k)] = v
            self.stack.append(d)
        elif op == _Op.POP:
            if self.stack: self.stack.pop()
        elif op == _Op.LEN:
            v = self.stack.pop() if self.stack else None
            self.stack.append(len(v) if hasattr(v, '__len__') else 0)
        elif op == _Op.PRINT:
            v = self.stack.pop() if self.stack else None
            import sys as _sys; print(self.format_value(v))
        elif op == _Op.PRINTN:
            n = int(instr[1])
            vals = [self.stack.pop() for _ in range(n)]; vals.reverse()
            import sys as _sys; print(' '.join(self.format_value(v) for v in vals))
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
    def run(self):
        if self._halted:
            return self._last_result
        while self.pc < len(self.bytecode):
            self._tick()
            if not self._maybe_pause_runtime_debugger():
                break
            if not self._debug_hook():
                # stop requested by debugger
                break
            instr = self.bytecode[self.pc]
            op = instr[0]
            if self._profile:
                self._opcounts[op] = self._opcounts.get(op, 0) + 1
            try:
                if op in (Op.HALT, Op.STOP):
                    self._halted = True
                    break

                elif op == Op.TRY:
                    catch_pc = int(instr[1])
                    finally_pc = int(instr[2])
                    err_name = instr[3] if len(instr) > 3 else None
                    self._try_stack.append({
                        'catch_pc': catch_pc,
                        'finally_pc': finally_pc,
                        'err_name': err_name,
                        'stack_len': len(self.stack),
                    })

                elif op == Op.ENDTRY:
                    if self._try_stack:
                        self._try_stack.pop()

                elif op == Op.PUSH:
                    val = instr[1]
                    # Normalize simple literals
                    if isinstance(val, str):
                        low = val.lower()
                        if low == 'true': val = True
                        elif low == 'false': val = False
                        elif low in ('none', 'null'): val = None
                        else:
                            s = val
                            if s.replace('.', '', 1).replace('-', '', 1).isdigit():
                                val = float(s) if '.' in s else int(s)
                    self._enforce_value_limits(val)
                    self.stack.append(val)

                elif op == Op.STORE:
                    self.variables[-1][instr[1]] = self.stack.pop() if self.stack else None

                elif op == Op.STORE_AUTO:
                    name = instr[1]
                    val = self.stack.pop() if self.stack else None
                    self.variables[-1][name] = val
                    # If the name exists in keep store, keep it in sync (ergonomic updates)
                    if self._keep_enabled and name in self._keep_values:
                        self._keep_values[name] = val
                        self._keep_dirty = True

                elif op == Op.STORE_KEEP:
                    name = instr[1]
                    val = self.stack.pop() if self.stack else None
                    # always store in current scope too (ergonomic)
                    self.variables[-1][name] = val
                    if self._keep_enabled:
                        self._keep_values[name] = val
                        self._keep_dirty = True

                elif op == Op.SEED:
                    # seed deterministic RNG
                    seed_val = self.stack.pop() if self.stack else 0
                    try:
                        seed_int = int(seed_val)
                    except Exception:
                        seed_int = 0
                    if self._replay.cfg.mode == "replay":
                        seed_int = int(self._replay.next_seed())
                    else:
                        self._replay.record_seed(seed_int)
                    import random as _random
                    self.rng = _random.Random(seed_int)

                elif op == Op.GLOBAL_SEED:
                    # global_seed(n): set global base seed, persist (best-effort),
                    # then derive and reseed current script RNG.
                    seed_val = self.stack.pop() if self.stack else 0
                    try:
                        base = int(seed_val)
                    except Exception:
                        base = 0

                    # NOTE(v3.6.1): do not persist global seed to disk implicitly

                    self._global_seed = base

                    # Derive deterministic per-script seed
                    try:
                        import hashlib as _hashlib
                        payload = f"{int(base)}::{str(self.filename or '<memory>')}".encode("utf-8")
                        digest = _hashlib.sha256(payload).digest()
                        seed_int = int.from_bytes(digest[:8], "little", signed=False)
                    except Exception:
                        seed_int = int(base)

                    if self._replay.cfg.mode == "replay":
                        seed_int = int(self._replay.next_seed())
                    else:
                        self._replay.record_seed(seed_int)

                    import random as _random
                    self.rng = _random.Random(seed_int)

                elif op == Op.LOAD:
                    _ln = instr[1]
                    # v1.4.9: first check variables/keep, then func_table as func ref
                    _lv = None
                    _found = False
                    for _scope in reversed(self.variables):
                        if _ln in _scope:
                            _lv = _scope[_ln]; _found = True; break
                    if not _found and self._keep_enabled and _ln in self._keep_values:
                        _lv = self._keep_values[_ln]; _found = True
                    if not _found:
                        _lv = ("__func__", _ln) if _ln in self.func_table else 0
                    self.stack.append(_lv)

                elif op == Op.ADD:
                    b = self.stack.pop(); a = self.stack.pop()
                    if isinstance(a, str) or isinstance(b, str):
                        out = self.format_value(a) + self.format_value(b)
                        self._enforce_value_limits(out)
                        self.stack.append(out)
                    else:
                        self.stack.append(a + b)

                elif op == Op.SUB:
                    b = self.stack.pop(); a = self.stack.pop()
                    self.stack.append(a - b)

                elif op == Op.MUL:
                    b = self.stack.pop(); a = self.stack.pop()
                    self.stack.append(a * b)

                elif op == Op.DIV:
                    b = self.stack.pop(); a = self.stack.pop()
                    # raise on division by zero (catchable by try/catch)
                    if b == 0:
                        raise ZeroDivisionError('division by zero')
                    self.stack.append(a / b)

                elif op == Op.PRINT:
                    print(self.format_value(self.stack.pop() if self.stack else None))

                elif op == Op.PRINTN:
                    n = int(instr[1]) if len(instr) > 1 else 0
                    vals = []
                    for _ in range(max(0, n)):
                        vals.append(self.stack.pop() if self.stack else None)
                    vals.reverse()
                    out = " ".join(self.format_value(v) for v in vals)
                    self._enforce_value_limits(out)
                    print(out)

                elif op == Op.SHOW_PREC:
                    self.precision = self.stack.pop()

                elif op == Op.COMPARE:
                    cmp_op = instr[1] if len(instr) > 1 else '=='
                    b = self.stack.pop(); a = self.stack.pop()
                    num_ok = True
                    try:
                        af = float(a); bf = float(b)
                    except:
                        num_ok = False
                    if num_ok:
                        if cmp_op == '==': res = (af == bf)
                        elif cmp_op == '!=': res = (af != bf)
                        elif cmp_op == '>': res = (af > bf)
                        elif cmp_op == '<': res = (af < bf)
                        elif cmp_op == '>=': res = (af >= bf)
                        elif cmp_op == '<=': res = (af <= bf)
                        else: res = False
                    else:
                        if cmp_op == '==': res = (a == b)
                        elif cmp_op == '!=': res = (a != b)
                        else: res = False
                    self.stack.append(res)

                elif op == Op.BOOL_AND:
                    b = self.stack.pop(); a = self.stack.pop()
                    self.stack.append(self._truthy(a) and self._truthy(b))

                elif op == Op.BOOL_OR:
                    b = self.stack.pop(); a = self.stack.pop()
                    self.stack.append(self._truthy(a) or self._truthy(b))

                elif op == Op.BOOL_NOT:
                    a = self.stack.pop()
                    self.stack.append(not self._truthy(a))

                elif op == Op.LEN:
                    a = self.stack.pop()
                    try:
                        if isinstance(a, (list, dict, str, MellowLangRange)):
                            self.stack.append(len(a))
                        elif hasattr(a, "__len__") and hasattr(a, "__getitem__"):
                            # allow safe view-like iterables
                            self.stack.append(int(len(a)))
                        else:
                            self.stack.append(0)
                    except Exception:
                        self.stack.append(0)

                elif op == Op.GETITEM:
                    idxv = self.stack.pop()
                    target = self.stack.pop()
                    try:
                        if isinstance(target, list):
                            i2 = int(idxv)
                            if i2 < 0: i2 = len(target) + i2
                            self.stack.append(target[i2] if 0 <= i2 < len(target) else None)
                        elif isinstance(target, dict):
                            self.stack.append(target.get(idxv, None))
                        elif isinstance(target, str):
                            i2 = int(idxv)
                            if i2 < 0: i2 = len(target) + i2
                            self.stack.append(target[i2] if 0 <= i2 < len(target) else '')
                        elif isinstance(target, MellowLangRange):
                            i2 = int(idxv)
                            if i2 < 0: i2 = len(target) + i2
                            self.stack.append(target[i2] if 0 <= i2 < len(target) else None)
                        elif hasattr(target, "__getitem__"):
                            i2 = int(idxv) if isinstance(idxv, (int, float, bool)) or (isinstance(idxv, str) and idxv.lstrip('-').isdigit()) else idxv
                            if isinstance(i2, int) and i2 < 0:
                                try: i2 = len(target) + i2
                                except: pass
                            try:
                                self.stack.append(target[i2])
                            except Exception:
                                self.stack.append(None)
                        else:
                            self.stack.append(None)
                    except Exception:
                        self.stack.append(None)

                elif op == Op.BUILD_LIST:
                    n = int(instr[1])
                    items = []
                    for _ in range(n):
                        items.append(self.stack.pop() if self.stack else None)
                    items.reverse()
                    self._enforce_value_limits(items)
                    self.stack.append(items)

                elif op == Op.BUILD_MAP:
                    n = int(instr[1])
                    d = {}
                    for _ in range(n):
                        val = self.stack.pop() if self.stack else None
                        key = self.stack.pop() if self.stack else None
                        if not isinstance(key, str):
                            key = str(key)
                        d[key] = val
                    self._enforce_value_limits(d)
                    self.stack.append(d)

                elif op == Op.JUMP:
                    self.pc = instr[1]
                    continue

                elif op == Op.JIF:
                    cond = self.stack.pop() if self.stack else False
                    if not self._truthy(cond):
                        self.pc = instr[1]
                        continue

                elif op == Op.CALL:
                    f_name = instr[1]
                    argc = int(instr[2]) if len(instr) > 2 else 0
                    # v1.4.9: first-class fn – variable might hold a ("__func__", name) ref
                    _call_var = self._load_var(f_name)
                    if isinstance(_call_var, tuple) and len(_call_var) == 2 and _call_var[0] == "__func__":
                        f_name = _call_var[1]
                    if f_name in self.func_table:
                        pcount = int(self.func_table[f_name].get('param_count', 0))
                        if argc > pcount:
                            self._raise_sandbox(f"too many args for {f_name} (got {argc}, want {pcount})")
                        for _ in range(pcount - argc):
                            self.stack.append(None)

                        # push return address + frame info
                        call_line, call_col = self._pos()
                        self.call_stack.append(self.pc + 1)
                        self.frame_stack.append({
                            "name": f_name,
                            "filename": self.filename,
                            "line": call_line,
                            "col": call_col,
                        })
                        self.variables.append({})
                        self.pc = int(self.func_table[f_name]['address'])
                        continue
                    if f_name == 'range':
                        args = []
                        for _ in range(argc):
                            args.append(self.stack.pop() if self.stack else None)
                        args.reverse()
                        try:
                            if len(args) == 1:
                                start, end, step = 0, int(args[0]), 1
                            elif len(args) == 2:
                                start, end, step = int(args[0]), int(args[1]), 1
                            elif len(args) == 3:
                                start, end, step = int(args[0]), int(args[1]), int(args[2])
                            else:
                                self._raise_runtime('range expects 1-3 args')
                            self.stack.append(MellowLangRange(start, end, step))
                        except ValueError as e:
                            self._raise_runtime(str(e))
                        self.pc += 1
                        continue
                    # Built-in helpers (game/AI friendly) implemented by VM
                    # storage_dir/storage_pwd allow scripts to choose where files are written (Python/Lua-like UX)
                    if f_name in (
                        'mkdir','save_data','load_data',
                        'file_read','file_write','file_append','file_exists','file_delete',
                        'storage_dir','storage_pwd','storage_info',
                        # Secure save system (v1.3.4)
                        'save_init','save_set','save_get','save_commit','save_load',
                        'save_list','save_delete','save_clear',
                        # Hybrid (Level C) signed saves + networking (v1.3.5)
                        'save_commit_signed','save_load_signed',
                        'net_http_post','net_http_get',
                        'net_ws_connect','net_ws_send','net_ws_recv','net_ws_close','net_ws_state',
                        # Host filesystem (dev/tooling) - permission gated in project mode
                        'fs_read','fs_write','fs_append','fs_exists','fs_delete','fs_mkdir','fs_pwd',
                    ):
                        # storage_dir/storage_pwd/storage_info are safe even if allow_storage is false
                        # (they don't touch the filesystem; they only configure/query sandbox root).
                        if f_name not in ('storage_dir','storage_pwd','storage_info',
                                          'save_init','save_set','save_get','save_commit','save_load','save_list','save_delete','save_clear',
                                          'save_commit_signed','save_load_signed',
                                          'net_http_post','net_http_get','net_ws_connect','net_ws_send','net_ws_recv','net_ws_close','net_ws_state',
                                          'fs_read','fs_write','fs_append','fs_exists','fs_delete','fs_mkdir','fs_pwd'):
                            if not self.config.get('allow_storage', True):
                                self._raise_sandbox('storage is disabled')
                        # pop call args (same calling convention as syscalls)
                        args = []
                        for _ in range(argc):
                            args.append(self.stack.pop() if self.stack else None)
                        args.reverse()
                        # v1.2.3+: optional named args are compiled as a tagged trailing map:
                        #   {"$kwargs": {"mode": "w", ...}}
                        # This avoids ambiguity with users passing a normal dict
                        # (e.g. save_data("profile", {"hp": 10})).
                        kwargs = {}
                        if args and isinstance(args[-1], dict) and "$kwargs" in args[-1]:
                            kw_obj = args[-1] or {}
                            inner = kw_obj.get("$kwargs")
                            if isinstance(inner, dict):
                                kwargs = inner
                                args = args[:-1]
                        import os

                        # ---- Secure Save System (v1.3.4) ----
                        if f_name in ('save_init','save_set','save_get','save_commit','save_load','save_list','save_delete','save_clear',
                                      'save_commit_signed','save_load_signed'):
                            if not bool(self.config.get('allow_save', True)):
                                self._raise_sandbox('save is disabled')
                            from ..save_core import SaveSystem, SaveLimits
                            from ..net_core import http_post_json, b64_decode
                            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                            from cryptography.hazmat.primitives import hashes
                            import base64

                            # state
                            app_id = str(self.config.get('save_app_id') or '')
                            buf = self.config.get('save_buffer')
                            if not isinstance(buf, dict):
                                buf = {}
                                self.config['save_buffer'] = buf

                            limits = SaveLimits(
                                max_slots=int(self.config.get('save_slots_max', 10) or 10),
                                max_bytes=int(self.config.get('save_bytes_max', 1_048_576) or 1_048_576),
                            )

                            def _require_app_id():
                                if not app_id:
                                    self._raise_runtime('SAVE_NOT_INITIALIZED: call save_init(app_id="...") first')

                            if f_name == 'save_init':
                                # save_init(app_id="my.game")
                                if len(args) < 1:
                                    self._raise_runtime('save_init expects 1 arg: app_id')
                                app_id2 = str(args[0])
                                self.config['save_app_id'] = app_id2
                                # reset buffer on init
                                self.config['save_buffer'] = {}
                                # touch directory
                                _ = SaveSystem(app_id=app_id2, limits=limits)
                                self.stack.append(True)
                                self.pc += 1
                                continue

                            _require_app_id()
                            ss = SaveSystem(app_id=app_id, limits=limits)
                            if f_name == 'save_set':
                                if len(args) < 2:
                                    self._raise_runtime('save_set expects 2 args: key, value')
                                k = str(args[0])
                                v = args[1]
                                buf[k] = v
                                self.stack.append(True)
                                self.pc += 1
                                continue
                            if f_name == 'save_get':
                                if len(args) < 1:
                                    self._raise_runtime('save_get expects 1 arg: key')
                                k = str(args[0])
                                default = args[1] if len(args) > 1 else None
                                self.stack.append(buf.get(k, default))
                                self.pc += 1
                                continue
                            if f_name == 'save_clear':
                                buf.clear()
                                self.stack.append(True)
                                self.pc += 1
                                continue
                            if f_name == 'save_commit':
                                if len(args) < 1:
                                    self._raise_runtime('save_commit expects 1 arg: slot')
                                slot = str(args[0])
                                try:
                                    ss.commit(slot, dict(buf))
                                except Exception as e:
                                    self._raise_runtime(str(e))
                                self.stack.append(True)
                                self.pc += 1
                                continue
                            if f_name == 'save_commit_signed':
                                # save_commit_signed(slot, url, pubkey_b64, token=None)
                                if len(args) < 3:
                                    self._raise_runtime('save_commit_signed expects 3 args: slot, url, pubkey_b64')
                                slot = str(args[0])
                                url = str(args[1])
                                pub_b64 = str(args[2])
                                token = str(args[3]) if len(args) > 3 and args[3] is not None else None

                                if not bool(self.config.get('allow_net', False)):
                                    self._raise_sandbox('net is disabled')
                                # Allowlist check (http)
                                allow = str(self.config.get('net_http_allow') or '')
                                if allow:
                                    ok = False
                                    for prefix in allow.split(','):
                                        prefix = prefix.strip()
                                        if prefix and url.startswith(prefix):
                                            ok = True
                                            break
                                    if not ok:
                                        self._raise_sandbox('net_http: url not allowlisted')

                                # Canonical plaintext payload (same as SaveSystem)
                                import json as _json
                                payload_bytes = _json.dumps(dict(buf), ensure_ascii=False, separators=(",", ":")).encode('utf-8')
                                digest = hashes.Hash(hashes.SHA256())
                                digest.update(payload_bytes)
                                hhex = digest.finalize().hex()

                                headers = {}
                                if token:
                                    headers['Authorization'] = f"Bearer {token}"
                                try:
                                    resp = http_post_json(url, {
                                        'app_id': app_id,
                                        'slot': slot,
                                        'hash_sha256': hhex,
                                    }, timeout_s=float(self.config.get('net_timeout_s', 10.0) or 10.0), headers=headers)
                                except Exception as e:
                                    self._raise_runtime(str(e))

                                sig_b64 = resp.get('signature_b64') or resp.get('sig_b64') or resp.get('signature')
                                if not isinstance(sig_b64, str) or not sig_b64:
                                    self._raise_runtime('SAVE_SIGNATURE: server did not return signature_b64')
                                try:
                                    sig = base64.b64decode(sig_b64.encode('ascii'))
                                except Exception:
                                    self._raise_runtime('SAVE_SIGNATURE: invalid base64 signature')
                                # Verify signature locally before writing
                                try:
                                    pk = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64.encode('ascii')))
                                    pk.verify(sig, bytes.fromhex(hhex))
                                except Exception:
                                    self._raise_runtime('SAVE_SIGNATURE_INVALID: signature verify failed')
                                try:
                                    ss.commit_signed(slot, dict(buf), signature=sig)
                                except Exception as e:
                                    self._raise_runtime(str(e))
                                self.stack.append(True)
                                self.pc += 1
                                continue
                            if f_name == 'save_load':
                                if len(args) < 1:
                                    self._raise_runtime('save_load expects 1 arg: slot')
                                slot = str(args[0])
                                try:
                                    obj = ss.load(slot)
                                except Exception as e:
                                    self._raise_runtime(str(e))
                                if obj is None:
                                    self.stack.append(False)
                                else:
                                    buf.clear()
                                    buf.update(obj)
                                    self.stack.append(True)
                                self.pc += 1
                                continue
                            if f_name == 'save_load_signed':
                                # save_load_signed(slot, pubkey_b64)
                                if len(args) < 2:
                                    self._raise_runtime('save_load_signed expects 2 args: slot, pubkey_b64')
                                slot = str(args[0])
                                pub_b64 = str(args[1])
                                try:
                                    obj = ss.load(slot)
                                except Exception as e:
                                    self._raise_runtime(str(e))
                                if obj is None:
                                    self.stack.append(False)
                                    self.pc += 1
                                    continue
                                sig_hex = obj.get('$signature')
                                if not isinstance(sig_hex, str) or not sig_hex:
                                    self._raise_runtime('SAVE_UNSIGNED: save file has no server signature')
                                # Remove signature from buffer
                                try:
                                    sig = bytes.fromhex(sig_hex)
                                except Exception:
                                    self._raise_runtime('SAVE_CORRUPT: invalid signature encoding')
                                obj2 = dict(obj)
                                obj2.pop('$signature', None)

                                import json as _json
                                payload_bytes = _json.dumps(obj2, ensure_ascii=False, separators=(",", ":")).encode('utf-8')
                                digest = hashes.Hash(hashes.SHA256())
                                digest.update(payload_bytes)
                                hhex = digest.finalize().hex()
                                try:
                                    pk = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64.encode('ascii')))
                                    pk.verify(sig, bytes.fromhex(hhex))
                                except Exception:
                                    self._raise_runtime('SAVE_SIGNATURE_INVALID: signature verify failed')
                                buf.clear()
                                buf.update(obj2)
                                self.stack.append(True)
                                self.pc += 1
                                continue
                            if f_name == 'save_list':
                                self.stack.append(ss.list_slots())
                                self.pc += 1
                                continue
                            if f_name == 'save_delete':
                                if len(args) < 1:
                                    self._raise_runtime('save_delete expects 1 arg: slot')
                                slot = str(args[0])
                                self.stack.append(ss.delete_slot(slot))
                                self.pc += 1
                                continue

                        # ---- Networking built-ins (v1.3.5) ----
                        if f_name in ('net_http_post','net_http_get','net_ws_connect','net_ws_send','net_ws_recv','net_ws_close','net_ws_state'):
                            if not bool(self.config.get('allow_net', False)):
                                self._raise_sandbox('net is disabled')
                            from ..net_core import http_post_json, http_get_json, ws_manager
                            import base64

                            # Limits
                            max_bytes = int(self.config.get('net_max_bytes', 262144) or 262144)
                            timeout_s = float(self.config.get('net_timeout_s', 10.0) or 10.0)

                            def _check_url(url: str, kind: str) -> None:
                                key = 'net_http_allow' if kind == 'http' else 'net_ws_allow'
                                allow = str(self.config.get(key) or '')
                                if not allow:
                                    self._raise_sandbox(f'net_{kind}: no allowlist configured')
                                ok = False
                                for prefix in allow.split(','):
                                    prefix = prefix.strip()
                                    if prefix and url.startswith(prefix):
                                        ok = True
                                        break
                                if not ok:
                                    self._raise_sandbox(f'net_{kind}: url not allowlisted')

                            if f_name == 'net_http_post':
                                if len(args) < 2:
                                    self._raise_runtime('net_http_post expects 2 args: url, json_obj')
                                url = str(args[0])
                                _check_url(url, 'http')
                                body = args[1]
                                if not isinstance(body, dict):
                                    self._raise_runtime('net_http_post: json_obj must be a map')
                                token = str(args[2]) if len(args) > 2 and args[2] is not None else None
                                headers = {}
                                if token:
                                    headers['Authorization'] = f"Bearer {token}"
                                try:
                                    resp = http_post_json(url, body, timeout_s=timeout_s, headers=headers)
                                except Exception as e:
                                    self._raise_runtime(str(e))
                                # crude size guard
                                import json as _json
                                raw = _json.dumps(resp, ensure_ascii=False).encode('utf-8')
                                if len(raw) > max_bytes:
                                    self._raise_runtime('NET_QUOTA_BYTES: response too large')
                                self.stack.append(resp)
                                self.pc += 1
                                continue

                            if f_name == 'net_http_get':
                                if len(args) < 1:
                                    self._raise_runtime('net_http_get expects 1 arg: url')
                                url = str(args[0])
                                _check_url(url, 'http')
                                token = str(args[1]) if len(args) > 1 and args[1] is not None else None
                                headers = {}
                                if token:
                                    headers['Authorization'] = f"Bearer {token}"
                                try:
                                    resp = http_get_json(url, timeout_s=timeout_s, headers=headers)
                                except Exception as e:
                                    self._raise_runtime(str(e))
                                import json as _json
                                raw = _json.dumps(resp, ensure_ascii=False).encode('utf-8')
                                if len(raw) > max_bytes:
                                    self._raise_runtime('NET_QUOTA_BYTES: response too large')
                                self.stack.append(resp)
                                self.pc += 1
                                continue

                            if f_name == 'net_ws_connect':
                                if len(args) < 1:
                                    self._raise_runtime('net_ws_connect expects 1 arg: url')
                                url = str(args[0])
                                _check_url(url, 'ws')
                                token = str(args[1]) if len(args) > 1 and args[1] is not None else None
                                headers = {}
                                if token:
                                    headers['Authorization'] = f"Bearer {token}"
                                hid = ws_manager().connect(url, headers=headers)
                                self.stack.append(int(hid))
                                self.pc += 1
                                continue

                            if f_name == 'net_ws_send':
                                if len(args) < 2:
                                    self._raise_runtime('net_ws_send expects 2 args: conn_id, data')
                                hid = int(args[0])
                                data = args[1]
                                if isinstance(data, str):
                                    b = data.encode('utf-8')
                                elif isinstance(data, bytes):
                                    b = data
                                else:
                                    # allow json map/list
                                    import json as _json
                                    b = _json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode('utf-8')
                                if len(b) > max_bytes:
                                    self._raise_runtime('NET_QUOTA_BYTES: payload too large')
                                ok = ws_manager().send(hid, b)
                                self.stack.append(bool(ok))
                                self.pc += 1
                                continue

                            if f_name == 'net_ws_recv':
                                if len(args) < 1:
                                    self._raise_runtime('net_ws_recv expects 1 arg: conn_id')
                                hid = int(args[0])
                                tout = float(args[1]) if len(args) > 1 and args[1] is not None else 0.0
                                b = ws_manager().recv(hid, timeout_s=tout)
                                if b is None:
                                    self.stack.append(None)
                                else:
                                    if len(b) > max_bytes:
                                        self._raise_runtime('NET_QUOTA_BYTES: incoming message too large')
                                    # return utf-8 string if possible, else base64
                                    try:
                                        self.stack.append(b.decode('utf-8'))
                                    except Exception:
                                        self.stack.append(base64.b64encode(b).decode('ascii'))
                                self.pc += 1
                                continue

                            if f_name == 'net_ws_close':
                                if len(args) < 1:
                                    self._raise_runtime('net_ws_close expects 1 arg: conn_id')
                                hid = int(args[0])
                                self.stack.append(bool(ws_manager().close(hid)))
                                self.pc += 1
                                continue

                            if f_name == 'net_ws_state':
                                if len(args) < 1:
                                    self._raise_runtime('net_ws_state expects 1 arg: conn_id')
                                hid = int(args[0])
                                self.stack.append(ws_manager().state(hid))
                                self.pc += 1
                                continue

                        if f_name == 'mkdir':
                            target = args[0] if args else '.'
                            full, _base = self._safe_fs_path(target)
                            os.makedirs(full, exist_ok=True)
                            self.stack.append(True)
                            self.pc += 1
                            continue

                        # storage_dir("path") lets scripts choose where storage/files are written.
                        # Default behavior is still sandbox-friendly: only relative paths are allowed.
                        # To allow absolute paths / ".." segments, run with --unsafe-fs.
                        if f_name in ('storage_dir','storage_pwd','storage_info'):
                            base = self.config.get('storage_dir', 'mellow_saves')
                            if f_name == 'storage_dir':
                                target = args[0] if args else '.'
                                raw = '' if target is None else str(target).strip().strip('"').strip("'")
                                raw = raw.replace('\\', '/').strip()
                                if raw in ('', '.'):
                                    raw = '.'

                                project_mode = bool(self.config.get('project_mode', False))
                                unsafe = bool(self.config.get('allow_unsafe_fs', False))

                                # In project mode, storage_dir is always sandboxed under <project_root>/<sandbox_root>.
                                if project_mode:
                                    if os.path.isabs(raw):
                                        self._raise_sandbox(
                                            'storage_dir: absolute paths are disabled in project mode. '
                                            'Tip: use a sandbox slot name, e.g. storage_dir("profile_01").'
                                        )
                                    if raw == '..' or raw.startswith('../') or raw.startswith('..\\'):
                                        self._raise_sandbox('storage_dir: ".." traversal is blocked in project mode.')
                                    pr = str(self.config.get('project_root') or os.getcwd())
                                    sr = str(self.config.get('sandbox_root') or 'saves')
                                    # '.' means sandbox root
                                    if raw in ('.', ''):
                                        self.config['storage_dir'] = os.path.join(pr, sr)
                                    else:
                                        self.config['storage_dir'] = os.path.join(pr, sr, raw)
                                    self.stack.append(True)
                                else:
                                    # Dev mode: allow relative paths by default; absolute/'..' only with --unsafe-fs
                                    if os.path.isabs(raw) and not unsafe:
                                        self._raise_sandbox(
                                            'storage_dir: absolute paths are disabled by default. '
                                            'Tip: use a relative path (e.g. "examples" or ".") or run with --unsafe-fs.'
                                        )
                                    if (raw == '..' or raw.startswith('../') or raw.startswith('..\\')) and not unsafe:
                                        self._raise_sandbox(
                                            'storage_dir: ".." traversal is blocked. '
                                            'Tip: choose a folder under the project (e.g. "saves") or run with --unsafe-fs.'
                                        )
                                    self.config['storage_dir'] = raw
                                    self.stack.append(True)
                            elif f_name == 'storage_pwd':
                                self.stack.append(str(base))
                            else:
                                import os as _os
                                self.stack.append({
                                    'storage_dir': str(base),
                                    'storage_abs': _os.path.abspath(str(base)),
                                })
                            self.pc += 1
                            continue

                        # Host filesystem built-ins (fs_*)
                        if f_name.startswith('fs_'):
                            import os as _os
                            op_kind = 'read' if f_name in ('fs_read','fs_exists','fs_pwd') else 'write'
                            if f_name == 'fs_pwd':
                                if bool(self.config.get('project_mode', False)):
                                    self.stack.append(str(self.config.get('project_root') or _os.getcwd()))
                                else:
                                    self.stack.append(str(_os.getcwd()))
                                self.pc += 1
                                continue

                            path0 = args[0] if args else '.'
                            full = self._fs_resolve(path0, op=op_kind)
                            if f_name == 'fs_mkdir':
                                _os.makedirs(full, exist_ok=True)
                                self.stack.append(True)
                                self.pc += 1
                                continue
                            if f_name == 'fs_exists':
                                self.stack.append(bool(_os.path.exists(full)))
                                self.pc += 1
                                continue
                            if f_name == 'fs_delete':
                                if _os.path.exists(full):
                                    _os.remove(full)
                                    self.stack.append(True)
                                else:
                                    self.stack.append(False)
                                self.pc += 1
                                continue
                            if f_name == 'fs_read':
                                mode = str(args[1]) if len(args) > 1 else 'r'
                                if 'b' in mode:
                                    with open(full, mode) as f:
                                        self.stack.append(f.read())
                                else:
                                    with open(full, mode, encoding='utf-8') as f:
                                        self.stack.append(f.read())
                                self.pc += 1
                                continue
                            if f_name in ('fs_write','fs_append'):
                                data = args[1] if len(args) > 1 else ''
                                mode = str(args[2]) if len(args) > 2 else ('a' if f_name == 'fs_append' else 'w')
                                if f_name == 'fs_append' and 'a' not in mode:
                                    mode = 'ab' if 'b' in mode else 'a'
                                # ensure parent exists
                                parent = _os.path.dirname(full)
                                if parent and not _os.path.exists(parent):
                                    _os.makedirs(parent, exist_ok=True)
                                if 'b' in mode:
                                    b = data if isinstance(data, (bytes, bytearray)) else str(data).encode('utf-8')
                                    with open(full, mode) as f:
                                        f.write(b)
                                else:
                                    with open(full, mode, encoding='utf-8') as f:
                                        f.write(str(data))
                                self.stack.append(True)
                                self.pc += 1
                                continue
                        if f_name in ('save_data','load_data'):
                            if f_name == 'save_data':
                                if len(args) < 2:
                                    self._raise_runtime('save_data expects 2 args')
                                a, b = args[0], args[1]
                                if isinstance(a, str) and not isinstance(b, str):
                                    key, value = a, b
                                elif isinstance(b, str) and not isinstance(a, str):
                                    key, value = b, a
                                else:
                                    key, value = str(a), b
                                self._save_json(key, value)
                                self.stack.append(True)
                            else:
                                if len(args) < 1:
                                    self._raise_runtime('load_data expects 1 arg')
                                self.stack.append(self._load_json(args[0]))
                            self.pc += 1
                            continue
                        # file operations under base dir
                        path = args[0] if args else ''
                        data = args[1] if len(args) >= 2 else ''
                        mode = str(args[2] if len(args) >= 3 else (args[1] if len(args) >= 2 else 'r'))
                        if isinstance(kwargs, dict) and 'mode' in kwargs:
                            mode = str(kwargs.get('mode'))
                        full, base_dir = self._safe_fs_path(path)
                        if f_name in ('file_write','file_append') and not os.path.isdir(base_dir):
                            os.makedirs(base_dir, exist_ok=True)
                        if f_name == 'file_exists':
                            self.stack.append(os.path.exists(full))
                        elif f_name == 'file_delete':
                            try:
                                os.remove(full)
                                self.stack.append(True)
                            except FileNotFoundError:
                                self.stack.append(False)
                        elif f_name == 'file_read':
                            m = mode if mode in ('r','rb') else 'r'
                            with open(full, m, encoding=None if 'b' in m else 'utf-8') as f:
                                self.stack.append(f.read())
                        elif f_name == 'file_write':
                            m = mode if mode in ('w','wb') else 'w'
                            with open(full, m, encoding=None if 'b' in m else 'utf-8') as f:
                                f.write(data if isinstance(data, (str, bytes)) else str(data))
                            self.stack.append(True)
                        elif f_name == 'file_append':
                            m = mode if mode in ('a','ab') else 'a'
                            with open(full, m, encoding=None if 'b' in m else 'utf-8') as f:
                                f.write(data if isinstance(data, (str, bytes)) else str(data))
                            self.stack.append(True)
                        self.pc += 1
                        continue
                    # --- AI-ish friendly hint: suggest close names ---
                    try:
                        import difflib
                        candidates = set()
                        candidates.update(getattr(self, 'func_table', {}).keys())
                        candidates.update(['mkdir','save_data','load_data','file_read','file_write','file_append','file_exists','file_delete',
                                           'storage_dir','storage_pwd','storage_info',
                                           'save_init','save_set','save_get','save_commit','save_load','save_list','save_delete','save_clear'])
                        candidates.update(['storage_dir','storage_pwd','storage_info'])
                        # common stdlib helpers (exposed as functions)
                        candidates.update(['vec2','vec3','vec','vector','range','wait','show','print'])
                        sugg = difflib.get_close_matches(str(f_name), sorted(candidates), n=3, cutoff=0.6)
                    except Exception:
                        sugg = []

                    msg = f"Unknown skill: {f_name}"
                    if sugg:
                        msg += "\nHint: did you mean: " + ", ".join(sugg)
                    msg += "\nTip: skills must be defined with `def name(...):` or provided by the host/stdlib."
                    self._raise_runtime(msg)


                elif op == Op.RETURN:
                    res = self.stack.pop() if self.stack else None
                    if self.variables:
                        self.variables.pop()
                    self.pc = self.call_stack.pop() if self.call_stack else len(self.bytecode)
                    if self.frame_stack:
                        self.frame_stack.pop()
                    self.stack.append(res)
                    continue

                elif op == Op.ARG:
                    self.variables[-1][instr[1]] = self.stack.pop() if self.stack else None

                elif op == Op.ASK:
                    if not self.config.get('allow_ask', False):
                        self._raise_sandbox('ask() is disabled')
                    prompt = self.stack.pop() if self.stack else ''
                    raw = input(str(prompt))
                    if raw.lower() == 'true': val = True
                    elif raw.lower() == 'false': val = False
                    else:
                        try:
                            val = float(raw) if '.' in raw else int(raw)
                        except ValueError:
                            val = raw
                    self._enforce_value_limits(val)
                    self.stack.append(val)

                elif op == Op.RANDOM:
                    high = int(self.stack.pop())
                    low = int(self.stack.pop())
                    result = self.rng.randint(low, high)
                    if self._replay.cfg.mode == 'replay':
                        result = self._replay.next_random_result(low, high)
                    else:
                        self._replay.record_random(low, high, result)
                    self.stack.append(result)

                elif op == Op.RANDFLOAT:
                    result = float(self.rng.random())
                    if self._replay.cfg.mode == 'replay':
                        result = self._replay.next_randfloat()
                    else:
                        self._replay.record_randfloat(result)
                    self.stack.append(result)

                elif op == Op.WAIT:
                    if not self.config.get('allow_wait', True):
                        self._raise_sandbox('wait() is disabled')
                    seconds = self.stack.pop()
                    try:
                        import time
                        time.sleep(float(seconds))
                    except Exception:
                        pass

                elif op == Op.SAVE_VAL:
                    value = self.stack.pop() if self.stack else None
                    filename = self.stack.pop() if self.stack else ''
                    self._save_json(filename, value)

                elif op == Op.SAVE:
                    filename = self.stack.pop() if self.stack else ''
                    var_name = instr[1]
                    self._save_json(filename, self._load_var(var_name))

                elif op == Op.LOAD_F:
                    filename = self.stack.pop() if self.stack else ''
                    var_name = instr[1]
                    self.variables[-1][var_name] = self._load_json(filename)

                elif op == Op.LIST_HAS:
                    item = self.stack.pop() if self.stack else None
                    target_list = self.stack.pop() if self.stack else []
                    self.stack.append(item in target_list if isinstance(target_list, list) else False)

                elif op == Op.LIST_PUT:
                    target_list = self.stack.pop() if self.stack else []
                    item = self.stack.pop() if self.stack else None
                    if not isinstance(target_list, list):
                        self._raise_runtime('put target is not a list')
                    target_list.append(item)
                    self._enforce_value_limits(target_list)

                elif op == Op.POP:
                    if self.stack:
                        self.stack.pop()

                elif op == Op.SYSCALL:
                    argc = int(instr[1]) if len(instr) > 1 else 0
                    args = []
                    for _ in range(argc):
                        args.append(self.stack.pop() if self.stack else None)
                    args.reverse()
                    name = self.stack.pop() if self.stack else ''

                    # v1.4.7: list.map/filter/reduce with user-defined function support
                    if name in ("std.list.map", "std.list.filter", "std.list.reduce") and len(args) >= 2:
                        _lst = args[0]
                        _fn_ref = args[1]
                        # v1.4.9: use _call_fn (proper sub-VM) — works with lambdas + first-class fns
                        if isinstance(_lst, list):
                            if name == "std.list.map":
                                _res = [self._call_fn(_fn_ref, [_it]) for _it in _lst]
                            elif name == "std.list.filter":
                                _res = [_it for _it in _lst if self._truthy(self._call_fn(_fn_ref, [_it]))]
                            else:  # reduce
                                _ini = args[2] if len(args) >= 3 else None
                                _acc = _ini if _ini is not None else (_lst[0] if _lst else None)
                                _st = 0 if _ini is not None else 1
                                for _it in _lst[_st:]:
                                    _acc = self._call_fn(_fn_ref, [_acc, _it])
                                _res = _acc
                            self.stack.append(_res)
                            self.pc += 1
                            continue

                    res = self._syscall(name, args)
                    self.stack.append(res)

                # ── v1.4.9: new opcodes ──────────────────────────────

                elif op == Op.MOD:
                    b = self.stack.pop(); a = self.stack.pop()
                    try:
                        self.stack.append(int(a) % int(b) if isinstance(a, int) and isinstance(b, int) else float(a) % float(b))
                    except Exception:
                        self.stack.append(None)

                elif op == Op.POW_OP:
                    b = self.stack.pop(); a = self.stack.pop()
                    try:
                        result = float(a) ** float(b)
                        self.stack.append(int(result) if result == int(result) else result)
                    except Exception:
                        self.stack.append(None)

                elif op == Op.PUSH_FUNC:
                    # Push a function reference (name, func_table_snapshot)
                    f_name = instr[1]
                    self.stack.append(("__func__", f_name))

                elif op == Op.CALL_VAL:
                    # Call a function value on the stack
                    argc = int(instr[1]) if len(instr) > 1 else 0
                    args_cv = []
                    for _ in range(argc):
                        args_cv.append(self.stack.pop() if self.stack else None)
                    args_cv.reverse()
                    func_ref = self.stack.pop() if self.stack else None
                    if isinstance(func_ref, tuple) and len(func_ref) == 2 and func_ref[0] == "__func__":
                        f_name = func_ref[1]
                        if f_name in self.func_table:
                            pcount = int(self.func_table[f_name].get('param_count', 0))
                            for a in args_cv:
                                self.stack.append(a)
                            for _ in range(pcount - len(args_cv)):
                                self.stack.append(None)
                            call_line, call_col = self._pos()
                            self.call_stack.append(self.pc + 1)
                            self.frame_stack.append({"name": f_name, "filename": self.filename, "line": call_line, "col": call_col})
                            self.variables.append({})
                            self.pc = int(self.func_table[f_name]['address'])
                            continue
                    self.stack.append(None)

                elif op == Op.SLICE:
                    # Stack: target, start_or_None, stop_or_None
                    stop_v = self.stack.pop() if self.stack else None
                    start_v = self.stack.pop() if self.stack else None
                    target_v = self.stack.pop() if self.stack else None
                    try:
                        s_idx = int(start_v) if start_v is not None else None
                        e_idx = int(stop_v) if stop_v is not None else None
                        if isinstance(target_v, (list, str)):
                            self.stack.append(target_v[s_idx:e_idx])
                        else:
                            self.stack.append(None)
                    except Exception:
                        self.stack.append(None)

                elif op == Op.IMPORT:
                    # v1.4.9: import "path.mellow" as alias
                    # Compile module, run in sub-VM to get exported vars,
                    # then append module bytecode to self.bytecode and register
                    # qualified function names with corrected addresses.
                    path = instr[1]
                    alias = instr[2]
                    try:
                        import os as _os
                        from ..compiler import Compiler as _Compiler
                        if str(path).startswith('pkg:'):
                            from ..package_manager import resolve_import_entry as _resolve_import_entry
                            _resolved = _resolve_import_entry(str(path)[4:], _os.path.dirname(self.filename or '') or '.')
                            if not _resolved:
                                raise RuntimeError(f"package import not installed: {str(path)[4:]}")
                            path = _resolved
                        base_dir = _os.path.dirname(self.filename or '') or '.'
                        full_path = _os.path.join(base_dir, path)
                        if not _os.path.exists(full_path):
                            full_path = path
                        with open(full_path, 'r', encoding='utf-8') as _f:
                            _src = _f.read()
                        _c = _Compiler()
                        _prog = _c.compile(_src, filename=full_path)

                        # Run sub-VM to execute module-level code (keep vars, etc.)
                        _sub_cfg = {k: v for k, v in self.config.items()}
                        _sub_cfg['max_steps'] = 2_000_000
                        _sub = MellowLangVM(list(_prog.bytecode),
                                            dict(_prog.func_table or {}),
                                            dict(_prog.event_table or {}),
                                            config=_sub_cfg, filename=full_path)
                        _sub.run()

                        # Merge module's function table into parent with alias prefix
                        # Also build set of module-internal function names for patching
                        _mod_fnames = set((_prog.func_table or {}).keys())
                        _offset = len(self.bytecode)

                        # Append module bytecode, patching:
                        # 1. JUMP/JIF addresses (add offset so they point to correct parent positions)
                        # 2. CALL instructions (qualify internal calls with alias prefix)
                        from ..constants import Op as _Op
                        _ADDR_OPS = {_Op.JUMP, _Op.JIF}  # opcodes whose arg[1] is a PC address

                        for _bc in _prog.bytecode:
                            _bop = _bc[0]
                            if _bop in _ADDR_OPS:
                                # Add offset to jump target
                                _new_bc = (_bop, int(_bc[1]) + _offset) + _bc[2:]
                                self.bytecode.append(_new_bc)
                            elif _bop == _Op.TRY:
                                # TRY catch_pc finally_pc err_name
                                _catch = (int(_bc[1]) + _offset) if _bc[1] is not None else None
                                _fin   = (int(_bc[2]) + _offset) if len(_bc)>2 and _bc[2] is not None else None
                                self.bytecode.append((_bop, _catch, _fin) + _bc[3:])
                            elif _bop == _Op.CALL and len(_bc) >= 2 and _bc[1] in _mod_fnames:
                                # Qualify internal call: factorial → utils.factorial
                                self.bytecode.append((_Op.CALL, f"{alias}.{_bc[1]}") + _bc[2:])
                            else:
                                self.bytecode.append(_bc)

                        for _sk, _meta in (_prog.func_table or {}).items():
                            self.func_table[f"{alias}.{_sk}"] = {
                                **_meta,
                                'address': int(_meta['address']) + _offset,
                            }

                        # Copy module-level exported variables as alias.varname
                        for _scope in _sub.variables:
                            for _vn, _vv in _scope.items():
                                if not _vn.startswith('__'):
                                    self.variables[-1][f"{alias}.{_vn}"] = _vv
                        # Also copy keep_values
                        for _vn, _vv in _sub._keep_values.items():
                            if not _vn.startswith('__'):
                                self.variables[-1][f"{alias}.{_vn}"] = _vv

                    except Exception as _ie:
                        import sys as _sys
                        print(f"[mellow import warning] {path}: {_ie}", file=_sys.stderr)

                else:
                    self._raise_runtime(f'Unknown opcode: {op}')

                self.pc += 1
            except Exception as e:
                # record crash in replay? (optional)
                if self._handle_exception(e):
                    continue
                raise

        # persist keep vars (disabled by default)
        if self._keep_enabled and self._keep_dirty and self.config.get("persist_keep", False):
            try:
                key = (self.filename or "<memory>")
                self._save_json(f"__keep__{key}", self._keep_values)
                self._keep_dirty = False
            except Exception:
                pass

        # write AI decision timeline (best-effort)
        if self._ai_trace and self._ai_timeline_path and self._ai_events:
            try:
                import json as _json
                with open(str(self._ai_timeline_path), "a", encoding="utf-8") as f:
                    for ev in self._ai_events:
                        f.write(_json.dumps(ev, ensure_ascii=False) + "\n")
            except Exception:
                pass

        # final result
        result = self.stack[-1] if self.stack else None
        if self._profile:
            import time as _time
            elapsed_ms = int((_time.monotonic() - self._t0) * 1000.0)
            return {
                'result': result,
                'steps': int(self._steps),
                'elapsed_ms': elapsed_ms,
                'opcode_counts': dict(self._opcounts),
                'syscall_budget_left': int(self._budget),
            }
        return result
