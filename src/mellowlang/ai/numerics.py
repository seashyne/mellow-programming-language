"""Numeric helpers used across the AI surface."""

from __future__ import annotations

import math
from typing import List


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))

def _relu(x: float) -> float:
    return max(0.0, x)

def _softmax(xs: List[float]) -> List[float]:
    m = max(xs)
    exps = [math.exp(v - m) for v in xs]
    s = sum(exps)
    return [v / s for v in exps]

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))

def _matmul(mat: List[List[float]], vec: List[float]) -> List[float]:
    return [_dot(row, vec) for row in mat]

def _add_vec(a: List[float], b: List[float]) -> List[float]:
    return [x + y for x, y in zip(a, b)]

def _scale_vec(a: List[float], s: float) -> List[float]:
    return [x * s for x in a]

def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    aa = a[:n]
    bb = b[:n]
    dot = sum(x * y for x, y in zip(aa, bb))
    ma = math.sqrt(sum(x * x for x in aa)) or 1.0
    mb = math.sqrt(sum(y * y for y in bb)) or 1.0
    return dot / (ma * mb)
