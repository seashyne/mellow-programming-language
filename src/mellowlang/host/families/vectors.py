"""Mellow host syscall family: vectors."""

from __future__ import annotations

import math as _math
from ..base import HostFunction, HostRegistry


def register_vectors_functions(h: HostRegistry) -> None:
    """Register the vectors syscalls on a fresh host registry."""
    # ----- std.math (vectors) -----
    # Representation: vectors are plain python lists [x,y,...]
    # Design goals (MellowLang identity):
    #  - fast in VM hot loops
    #  - works for multiple domains (2D/3D/ND) without adding OOP/metatables
    #  - predictable errors
    _VEC_MIN_DIM = 2
    _VEC_MAX_DIM = 16

    def _expect_vec(v) -> int:
        if not isinstance(v, list):
            raise RuntimeError('std.math.vec: expected vector list')
        n = len(v)
        if n < _VEC_MIN_DIM or n > _VEC_MAX_DIM:
            raise RuntimeError(f'std.math.vec: dimension must be {_VEC_MIN_DIM}-{_VEC_MAX_DIM} (got {n})')
        return n

    def _vector(args):
        """Generic vector constructor.

        Supported:
          - vector(x, y, ...) / vec(x, y, ...)  (dimension inferred from arg count)
          - vector(dim, x, y, ...)             (explicit dim, must match values count)
          - vector(existing_vec)               (copy)
        """
        if len(args) == 1 and isinstance(args[0], list):
            v = args[0]
            n = _expect_vec(v)
            return [float(v[i]) for i in range(n)]

        if len(args) >= 3 and isinstance(args[0], (int, float)):
            dim = int(args[0])
            # explicit dim form only if it matches remaining values
            if dim >= _VEC_MIN_DIM and dim <= _VEC_MAX_DIM and (len(args) - 1) == dim:
                vals = args[1:]
                return [float(x) for x in vals]

        # inferred dimension
        if len(args) < _VEC_MIN_DIM:
            raise RuntimeError(f'std.math.vector: expected at least {_VEC_MIN_DIM} numbers')
        if len(args) > _VEC_MAX_DIM:
            raise RuntimeError(f'std.math.vector: too many components (max {_VEC_MAX_DIM})')
        return [float(x) for x in args]

    def _vec2(args):
        return [float(args[0]), float(args[1])]

    def _vec3(args):
        return [float(args[0]), float(args[1]), float(args[2])]

    def _vec_add(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_add: dimension mismatch')
        return [float(a[i]) + float(b[i]) for i in range(n)]

    def _vec_sub(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_sub: dimension mismatch')
        return [float(a[i]) - float(b[i]) for i in range(n)]

    def _vec_mul(args):
        a, s = args[0], float(args[1])
        n = _expect_vec(a)
        return [float(a[i]) * s for i in range(n)]

    def _vec_dot(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_dot: dimension mismatch')
        return sum(float(a[i]) * float(b[i]) for i in range(n))

    def _vec_len(args):
        a = args[0]
        n = _expect_vec(a)
        return _math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(n)))

    def _vec_norm(args):
        a = args[0]
        n = _expect_vec(a)
        l = _math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(n)))
        if l == 0:
            return [0.0 for _ in range(n)]
        return [float(a[i]) / l for i in range(n)]

    def _vec_dist(args):
        a, b = args[0], args[1]
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_dist: dimension mismatch')
        return _math.sqrt(sum((float(a[i]) - float(b[i]))**2 for i in range(n)))

    def _vec_dim(args):
        return _expect_vec(args[0])

    def _vec_axis(args):
        v, idx = args[0], args[1]
        n = _expect_vec(v)
        try:
            i = int(idx)
        except Exception:
            raise RuntimeError('std.math.vec_axis: index must be int')
        if i < 0 or i >= n:
            raise RuntimeError(f'std.math.vec_axis: index out of range (0..{n-1}, got {i})')
        return float(v[i])

    def _vec_lerp(args):
        a, b, t = args[0], args[1], float(args[2])
        n = _expect_vec(a)
        if _expect_vec(b) != n:
            raise RuntimeError('std.math.vec_lerp: dimension mismatch')
        return [float(a[i]) + (float(b[i]) - float(a[i])) * t for i in range(n)]

    def _vec_limit(args):
        v, max_len = args[0], float(args[1])
        n = _expect_vec(v)
        if max_len < 0:
            max_len = 0.0
        l = _math.sqrt(sum(float(v[i]) * float(v[i]) for i in range(n)))
        if l == 0 or l <= max_len:
            return [float(v[i]) for i in range(n)]
        s = max_len / l
        return [float(v[i]) * s for i in range(n)]

    # register
    h.register(HostFunction('std.math.vector', _vector, cost=1, min_args=1, max_args=_VEC_MAX_DIM+1))
    h.register(HostFunction('std.math.vec2', _vec2, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec3', _vec3, cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.math.vec_add', _vec_add, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_sub', _vec_sub, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_mul', _vec_mul, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_dot', _vec_dot, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_len', _vec_len, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.vec_norm', _vec_norm, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.vec_dist', _vec_dist, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_dim', _vec_dim, cost=1, min_args=1, max_args=1))
    h.register(HostFunction('std.math.vec_axis', _vec_axis, cost=1, min_args=2, max_args=2))
    h.register(HostFunction('std.math.vec_lerp', _vec_lerp, cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.math.vec_limit', _vec_limit, cost=1, min_args=2, max_args=2))
