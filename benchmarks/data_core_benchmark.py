from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from mellowlang.data_core import DataStreamManager


def run_benchmark(rows: int, batch_size: int, repeats: int = 5) -> dict[str, object]:
    samples: list[float] = []
    consumed = 0
    for _ in range(repeats):
        manager = DataStreamManager(
            resolve_read=str,
            resolve_write=str,
            check_cancelled=lambda: None,
            max_batch_size=batch_size,
        )
        source = ({"id": index, "amount": index % 100} for index in range(rows))
        started = time.perf_counter()
        stream = manager.open_iterable(source, batch_size)
        consumed = 0
        while True:
            batch = manager.next_batch(stream)
            if not batch:
                break
            consumed += len(batch)
        samples.append(time.perf_counter() - started)
    elapsed = statistics.median(samples)
    return {
        "rows": consumed,
        "batch_size": batch_size,
        "repeats": repeats,
        "median_seconds": elapsed,
        "samples_seconds": samples,
        "rows_per_second": consumed / elapsed if elapsed else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = json.dumps(
        run_benchmark(args.rows, args.batch_size, args.repeats),
        indent=2,
    )
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
