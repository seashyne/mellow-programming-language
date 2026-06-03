# Mellow v2.1 Standalone Runtime Core Pack

This pack starts the transition from a CPython-hosted native extension to a standalone runtime core.

## What changed

- Added `native/standalone/` with a pure-C runtime core scaffold.
- Introduced a standalone typed value model (`MValue`) that does not depend on `PyObject*`.
- Added a pure-C instruction format, frame model, source-span map, and debugger hook contract.
- Added a minimal executable demo through CMake.
- Added Python-side tooling to inspect and build the standalone runtime source tree:
  - `mellow standalone status`
  - `mellow standalone doctor`
  - `mellow standalone build`

## Why this matters

Previous native packs still depended on CPython embedding and Python object semantics.
This pack extracts the **runtime core abstraction** needed for a true Python-free future runtime.

## Current scope

This is not yet a full replacement for the Python-hosted VM.
It is the first core extraction milestone.

Implemented in standalone core:
- typed value model
- instruction stream
- minimal VM execution loop
- source span metadata shape
- debugger hook interface

Not yet migrated:
- full opcode set
- module/package loading
- stdlib/host APIs
- workflow engine parity
- replay/debugger parity
- ownership-aware containers and memory management

## Build

```bash
mellow standalone status
mellow standalone doctor
mellow standalone build
```

Or with CMake directly:

```bash
cmake -S native/standalone -B native/standalone/build
cmake --build native/standalone/build
```
