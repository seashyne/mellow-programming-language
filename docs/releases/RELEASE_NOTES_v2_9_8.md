# Release Notes v2.9.8

v2.9.8 moves runtime services into native C. The language surface did not grow;
what changed is where storage, ledger, money, and server work executes, so the
same bytecode now behaves the same on all three engines.

## Native service migration

- `storage_*`, `save_*`, `fs_*`, and `file_*` lower to `std.*` syscalls and run
  in C on both the CPython extension (`--engine=c`) and the standalone
  executable.
- The save-path sandbox is enforced inside the native engines, so a native
  program cannot write outside the project save root either.
- Ledger, money, server, and the SM CLI share the native syscall id table, so
  one registration path serves all of them.
- The Python VM keeps its legacy builtins and re-enters them from the syscall
  instruction on a VM-private bytecode copy, which leaves the shared compile
  cache untouched.

## Parity coverage

- `tests/fixtures/storage_core.mellow` and `tests/fixtures/ledger_core.mellow`
  are the shared fixtures; native entry hashes are compared against
  `mellowlang.ledger_core`.
- `tests/native` covers the migrated services end to end against the built
  `mellow.exe`.
- `examples/native_server.mellow` is the maintained native HTTP example used by
  `mellow server serve`.

## Workspace boundaries

- The boundary gate now rejects build artifacts committed at the repository
  root and any `native/` surface missing from `docs/PROJECT_STRUCTURE.md`.
- Generated trees (`mellow_agent_packages/`, benchmark scratch dirs) are
  ignored instead of cleaned up after the fact.

## Deferred

- The encrypted save envelope (ChaCha20Poly1305 with HKDF) stays a Python
  service; the native side stores and verifies, phase 2 moves the crypto.
- MELV standalone CLI hooks remain Python-side until the storage track closes.

## Benchmarks (quick profile)

- `arithmetic_loop` 25.2-25.6x over the Python VM, `function_calls` 7.6-9.8x,
  `money_add` 2.7x.
- Standalone native run median 6.5-7.0 ms, Python CLI startup 63-64 ms.
- `ledger_post` still reads 0.66-0.69x because the workload is only 60
  transactions and the native side is timed as a subprocess, so process startup
  and compilation dominate the measurement.
