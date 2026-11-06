from __future__ import annotations

from typing import Any

from ..constants import Op


# The native engines reach these services through std.* syscalls, while the
# Python VM implements them as built-in call names.
STORAGE_SYSCALL_BUILTINS = {
    "std.storage.dir": "storage_dir",
    "std.storage.pwd": "storage_pwd",
    "std.storage.info": "storage_info",
    "std.storage.save": "save_data",
    "std.storage.load": "load_data",
    "std.storage.mkdir": "mkdir",
    "std.fs.read": "fs_read",
    "std.fs.write": "fs_write",
    "std.fs.append": "fs_append",
    "std.fs.exists": "fs_exists",
    "std.fs.delete": "fs_delete",
    "std.fs.mkdir": "fs_mkdir",
    "std.fs.pwd": "fs_pwd",
    "std.file.read": "file_read",
    "std.file.write": "file_write",
    "std.file.append": "file_append",
    "std.file.exists": "file_exists",
    "std.file.delete": "file_delete",
}

# Every call name the Python VM implements as a storage-side built-in.
STORAGE_BUILTIN_NAMES = frozenset({
    "mkdir", "save_data", "load_data",
    "file_read", "file_write", "file_append", "file_exists", "file_delete",
    "storage_dir", "storage_pwd", "storage_info",
    # Secure save system (v1.3.4)
    "save_init", "save_set", "save_get", "save_commit", "save_load",
    "save_list", "save_delete", "save_clear",
    # Hybrid (Level C) signed saves + networking (v1.3.5)
    "save_commit_signed", "save_load_signed",
    "net_http_post", "net_http_get",
    "net_ws_connect", "net_ws_send", "net_ws_recv", "net_ws_close", "net_ws_state",
    # Host filesystem (dev/tooling) - permission gated in project mode
    "fs_read", "fs_write", "fs_append", "fs_exists", "fs_delete", "fs_mkdir", "fs_pwd",
})

# Only the slot helpers obey allow_storage; the others either configure the
# sandbox or carry their own permission gates.
STORAGE_SLOT_NAMES = frozenset({
    "mkdir", "save_data", "load_data",
    "file_read", "file_write", "file_append", "file_exists", "file_delete",
})


class StorageMixin:
    _private_bytecode = False

    def _dispatch_storage_syscall(self, name: str, args: list, argc: int) -> None:
        """Re-enter this VM's storage built-ins for a std.* syscall.

        The compile cache hands one instruction list to every run, so the
        SYSCALL -> CALL rewrite happens on a copy this VM owns, leaving the pc
        on the rewritten instruction.
        """
        if not self._private_bytecode:
            self.bytecode = list(self.bytecode)
            self._private_bytecode = True
        self.stack.extend(args)
        self.bytecode[self.pc] = (Op.CALL, STORAGE_SYSCALL_BUILTINS[name], argc)

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
