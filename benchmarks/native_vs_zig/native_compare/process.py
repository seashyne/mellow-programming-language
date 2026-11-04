from __future__ import annotations

import statistics
import subprocess
import time
from typing import Any


def _time_command(command: list[str], repeats: int, expected_output: str) -> dict[str, Any]:
    warmup = subprocess.run(command, capture_output=True, text=True, check=True)
    expected = warmup.stdout.strip()
    if expected != expected_output:
        raise RuntimeError(f"unexpected output from {' '.join(command)}: {expected}")

    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        elapsed = time.perf_counter() - started
        output = completed.stdout.strip()
        if output != expected:
            raise RuntimeError(f"benchmark output changed: {output} != {expected}")
        samples.append(elapsed)

    median = statistics.median(samples)
    return {
        "command": command,
        "output": expected,
        "repeats": repeats,
        "median_ms": median * 1000.0,
        "average_ms": statistics.fmean(samples) * 1000.0,
        "min_ms": min(samples) * 1000.0,
        "max_ms": max(samples) * 1000.0,
        "samples_ms": [sample * 1000.0 for sample in samples],
    }


def _zig_version(zig: str) -> str:
    return subprocess.run([zig, "version"], capture_output=True, text=True, check=True).stdout.strip()


def _tool_version(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    return (completed.stdout or completed.stderr).strip()
