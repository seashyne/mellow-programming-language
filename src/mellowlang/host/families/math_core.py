"""Mellow host syscall family: math core."""

from __future__ import annotations

from ..base import HostFunction, HostRegistry


def register_math_core_functions(h: HostRegistry) -> None:
    """Register the math core syscalls on a fresh host registry."""
    def _clamp(args):
        x, lo, hi = float(args[0]), float(args[1]), float(args[2])
        return max(lo, min(hi, x))
    h.register(HostFunction(
        name="math.clamp",
        handler=_clamp,
        cost=1,
        min_args=3,
        max_args=3
    ))

    
    # ----- std.math (advanced) -----
    import math as _math
    h.register(HostFunction('std.math.abs', lambda a: abs(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.min', lambda a: float(a[0]) if float(a[0]) < float(a[1]) else float(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.max', lambda a: float(a[0]) if float(a[0]) > float(a[1]) else float(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.floor', lambda a: _math.floor(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.ceil', lambda a: _math.ceil(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.round', lambda a: round(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.sqrt', lambda a: _math.sqrt(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.pow', lambda a: _math.pow(float(a[0]), float(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.sin', lambda a: _math.sin(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.cos', lambda a: _math.cos(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.tan', lambda a: _math.tan(float(a[0])), cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.atan2', lambda a: _math.atan2(float(a[0]), float(a[1])), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.pi', lambda a: _math.pi, cost=1, min_args=0, max_args=0))
    h.register(HostFunction('std.math.clamp', _clamp, cost=1, min_args=3, max_args=3))
    def _lerp(args):
        a0, a1, t = float(args[0]), float(args[1]), float(args[2])
        return a0 + (a1 - a0) * t
    h.register(HostFunction('std.math.lerp', _lerp, cost=1, min_args=3, max_args=3))
