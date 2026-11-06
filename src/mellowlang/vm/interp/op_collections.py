"""Length, indexing, the builders and list edits."""

from __future__ import annotations

from ...constants import Op
from ...range_core import MellowLangRange
from .actions import _STEP


class CollectionMixin:
    def _exec_collections(self, op, instr) -> object:
        """LEN, GETITEM and the list/map builders."""
        if op == Op.LEN:
            a = self.stack.pop()
            try:
                if isinstance(a, (list, dict, str, MellowLangRange)):
                    self.stack.append(len(a))
                elif hasattr(a, "__len__") and hasattr(a, "__getitem__"):
                    # allow safe view-like iterables
                    self.stack.append(int(len(a)))
                else:
                    self.stack.append(0)
            except Exception:
                self.stack.append(0)
            return _STEP
        if op == Op.GETITEM:
            idxv = self.stack.pop()
            target = self.stack.pop()
            if isinstance(target, (list, str, MellowLangRange)):
                i2 = int(idxv)
                if i2 < 0:
                    i2 = len(target) + i2
                if not 0 <= i2 < len(target):
                    raise IndexError("index out of range")
                self.stack.append(target[i2])
            elif isinstance(target, dict):
                if idxv not in target:
                    raise KeyError("missing map key")
                self.stack.append(target[idxv])
            elif hasattr(target, "__getitem__"):
                i2 = int(idxv) if isinstance(idxv, (int, float, bool)) or (isinstance(idxv, str) and idxv.lstrip('-').isdigit()) else idxv
                if isinstance(i2, int) and i2 < 0:
                    i2 = len(target) + i2
                self.stack.append(target[i2])
            else:
                raise TypeError("value is not indexable")
            return _STEP
        if op == Op.BUILD_LIST:
            n = int(instr[1])
            items = []
            for _ in range(n):
                items.append(self.stack.pop() if self.stack else None)
            items.reverse()
            self._enforce_value_limits(items)
            self.stack.append(items)
            return _STEP
        if op == Op.BUILD_MAP:
            n = int(instr[1])
            d = {}
            for _ in range(n):
                val = self.stack.pop() if self.stack else None
                key = self.stack.pop() if self.stack else None
                if not isinstance(key, str):
                    key = str(key)
                d[key] = val
            d = {key: d[key] for key in reversed(d)}  # pairs arrive last-first
            self._enforce_value_limits(d)
            self.stack.append(d)
            return _STEP
        raise AssertionError("_exec_collections received " + repr(op))

    def _exec_list_ops(self, op, instr) -> object:
        """LIST_HAS, LIST_PUT and POP."""
        if op == Op.LIST_HAS:
            item = self.stack.pop() if self.stack else None
            target_list = self.stack.pop() if self.stack else []
            self.stack.append(item in target_list if isinstance(target_list, list) else False)
            return _STEP
        if op == Op.LIST_PUT:
            target_list = self.stack.pop() if self.stack else []
            item = self.stack.pop() if self.stack else None
            if not isinstance(target_list, list):
                self._raise_runtime('put target is not a list')
            target_list.append(item)
            self._enforce_value_limits(target_list)
            return _STEP
        if op == Op.POP:
            if self.stack:
                self.stack.pop()
            return _STEP
        raise AssertionError("_exec_list_ops received " + repr(op))
