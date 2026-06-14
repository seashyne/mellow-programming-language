from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig


def _source(rows: int, rounds: int) -> str:
    values = ",".join(
        f'{{"id":{index},"kind":"sale","amount":{index % 100}}}'
        for index in range(rows)
    )
    return (
        f"let rows = [{values}]\n"
        "let round = 0\n"
        "let total = 0\n"
        f"while round < {rounds}:\n"
        '    let selected = data.where(rows, "amount", ">=", 50)\n'
        '    let projected = data.project(selected, ["id", "amount"])\n'
        '    total = data.sum(projected, "amount")\n'
        "    round = round + 1\n"
    )


def run_benchmark(rows: int, rounds: int, repeats: int) -> dict[str, object]:
    program = Compiler().compile(_source(rows, rounds), filename="<native-data-benchmark>")
    results: dict[str, object] = {
        "rows": rows,
        "rounds": rounds,
        "rows_processed_per_transform": rows * rounds,
        "repeats": repeats,
        "engines": {},
    }
    for engine in ("py", "c"):
        samples: list[float] = []
        for _ in range(repeats):
            vm = MellowVM()
            started = time.perf_counter()
            vm.run(
                program,
                config=RunConfig(
                    engine=engine,
                    native_allow_fallback=False,
                    native_require=(engine == "c"),
                    max_steps=10_000_000,
                    syscall_budget=1_000_000,
                ),
            )
            samples.append(time.perf_counter() - started)
        median = statistics.median(samples)
        results["engines"][engine] = {
            "median_seconds": median,
            "rows_per_second": (rows * rounds) / median,
            "samples_seconds": samples,
        }
    py_median = results["engines"]["py"]["median_seconds"]
    c_median = results["engines"]["c"]["median_seconds"]
    results["native_speedup"] = py_median / c_median
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000)
    parser.add_argument("--rounds", type=int, default=250)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.rows > 1_500:
        parser.error("--rows must be <= 1500 to stay within the VM stack limit")
    payload = json.dumps(
        run_benchmark(args.rows, args.rounds, args.repeats),
        indent=2,
    )
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
