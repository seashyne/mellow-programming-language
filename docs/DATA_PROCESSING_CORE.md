# Data Processing Core

Mellow v2.6.0 processes large files as bounded batches instead of loading an
entire dataset into one list.

## Runtime model

- JSONL and CSV streams are opened as opaque handles.
- `data_next(handle)` returns at most the configured batch size.
- Empty batches signal end-of-stream.
- `data_cancel` and `data_close` release resources.
- `--max-ms` is checked while reading records and executing data operations.

## Recommended command

```bash
mellow run job.mellow --sandbox=data --data-batch-size 1000 --data-max-rows 5000
```

SQLite writes are disabled unless explicitly enabled:

```bash
mellow run import.mellow --sandbox=data --data-write
```

## Benchmark

```bash
python benchmarks/data_core_benchmark.py --rows 10000
python benchmarks/data_core_benchmark.py --rows 100000
python benchmarks/data_core_benchmark.py --rows 1000000
```

The benchmark reports elapsed time and rows per second. Performance depends on
storage, Python version, record width, and transformation complexity.

## Boundaries

This core is intended for business rules, ETL-style scripts, validation, and
batch orchestration. Databases and analytical engines should remain responsible
for storage, indexing, joins, parallel scans, and distributed execution.
