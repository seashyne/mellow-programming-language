# frinds/range_core.py
from __future__ import annotations

class MellowLangRange:
    """Lightweight, non-list range view.

    - Compatible with MellowLangVM foreach loop (LEN + GETITEM).
    - Semantics match Python's range(): end is exclusive.

    NOTE: This is intentionally not a list to reduce memory.
    """

    __slots__ = ("start", "end", "step", "_len")

    def __init__(self, start: int, end: int, step: int = 1):
        if step == 0:
            raise ValueError("range: step cannot be 0")
        self.start = int(start)
        self.end = int(end)
        self.step = int(step)
        self._len = self._calc_len()

    def _calc_len(self) -> int:
        s, e, st = self.start, self.end, self.step
        if st > 0:
            if s >= e:
                return 0
            # ceil((e - s)/st)
            return (e - s + st - 1) // st
        else:
            if s <= e:
                return 0
            st_abs = -st
            return (s - e + st_abs - 1) // st_abs

    def __len__(self) -> int:
        return self._len

    def __getitem__(self, idx: int):
        i = int(idx)
        if i < 0 or i >= self._len:
            raise IndexError
        return self.start + i * self.step

    def __iter__(self):
        for i in range(self._len):
            yield self.start + i * self.step

    def __repr__(self) -> str:
        return f"MellowLangRange({self.start}, {self.end}, {self.step})"
