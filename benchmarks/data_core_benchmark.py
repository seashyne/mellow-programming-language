from __future__ import annotations

import argparse
import json
import time

from mellowlang.data_core import DataStreamManager


def run_benchmark(rows: int, batch_size: int) -> dict[str, float | int]:
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
    elapsed = time.perf_counter() - started
    return {
        "rows": consumed,
        "batch_size": batch_size,
        "elapsed_seconds": elapsed,
        "rows_per_second": consumed / elapsed if elapsed else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=1_000)
    args = parser.parse_args()
    print(json.dumps(run_benchmark(args.rows, args.batch_size), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
