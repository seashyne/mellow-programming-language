# Changelog

## Unreleased

## 2.9.3 - 2026-06-18

### Stability and Documentation
- Add `spec/mellow-2.9.3-stability.json` and `scripts/test-v293-stability.ps1`.
- Extend `mellow release-gate` to run `tests/core`, `tests/language`, and registry smoke tests.
- Add `docs/CORE_DOCS.md`, `docs/LEGACY_BOUNDARIES.md`, and `docs/experimental/README.md`.
- Move agents, MMG, playground, desktop, and hosted-ecosystem docs under `docs/experimental/`.
- Add `tests/language/test_v293_release_contract.py`.

### mellow-sdk
- Add `mellow-sdk` starter package with Python OpenAI SDK-shaped API.
- Add `src/mellowlang/sdk_core.py` host bridge and optional `sdk` Python extra.
- Add `docs/MELLOW_SDK.md`.

## 2.9.2 - 2026-06-16

### Security and Performance Gates
- Add `mellow bench`, `mellow security audit`, and `mellow release-gate`.
- Add release-gate checks for benchmark smoke tests, sandbox enforcement, and official package integrity.
- Make AI agent tool policy default-deny while preserving explicit `--tool` allow behavior.
- Add the Mellow AI security and performance policy document.

### Native Runtime
- Add native LLM tensor batch dispatch plumbing and Python fallback batching.
- Block native storage path traversal before entering the C VM and align native storage source with sandboxed storage paths.

## 2.9.1 - 2026-06-14

### Core LLM
- Add the official `core-llm` package with dataset, training, evaluation,
  generation, completion, chat, checkpoint, backend, and device-planning APIs.
- Add the Mellow-owned native tensor backend foundation with matmul, softmax,
  GELU, and layer-normalization kernels plus a Python reference fallback.
- Add x64 and ARM64 selection to the Windows native build helper.

### Performance
- Add a bounded in-process compiler cache for repeated source compilation.
- Add a fast CLI version path, reducing measured cold version startup from
  roughly 216 ms to roughly 64 ms on the development machine.
- Add batched tensor host calls and separate cold/warm compile benchmarks.

### Native-First Default
- Make the native C VM the default engine for `RunConfig()` and `mellow run`.
- Keep Python fallback enabled for unavailable native builds and runtime features
  without native parity, including debugger, events, and record/replay.
- Preserve `--engine=auto` as a compatibility mode and `--engine=py` as an
  explicit Python override.

## 2.8.0 - 2026-06-13

### Ledger Core
- Add immutable double-entry ledger primitives through `std.ledger`.
- Require every transaction to contain at least two postings whose Decimal amounts sum to zero.
- Add deterministic SHA-256 hash chaining, duplicate transaction protection, balance queries, entry snapshots, and tamper verification.
- Keep ledger creation and posting free of implicit timestamps so replayed inputs produce identical hashes.
- Add strict Python/native parity through the per-run native host bridge.

### Boundaries
- Ledger Core is an in-memory business-rule primitive, not a bank-grade database or payment processor.
- Persistence, authentication, authorization, signatures, external audit storage, and regulatory compliance remain host-application responsibilities.

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
