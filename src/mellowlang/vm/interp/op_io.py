"""Output, interaction and persistence instructions."""

from __future__ import annotations

from ...constants import Op
from .actions import _STEP


class IOMixin:
    def _exec_output(self, op, instr) -> object:
        """PRINT, PRINTN and the precision setting."""
        if op == Op.PRINT:
            print(self.format_value(self.stack.pop() if self.stack else None))
            return _STEP
        if op == Op.PRINTN:
            n = int(instr[1]) if len(instr) > 1 else 0
            vals = []
            for _ in range(max(0, n)):
                vals.append(self.stack.pop() if self.stack else None)
            vals.reverse()
            out = " ".join(self.format_value(v) for v in vals)
            self._enforce_value_limits(out)
            print(out)
            return _STEP
        if op == Op.SHOW_PREC:
            self.precision = self.stack.pop()
            return _STEP
        raise AssertionError("_exec_output received " + repr(op))

    def _exec_interaction(self, op, instr) -> object:
        """ASK, RANDOM, RANDFLOAT and WAIT."""
        if op == Op.ASK:
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
            return _STEP
        if op == Op.RANDOM:
            high = int(self.stack.pop())
            low = int(self.stack.pop())
            result = self.rng.randint(low, high)
            if self._replay.cfg.mode == 'replay':
                result = self._replay.next_random_result(low, high)
            else:
                self._replay.record_random(low, high, result)
            self.stack.append(result)
            return _STEP
        if op == Op.RANDFLOAT:
            result = float(self.rng.random())
            if self._replay.cfg.mode == 'replay':
                result = self._replay.next_randfloat()
            else:
                self._replay.record_randfloat(result)
            self.stack.append(result)
            return _STEP
        if op == Op.WAIT:
            if not self.config.get('allow_wait', True):
                self._raise_sandbox('wait() is disabled')
            seconds = self.stack.pop()
            try:
                import time
                time.sleep(float(seconds))
            except Exception:
                pass
            return _STEP
        raise AssertionError("_exec_interaction received " + repr(op))

    def _exec_persistence(self, op, instr) -> object:
        """SAVE_VAL, SAVE and LOAD_F."""
        if op == Op.SAVE_VAL:
            value = self.stack.pop() if self.stack else None
            filename = self.stack.pop() if self.stack else ''
            self._save_json(filename, value)
            return _STEP
        if op == Op.SAVE:
            filename = self.stack.pop() if self.stack else ''
            var_name = instr[1]
            self._save_json(filename, self._load_var(var_name))
            return _STEP
        if op == Op.LOAD_F:
            filename = self.stack.pop() if self.stack else ''
            var_name = instr[1]
            self.variables[-1][var_name] = self._load_json(filename)
            return _STEP
        raise AssertionError("_exec_persistence received " + repr(op))
