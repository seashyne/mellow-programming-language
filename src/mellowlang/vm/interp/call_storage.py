"""The storage-builtin walk that used to sit inside the CALL arm."""

from __future__ import annotations

from ..storage import STORAGE_BUILTIN_NAMES, STORAGE_SLOT_NAMES
from .actions import _NEXT, _PASS

# The order is the order the original if-chain tested the name groups in.
STORAGE_GROUPS = (
    "_call_save_builtins",
    "_call_net_builtins",
    "_call_fs_builtins",
)


class StorageCallMixin:
    def _exec_storage_builtins(self, f_name: str, argc: int) -> object:
        """Walk the storage name groups in the order the original chain tested them."""
        if f_name not in STORAGE_BUILTIN_NAMES:
            return _PASS
        if f_name in STORAGE_SLOT_NAMES and not self.config.get('allow_storage', True):
            self._raise_sandbox('storage is disabled')
        # pop call args (same calling convention as syscalls)
        args = []
        for _ in range(argc):
            args.append(self.stack.pop() if self.stack else None)
        args.reverse()
        # v1.2.3+: optional named args are compiled as a tagged trailing map:
        #   {"$kwargs": {"mode": "w", ...}}
        # This avoids ambiguity with users passing a normal dict
        # (e.g. save_data("profile", {"hp": 10})).
        kwargs = {}
        if args and isinstance(args[-1], dict) and "$kwargs" in args[-1]:
            kw_obj = args[-1] or {}
            inner = kw_obj.get("$kwargs")
            if isinstance(inner, dict):
                kwargs = inner
                args = args[:-1]
        for group in STORAGE_GROUPS:
            action = getattr(self, group)(f_name, args, kwargs)
            if action is not _PASS:
                return action
        self.pc += 1
        return _NEXT
