# Changelog

## 2.7.1 - 2026-06-13

### Native Data Acceleration
- Implement `std.data.where`, `std.data.project`, and `std.data.sum` directly in the C VM.
- Preserve Python VM behavior for comparison operators, `contains`, missing fields, mixed integer/float sums, and non-map rows.
- Align native `None` output with the Python VM while extending strict output parity coverage.
- Add native transform edge-case parity coverage with Python fallback disabled.
- Add `benchmarks/native_data_transform_benchmark.py` for repeatable Python/C engine comparisons.
- Improve the representative where+project+sum workload from about 1.33x native speedup before this patch to about 3.2-4.1x, reaching roughly 8.3-10.8 million rows/second on the development machine.

### Boundaries
- JSONL/CSV parsing, stream handles, SQLite, sandbox path checks, deadlines, and cleanup remain managed by the host bridge.

## 2.7.0 - 2026-06-13

### Native Stdlib Parity
- Add a per-run native host bridge so the C VM can call stateful and optional stdlib services without falling back to the Python VM.
- Add strict native parity for Decimal-backed `std.money`.
- Add strict native parity for bounded JSONL/CSV streams and parameterized SQLite in `std.data`.
- Preserve data batch, record, stream, query, write, path, and time limits in native execution.
- Close native data streams and SQLite handles at the end of every run.
- Enforce storage denial inside the C VM for the finance sandbox profile.
- Stop forcing finance and data sandbox profiles to the Python VM.
- Add native money, JSONL, and SQLite lifecycle tests with fallback disabled.

### Deferred
- Native debugger, event dispatch, and deterministic record/replay parity.
- Native implementations for external database adapters and distributed data execution.

## 2.6.0 - 2026-06-13

### Data Processing Core
- Add bounded streaming readers for JSONL and CSV.
- Add batch projection, filtering, field summation, stream inspection, cancellation, and close operations.
- Add parameterized SQLite query/execute APIs with row limits and read-only query enforcement.
- Add persistent SQLite handles, including in-memory databases for transactional rule workflows.
- Add `--sandbox=data` and CLI controls for batch size, record size, open streams, query rows, and explicit data-write permission.
- Route data-core programs through the Python VM until native data parity is implemented.
- Add fixtures, core tests, an example program, and a 10K/100K/1M-capable benchmark.

### Safety
- Batch size and query results are bounded to provide backpressure.
- Runtime time limits are checked during stream reads and database operations.
- SQL values are bound through placeholders rather than string interpolation.

### Deferred
- Native C VM parity for `std.data`.
- External PostgreSQL/ClickHouse adapters.
- Parallel workers and distributed execution.

## 2.5.0 - 2026-06-13

### Production Scripting Core
- Add Decimal-backed `std.money` helpers for exact money-style rules.
- Add top-level money aliases such as `money(...)`, `money_add(...)`, and `money_format(...)`.
- Add `--sandbox=finance` for stricter rule-script execution: no ask/wait/storage/save/network and Python VM routing until native sandbox parity is complete.
- Teach the IR compiler path to lower money stdlib calls without treating them as user skills.
- Add core tests for money precision and finance sandbox enforcement.

### Deferred
- Native C VM parity for `std.money`.
- A full language-level `decimal` literal/type syntax.
- Audit-log and immutable ledger primitives.

## 2.4.0 - 2026-06-13

### Native Core Parity
- Add `tests/native` as the strict Python VM vs native C VM parity gate for the stable language core.
- Fix the Python-to-C VM bridge so current native extensions can run without accidental `host=` keyword failures.
- Add native C support for compiled `range(...)` calls used by stable `for` loops.
- Report native parity as `stable-core` while keeping debugger, event, and record/replay fallback status explicit.
- Build the native extension in CI before running native parity tests.

### Stable
- Bump package and runtime version to `2.4.0`.
- Keep `frameworks.mellow_ui` in the release verification set.

### Deferred
- Native debugger pause/inspect parity.
- Native event handler execution parity.
- Native record/replay parity.

## 2.3.5 - 2026-06-13

### Release Polish
- Treat `tests/core` as the stable release gate.
- Limit GitHub Actions to stable core tests while legacy and experimental suites are being triaged.
- Add stable-core documentation and a release checklist.
- Add a Windows native build helper script for the optional C extension.
- Make `frameworks.mellow_ui` installable and runnable as a Python framework package.
- Add JSON rendering support for Mellow UI framework previews/tools.

### Deferred
- Full legacy and experimental test suite cleanup.
- Broader native VM parity beyond core execution.
- Packaging binary artifacts for release downloads.

## 2.3.4 - 2026-06-04

### Stable
- Added `tests/core` as the stable language gate.
- Improved `mellow doctor` output and optional feature reporting.
- Split optional dependencies out of the default install.
- Fixed core language regressions around functions, `range(...)`, and indexed values.
- Fixed Windows native VM build issues in source.

### Experimental
- Native VM can run core examples through `--engine=c`, but the Python VM remains needed for record/replay, event handlers, and debugger parity.
- Agent, MMG, desktop, registry, and full legacy test surfaces are not release gates yet.
