from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import statistics
import subprocess
import time
from pathlib import Path


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def run_benchmark(
    binary: Path,
    source: Path,
    repeats: int,
    command_prefix: str,
    architecture: str,
    mode: str,
) -> dict[str, object]:
    command = [*shlex.split(command_prefix), str(binary), str(source)]

    warmup = subprocess.run(command, capture_output=True, text=True, check=True)
    expected_output = warmup.stdout
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        samples.append(time.perf_counter() - started)
        if completed.stdout != expected_output:
            raise RuntimeError("benchmark output changed between runs")

    median = statistics.median(samples)
    return {
        "architecture": architecture,
        "mode": mode,
        "host": platform.platform(),
        "command": command,
        "repeats": repeats,
        "output": expected_output.strip(),
        "median_seconds": median,
        "p95_seconds": _percentile(samples, 0.95),
        "min_seconds": min(samples),
        "max_seconds": max(samples),
        "runs_per_second": 1.0 / median,
        "samples_seconds": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark the standalone Mellow C runtime."
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--command-prefix", default="")
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--mode", choices=("native", "qemu-emulated"), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error("--repeats must be at least 3")

    result = run_benchmark(
        args.binary,
        args.source,
        args.repeats,
        args.command_prefix,
        args.architecture,
        args.mode,
    )
    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)

    if os.environ.get("GITHUB_ACTIONS") == "true":
        median_ms = float(result["median_seconds"]) * 1_000
        p95_ms = float(result["p95_seconds"]) * 1_000
        print(
            f"::notice title=Mellow {args.architecture} benchmark::"
            f"mode={args.mode}, median={median_ms:.3f} ms, "
            f"p95={p95_ms:.3f} ms, repeats={args.repeats}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
