"""Directory, storage-info and file builtins, last in the storage name walk. One step of the storage name walk."""

from __future__ import annotations

import os
from .actions import _NEXT, _PASS


class FsGroupMixin:
    def _call_fs_builtins(self, f_name: str, args: list, kwargs: dict) -> object:
        """Directory, storage-info and file builtins, last in the storage name walk."""
        if f_name == 'mkdir':
            target = args[0] if args else '.'
            full, _base = self._safe_fs_path(target)
            os.makedirs(full, exist_ok=True)
            self.stack.append(True)
            self.pc += 1
            return _NEXT

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
            return _NEXT

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
                return _NEXT

            path0 = args[0] if args else '.'
            full = self._fs_resolve(path0, op=op_kind)
            if f_name == 'fs_mkdir':
                _os.makedirs(full, exist_ok=True)
                self.stack.append(True)
                self.pc += 1
                return _NEXT
            if f_name == 'fs_exists':
                self.stack.append(bool(_os.path.exists(full)))
                self.pc += 1
                return _NEXT
            if f_name == 'fs_delete':
                if _os.path.exists(full):
                    _os.remove(full)
                    self.stack.append(True)
                else:
                    self.stack.append(False)
                self.pc += 1
                return _NEXT
            if f_name == 'fs_read':
                mode = str(args[1]) if len(args) > 1 else 'r'
                if 'b' in mode:
                    with open(full, mode) as f:
                        self.stack.append(f.read())
                else:
                    with open(full, mode, encoding='utf-8') as f:
                        self.stack.append(f.read())
                self.pc += 1
                return _NEXT
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
                return _NEXT
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
            return _NEXT
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
        return _PASS
