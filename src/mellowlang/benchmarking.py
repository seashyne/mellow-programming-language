from __future__ import annotations

import statistics
import time
from typing import Any

from .compiler.compiler import Compiler
from .vm import MellowVM, RunConfig


def _median_ms(samples: list[float]) -> float:
    return round(statistics.median(samples) * 1000.0, 3) if samples else 0.0


def _bench_compile(rounds: int) -> dict[str, Any]:
    source = "\n".join([
        "let total = 0",
        "for i in range(0, 100):",
        "    total = total + i",
        "print(total)",
        "",
    ])
    cold: list[float] = []
    warm: list[float] = []
    compiler = Compiler()
    Compiler.clear_cache()
    for _ in range(rounds):
        start = time.perf_counter()
        Compiler().compile(source, filename="<bench-cold>")
        cold.append(time.perf_counter() - start)
    for _ in range(rounds):
        start = time.perf_counter()
        compiler.compile(source, filename="<bench-warm>")
        warm.append(time.perf_counter() - start)
    return {
        "name": "compiler",
        "rounds": rounds,
        "cold_ms": _median_ms(cold),
        "warm_cache_ms": _median_ms(warm),
        "cache": Compiler.cache_info(),
    }


def _bench_vm(rounds: int) -> dict[str, Any]:
    source = "\n".join([
        "let total = 0",
        "for i in range(0, 250):",
        "    total = total + i",
        "",
    ])
    program = Compiler().compile(source, filename="<bench-vm>")
    samples: list[float] = []
    for _ in range(rounds):
        vm = MellowVM()
        start = time.perf_counter()
        vm.run(program, config=RunConfig(max_steps=100_000))
        samples.append(time.perf_counter() - start)
    return {
        "name": "python-vm",
        "rounds": rounds,
        "median_ms": _median_ms(samples),
    }


def _bench_native_batch(rounds: int) -> dict[str, Any]:
    from . import llm_native

    operations = [
        {"op": "softmax", "values": [1, 2, 3, 4]},
        {"op": "gelu", "values": [-1, 0, 1]},
        {"op": "layer_norm", "values": [1, 2, 3], "gamma": [1, 1, 1], "beta": [0, 0, 0]},
        {"op": "matmul", "a": [1, 2, 3, 4], "b": [5, 6, 7, 8], "m": 2, "n": 2, "k": 2},
    ]
    samples: list[float] = []
    last: list[dict[str, Any]] = []
    for _ in range(rounds):
        start = time.perf_counter()
        last = llm_native.run_batch(operations)
        samples.append(time.perf_counter() - start)
    return {
        "name": "native-host-batch",
        "rounds": rounds,
        "median_ms": _median_ms(samples),
        "backend": llm_native.capabilities().get("backend"),
        "native_available": bool(llm_native.capabilities().get("available")),
        "operations": len(operations),
        "errors": sum(1 for item in last if "error" in item),
    }


def run_benchmarks(rounds: int = 5) -> dict[str, Any]:
    rounds = max(1, int(rounds))
    suites = [_bench_compile(rounds), _bench_vm(rounds), _bench_native_batch(rounds)]
    return {
        "ok": all(not suite.get("errors") for suite in suites),
        "rounds": rounds,
        "suites": suites,
    }
