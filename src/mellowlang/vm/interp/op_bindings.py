"""Operand push, the store forms, the seeds and load."""

from __future__ import annotations

from ...constants import Op
from .actions import _STEP


class BindingMixin:
    def _exec_bindings(self, op, instr) -> object:
        """PUSH and the store/load forms, including the seed ops."""
        if op == Op.PUSH:
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
            return _STEP
        if op == Op.STORE:
            self.variables[-1][instr[1]] = self.stack.pop() if self.stack else None
            return _STEP
        if op == Op.STORE_AUTO:
            name = instr[1]
            val = self.stack.pop() if self.stack else None
            self.variables[-1][name] = val
            # If the name exists in keep store, keep it in sync (ergonomic updates)
            if self._keep_enabled and name in self._keep_values:
                self._keep_values[name] = val
                self._keep_dirty = True
            return _STEP
        if op == Op.STORE_KEEP:
            name = instr[1]
            val = self.stack.pop() if self.stack else None
            # always store in current scope too (ergonomic)
            self.variables[-1][name] = val
            if self._keep_enabled:
                self._keep_values[name] = val
                self._keep_dirty = True
            return _STEP
        if op == Op.SEED:
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
            return _STEP
        if op == Op.GLOBAL_SEED:
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
            return _STEP
        if op == Op.LOAD:
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
                if _ln in self.func_table:
                    _lv = ("__func__", _ln)
                else:
                    raise RuntimeError(f"undefined name: {_ln}")
            self.stack.append(_lv)
            return _STEP
        raise AssertionError("_exec_bindings received " + repr(op))
