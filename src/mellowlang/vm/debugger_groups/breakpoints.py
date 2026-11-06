"""Parsing the breakpoint specifications a debug run is configured with."""

from __future__ import annotations


class BreakpointMixin:
    def _parse_break_lines(self, spec: str) -> set[int]:
        out: set[int] = set()
        spec = (spec or "").strip()
        if not spec:
            return out
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    lo = int(a.strip()); hi = int(b.strip())
                except Exception:
                    continue
                if hi < lo:
                    lo, hi = hi, lo
                for n in range(lo, hi + 1):
                    out.add(n)
            else:
                try:
                    out.add(int(part))
                except Exception:
                    continue
        return out
