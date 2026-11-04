"""IMPORT: load a module file into a namespace."""

from __future__ import annotations

from ...constants import Op
from .actions import _STEP


class ImportMixin:
    def _exec_import(self, op, instr) -> object:
        """IMPORT."""
        if op == Op.IMPORT:
            path = instr[1]
            alias = instr[2]
            try:
                import os as _os
                from ...compiler import Compiler as _Compiler
                if str(path).startswith('pkg:'):
                    from ...package_manager import resolve_import_entry as _resolve_import_entry
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
                _sub = self._sub_vm(list(_prog.bytecode),
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
                from ...constants import Op as _Op
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
                        # Qualify internal call: factorial â†’ utils.factorial
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
            return _STEP
        raise AssertionError("_exec_import received " + repr(op))
