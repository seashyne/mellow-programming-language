"""The dispatch loop: fetch an instruction, hand it to the family that owns its opcode."""

from __future__ import annotations

from ...constants import Op
from .actions import _HALT, _NEXT


class ExecuteMixin:
    OP_HANDLERS = {
        Op.ADD: "_exec_arithmetic",
        Op.ARG: "_exec_skill_return",
        Op.ASK: "_exec_interaction",
        Op.BOOL_AND: "_exec_comparisons",
        Op.BOOL_NOT: "_exec_comparisons",
        Op.BOOL_OR: "_exec_comparisons",
        Op.BUILD_LIST: "_exec_collections",
        Op.BUILD_MAP: "_exec_collections",
        Op.CALL: "_exec_call",
        Op.CALL_VAL: "_exec_first_class",
        Op.COMPARE: "_exec_comparisons",
        Op.DIV: "_exec_arithmetic",
        Op.ENDTRY: "_exec_try_frames",
        Op.GETITEM: "_exec_collections",
        Op.GLOBAL_SEED: "_exec_bindings",
        Op.HALT: "_exec_try_frames",
        Op.IMPORT: "_exec_import",
        Op.JIF: "_exec_jumps",
        Op.JUMP: "_exec_jumps",
        Op.LEN: "_exec_collections",
        Op.LIST_HAS: "_exec_list_ops",
        Op.LIST_PUT: "_exec_list_ops",
        Op.LOAD: "_exec_bindings",
        Op.LOAD_F: "_exec_persistence",
        Op.MOD: "_exec_mod_pow",
        Op.MUL: "_exec_arithmetic",
        Op.POP: "_exec_list_ops",
        Op.POW_OP: "_exec_mod_pow",
        Op.PRINT: "_exec_output",
        Op.PRINTN: "_exec_output",
        Op.PUSH: "_exec_bindings",
        Op.PUSH_FUNC: "_exec_first_class",
        Op.RANDFLOAT: "_exec_interaction",
        Op.RANDOM: "_exec_interaction",
        Op.RETURN: "_exec_skill_return",
        Op.SAVE: "_exec_persistence",
        Op.SAVE_VAL: "_exec_persistence",
        Op.SEED: "_exec_bindings",
        Op.SHOW_PREC: "_exec_output",
        Op.SLICE: "_exec_first_class",
        Op.STOP: "_exec_try_frames",
        Op.STORE: "_exec_bindings",
        Op.STORE_AUTO: "_exec_bindings",
        Op.STORE_KEEP: "_exec_bindings",
        Op.SUB: "_exec_arithmetic",
        Op.SYSCALL: "_exec_syscall",
        Op.TRY: "_exec_try_frames",
        Op.WAIT: "_exec_interaction",
    }

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
                handler = self.OP_HANDLERS.get(op)
                if handler is None:
                    self._raise_runtime(f'Unknown opcode: {op}')
                else:
                    action = getattr(self, handler)(op, instr)
                    if action is _HALT:
                        break
                    if action is _NEXT:
                        continue
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
        self._replay.close()
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
