# mellowlang/storage_core.py
from __future__ import annotations
import json
import os
from typing import Any, Optional

class StorageCore:
    """Sandboxed file + JSON persistence.

    Design goals (v1.0.7):
    - System-managed base directory: ./mellow_saves (NOT auto-created; user must mkdir())
    - Safe paths only (no absolute path / no traversal)
    - JSON helpers: save_data / load_data (forces .json)
    - File helpers: file_read / file_write / file_append / file_exists / file_delete / mkdir
      * For subfolders: **we do NOT auto-create**. User should call mkdir() explicitly.
    """

    def __init__(self, engine, base_dir: str = "mellow_saves"):
        self.engine = engine
        self.base_dir = base_dir
        self.commands = [
            # JSON
            "save_data", "load_data",
            # generic files
            "file_read", "file_write", "file_append",
            "file_exists", "file_delete",
            "mkdir",
        ]

    # ---------- path helpers ----------
    def _normalize_rel(self, path: Any, *, force_ext: Optional[str] = None) -> str:
        raw = str(path).strip().strip('"').strip("'")
        raw = raw.replace("\\", "/").lstrip("/")
        if not raw or raw in (".", ".."):
            raw = "save"
        if force_ext and not raw.lower().endswith(force_ext.lower()):
            raw += force_ext
        base = os.path.normpath(self.base_dir)
        full = os.path.normpath(os.path.join(base, raw))
        if not (full == base or full.startswith(base + os.sep)):
            raise ValueError("invalid path (path traversal blocked)")
        return full

    def _ensure_base_dir(self):
        if not os.path.isdir(self.base_dir):
            raise FileNotFoundError(
                f"Storage base folder '{self.base_dir}' does not exist. Create it with mkdir('.') or mkdir('') first."
            )

    def _require_parent_exists(self, full_path: str):
        parent = os.path.dirname(full_path) or self.base_dir
        base = os.path.normpath(self.base_dir)
        if os.path.normpath(parent) != base and not os.path.exists(parent):
            raise FileNotFoundError(f"Folder not found: {parent} (create it first with mkdir())")

    # ---------- command dispatch ----------
    def execute(self, name: str, args: list):
        try:
            if name == "save_data":
                a0 = args[0] if len(args) > 0 else None
                a1 = args[1] if len(args) > 1 else "save"
                # Accept both orders:
                #   save_data(data, filename)
                #   save_data(filename, data)
                if isinstance(a0, str) and not isinstance(a1, str):
                    a0, a1 = a1, a0
                return self.save_data(a0, a1)

            if name == "load_data":
                return self.load_data(args[0] if args else "save")

            if name == "file_read":
                path = args[0] if args else ""
                mode = str(args[1]) if len(args) > 1 else "r"
                return self.file_read(path, mode)

            if name == "file_write":
                path = args[0] if len(args) > 0 else ""
                data = args[1] if len(args) > 1 else ""
                mode = str(args[2]) if len(args) > 2 else "w"
                return self.file_write(path, data, mode)

            if name == "file_append":
                path = args[0] if len(args) > 0 else ""
                data = args[1] if len(args) > 1 else ""
                mode = str(args[2]) if len(args) > 2 else "a"
                return self.file_append(path, data, mode)

            if name == "file_exists":
                path = args[0] if args else ""
                return self.file_exists(path)

            if name == "file_delete":
                path = args[0] if args else ""
                return self.file_delete(path)

            if name == "mkdir":
                path = args[0] if args else ""
                return self.mkdir(path)

        except Exception as e:
            if hasattr(self.engine, "error_handler"):
                self.engine.error_handler.report("STORAGE", str(e))
            return None

        return None

    # ---------- JSON helpers ----------
    def save_data(self, data: Any, filename: Any) -> bool:
        self._ensure_base_dir()
        path = self._normalize_rel(filename, force_ext=".json")
        self._require_parent_exists(path)
        # Atomic write
        import tempfile
        parent = os.path.dirname(path) or self.base_dir
        fd, tmp = tempfile.mkstemp(prefix=".mellow_", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def load_data(self, filename: Any):
        self._ensure_base_dir()
        path = self._normalize_rel(filename, force_ext=".json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    # ---------- file helpers ----------
    _ALLOWED_MODES = {"r","w","a","rb","wb","ab"}

    def _sanitize_mode(self, mode: str, *, default: str) -> str:
        m = (mode or default).strip()
        if m not in self._ALLOWED_MODES:
            raise ValueError(f"Invalid file mode: {m} (allowed: {sorted(self._ALLOWED_MODES)})")
        return m

    def file_read(self, path: Any, mode: str = "r"):
        self._ensure_base_dir()
        m = self._sanitize_mode(mode, default="r")
        full = self._normalize_rel(path, force_ext=None)
        if "b" in m:
            with open(full, m) as f:
                return f.read()
        with open(full, m, encoding="utf-8") as f:
            return f.read()

    def file_write(self, path: Any, data: Any, mode: str = "w") -> bool:
        self._ensure_base_dir()
        m = self._sanitize_mode(mode, default="w")
        full = self._normalize_rel(path, force_ext=None)
        self._require_parent_exists(full)
        if "b" in m:
            b = data if isinstance(data, (bytes, bytearray)) else str(data).encode("utf-8")
            with open(full, m) as f:
                f.write(b)
            return True
        with open(full, m, encoding="utf-8") as f:
            f.write(str(data))
        return True

    def file_append(self, path: Any, data: Any, mode: str = "a") -> bool:
        # just write with append mode
        m = self._sanitize_mode(mode, default="a")
        if "a" not in m:
            # enforce append semantics
            m = "ab" if "b" in m else "a"
        return self.file_write(path, data, m)

    def file_exists(self, path: Any) -> bool:
        full = self._normalize_rel(path, force_ext=None)
        return os.path.exists(full)

    def file_delete(self, path: Any) -> bool:
        full = self._normalize_rel(path, force_ext=None)
        if os.path.exists(full):
            os.remove(full)
            return True
        return False

    def mkdir(self, path: Any) -> bool:
        # mkdir is explicit, so it is allowed to create the base dir.
        os.makedirs(self.base_dir, exist_ok=True)
        raw = str(path).strip().strip('"').strip("'").replace('\\', '/').strip('/')
        if not raw or raw in ('.',):
            return True
        full = self._normalize_rel(raw, force_ext=None)
        os.makedirs(full, exist_ok=True)
        return True
