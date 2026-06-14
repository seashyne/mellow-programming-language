from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from mellowlang import __version__
from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig
from mellowlang.vm.cbridge import c_vm_capabilities


@dataclass(frozen=True)
class Workload:
    name: str
    units: int
    unit_name: str
    source: str


WORKLOADS = (
    Workload(
        name="arithmetic_loop",
        units=20_000,
        unit_name="iterations",
        source="""
let i = 0
let total = 0
while i < 20000:
    total = total + i
    i = i + 1
""".lstrip(),
    ),
    Workload(
        name="function_calls",
        units=8_000,
        unit_name="calls",
        source="""
def add_one(value):
    return value + 1

let i = 0
let total = 0
while i < 8000:
    total = add_one(total)
    i = i + 1
""".lstrip(),
    ),
    Workload(
        name="money_add",
        units=3_000,
        unit_name="operations",
        source="""
let i = 0
let total = money("0.00", "THB")
let step = money("0.01", "THB")
while i < 3000:
    total = money_add(total, step)
    i = i + 1
""".lstrip(),
    ),
    Workload(
        name="ledger_post",
        units=60,
        unit_name="transactions",
        source="""
let i = 0
let book = ledger_create("THB")
while i < 60:
    book = ledger_post(
        book,
        f"tx-{i}",
        [
            {"account": "cash", "amount": "1.00"},
            {"account": "revenue", "amount": "-1.00"}
        ]
    )
    i = i + 1
""".lstrip(),
    ),
)


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _measure(repeats: int, operation: Callable[[], None]) -> dict[str, object]:
    samples: list[float] = []
    operation()
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - started)
    return {
        "median_seconds": statistics.median(samples),
        "p95_seconds": _percentile(samples, 0.95),
        "min_seconds": min(samples),
        "max_seconds": max(samples),
        "samples_seconds": samples,
    }


def _runtime_result(workload: Workload, engine: str, repeats: int) -> dict[str, object]:
    program = Compiler().compile(workload.source, filename=f"<benchmark:{workload.name}>")
    last_vm: MellowVM | None = None

    def run_once() -> None:
        nonlocal last_vm
        last_vm = MellowVM()
        last_vm.run(
            program,
            config=RunConfig(
                engine=engine,
                native_allow_fallback=False,
                native_require=(engine == "c"),
                max_steps=5_000_000,
                syscall_budget=1_000_000,
            ),
        )

    result = _measure(repeats, run_once)
    median = float(result["median_seconds"])
    result.update(
        {
            "engine_requested": engine,
            "engine_used": last_vm.last_engine if last_vm else None,
            "engine_detail": last_vm.last_engine_detail if last_vm else None,
            "units": workload.units,
            "unit_name": workload.unit_name,
            "units_per_second": workload.units / median if median else 0,
        }
    )
    return result


def _compile_result(repeats: int) -> dict[str, object]:
    source = "\n".join(
        f"let value_{index} = ({index} + 3) * 2"
        for index in range(250)
    )
    result = _measure(
        repeats,
        lambda: Compiler().compile(source, filename="<benchmark:compile>"),
    )
    result["source_lines"] = 250
    result["lines_per_second"] = 250 / float(result["median_seconds"])
    return result


def _cli_startup_result(repeats: int, root: Path) -> dict[str, object]:
    command = [sys.executable, "-m", "mellowlang", "--version"]

    def run_once() -> None:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout)

    result = _measure(repeats, run_once)
    result["command"] = command
    return result


def run_benchmark(repeats: int) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    runtime: dict[str, object] = {}
    for workload in WORKLOADS:
        engines = {
            engine: _runtime_result(workload, engine, repeats)
            for engine in ("py", "c")
        }
        engines["native_speedup"] = (
            float(engines["py"]["median_seconds"])
            / float(engines["c"]["median_seconds"])
        )
        runtime[workload.name] = engines

    return {
        "metadata": {
            "mellow_version": __version__,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "repeats": repeats,
            "native_capabilities": c_vm_capabilities(),
        },
        "compile": _compile_result(repeats),
        "cli_startup": _cli_startup_result(repeats, root),
        "runtime": runtime,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error("--repeats must be at least 3")

    result = run_benchmark(args.repeats)
    payload = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
