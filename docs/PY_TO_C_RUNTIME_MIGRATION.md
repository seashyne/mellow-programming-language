# Python to C / Mellow Runtime Migration

This document tracks the path for moving old Python-backed systems into the
native C runtime and exposing them through Mellow runtime APIs.

## Goal

The target is a Mellow distribution where normal users can compile, run, package,
and use core runtime features without loading Python or CPython.

Python may remain as a development/bootstrap tool during migration, but it must
not be required by the stable runtime path.

## Current Native Base

The native runtime already exists under `native/standalone/`:

- `src/mellowc.c`, `src/mellowc_lexer.c`, `src/mellowc_parser.c` compile
  `.mellow` source to native bytecode.
- `src/mellowrt_core.c` executes bytecode and owns value memory.
- `src/mellowrt_syscalls.c` provides built-in runtime functions.
- `src/mellow_runtime.c` exposes the experimental embeddable C ABI.
- `src/mellowrt_main.c` provides the native `mellow` CLI.

Native add-on systems already started:

- `native/melv/` implements the dependency-free MELV2 video container.
- `native/sm/` implements the dependency-free SM3 Smallless codec.
- `native/mellowvm/` and `native/mellowllm/` provide optional CPython extension
  acceleration while native standalone catches up.

## Migration Rules

1. Runtime-critical behavior moves to C first.
2. User-facing package APIs are exposed through Mellow packages and host
   built-ins, not by importing Python modules.
3. Python wrappers may remain only as compatibility shims while tests prove C
   parity.
4. Existing Python formats must remain readable unless a major version
   explicitly drops them.
5. New C implementations must have conformance tests against the current Python
   behavior before Python becomes optional.

## Priority Order

### P0: Run Programs Without Python

Scope:

- parser/compiler parity for stable Mellow syntax
- bytecode/runtime parity
- imports and installed package resolution
- package API exposure through Mellow source imports
- core built-ins and stdlib surface
- runtime diagnostics and error locations

Primary native files:

- `native/standalone/src/mellowc*.c`
- `native/standalone/src/mellowrt_core.c`
- `native/standalone/src/mellowrt_syscalls.c`
- `native/standalone/src/mellowrt_packages.c`
- `native/standalone/include/*.h`

Python systems to retire from the stable run path:

- `src/mellowlang/parser.py`
- `src/mellowlang/compiler/*.py`
- `src/mellowlang/vm/python_vm.py`
- `src/mellowlang/vm/cbridge.py`
- `src/mellowlang/host/runtime.py`

Status:

- native standalone resolves installed package entries in C
- native compiler expands package source before function scanning
- package aliases such as `use math-kit as kit` can call `kit.double(...)`
  without importing Python

### P1: Native Core Services

Move Python-backed stdlib services into C modules or native runtime built-ins.

Targets:

- storage/file APIs: `src/mellowlang/storage_core.py`, `src/mellowlang/vm/storage.py`
- secure save envelope: `src/mellowlang/save_core.py`
- data transforms and ledger: `src/mellowlang/data_core.py`,
  `src/mellowlang/ledger_core.py`
- time/range/list/math helpers: `src/mellowlang/*_core.py`
- network host bindings: `src/mellowlang/net_core.py`

Expected native layout:

- `native/standalone/src/mellowrt_storage.c`
- `native/standalone/src/mellowrt_save.c`
- `native/standalone/src/mellowrt_data.c`
- `native/standalone/src/mellowrt_net.c`

Use Mellow packages for the public declarations and examples, with C built-ins
behind them.

Landed: storage slots plus the `file_*` and `fs_*` APIs, and the ledger, money,
server, and SM CLI services are native built-ins in both engines
(`native/mellowvm/src/mellowvm_storage.inc`,
`native/standalone/src/mellowrt_storage.c`, `mellowrt_ledger.c`,
`mellowrt_money.c`, `mellowrt_server.c`, `mellowrt_sm_cli.c`).
`tests/fixtures/storage_core.mellow` and `tests/fixtures/ledger_core.mellow` are
the conformance programs they share with the Python VM. Remaining P1 targets:
secure save envelope (`mellowrt_save.c`), network host bindings
(`mellowrt_net.c`), data transforms (`mellowrt_data.c`), and the time/range/list
and math helper cores.

### P2: Native Asset/Codec Tooling

Already started:

- MELV2: `native/melv/`
- SM3: `native/sm/`
- standalone SM CLI module: `native/standalone/src/mellowrt_sm_cli.c`

Remaining work:

- add standalone CLI hooks so native `mellow melv ...` works without Python
- keep Python CLI wrappers as compatibility only
- add CMake targets and C conformance tests for codecs

### P3: Package Manager Without Python Runtime

Package install/publish tooling is currently Python-heavy. This can move in two
steps:

1. native package resolver and lockfile reader for runtime imports
2. native package CLI for install/search/verify/publish

Targets:

- `src/mellowlang/package_manager.py`
- `src/mellowlang/packages/*.py`
- `src/mellowlang/cli/commands/packages.py`

Native runtime import resolution should land before full registry publishing.

Landed: `native/standalone/src/mellowrt_pkg.c` implements the local registry
workflow end to end — `pkg init`, `publish`, `install`, `list`, `search`,
`info`, `add`, `remove`, and `uninstall`, including recursive dependency
installs and the shared `mellow.toml`/`mellow.pkg.json`/`mellow.lock`/
`.mellow_aliases.json` formats. `tests/native/test_native_pkg_cli.py` is the
conformance gate. Remaining: HTTPS registry fetch, `.mpkg` ZIP archives,
signature verification, and the update planner.

### P4: Developer Tooling

These are not required for running end-user programs and should move after the
runtime is stable:

- LSP: `src/mellowlang/lsp_server.py`
- playground server: `src/mellowlang/playground/server.py`
- web generator: `src/mellowlang/web.py`
- release/security audit tooling
- agent deployment/control-plane tools

Some may remain Python or move to separate tools because they are development
services, not core runtime requirements.

## Mellow Runtime Exposure

Each migrated C subsystem should expose:

- C API for embedding and tests
- native CLI command when it is a tool
- Mellow package declarations when user code should call it
- conformance tests against the old Python behavior

Example pattern:

```text
native/<system>/include/<system>.h
native/<system>/src/<system>.c
src/mellowlang/<system>_codec.py       compatibility shim only
starter_packages/core-<system>/src/*   Mellow package-facing API
tests/native/test_<system>_parity.py   parity gate
```

Official runtime packages under `starter_packages/` and
`mellow_packages/registry/` must not ship Python source files. Package-facing
APIs should be Mellow files that call native host modules, with Python reserved
for compatibility shims and development tooling outside the runtime package
path.

The release-facing package gate is:

```bash
mellow pkg audit
```

It checks starter packages plus the latest local-registry versions for manifest
sync, Mellow entry compilation, missing dependencies, and Python source leakage.

## Native-Core Tooling Contract

LSP, playground, and agent tools should share native-core contracts before their
transport/server shells are migrated. The current shared contract is
`native-core-diagnostics-v1`:

- compiler/lint diagnostics are normalized in `src/mellowlang/diagnostics.py`
- diagnostics include line/column, error code, source excerpt, fix hints, and an
  AI-readable prompt context
- LSP publishes these diagnostics as `mellow-native-core`
- playground returns diagnostics and AI hints in `/api/run` and `/api/compile`
  payloads, including compile-failure responses
- agent debug payloads declare `diagnostics_contract =
  native-core-diagnostics-v1`

This makes editor, playground, and agent behavior depend on one structured core
instead of separate Python-only string parsing paths. The remaining migration is
to move each transport shell to a native executable while preserving the same
JSON contract.

## Done Criteria

A Python-backed system is considered migrated only when:

- native C implementation exists
- native standalone can use it without CPython
- Python wrapper is optional or compatibility-only
- tests cover success, invalid input, corrupted data, and old-format migration
- docs name the native path as the stable path

## Current Next Step

Storage, save-slot, ledger, money, and server services now run behind native
built-ins, so the next practical move is the standalone MELV CLI hook: make
`mellow melv ...` work from the C executable without importing Python, keeping
the Python CLI as a compatibility wrapper. The secure save envelope
(`mellowrt_save.c`) and the network host bindings (`mellowrt_net.c`) stay in the
queue; the envelope is deliberately held for phase 2.
