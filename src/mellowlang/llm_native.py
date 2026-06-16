from __future__ import annotations

import math
from typing import Any, Iterable, List


try:
    from . import _mellowllm as _native  # type: ignore
except Exception:
    _native = None


def _flatten(values: Iterable[Any]) -> List[float]:
    return [float(v) for v in values]


def available() -> bool:
    return _native is not None


def capabilities() -> dict:
    if _native is not None:
        caps = dict(_native.capabilities())
        caps["available"] = True
        return caps
    return {
        "available": False,
        "backend": "python-reference",
        "kernels": ["matmul", "softmax", "gelu", "layer_norm", "batch"],
        "devices": ["cpu"],
        "dtype": "float64",
    }


def matmul(a: list, b: list, m: int, n: int, k: int) -> list:
    if _native is not None:
        return list(_native.matmul(_flatten(a), _flatten(b), int(m), int(n), int(k)))
    af = _flatten(a)
    bf = _flatten(b)
    out = []
    for row in range(m):
        for col in range(n):
            total = 0.0
            for idx in range(k):
                total += af[row * k + idx] * bf[idx * n + col]
            out.append(total)
    return out


def softmax(values: list) -> list:
    if _native is not None:
        return list(_native.softmax(_flatten(values)))
    xs = _flatten(values)
    if not xs:
        return []
    peak = max(xs)
    exps = [math.exp(x - peak) for x in xs]
    total = sum(exps) or 1.0
    return [x / total for x in exps]


def gelu(values: list) -> list:
    if _native is not None:
        return list(_native.gelu(_flatten(values)))
    return [
        0.5 * x * (1.0 + math.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x * x * x)))
        for x in _flatten(values)
    ]


def layer_norm(values: list, gamma: list | None = None, beta: list | None = None, eps: float = 1e-5) -> list:
    xs = _flatten(values)
    g = _flatten(gamma or [1.0] * len(xs))
    b = _flatten(beta or [0.0] * len(xs))
    if _native is not None:
        return list(_native.layer_norm(xs, g, b, float(eps)))
    if not xs:
        return []
    mean = sum(xs) / len(xs)
    var = sum((x - mean) * (x - mean) for x in xs) / len(xs)
    scale = 1.0 / math.sqrt(var + float(eps))
    return [((x - mean) * scale) * g[i] + b[i] for i, x in enumerate(xs)]


def run_operation(item: dict) -> dict:
    op = str(item.get("op", ""))
    if op == "matmul":
        return {
            "op": op,
            "backend": capabilities().get("backend"),
            "values": matmul(
                item.get("a", []),
                item.get("b", []),
                int(item.get("m", 0)),
                int(item.get("n", 0)),
                int(item.get("k", 0)),
            ),
        }
    if op == "softmax":
        return {"op": op, "backend": capabilities().get("backend"), "values": softmax(item.get("values", []))}
    if op == "gelu":
        return {"op": op, "backend": capabilities().get("backend"), "values": gelu(item.get("values", []))}
    if op == "layer_norm":
        return {
            "op": op,
            "backend": capabilities().get("backend"),
            "values": layer_norm(item.get("values", []), item.get("gamma"), item.get("beta"), float(item.get("eps", 1e-5))),
        }
    return {"error": f"unknown tensor op: {op}"}


def run_batch(operations: list) -> list:
    if _native is not None and hasattr(_native, "batch"):
        return list(_native.batch(operations))
    results = []
    for index, item in enumerate(operations):
        if not isinstance(item, dict):
            results.append({"index": index, "error": "operation must be a map"})
            continue
        try:
            result = run_operation(item)
        except Exception as exc:
            result = {"error": f"{item.get('op', '')} failed: {exc}"}
        result["index"] = index
        results.append(result)
    return results
