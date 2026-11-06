"""Calling a skill or a first-class callable, and the single-step helper."""

from __future__ import annotations


class InvocationMixin:
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
        sub = self._sub_vm(
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
        from ...constants import Op as _Op
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
        from ...constants import Op as _Op
        op = instr[0]
        if op == _Op.PUSH:
            self.stack.append(instr[1])
        elif op == _Op.LOAD:
            _ln = instr[1]
            _lv = None; _found = False
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
                if not -len(target) <= i2 < len(target):
                    raise IndexError("index out of range")
                self.stack.append(target[i2])
            elif isinstance(target, dict):
                if idxv not in target:
                    raise KeyError("missing map key")
                self.stack.append(target[idxv])
            else:
                raise TypeError("value is not indexable")
        elif op == _Op.BUILD_LIST:
            n = int(instr[1]); items = [self.stack.pop() for _ in range(n)]; items.reverse()
            self.stack.append(items)
        elif op == _Op.BUILD_MAP:
            n = int(instr[1]); d = {}
            for _ in range(n):
                v = self.stack.pop(); k = self.stack.pop(); d[str(k)] = v
            self.stack.append({k: d[k] for k in reversed(d)})
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
