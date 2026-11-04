from __future__ import annotations

import subprocess
from typing import Any

from .process import _time_command


def _benchmark_runtime(
    result: dict[str, Any],
    workload: str,
    runtime: str,
    command: list[str],
    repeats: int,
    expected_output: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    slot = result["workloads"][workload].setdefault(runtime, {})
    if metadata:
        slot.update(metadata)
    slot["available"] = True
    try:
        slot["benchmark"] = _time_command(command, repeats, expected_output)
    except subprocess.CalledProcessError as exc:
        slot["failed"] = True
        slot["returncode"] = exc.returncode
        slot["stdout"] = exc.stdout
        slot["stderr"] = exc.stderr
        slot["command"] = command
    except RuntimeError as exc:
        slot["failed"] = True
        slot["error"] = str(exc)
        slot["command"] = command


def _ratio_summary(workload_result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    mellow = workload_result.get("mellow", {})
    mellow_bench = mellow.get("benchmark")
    if not mellow_bench:
        return summary
    mellow_median = float(mellow_bench["median_ms"])
    summary["mellow_median_ms"] = mellow_median
    for runtime in ("zig", "c", "python", "lua"):
        bench = workload_result.get(runtime, {}).get("benchmark")
        if not bench:
            continue
        runtime_median = float(bench["median_ms"])
        summary[f"{runtime}_median_ms"] = runtime_median
        if runtime in {"python", "lua"}:
            summary[f"mellow_faster_than_{runtime}_by"] = runtime_median / mellow_median if mellow_median else None
        else:
            summary[f"{runtime}_faster_by"] = mellow_median / runtime_median if runtime_median else None
    return summary
