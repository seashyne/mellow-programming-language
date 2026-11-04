"""CALL, SYSCALL and the first-class call forms."""

from __future__ import annotations

from ...constants import Op
from ...range_core import MellowLangRange
from ..storage import STORAGE_BUILTIN_NAMES, STORAGE_SYSCALL_BUILTINS
from .actions import _NEXT, _PASS, _STEP


class CallMixin:
    def _exec_call(self, op, instr) -> object:
        """CALL."""
        if op == Op.CALL:
            f_name = instr[1]
            argc = int(instr[2]) if len(instr) > 2 else 0
            # v1.4.9: first-class fn â€“ variable might hold a ("__func__", name) ref
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
                return _NEXT
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
                return _NEXT
            action = self._exec_storage_builtins(f_name, argc)
            if action is not _PASS:
                return action
            try:
                import difflib
                candidates = set()
                candidates.update(getattr(self, 'func_table', {}).keys())
                candidates.update(STORAGE_BUILTIN_NAMES)
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
            return _STEP
        raise AssertionError("_exec_call received " + repr(op))

    def _exec_syscall(self, op, instr) -> object:
        """SYSCALL."""
        if op == Op.SYSCALL:
            argc = int(instr[1]) if len(instr) > 1 else 0
            args = []
            for _ in range(argc):
                args.append(self.stack.pop() if self.stack else None)
            args.reverse()
            name = self.stack.pop() if self.stack else ''
            if name in STORAGE_SYSCALL_BUILTINS:
                self._dispatch_storage_syscall(str(name), args, argc)
                return _NEXT

            # v1.4.7: list.map/filter/reduce with user-defined function support
            if name in ("std.list.map", "std.list.filter", "std.list.reduce") and len(args) >= 2:
                _lst = args[0]
                _fn_ref = args[1]
                # v1.4.9: use _call_fn (proper sub-VM) â€” works with lambdas + first-class fns
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
                    return _NEXT

            res = self._syscall(name, args)
            self.stack.append(res)
            return _STEP
        raise AssertionError("_exec_syscall received " + repr(op))

    def _exec_first_class(self, op, instr) -> object:
        """PUSH_FUNC, CALL_VAL and SLICE."""
        if op == Op.PUSH_FUNC:
            f_name = instr[1]
            self.stack.append(("__func__", f_name))
            return _STEP
        if op == Op.CALL_VAL:
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
                    return _NEXT
            self.stack.append(None)
            return _STEP
        if op == Op.SLICE:
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
            return _STEP
        raise AssertionError("_exec_first_class received " + repr(op))
