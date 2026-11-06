"""Locking and validating the storage configuration and the save/load
paths a native run is handed."""

from __future__ import annotations

import os
from typing import Any, Dict

from ...constants import Op


def _lock_native_storage_dir(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return the config the native engine should run with.

    Project mode locks storage under <project_root>/<sandbox_root>; the Python VM
    does this in its constructor, so the native path needs the same resolution.
    A copy keeps the caller's config untouched for the Python fallback.
    """
    if not bool(config.get("project_mode", False)):
        return config
    project_root = os.path.abspath(str(config.get("project_root") or os.getcwd()))
    sandbox_root = str(config.get("sandbox_root") or "saves").strip().strip('"').strip("'").replace("\\", "/")
    if not sandbox_root:
        sandbox_root = "saves"
    locked = dict(config)
    locked["project_root"] = project_root
    locked["sandbox_root"] = sandbox_root
    base = config.get("storage_dir")
    raw = "" if base is None else str(base).strip().strip('"').strip("'")
    if raw in ("", ".", "mellow_saves", "saves"):
        locked["storage_dir"] = os.path.join(project_root, sandbox_root)
        return locked
    normalized = raw.replace("\\", "/")
    if os.path.isabs(normalized) and os.path.normcase(os.path.abspath(normalized)).startswith(
        os.path.normcase(os.path.join(project_root, sandbox_root))
    ):
        return locked  # already inside the sandbox — do not nest it again
    locked["storage_dir"] = os.path.join(project_root, sandbox_root, normalized.lstrip("/"))
    return locked


def _storage_path_unsafe(value: Any) -> bool:
    raw = ("" if value is None else str(value)).strip().strip('"').strip("'").replace("\\", "/")
    if not raw or raw == ".":
        return False
    if os.path.isabs(raw):
        return True
    parts = [part for part in raw.split("/") if part]
    return any(part == ".." for part in parts)


def _validate_native_storage_bytecode(bytecode: list[tuple], config: Dict[str, Any]) -> None:
    if not bool(config.get("allow_storage", True)):
        return
    stack: list[Any] = []
    for instr in bytecode:
        if not instr:
            continue
        op = instr[0]
        if op == Op.PUSH:
            stack.append(instr[1] if len(instr) > 1 else None)
        elif op == Op.BUILD_MAP:
            count = int(instr[1] if len(instr) > 1 else 0)
            for _ in range(max(0, count) * 2):
                if stack:
                    stack.pop()
            stack.append({"<map>": True})
        elif op == Op.SAVE_VAL:
            stack.pop() if stack else None
            filename = stack.pop() if stack else None
            if _storage_path_unsafe(filename):
                raise RuntimeError("SANDBOX: invalid storage path (path traversal blocked)")
        elif op in {Op.SAVE, Op.LOAD_F}:
            filename = stack.pop() if stack else None
            if _storage_path_unsafe(filename):
                raise RuntimeError("SANDBOX: invalid storage path (path traversal blocked)")
        else:
            stack.clear()
