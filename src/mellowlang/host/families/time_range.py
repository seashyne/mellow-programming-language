"""Mellow host syscall family: time range."""

from __future__ import annotations

from ...range_core import MellowLangRange
from ..base import HostFunction, HostRegistry


def register_time_range_functions(h: HostRegistry) -> None:
    """Register the time range syscalls on a fresh host registry."""
    # ----- std.time (advanced) -----
    import time as _time
    h.register(HostFunction('std.time.unix', lambda a: _time.time(), cost=1, min_args=0, max_args=0))
    h.register(HostFunction('std.time.ms', lambda a: int(_time.time() * 1000), cost=1, min_args=0, max_args=0))
    # Note: std.time.now is monotonic since host start; not guaranteed deterministic unless replayed
    start = _time.perf_counter()
    h.register(HostFunction('std.time.now', lambda a: _time.perf_counter() - start, cost=1, min_args=0, max_args=0))

# range (Python-like): std.range(end) or std.range(start, end, step)
    def _std_range(args):
        # returns an iterator-like view (no list allocation)
        if len(args) == 1:
            start, end, step = 0, int(args[0]), 1
        elif len(args) == 2:
            start, end, step = int(args[0]), int(args[1]), 1
        elif len(args) == 3:
            start, end, step = int(args[0]), int(args[1]), int(args[2])
        else:
            raise RuntimeError('std.range: expected 1-3 args')
        if step == 0:
            raise RuntimeError('std.range: step cannot be 0')
        return MellowLangRange(start, end, step)

    h.register(HostFunction(
        name='std.range',
        handler=_std_range,
        cost=1,
        min_args=1,
        max_args=3
    ))
    h.register(HostFunction(
        name='range',
        handler=_std_range,
        cost=1,
        min_args=1,
        max_args=3
    ))
