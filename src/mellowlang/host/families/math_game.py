"""Mellow host syscall family: math game."""

from __future__ import annotations

from ..base import HostFunction, HostRegistry


def register_math_game_functions(h: HostRegistry) -> None:
    """Register the math game syscalls on a fresh host registry."""
    # ==========================================================
    # v1.4.7: Math game helpers
    # ==========================================================
    import math as _math

    h.register(HostFunction('std.math.sign',
        lambda a: (1 if float(a[0]) > 0 else (-1 if float(a[0]) < 0 else 0)),
        cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.fmod',
        lambda a: float(a[0]) % float(a[1]), cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.deg_to_rad',
        lambda a: float(a[0]) * _math.pi / 180.0, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.rad_to_deg',
        lambda a: float(a[0]) * 180.0 / _math.pi, cost=1, min_args=1, max_args=1))

    def _distance(args):
        ax, ay = float(args[0][0]), float(args[0][1])
        bx, by = float(args[1][0]), float(args[1][1])
        return _math.sqrt((bx-ax)**2 + (by-ay)**2)
    h.register(HostFunction('std.math.distance', _distance, cost=1, min_args=2, max_args=2))

    def _angle_between(args):
        ax, ay = float(args[0][0]), float(args[0][1])
        bx, by = float(args[1][0]), float(args[1][1])
        return _math.degrees(_math.atan2(by-ay, bx-ax))
    h.register(HostFunction('std.math.angle_between', _angle_between, cost=1, min_args=2, max_args=2))
